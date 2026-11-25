"""The UI lab: a PNG and a timing JSON per state, and the gate - a new
part over budget fails the run; a state not gated is recorded only. A new
part over budget is run once more - up to twice more again while the PC
measures saturated - and judged on the last, with the first shown: a slow
moment passes, a real slowdown doesn't (projects 140 and 197, decision
0040). An action that happens once in a widget's life is judged on five
fresh ones (decision 0047). The PC's load is set here, never read."""

import contextlib
import gc
import itertools
import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from tests import budget_judge
from tests.budget_judge import Sampled, within
from tools.ui_lab import __main__ as cli
from tools.ui_lab import caption_window, lab, new_parts, pages

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next import caption_windows as caption_windows_module
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.views.caption_window import StoredWindows
from polyglotic_desktop.ui_next.words_page import WordsPage
from tools import busy_pc, start_record, timing_record


@pytest.fixture(autouse=True)
def load(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The PC's load as the lab reads it: 10 % (quiet)
    unless a test says otherwise."""
    readings = [0.1]
    monkeypatch.setattr(busy_pc, "busy_share", lambda seconds=0.2: readings[0])
    monkeypatch.setattr(busy_pc, "wait_for_calm", lambda *args, **kwargs: readings[0])
    return readings


def slow_state(lab_: lab.Lab) -> QWidget:
    lab_.time("click", lambda: time.sleep(0.06), budget=budgets.CLICK)
    return QLabel("slow")


def test_first_window_state_forgets_languages_from_earlier_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The set-up golden has a new learner's language order in every run."""
    monkeypatch.setattr(
        caption_windows_module,
        "stored_windows",
        lambda _stored: StoredWindows(recent_spoken=("zh", "vi")),
    )
    state_lab = lab.Lab(lab.application(), tmp_path)
    windows, _ = caption_window._first_window(state_lab)
    try:
        assert windows.recent_spoken() == ()
    finally:
        for close in reversed(state_lab.closing):
            close()


@contextlib.contextmanager
def restored_interface_language() -> Iterator[None]:
    """Scope an in-process CLI run as its real one-run process scopes it.

    The lab deliberately installs translators and the locale for the life of
    its process. This test invokes that production path in pytest's shared Qt
    process, so put back its dynamic property, default locale, style language,
    and exact prior translator stack even when an assertion or the CLI fails.
    """
    app = QApplication.instance()
    assert app is not None
    language = app.property("interface_language")
    locale = QLocale()
    translators = list(app.findChildren(QTranslator))
    try:
        yield
    finally:
        for translator in app.findChildren(QTranslator):
            if translator not in translators:
                app.removeTranslator(translator)
                translator.setParent(None)
        app.setProperty("interface_language", language)
        QLocale.setDefault(locale)
        interface_language_code = language if isinstance(language, str) else ""
        style.use_interface_language(interface_language_code)


def test_learner_caption_actions_reach_the_timing_gate(tmp_path: Path) -> None:
    states = [
        state
        for state in cli.new_states()
        if state.name.startswith("ui_next.w1_learner_")
    ]
    results = lab.run(states, tmp_path, golden_store=tmp_path)
    gated = cli.gated_timings(results)
    expected = {
        "ui_next.w1_learner_resize_drag: resize_drag_step": (40, budgets.FRAME),
        "ui_next.w1_learner_caption_during_glide: caption_during_glide": (
            6,
            budgets.NEW_CAPTION,
        ),
        "ui_next.w1_learner_timing_switch: timing_switch": (12, budgets.CLICK),
        "ui_next.w1_learner_preset_switch: preset_switch": (12, budgets.CLICK),
    }
    assert len(results) == len(expected)
    assert expected.keys() <= gated.keys()
    for result in results:
        assert result.golden is None
        assert len(result.actions) == 1
        for name, action in result.actions.items():
            count, budget = expected[f"{result.state}: {name}"]
            assert action.budget is budget
            assert len(action.samples) == count

    resize = next(
        result for result in results if result.state == "ui_next.w1_learner_resize_drag"
    )
    action = resize.actions["resize_drag_step"]
    # Project 590's preview 2 median was 23.1 ms. It must fail the median
    # budget even if every sample is under the 50 ms slot ceiling.
    action.samples[:] = [23.1] * len(action.samples)
    assert resize.over_budget() == ["resize_drag_step"]


def test_a_state_writes_its_png_and_json(tmp_path: Path) -> None:
    state = next(s for s in new_parts.STATES if s.name == "ui_next.caption_window_1000")
    (result,) = lab.run([state], tmp_path)
    assert (tmp_path / f"{state.name}.png").stat().st_size > 1000
    written = json.loads((tmp_path / f"{state.name}.json").read_text(encoding="utf-8"))
    assert written["gated"] is True
    resize = written["actions"]["resize_step"]
    assert resize["n"] == 30 and resize["budget"] == "frame"
    assert resize["within"] is True
    assert written["spans"]["caption_surface.paint"]["n"] >= 30
    assert result.over_budget() == []
    assert "| ui_next.caption_window_1000 | resize_step |" in (
        tmp_path / "summary.md"
    ).read_text(encoding="utf-8")


def test_busy_every_try_is_unmeasured_but_checks_still_fail(
    tmp_path: Path, load: list[float]
) -> None:
    load[0] = 0.9
    state = lab.State("ui_next.busy", slow_state, gated=True)
    (result,) = lab.run([state], tmp_path)
    assert result.tries == busy_pc.MOST_TRIES
    assert result.timing_unmeasured
    assert result.over_budget() == []
    assert "not measured (busy)" in (tmp_path / "summary.md").read_text().lower()
    result.findings.append(lab.Finding("clipped", "widget", "detail"))
    assert result.failed()


@pytest.mark.parametrize(("required", "fails"), [(False, 0), (True, 1)])
def test_all_busy_is_a_warning_except_on_the_mandatory_measurement_run(
    tmp_path: Path,
    load: list[float],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    required: bool,
    fails: int,
) -> None:
    load[0] = 0.9
    state = lab.State("ui_next.busy", slow_state, gated=True)
    monkeypatch.setattr(cli, "new_states", lambda: [state])
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    args = [
        "--gate",
        "--checks-only",
        "--language",
        "es",
        "--out",
        str(tmp_path / str(required)),
    ]
    if required:
        args.append("--require-timings")
    app = lab.application()
    prior_language = app.property("interface_language")
    prior_locale = QLocale()
    prior_number = prior_locale.toString(1234.5, "f", 1)
    prior_translators = list(app.findChildren(QTranslator))
    with restored_interface_language():
        assert cli.main(args) == fails
        said = capsys.readouterr().err
        assert app.property("interface_language") == "es"
        assert QLocale().name().startswith("es")
    assert app.property("interface_language") == prior_language
    assert QLocale().name() == prior_locale.name()
    assert QLocale().toString(1234.5, "f", 1) == prior_number
    assert list(app.findChildren(QTranslator)) == prior_translators
    assert "timing not measured (busy)" in said
    assert ("required timing not measured" in said) is required


def test_quiet_over_budget_still_fails(tmp_path: Path) -> None:
    (result,) = lab.run([lab.State("ui_next.quiet", slow_state, gated=True)], tmp_path)
    assert not result.timing_unmeasured
    assert result.over_budget() == ["click"]
    assert result.failed()


@pytest.mark.parametrize(("gated", "fails"), [(True, 1), (False, 0)])
def test_only_a_new_part_over_budget_fails_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gated: bool, fails: int
) -> None:
    state = lab.State("ui_next.slow" if gated else "ui.slow", slow_state, gated=gated)
    monkeypatch.setattr(new_parts, "STATES", [state])
    # only these states, whatever the lab gains later (not each module's list)
    monkeypatch.setattr(cli, "new_states", lambda: list(new_parts.STATES))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert cli.main(["--gate", "--out", str(tmp_path)]) == fails
    written = json.loads((tmp_path / f"{state.name}.json").read_text(encoding="utf-8"))
    assert written["actions"]["click"]["within"] is False
    assert ("click" in written["first_try"]) is gated  # a new part ran twice


@pytest.mark.parametrize(
    ("slow", "fails"),
    [((1,), 0), ((1, 7), 1)],
    ids=["a slow moment in the first run", "one slow click in every run"],
)
def test_a_new_part_over_budget_is_run_once_more_and_both_runs_shown(
    tmp_path: Path, slow: tuple[int, ...], fails: int
) -> None:
    calls = itertools.count(1)

    def click() -> None:
        if next(calls) in slow:  # six clicks a run: 1-6, then 7-12
            time.sleep(0.06)

    def state(lab_: lab.Lab) -> QWidget:
        lab_.time("click", click, repeat=6, budget=budgets.CLICK)
        return QLabel("a click")

    (result,) = lab.run([lab.State("ui_next.click", state, gated=True)], tmp_path)
    assert len(result.over_budget()) == fails  # the gate's verdict: the second run
    written = json.loads((tmp_path / "ui_next.click.json").read_text(encoding="utf-8"))
    assert written["first_try"]["click"]["max_ms"] >= 60  # the first run, shown
    assert written["actions"]["click"]["within"] == (fails == 0)
    table = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "on try 2 (try 1 over: median" in table


@pytest.mark.parametrize(
    ("slow", "tries", "fails"),
    [((1, 7, 13), 4, 0), ((1, 7, 13, 19), 4, 0)],
    ids=["a slow click in three runs", "one slow click in every run"],
)
def test_a_saturated_pc_gets_two_runs_more_and_says_so(
    tmp_path: Path,
    load: list[float],
    slow: tuple[int, ...],
    tries: int,
    fails: int,
) -> None:
    load[0] = 0.97
    calls = itertools.count(1)

    def click() -> None:
        if next(calls) in slow:  # six clicks a run: 1-6, 7-12, 13-18, 19-24
            time.sleep(0.06)

    def state(lab_: lab.Lab) -> QWidget:
        lab_.time("click", click, repeat=6, budget=budgets.CLICK)
        return QLabel("a click")

    (result,) = lab.run([lab.State("ui_next.click", state, gated=True)], tmp_path)
    assert result.tries == tries and len(result.over_budget()) == fails
    written = json.loads((tmp_path / "ui_next.click.json").read_text(encoding="utf-8"))
    assert written["tries"] == tries and written["busy"] == [0.97, 0.97, 0.97, 0.97]
    table = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "on try 4 (try 1 over: median" in table and "the PC 97% busy)" in table


@pytest.mark.parametrize(
    ("slow", "tries", "fails"),
    [((1,), 1, 0), ((1, 2, 3, 6, 7, 8), 2, 1)],
    ids=["one slow first show", "three slow first shows in every try"],
)
def test_a_first_show_is_judged_on_the_median_of_five_fresh_ones(
    tmp_path: Path, slow: tuple[int, ...], tries: int, fails: int
) -> None:
    """Decision 0047: an action that happens once in a widget's life, timed
    on five fresh widgets, each set up untimed; their median is its run."""
    shows = itertools.count(1)
    made: list[int] = []

    def fresh() -> Callable[[], object]:
        made.append(len(made))

        def show() -> None:
            if next(shows) in slow:  # five shows a try: 1-5, then 6-10
                time.sleep(0.06)

        return show

    def state(lab_: lab.Lab) -> QWidget:
        lab_.time_fresh("first_show", fresh, budget=budgets.PAGE_SWITCH_COLD)
        return QLabel("shown")

    (result,) = lab.run([lab.State("ui_next.shown", state, gated=True)], tmp_path)
    assert result.tries == tries and len(made) == 5 * tries  # fresh ones, each try
    assert len(result.over_budget()) == fails
    written = json.loads((tmp_path / "ui_next.shown.json").read_text(encoding="utf-8"))
    judged, each = (
        written["actions"]["first_show"],
        written["actions"]["first_show_each"],
    )
    assert judged["n"] == 1 and judged["within"] == (fails == 0)
    assert each["n"] == 5 and "budget" not in each  # recorded, not judged


def _words_first_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, every_page: bool = False
) -> lab.Result:
    """`w4_words_met_1000` in the lab, each try's first page's first show
    slowed by 60 ms - every page's, with `every_page` - and its first show (the five fresh pages'
    median, decision 0047) judged as `budget_judge` judges every budget
    test: on a busy runner tried again; over, but not slower than main's
    record, passed on the train; and over, said in the words GitHub's
    machines list and don't fail (polyglotic-hq 565, 578: the bare
    assertion failed GitHub's slower Windows machines 3 times, 552, 557,
    572). The last run's result."""
    learner = pages.met_learner_tools
    tried: list[lab.Result] = []

    def tools(met: int, zh: ChineseDictionary | None = None) -> LearningTools:
        trying[0] = True  # a try starts
        return learner(met, zh)

    trying = [False]

    class Slowed(WordsPage):
        def showEvent(self, event: QShowEvent) -> None:
            if every_page or trying[0]:
                time.sleep(0.06)
            trying[0] = False
            super().showEvent(event)

    monkeypatch.setattr(pages, "met_learner_tools", tools)
    monkeypatch.setattr(pages, "WordsPage", Slowed)
    state = next(s for s in pages.STATES if s.name == "ui_next.w4_words_met_1000")

    def take() -> Sampled:
        (result,) = lab.run([state], tmp_path)
        tried.append(result)
        return Sampled(tuple(result.actions["page_switch_cold"].samples))

    within(budgets.PAGE_SWITCH_COLD, take)
    return tried[-1]


def test_words_first_show_passes_a_slow_moment_in_each_try(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """234: in desktop #350's CI, `w4_words_met_10000`'s first show - 22-26
    ms in most runs - took 51.0 ms, then 58.7 ms on the retry, while the
    runner was busy, and failed the job. Timed once, a slow moment in each
    try fails; judged on five fresh pages (decision 0047), it passes."""
    result = _words_first_show(tmp_path, monkeypatch)
    assert max(result.actions["page_switch_cold_each"].samples) >= 60


def test_words_first_show_slow_every_time_is_a_budgets_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 578: a first show over its budget on most of the five
    pages - a real slowdown, or a slower machine - fails as a budget, in
    `budget_judge`'s words (`remote_test.py`'s BUDGET), not as a bare
    assertion GitHub's machines can't tell from a broken test."""
    monkeypatch.setattr(budget_judge, "beside_main", lambda *_: "")
    monkeypatch.setattr(budget_judge, "JUDGED", [])  # not in the run's summary
    with pytest.raises(AssertionError, match=r"over its [\d.]+ ms \(any one run"):
        _words_first_show(tmp_path, monkeypatch, every_page=True)


def test_the_garbage_collector_is_held_off_while_an_action_is_timed(
    tmp_path: Path,
) -> None:
    seen: list[bool] = []

    def state(lab_: lab.Lab) -> QWidget:
        lab_.time("look", lambda: seen.append(gc.isenabled()), repeat=2)
        return QLabel("look")

    lab.run([lab.State("ui.look", state, gated=False)], tmp_path)
    assert seen == [False, False] and gc.isenabled()


def test_fonts_are_warmed_before_the_first_state_is_timed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first text drawn loads its fonts (about 40 ms): it once landed in
    the first state as a run over the slot budget."""
    calls: list[str] = []
    monkeypatch.setattr(lab, "warm_fonts", lambda: calls.append("warm"))

    def first(lab_: lab.Lab) -> QWidget:
        calls.append("state")
        return QLabel("first")

    lab.run([lab.State("ui.first", first, gated=False)], tmp_path)
    assert calls == ["warm", "state"]
    monkeypatch.undo()
    lab.warm_fonts()  # and the real one runs offscreen


# -- the app's own text size (polyglotic-hq 292) ----------------------------------------


def test_the_goldens_are_approved_only_at_the_apps_normal_text_size(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit):
        cli.main(["approve", "--app-text-size", "largest", "--out", str(tmp_path)])


def test_each_state_begins_at_the_runs_app_text_size() -> None:
    """A state that leaves another size behind it (a `text_sizes` state goes
    back to Normal) doesn't carry it into the next: a Largest run checked
    most of its states at Normal until each began at the run's own."""
    begun: list[float] = []

    def leaves_normal(_lab: lab.Lab) -> QWidget:
        begun.append(style.app_text_size())
        style.use_app_text_size("normal")
        return QWidget()

    states = [lab.State(name, leaves_normal, False) for name in ("a", "b")]
    try:
        for state in cli.at_app_text_size(states, "largest"):
            state.run(lab.Lab(lab.application(), Path()))
        assert begun == [1.75, 1.75]
    finally:
        style.use_app_text_size("normal")


class LabClock:
    """The lab's clock in a gate's test (`time` in `tools.ui_lab.lab`): its
    `sleep` moves it on and sleeps nothing, so a click takes what the test
    says, whatever the PC. GitHub's Mac slept 50 and 60 ms as 125 and 151,
    and a click as slow as main's read as twice as slow (polyglotic-hq 420:
    the first Mac run of the suite)."""

    def __init__(self) -> None:
        self.seconds = 0.0
        self.monotonic = time.monotonic  # the lab's waits: the PC's own

    def perf_counter(self) -> float:
        return self.seconds

    def sleep(self, seconds: float) -> None:
        self.seconds += seconds


def clicks_taking(ms: float) -> lab.State:
    """A gated state whose six clicks each take `ms` (the click's budget: 30),
    on the lab's clock: a `LabClock` in a gate's test."""

    def state(lab_: lab.Lab) -> QWidget:
        lab_.time(
            "click", lambda: lab.time.sleep(ms / 1000), repeat=6, budget=budgets.CLICK
        )
        return QLabel("clicks")

    return lab.State("ui_next.clicks", state, gated=True)


def gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: lab.State,
    event: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    """The lab's gate on `state` alone, as CI runs it on a pull request or
    a push to main: its exit code and what it said."""
    monkeypatch.setattr(new_parts, "STATES", [state])
    monkeypatch.setattr(cli, "new_states", lambda: list(new_parts.STATES))
    monkeypatch.setattr(cli.goldens, "GOLDENS", None)  # the budgets alone
    monkeypatch.setattr(lab, "time", LabClock())
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path / "records"))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv(
        "GITHUB_REF", "refs/heads/main" if event == "push" else "refs/pull/1/merge"
    )
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234567890")
    code = cli.main(["--gate", "--out", str(tmp_path / "out")])
    return code, capsys.readouterr().err


MAIN = timing_record.kind(100, "normal", "en")


@pytest.mark.parametrize(
    ("main_ms", "fails"),
    [(60.0, 0), (30.0, 1)],
    ids=["as slow on main", "twice as slow as main"],
)
def test_a_pull_request_over_budget_fails_only_if_slower_than_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    main_ms: float,
    fails: int,
) -> None:
    """Decision 0136 (polyglotic-hq 344): main's theme change crept from 29
    to 76 ms of its 100 and failed pull requests that hadn't touched it. A
    click at 60 ms (its budget: 30) on a pull request: as main's record has
    it, over its budget as main is - said, not failed; main's at 30 ms, the
    change made it twice as slow - failed."""
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path / "records"))
    timing_record.save(
        MAIN,
        {"ui_next.clicks: click": timing_record.Timing(main_ms, main_ms)},
        "1234abcd",
    )
    code, said = gate(tmp_path, monkeypatch, clicks_taking(60), "pull_request", capsys)
    assert code == fails, said
    if fails:
        assert "over budget - ui_next.clicks: click" in said
    else:
        assert "over its budget as main is - ui_next.clicks: click - median" in said
        assert "main's (1234abcd) median 60.0" in said


def test_main_is_held_to_the_budget_alone_and_keeps_its_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Main's runs are never excused: main going over is seen there. Its
    timings become the record pull requests are compared with."""
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path / "records"))
    timing_record.save(
        MAIN, {"ui_next.clicks: click": timing_record.Timing(60.0, 60.0)}, "1234abcd"
    )
    code, said = gate(tmp_path, monkeypatch, clicks_taking(60), "push", capsys)
    assert code == 1 and "over budget - ui_next.clicks: click" in said
    record = timing_record.load(MAIN)
    assert record is not None and record.commit == "abcdef1234567890"
    kept = record.timings["ui_next.clicks: click"]
    assert 60 <= kept.median_ms < 120 and kept.longest_ms >= kept.median_ms


def test_a_gate_run_in_a_test_never_keeps_this_pcs_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Polyglotic-hq 367: CI's Checks on a push to main run these tests with
    the push's own environment, and a test's gate kept its made-up timings
    (none, or one click) as main's record on the PC, over the UI lab's own.
    Every pull request's lab after that was judged against it: with nothing
    of main's to compare, any action over its budget failed."""
    pc = tmp_path / "this-pc"
    monkeypatch.setattr(start_record, "RECORD_FOLDER", pc)
    monkeypatch.setattr(new_parts, "STATES", [clicks_taking(1)])
    monkeypatch.setattr(cli, "new_states", lambda: list(new_parts.STATES))
    monkeypatch.setattr(cli.goldens, "GOLDENS", None)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    assert cli.main(["--gate", "--out", str(tmp_path / "out")]) == 0
    assert not pc.exists() or not any(pc.iterdir())


def test_without_a_record_a_pull_request_is_held_to_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No record of main's here (another PC, or none kept yet): the gate is
    the budget, as before 0136."""
    code, said = gate(tmp_path, monkeypatch, clicks_taking(60), "pull_request", capsys)
    assert code == 1 and "over budget - ui_next.clicks: click" in said


def test_the_lab_command_runs_holding_the_shared_qt_lock(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`python -m tools.ui_lab` waits for the shared Qt lock and 3.0 GB free
    on the user's PC, and holds the lock while it runs (polyglotic-hq 563,
    `tools/qt_lock.py`): it lived only in the agents' wrappers, and a lab
    run started without one held nothing (551)."""
    seen: list[str] = []
    holding: list[str] = []

    @contextlib.contextmanager
    def held(what: str) -> Iterator[bool]:
        seen.append(what)
        holding.append(what)
        yield True
        holding.remove(what)

    def main(argv: list[str] | None = None) -> int:
        assert holding == ["tools.ui_lab languages --jobs 4"], "ran without it"
        return 0

    monkeypatch.setattr(cli.qt_lock, "held", held)
    monkeypatch.setattr(cli, "main", main)
    assert cli.locked(["languages", "--jobs", "4"]) == 0
    assert seen == ["tools.ui_lab languages --jobs 4"] and not holding

    def waited_too_long(what: str) -> Iterator[bool]:
        raise cli.qt_lock.GaveUp("qt.lock: gave up after 45 min: ...")

    monkeypatch.setattr(cli.qt_lock, "held", waited_too_long)
    assert cli.locked(["--gate"]) == 2
    assert "gave up after 45 min" in capsys.readouterr().err


def test_timing_states_show_the_default_and_explicit_live_update_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import Mock

    from tools.ui_lab import panels

    from polyglotic_desktop.core.listening.timing import LIVE_UPDATE_INTERVAL_SEC

    panel = Mock()
    make_panel = Mock(return_value=panel)
    monkeypatch.setattr(panels, "TimingPanel", make_panel)
    monkeypatch.setattr(panels, "page", Mock())

    for state in panels.STATES:
        if not state.name.startswith("ui_next.panel_timing_"):
            continue
        state.run(Mock())
        view = make_panel.call_args.args[0]
        expected = (
            6.0 if state.name.endswith("_live_slower") else LIVE_UPDATE_INTERVAL_SEC
        )
        assert view.value.live_interval == expected, state.name
