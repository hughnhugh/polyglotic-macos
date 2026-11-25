"""The lab's driver: states, timed actions, screenshots, the code checks,
the JSON and the gate.

A state is a function that sets the interface up as it should look, times
its actions with `Lab.time`, and returns the widget to photograph. Times
are wall time on the interface thread for the action and everything it
queues, as project 108's bench measured them. Once photographed, the
state's windows go through the code checks (`checks.py`), and a new
part's picture is compared with its golden (`goldens.py`). A new part
that fails anything has its pictures copied to `failed/` - what CI keeps.

The garbage collector is held off while an action is timed, and a new
part over a budget is run once more, from the start, and up to twice more
again while the PC measures saturated (`tools.busy_pc`, decision 0040):
the gate judges the last run, and the first is reported with it
(polyglotic-hq projects 140 and 197). A slow moment of a busy PC passes; a
real slowdown is over in every run. An action that happens once in a
widget's life, timed once, has no median to steady it: Words' first show
for a big learner is timed on five fresh pages and judged on their median
(`Lab.time_fresh`, decision 0047). Before each gated state, the lab times
a fixed reference step (`reference.py`): how slow the PC is right then,
for comparing a pull request's timings with main's at like load (decision
0169).
"""

import gc
import json
import os
import statistics
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
WINDOWS_FONTS = Path("C:/Windows/Fonts")
if WINDOWS_FONTS.is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", str(WINDOWS_FONTS))

from PySide6.QtCore import QEvent, QEventLoop, QPoint, QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QPainter,
    QRegion,
    QTextLayout,
)
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.listening.spoken import SteadyLanguage
from polyglotic_desktop.perf import budgets, spans
from polyglotic_desktop.perf.budgets import Budget
from polyglotic_desktop.ui import interface_language
from polyglotic_desktop.ui_next import caption_windows, style
from polyglotic_desktop.ui_next.caption_layout import LATIN_FAMILIES
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.glyphs import Glyph
from polyglotic_desktop.ui_next.home import PlayingWave
from tools import busy_pc
from tools.ui_lab import checks, design, goldens, reference
from tools.ui_lab.checks import Finding
from tools.ui_lab.goldens import Golden


class _NeverSteady(SteadyLanguage):
    """The lab's caption windows never ask "Always hear it as ...?"
    (polyglotic-hq 317, decision 0109): its recorded sessions are steady
    Mandarin, so the question would sit over every state's captions. It
    has a state of its own (`caption_window.spoken_question`)."""

    def heard(self, language: str | None, languages_heard: Iterable[str]) -> None:
        return None


@contextmanager
def _windows_never_ask() -> Iterator[None]:
    """While the lab runs, and only then (the tests import the lab too)."""
    real = caption_windows.SteadyLanguage
    caption_windows.SteadyLanguage = _NeverSteady  # type: ignore[misc]
    try:
        yield
    finally:
        caption_windows.SteadyLanguage = real  # type: ignore[misc]


SCENE = QColor("#4a5a6a")
"""What a caption window is photographed over: a stand-in for a video."""


FRESH_TIMES = 5
"""The fresh widgets `Lab.time_fresh` times an action on: as many as the
start's gate takes starts (decision 0046)."""


@dataclass
class Timed:
    """An action's runs, in milliseconds, and the budget it's held to."""

    samples: list[float]
    budget: Budget | None

    def describe(self) -> str:
        """The median and longest run, for a first try's note."""
        return (
            f"median {statistics.median(self.samples):.1f} ms,"
            f" max {max(self.samples):.1f} ms"
        )

    def summary(self) -> dict[str, object]:
        ordered = sorted(self.samples)
        median = statistics.median(ordered)
        found: dict[str, object] = {
            "n": len(ordered),
            "median_ms": round(median, 2),
            "p90_ms": round(ordered[int(0.9 * (len(ordered) - 1))], 2),
            "max_ms": round(ordered[-1], 2),
        }
        if self.budget is not None:
            found.update(
                budget=self.budget.name,
                budget_ms=self.budget.ms,
                within=self.within(),
            )
        return found

    def within(self) -> bool:
        """The median within the budget, and no run over the slot budget
        (50 ms) - or over the budget itself, where that's longer (a theme
        change: 100 ms)."""
        if self.budget is None:
            return True
        longest = max(self.budget.ms, budgets.SLOT.ms)
        return (
            statistics.median(self.samples) <= self.budget.ms
            and max(self.samples) <= longest
        )


@dataclass
class Result:
    state: str
    gated: bool
    actions: dict[str, Timed] = field(default_factory=dict)
    spans: dict[str, dict[str, float]] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    design: list[Finding] = field(default_factory=list)
    """The design detector's findings (`design.py`): gated against its baseline."""
    notes: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)
    golden: Golden | None = None
    photo: QImage | None = field(default=None, repr=False, compare=False)
    first_try: dict[str, Timed] = field(default_factory=dict)
    """A new part run more than once (over a budget the first time): the
    first run's timings. The gate judges the last."""
    tries: int = 1
    busy: list[float | None] = field(default_factory=list)
    """The PC's load immediately before each timed try."""
    timing_unmeasured: bool = False
    """Every timed try began above the trustworthy load threshold."""
    reference_ms: float | None = None
    """A gated state's reference step (`reference.py`), timed just before
    its actions: what main's timings are scaled by (decision 0169)."""

    def over_budget(self) -> list[str]:
        if self.timing_unmeasured:
            return []
        return [name for name, timed in self.actions.items() if not timed.within()]

    def first_try_note(self, action: str) -> str:
        """What the first run found for `action`, if it was over then."""
        first = self.first_try.get(action)
        if first is None or first.within():
            return ""
        return f"try 1 over: {first.describe()}"

    def failed_checks(self) -> list[Finding]:
        """The code checks' findings that count (not waived)."""
        return [f for f in self.findings if not f.waived]

    def failed(self) -> bool:
        """Over a budget, a finding, or a picture unlike its golden."""
        return bool(
            self.over_budget()
            or self.failed_checks()
            or (self.golden is not None and self.golden.failed)
        )

    def to_json(self) -> dict[str, object]:
        return {
            "state": self.state,
            "gated": self.gated,
            "actions": {name: t.summary() for name, t in self.actions.items()},
            "spans": self.spans,
            "findings": [f.to_json() for f in self.findings],
            "design": [f.to_json() for f in self.design],
            "notes": self.notes,
            "words": self.words,
            "golden": (
                {"status": self.golden.status, "changed": self.golden.changed}
                if self.golden
                else None
            ),
            "first_try": {name: t.summary() for name, t in self.first_try.items()},
            "tries": self.tries,
            "busy": self.busy,
            "timing_unmeasured": self.timing_unmeasured,
            "reference_ms": (
                None if self.reference_ms is None else round(self.reference_ms, 2)
            ),
        }


class Lab:
    """What a state works with: the application, and its result so far."""

    def __init__(self, app: QApplication, out: Path) -> None:
        self.app = app
        self.out = out
        self.result = Result("", False)
        self.closing: list[Callable[[], object]] = []  # run once photographed

    def pump(self) -> None:
        """Runs everything queued on the interface thread."""
        for _ in range(2):
            self.app.sendPostedEvents()
            self.app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)

    def time(
        self,
        action: str,
        do: Callable[[], object],
        repeat: int = 1,
        budget: Budget | None = None,
    ) -> list[float]:
        """Runs `do` `repeat` times, each timed with what it queues, the
        garbage collector held off (a collection is the process's, not the
        action's: 91-99 ms in CI, 2026-11-07, project 115)."""
        samples = []
        collecting = gc.isenabled()
        gc.disable()
        try:
            for _ in range(repeat):
                start = time.perf_counter()
                do()
                self.pump()
                samples.append((time.perf_counter() - start) * 1000)
        finally:
            if collecting:
                gc.enable()
        found = self.result.actions.setdefault(action, Timed([], budget))
        found.samples += samples
        return samples

    def time_fresh(
        self,
        action: str,
        fresh: Callable[[], Callable[[], object]],
        budget: Budget | None = None,
        times: int = FRESH_TIMES,
    ) -> float:
        """An action that happens once in a widget's life - a page's first
        show - timed on `times` fresh widgets: `fresh()` sets one up, not
        timed, and returns the action. Their median is the action's one
        run, held to `budget` as any run is (decision 0047): one slow moment
        of a busy PC among them passes, a real slowdown - most of them over
        - doesn't. Each run is recorded, not judged, as `action` + "_each"."""
        runs = [self.time(f"{action}_each", fresh())[0] for _ in range(times)]
        median = statistics.median(runs)
        self.result.actions.setdefault(action, Timed([], budget)).samples.append(median)
        return median


@dataclass(frozen=True)
class State:
    """A state of the interface: `gated` if its budgets fail the run.
    `scene`: photographed over a stand-in video (a caption window).
    `visual_checks`: judge the picture as well as recording it."""

    name: str
    run: Callable[[Lab], QWidget]
    gated: bool
    scene: bool = False
    visual_checks: bool = True


def arrived(app: QApplication) -> None:
    """New captions sliding in (step and slide, 267) come to rest before
    the photograph: the checks judge them as they end up, not part way."""
    deadline = (
        time.monotonic() + 2.0
    )  # seconds allowed for the caption spring to settle
    while time.monotonic() < deadline and any(
        isinstance(w, CaptionWindow) and w.arriving for w in app.allWidgets()
    ):
        app.processEvents()
        time.sleep(0.01)


def photograph(widget: QWidget, scene: bool) -> QImage:
    """`widget` as an image - over the stand-in video, without its own
    window background, if `scene`."""
    if not scene:
        return widget.grab().toImage()
    shot = QImage(widget.size(), QImage.Format.Format_ARGB32)
    shot.fill(SCENE)
    painter = QPainter(shot)
    widget.render(painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    painter.end()
    return shot


def _as_seen(over_scene: QWidget | None, window: QWidget) -> QImage:
    """A window as the checks see it: over the stand-in video if it's
    see-through (a caption window, the lookup card) or the state shows it
    over one (`over_scene`: the bare caption surface)."""
    see_through = window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return photograph(window, see_through or window is over_scene)


WARM_UP = "这个游戏的画面很漂亮。 This game looks beautiful, 頑張って。"
"""Chinese, Latin and Japanese text: what the states draw."""


def warm_fonts() -> None:
    """Draws some text once before any state is timed. The first text a
    process draws loads its fonts - about 40 ms on the user's PC
    (2026-11-07, project 119) - and that landed in whichever state ran
    first, as one run over the 50 ms slot budget whenever the PC was busy
    (projects 112, 113 and 119 each saw it on `caption_window_empty`). The
    app pays it once, at start; the gate measures the steady state."""
    image = QImage(600, 60, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    for px in (12, 13, 21, 22):
        font = QFont()
        font.setPixelSize(px)
        layout = QTextLayout(WARM_UP, font)
        layout.beginLayout()
        layout.createLine()
        layout.endLayout()
        layout.draw(painter, QPointF(0, 0))
    painter.end()


WINDOWS_UI_FONT = "Segoe UI"
"""What Qt on Windows draws a widget that names no font in: Windows'
interface font (its message font), at `style.DEFAULT_POINTS` at 100 %."""
WINDOWS_CHINESE_FALLBACK = "MS UI Gothic"
"""What Windows draws Chinese in when a font list has no Chinese face, in
an English locale: the first face with Chinese in Qt's list for a locale
that isn't Chinese, Japanese or Korean (Arial, MS UI Gothic, Gulim,
SimSun, PMingLiU - qwindowsfontdatabasebase.cpp, `extraTryFontsForFamily`).
A Japanese face: Japan's glyph shapes (polyglotic-hq 176, 198)."""


def application() -> QApplication:
    """The lab's application, its fonts as on Windows (`use_windows_fonts`)."""
    found = QApplication.instance() or QApplication(["polyglotic-ui-lab"])
    assert isinstance(found, QApplication)
    use_windows_fonts(found)
    return found


def use_windows_fonts(app: QApplication) -> None:
    """Offscreen, the fonts as the app has them on Windows (polyglotic-hq
    198) - once per process, and only where Windows' fonts are:
    - **What names no font** is in Windows' interface font, Segoe UI 9 pt
      (`WINDOWS_UI_FONT`). Offscreen, Qt's own is "Sans Serif", which
      became the font folder's first family, Agency FB - a narrow display
      face - so a widget that named no font (the caption window's settings
      popover) measured narrower than on Windows.
    - **The font collections** (.ttc) are there. Qt's offscreen font
      database reads only a folder's .ttf, .otf, .pfa and .pfb files, so
      Microsoft YaHei UI and JhengHei UI, Yu Gothic, MS UI Gothic, SimSun
      and MingLiU weren't, and every Chinese face the interface names fell
      to DengXian.
    - **Chinese a font list has no face for** is in MS UI Gothic
      (`WINDOWS_CHINESE_FALLBACK`), as Windows draws it in an English
      locale - behind every family (`QFont.insertSubstitution`: after the
      list's own families and the symbols' face, `style.use_symbols`).
      Offscreen it came from whichever face Qt found first. The app puts
      the interface's Chinese faces before it, at start
      (`style.use_chinese_behind_every_font`; `run` does it as `main`
      does), so what the lab finds in MS UI Gothic is what that misses."""
    if not WINDOWS_FONTS.is_dir() or app.property("lab_windows_fonts"):
        return
    app.setProperty("lab_windows_fonts", True)
    for collection in sorted(WINDOWS_FONTS.glob("*.ttc")):
        QFontDatabase.addApplicationFont(str(collection))  # about 40 ms in all
    style.use_symbols()  # first, as `main` does: the symbols' face before
    named = {*QFontDatabase.families(), *style.UI_FAMILIES, *LATIN_FAMILIES}
    for family in named:  # with the families named that aren't one offscreen
        QFont.insertSubstitution(family, WINDOWS_CHINESE_FALLBACK)
    font = QFont(WINDOWS_UI_FONT)
    font.setPointSizeF(style.DEFAULT_POINTS)
    app.setFont(font)


def use_text_size(percent: int) -> None:
    """Windows' Text size simulated at `percent`: the system font as Qt
    reads it there (Segoe UI 9 pt at 100 %, so 13.5 pt at 150 %) and the
    interface's text size read from it as `main` reads it. The PC's own
    setting is never touched."""
    app = application()
    font = QFont(app.font())
    font.setPointSizeF(style.DEFAULT_POINTS * percent / 100)
    app.setFont(font)
    style.use_text_scale(style.text_scale_of(app.font()))


def run(
    states: list[State],
    out: Path,
    golden_store: Path | None = None,
    language: str = interface_language.ENGLISH,
    shown: Callable[[str, QWidget], None] | None = None,
) -> list[Result]:
    """Every state: its PNG and JSON in `out`, then `summary.json`. With
    `golden_store`, each new part's picture is compared with its golden.
    In the interface `language`, installed as the app installs it (decision
    0034) - once per run: a later run in another language starts a new
    process. `shown`: told each state's name and widget as it's checked
    (`seen`: which strings it shows)."""
    out.mkdir(parents=True, exist_ok=True)
    failed = out / "failed"
    for stale in failed.glob("*.png") if failed.is_dir() else []:
        stale.unlink()  # only this run's failures
    app = application()
    if app.property("interface_language") != language:
        app.setProperty("interface_language", language)
        interface_language.install(app, language)
        style.use_interface_language(language)
    warm_fonts()
    # Synthetic captions show the same local time on every run and host.
    sample_time = datetime(2026, 1, 15, 21, 43).astimezone()
    with (
        _windows_never_ask(),
        patch(
            "polyglotic_desktop.core.listening.history._utc_now",
            return_value=sample_time,
        ),
    ):
        return _run_states(app, states, out, failed, golden_store, shown)


def _run_states(
    app: QApplication,
    states: list[State],
    out: Path,
    failed: Path,
    golden_store: Path | None,
    shown: Callable[[str, QWidget], None] | None,
) -> list[Result]:
    """`run`'s states, one by one (`run` says what each gets)."""
    results = []
    for state in states:
        busy: list[float | None] = []
        if state.gated:
            busy.append(
                busy_pc.wait_for_calm(
                    busy_pc.UI_TIMING_MAX_BUSY, busy_pc.UI_TIMING_WAIT_SECONDS
                )
            )
            print(
                f"{state.name}: before try 1, {busy_pc.describe(busy[-1])}", flush=True
            )
        lab, widget = _run_state(app, state, out)
        first, tries = lab.result.actions, 1
        while state.gated and lab.result.over_budget() and tries < busy_pc.MOST_TRIES:
            if tries >= 2 and not busy_pc.saturated(
                busy[-1], busy_pc.UI_TIMING_MAX_BUSY
            ):
                break
            _close(app, lab, widget)
            busy.append(
                busy_pc.wait_for_calm(
                    busy_pc.UI_TIMING_MAX_BUSY, busy_pc.UI_TIMING_WAIT_SECONDS
                )
            )
            print(
                f"{state.name}: before try {tries + 1}, {busy_pc.describe(busy[-1])}",
                flush=True,
            )
            lab, widget = _run_state(app, state, out)
            tries += 1
        if state.gated:
            lab.result.busy = busy
            lab.result.timing_unmeasured = bool(busy) and all(
                busy_pc.saturated(load, busy_pc.UI_TIMING_MAX_BUSY) for load in busy
            )
        if tries > 1:
            lab.result.first_try, lab.result.tries = first, tries
        arrived(app)
        for wave in widget.findChildren(PlayingWave):
            wave.timer.stop()
            wave.frame = Glyph.SPEAKING  # same frame for the photograph and its checks
            wave.update()
        photo = photograph(widget, state.scene)
        photo.save(str(out / f"{state.name}.png"))
        lab.result.photo = photo
        before = diff = None
        if state.visual_checks:
            if golden_store is not None and state.gated:
                lab.result.golden, before, diff = goldens.compare(
                    state.name, photo, golden_store
                )
            as_seen = partial(_as_seen, widget if state.scene else None)
            inspected = checks.inspect(state.name, widget, as_seen)
            lab.result.findings = inspected.findings
            lab.result.notes = inspected.notes
            lab.result.words = inspected.words
            lab.result.design = design.inspect(widget, as_seen)
        if shown is not None:
            shown(state.name, widget)
        _close(app, lab, widget)
        (out / f"{state.name}.json").write_text(
            json.dumps(lab.result.to_json(), indent=1), encoding="utf-8"
        )
        if state.gated and lab.result.failed():
            failed.mkdir(exist_ok=True)
            photo.save(str(failed / f"{state.name}.png"))
            if before is not None and lab.result.golden and lab.result.golden.failed:
                before.save(str(failed / f"{state.name}.golden.png"))
            if diff is not None:
                diff.save(str(failed / f"{state.name}.diff.png"))
        results.append(lab.result)
        print(f"{state.name:44s} {_line(lab.result)}", flush=True)
    (out / "summary.json").write_text(
        json.dumps([r.to_json() for r in results], indent=1), encoding="utf-8"
    )
    (out / "summary.md").write_text(markdown(results), encoding="utf-8")
    return results


def _run_state(app: QApplication, state: State, out: Path) -> tuple[Lab, QWidget]:
    """`state` set up and its actions timed: its lab and the widget to
    photograph."""
    lab = Lab(app, out)
    lab.result = Result(state.name, state.gated)
    if state.gated:  # the PC's speed now, for comparing with main's (0169)
        lab.result.reference_ms = reference.time_step(app)
    with spans.recorded() as timings:
        widget = state.run(lab)
        lab.pump()
    lab.result.spans = timings.summary()
    return lab, widget


def _close(app: QApplication, lab: Lab, widget: QWidget) -> None:
    """Everything a state made, closed and deleted: each state starts with
    no windows."""
    widget.close()
    for close in lab.closing:
        close()
    for left in app.topLevelWidgets():
        left.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    lab.pump()


def _line(result: Result) -> str:
    parts = []
    for name, timed in result.actions.items():
        mark = "" if timed.within() else " OVER"
        if result.timing_unmeasured:
            mark = " NOT MEASURED (BUSY)"
        if result.first_try_note(name):
            mark += (
                f" (try {result.tries}; {result.first_try_note(name)}{_load(result)})"
            )
        parts.append(f"{name} {statistics.median(timed.samples):.1f}{mark}")
    failed = checks.count(result.findings)
    if failed:
        parts.append("checks: " + ", ".join(f"{n} {c}" for c, n in failed.items()))
    if result.golden is not None and result.golden.failed:
        parts.append(f"golden: {result.golden.describe()}")
    return ", ".join(parts)


def _load(result: Result) -> str:
    """How busy the PC was when it was read, if it was."""
    return f"; {busy_pc.describe(result.busy[-1])}" if result.busy else ""


def markdown(results: list[Result]) -> str:
    """The run as Markdown: the timings, the checks' findings, the goldens."""
    return (
        timings_markdown(results)
        + "\n"
        + findings_markdown(results)
        + "\n"
        + goldens_markdown(results)
    )


def timings_markdown(results: list[Result]) -> str:
    """Every timed action as a table: gated (new parts) first."""
    lines = [
        "## UI lab",
        "",
        (
            "Median and longest run in ms on the interface thread, offscreen. New"
            " parts are gated on their budget (the median, and any one run within"
            " 50 ms); one over is run once more - up to twice more again while"
            " the PC measures saturated (decision 0040) - and judged on the last,"
            " with the first shown. A state not gated is recorded."
        ),
        "",
        "| State | Action | Median | Max | Budget | |",
        "|---|---|---|---|---|---|",
    ]
    for result in sorted(results, key=lambda r: not r.gated):
        for name, timed in result.actions.items():
            summary = timed.summary()
            budget = f"{timed.budget.ms:g}" if timed.budget else ""
            verdict = ""
            if timed.budget is not None:
                verdict = "ok" if timed.within() else "**over**"
                if result.timing_unmeasured:
                    verdict = "**not measured (busy)**"
                if not result.gated:
                    verdict += " (recorded)"
                if result.first_try_note(name):
                    note = result.first_try_note(name) + _load(result)
                    verdict += f" on try {result.tries} ({note})"
            lines.append(
                f"| {result.state} | {name} | {summary['median_ms']} | "
                f"{summary['max_ms']} | {budget} | {verdict} |"
            )
    return "\n".join(lines) + "\n"


def goldens_markdown(results: list[Result]) -> str:
    """Each new part's picture against its golden: those that differ."""
    compared = [r for r in results if r.golden is not None]
    if not compared:
        return ""
    lines = ["## Golden images", ""]
    note = goldens.machine_note()
    if note:
        lines += [f"**Note:** {note}.", ""]
    differ = [r for r in compared if r.golden is not None and r.golden.failed]
    same = len(compared) - len(differ)
    lines.append(f"{same} of {len(compared)} new parts' states match their golden.")
    if differ:
        lines += [
            "",
            "| State | Picture | |",
            "|---|---|---|",
            *[
                f"| {r.state} | {r.golden.describe()} | **fails** |"
                for r in differ
                if r.golden is not None
            ],
            "",
            (
                "Each failing state's picture, golden and diff are in the run's"
                " `ui-lab-failed` artifact (3 days). If the change is intended,"
                " approve it on the user's PC: `uv run python -m tools.ui_lab"
                " approve`, then commit `tools/ui_lab/goldens/` - the pull request"
                " shows before and after."
            ),
        ]
    return "\n".join(lines) + "\n"


def findings_markdown(results: list[Result]) -> str:
    """The code checks' findings: the new parts' fail the gate; a state
    not gated has its findings recorded."""
    lines = [
        "## Code checks",
        "",
        (
            "Clipped text, text under 12 px, contrast, accessible names, keyboard"
            " reach, horizontal scrollbars, squashed layouts (tools/ui_lab/checks.py)."
            " New parts fail on any finding not waived; a state not gated is"
            " recorded."
        ),
        "",
    ]
    rows = [
        (result, finding)
        for result in sorted(results, key=lambda r: not r.gated)
        for finding in result.findings
    ]
    if not rows:
        return "\n".join([*lines, "No findings.", ""])
    lines += ["| State | Check | Where | Finding | |", "|---|---|---|---|---|"]
    for result, finding in rows:
        verdict = (
            f"waived: {finding.waived}"
            if finding.waived
            else ("**fails**" if result.gated else "recorded")
        )
        detail = finding.detail.replace("|", "\\|")
        lines.append(
            f"| {result.state} | {finding.check} | {finding.where} | {detail} |"
            f" {verdict} |"
        )
    return "\n".join(lines) + "\n"
