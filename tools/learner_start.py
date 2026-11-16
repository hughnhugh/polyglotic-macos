"""The app's start with a made-up learner of many words met: `main()` from
source, offscreen, timed from its call to the main window's first paint -
the span `--check-install`'s `window_seconds` measures, held to
`perf.budgets.START_FROM_SOURCE` (polyglotic-hq 220, 229). CI's start gate
(`tests/ui/test_start_with_a_big_learner.py`) runs it on the real CC-CEDICT;
by hand:

    uv run python -m tools.dictionaries.build --only cedict
    uv run python -m tools.learner_start --words 10000 --runs 5

With `--english-words N` the learner learns English too, N words met in
ECDICT: both dictionaries and both learning data files open at the start
(polyglotic-hq 306; `build --only ecdict` first).

The learner is made up, never a real learner's file: CC-CEDICT's commonest
N entries, heard on 163's Zipf curve, HSK 4 picked, with 212's proportions
of deck, known and saved words. A returning learner: the learning language
chosen, the tester agreement accepted, so nothing is asked.

Each start is a process of its own (`--child`), as a real start is. It
signs in nowhere and captures, plays and connects nothing: no hotkeys, no
app list, the device token's store in memory (empty), the update feed an
empty folder; it ends at the window's first paint, before the connection,
speech detection or anything after the window is reached. It writes in
the data folder it's given, and its time in a file beside it.

**With real windows** (`timed_start(..., real_windows=True)`, polyglotic-hq
322): the same start on Qt's `windows` platform, on a private desktop
(`tools/private_desktop.py`) - nothing reaches anyone's screen. Offscreen
skips what a learner's start spends most on: Windows' fonts read, and the
first native window. That start goes on past its paint, signed out (so
nothing is captured), to the event loop's first turn - the first moment a
click is answered - and ends there: `TimedStart.answers_ms`.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from functools import partial
from pathlib import Path

from tools import start_record

LEVEL = 4
"""The made-up learner's HSK level (2025 syllabus)."""

TODAY = date(2026, 11, 8)
"""The made-up learner's today, so the learner is the same whenever made."""

CHILD_TIMEOUT_SECONDS = 120
"""A start not ended by then is stopped. If it reached its window (its
report is written), that start counts: only its ending hung."""


def made_up_learner(cedict: Path, words: int, out: Path) -> None:
    """A learning data file at `out` for a Chinese learner who has met
    `cedict`'s commonest `words` entries: entry rank r heard
    max(1, round(20 * words / r ** 1.15)) times (163's Zipf curve), first
    heard up to 180 days before `TODAY`; HSK `LEVEL` picked; of the words
    still new at that level, words/40 in the deck, words/25 known by hand
    and words/50 saved (212's proportions). `cedict` may be ECDICT
    (`ecdict.sqlite`): an English learner the same way, no level picked
    (polyglotic-hq 306: both open at once)."""
    from polyglotic_desktop.adapters.sqlite_dictionary import GuardedDictionary
    from polyglotic_desktop.adapters.sqlite_learning import open_learning_store
    from polyglotic_desktop.core.learning.lookups import LookupContext
    from polyglotic_desktop.core.learning.vocabulary import Vocabulary
    from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
    from polyglotic_desktop.core.lexicon.english import EnglishDictionary
    from polyglotic_desktop.core.lexicon.meanings import short_meaning
    from polyglotic_desktop.core.shared import EntryId, Level, WordStatus
    from polyglotic_desktop.ports.learning import StoredExposures

    db = sqlite3.connect(f"{cedict.resolve().as_uri()}?mode=ro", uri=True)
    try:
        ids = [
            row[0]
            for row in db.execute(
                "SELECT id FROM entries"
                " ORDER BY frequency_rank IS NULL, frequency_rank, n LIMIT ?",
                (words,),
            )
        ]
    finally:
        db.close()
    if len(ids) < words:  # the tests' sample, say: a small learner, unsaid
        raise ValueError(f"{cedict.name} has {len(ids):,} entries, not {words:,}")
    file = GuardedDictionary(cedict)
    english = cedict.stem == "ecdict"
    dictionary = EnglishDictionary(file) if english else ChineseDictionary(file)
    out.unlink(missing_ok=True)
    store = open_learning_store(out)
    try:
        store.save_exposures(
            [
                StoredExposures(
                    entry,
                    max(1, round(20 * words / rank**1.15)),
                    0,
                    0,
                    TODAY - timedelta(days=rank % 180),
                )
                for rank, entry in enumerate(ids, 1)
            ],
            {},
        )
        scheme = "en-frequency" if english else "hsk-2025"
        vocabulary = Vocabulary(store, dictionary.facts, scheme)
        if not english:
            vocabulary.set_level(Level(scheme, LEVEL))
        new = [
            EntryId(e)
            for e in ids
            if vocabulary.status_of_entry(EntryId(e)).status is WordStatus.NEW
        ]
        deck, by_hand, saved = words // 40, words // 25, words // 50
        for entry_id in new[:deck]:
            vocabulary.set_status(entry_id, WordStatus.LEARNING)
        for entry_id in new[deck : deck + by_hand]:
            vocabulary.set_status(entry_id, WordStatus.KNOWN)
        category = vocabulary.categories[0].id
        for entry_id in new[deck + by_hand : deck + by_hand + saved]:
            entry = dictionary.entry(entry_id)
            if entry is None:
                continue
            vocabulary.save(
                entry_id,
                entry.headword,
                entry.traditional,
                entry.reading,
                short_meaning([entry]),
                category,
                LookupContext(entry.headword),
            )
    finally:
        store.close()
        file.close()


def returning_learner(
    folder: Path,
    learning: Path,
    english: Path | None = None,
    pack_language: str | None = None,
) -> Path:
    """A data folder at `folder` for a returning Chinese learner whose
    learning data is a copy of `learning`: the language chosen and the
    tester agreement accepted (no usage statistics, crash reports or
    exposures shared), so the start asks nothing. With `english`, a copy
    of it as English's learning data, and English learned too: both
    dictionaries open at the start (polyglotic-hq 306). With
    `pack_language`, that language learned too - a pack learner (decision
    0175): its learning data opens once its pack does, which must be in the
    dictionaries' `packs` folder (polyglotic-hq 436)."""
    from polyglotic_desktop.adapters.sqlite_outbox import open_outbox
    from polyglotic_desktop.core.shared.papers import TESTER_AGREEMENT_VERSION
    from polyglotic_desktop.ports.consent import Agreement, ConsentChoice

    folder.mkdir(parents=True)
    chosen: dict[str, object] = {"learning": "zh"}
    also: list[str] = []
    if english is not None:
        also.append("en")
        shutil.copy(english, folder / "learning-en.sqlite")
    if pack_language is not None:
        also.append(pack_language)
    if also:
        chosen["also_learning"] = also
    (folder / "settings.json").write_text(json.dumps(chosen), encoding="utf-8")
    shutil.copy(learning, folder / "learning.sqlite")
    at = datetime(2026, 11, 8, tzinfo=UTC)
    outbox = open_outbox(folder / "outbox.sqlite")
    try:
        outbox.save_consent(
            ConsentChoice(
                str(uuid.UUID(int=229)),
                at,
                usage=False,
                crashes=False,
                exposures=False,
                agreement=Agreement(TESTER_AGREEMENT_VERSION, at),
            )
        )
    finally:
        outbox.close()
    (folder / "no-feed").mkdir()
    return folder


@dataclasses.dataclass(frozen=True)
class TimedStart:
    """One start, timed."""

    window_ms: float
    """From `main()`'s call to the main window's first paint."""
    busy: float | None
    """How busy the rest of the PC was meanwhile: the share of its CPU time
    that everything but the start used (`busy_pc.OthersMeanwhile`); None
    where the counters can't be read."""
    threads: tuple[str, ...] = ()
    """The Python threads begun from `main()`'s call to the first paint, by
    name: each takes the interpreter from the window's build by turns, so
    only what the window or the moment after it needs belongs here
    (polyglotic-hq 314)."""
    parts: Mapping[str, float] = dataclasses.field(default_factory=dict)
    """Where the time went: each part of the start in milliseconds, in
    order, adding up to `window_ms` (`perf.start_parts`)."""
    answers_ms: float | None = None
    """From the first paint to the event loop's first turn: a click made
    before then waits. Only a start with real windows goes on that far;
    None too if it never got there."""
    pack_busy_ms: float | None = None
    """A pack learner's start (`timed_start(..., until_pack=...)`): the
    longest stretch of the interface thread's work the app's watchdog
    logged from the packs' opening to `PACK_SETTLED_MS` after the pack
    language's learning data opened (0: none over the watchdog's 50 ms);
    None if it never opened, or the start wasn't one."""
    pack_busy_in: str = ""
    """Where the watchdog said that stretch was (`file.py:function`)."""


def timed_start(
    data: Path,
    dictionaries: Path,
    real_windows: bool = False,
    until_pack: str | None = None,
) -> TimedStart:
    """A start from `main()`'s call to the main window's first paint, in a
    process of its own, on the learner's data folder `data` and the
    dictionaries in `dictionaries`, with how busy the rest of the PC was
    meanwhile. Offscreen - or with `real_windows`, on a private desktop,
    going on to the first moment a click is answered (the module's words).
    With `until_pack` (a pack language the learner learns,
    `returning_learner(..., pack_language=...)`): going on past the paint
    until that language's learning data has opened and settled, for the
    interface thread's longest stretch meanwhile (`pack_busy_ms`,
    polyglotic-hq 436)."""
    report = data.parent / f"{data.name}-start.json"
    command = [
        sys.executable,
        "-m",
        "tools.learner_start",
        "--child",
        str(data),
        str(dictionaries),
        str(report),
    ]
    if until_pack is not None:
        command += ["--until-pack", until_pack]
    here = Path(__file__).resolve().parents[1]
    if real_windows:
        said = _on_a_private_desktop(command, data.parent / f"{data.name}.log", here)
    else:
        said = _offscreen(command, data.parent / f"{data.name}-stderr.txt", here)
    if not report.exists():
        raise RuntimeError(f"the start didn't reach its window ({said[-2000:]})")
    found = json.loads(report.read_text(encoding="utf-8"))
    busy = found.get("busy")
    answers = found.get("answers_ms")
    pack_busy = found.get("pack_busy_ms")
    return TimedStart(
        float(found["window_ms"]),
        None if busy is None else float(busy),
        tuple(found.get("threads", ())),
        {str(part): float(ms) for part, ms in found.get("parts", {}).items()},
        None if answers is None else float(answers),
        None if pack_busy is None else float(pack_busy),
        str(found.get("pack_busy_in", "")),
    )


PACK_SETTLED_MS = 2000
"""How long a pack learner's start goes on after the pack language's
learning data opened: its Words section, Learning's card and the windows'
marks are drawn by then, and the stretch they made has ended and been
logged."""

BUSY = re.compile(r"interface thread busy (\d+) ms in (.+?)(?:, of | \(from |$)")
"""The app's watchdog's line for a long stretch (`perf.watchdog`): how long,
and where."""


def longest_busy(log: Path, since: datetime) -> tuple[float, str]:
    """The longest stretch the app's watchdog logged in `log` at or after
    `since` (the log's local times), and where; (0, "") if none."""
    longest = (0.0, "")
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return longest
    for line in lines:
        found = BUSY.search(line)
        if found is None:
            continue
        try:
            at = datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
        except ValueError:
            continue
        if at >= since and float(found.group(1)) > longest[0]:
            longest = (float(found.group(1)), found.group(2))
    return longest


UNTIL_IT_ANSWERS = "POLYGLOTIC_START_UNTIL_IT_ANSWERS"
"""Set for the child: go on past the paint to the event loop's first turn."""

FONTS_FOLDER = "QT_QPA_FONTDIR"
"""Qt's own fonts folder, which the tests set for the offscreen platform:
never a real start's, so the start with real windows runs without it."""


def _offscreen(command: list[str], output: Path, cwd: Path) -> str:
    """`command` run offscreen, stopped if it outlasts `CHILD_TIMEOUT_SECONDS`;
    how it went, in words. Its errors go to `output`, not a pipe: a venv's
    python.exe launches the real one, which can hold a pipe after the
    launcher is stopped and keep `run` waiting without bound. A start
    stopped after its report was written still counts - it reached its
    window; only its ending hung (polyglotic-hq 312: one in about 500)."""
    with output.open("wb") as errors:
        try:
            code: int | str = subprocess.run(
                command,
                env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                timeout=CHILD_TIMEOUT_SECONDS,
                check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            code = f"stopped after {CHILD_TIMEOUT_SECONDS} s"
    return f"exit {code}: {output.read_bytes().decode(errors='replace')}"


def _on_a_private_desktop(command: list[str], output: Path, cwd: Path) -> str:
    """`command` run with real windows on a desktop of its own, ended there
    if it outlasts `CHILD_TIMEOUT_SECONDS`; how it went, in words."""
    from tools.private_desktop import PrivateDesktop

    env = dict(os.environ, QT_QPA_PLATFORM="windows")
    env[UNTIL_IT_ANSWERS] = "1"
    env.pop(FONTS_FOLDER, None)
    with PrivateDesktop() as desktop:
        started = desktop.start(command, env=env, cwd=cwd, output=output)
        code = started.wait(CHILD_TIMEOUT_SECONDS)
    try:
        said = output.read_text(encoding="utf-8", errors="replace")
    except OSError:
        said = ""
    return f"exit {code}: {said}"


def ended_now() -> None:
    """This process ended at once, its threads where they are. On Windows
    by TerminateProcess, not os._exit: os._exit's ExitProcess runs every
    library's detach code once the other threads are stopped, and a thread
    stopped mid-way through loading a library (the start's imports thread)
    can leave that waiting for ever - one start in about 500 hung so after
    writing its time (polyglotic-hq 312, 2026-11-14: two hours, one thread
    left), as 302's start test once timed out."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0)
    os._exit(0)


def _child(
    data: Path, dictionaries: Path, report: Path, until_pack: str | None = None
) -> None:
    """`main()` on `data`, timed to the window's first paint, then ended at
    once - before the connection or anything after the window. With
    `until_pack`, it goes on until that pack language's learning data has
    opened and settled (`PACK_SETTLED_MS`), then ends."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from tests.fakes import MemoryCredentialStore

    from polyglotic_desktop import main as m
    from tools import busy_pc

    class NoHotkeys:
        def __init__(self, keys: object) -> None:
            pass

        def start(self) -> list[str]:
            return []

        def stop(self) -> None:
            pass

    class Silent:
        def play(self, audio: object, rate: int) -> bool:
            return True

        def stop(self) -> None:
            pass

    class NoWatch:
        def __init__(self, changed: object) -> None:
            pass

        def start(self) -> bool:
            return False

        def stop(self) -> None:
            pass

    real = m.os_adapters

    def os_adapters(system: str = sys.platform) -> m.OsAdapters:
        return dataclasses.replace(
            real(system),
            app_list=m.NoApps,
            credentials=lambda target: MemoryCredentialStore(),
            hotkeys=NoHotkeys,
            sound_out=Silent,
            foreground_watch=NoWatch,
        )

    shown: list[bool] = []
    started = 0.0
    others: busy_pc.OthersMeanwhile | None = None
    begun: list[str] = []  # the threads begun before the first paint

    class Shown(m.DesktopApp):
        def show_window(self) -> None:
            super().show_window()
            shown.append(True)

    until_it_answers = bool(os.environ.get(UNTIL_IT_ANSWERS))
    found: dict[str, object] = {}

    def answered(painted: float) -> None:
        """The event loop's first turn after the paint: a click is answered
        from now. The start ends here (a pack learner's goes on)."""
        found["answers_ms"] = round((time.perf_counter() - painted) * 1000, 1)
        report.write_text(json.dumps(found), encoding="utf-8")
        if until_pack is None:
            ended_now()

    packs_opened: list[datetime] = []

    def pack_settled() -> None:
        """The pack language's learning data opened `PACK_SETTLED_MS` ago:
        the longest stretch since the packs opened, and the start ends."""
        ms, where = longest_busy(data / "logs" / "polyglotic.log", packs_opened[0])
        found.update(pack_busy_ms=ms, pack_busy_in=where)
        report.write_text(json.dumps(found), encoding="utf-8")
        ended_now()

    if until_pack is not None:
        packs_start = m.PackDelivery.start
        language_opened = m.Hub.language_opened

        def packs_starting(packs: m.PackDelivery) -> None:
            packs_opened.append(datetime.now())  # local, as the log's times
            packs_start(packs)

        def opened(hub: m.Hub, other: m.LearningTools) -> None:
            language_opened(hub, other)
            if other.language == until_pack and packs_opened:
                QTimer.singleShot(PACK_SETTLED_MS, pack_settled)

        m.PackDelivery.start = packs_starting  # type: ignore[assignment]
        m.Hub.language_opened = opened  # type: ignore[assignment]

    class Timed(QApplication):
        def processEvents(self) -> None:  # type: ignore[override]
            super().processEvents()  # as main calls it: no arguments
            if shown and not found:  # main's after the window: its first paint
                painted = time.perf_counter()
                window_ms = (painted - started) * 1000
                m.start_parts.done("first_paint")  # main's own isn't reached
                busy = others.share() if others is not None else None
                found.update(
                    window_ms=round(window_ms, 1),
                    busy=None if busy is None else round(busy, 3),
                    threads=sorted(begun),
                    parts={
                        part: round(ms, 1) for part, ms in m.start_parts.parts().items()
                    },
                )
                report.write_text(json.dumps(found), encoding="utf-8")
                if not until_it_answers and until_pack is None:
                    ended_now()  # nothing after the window: no connection
                # main goes on - signed out, so nothing is captured, and its
                # server an address nothing answers at - to its event loop,
                # whose first turn runs this
                QTimer.singleShot(0, partial(answered, painted))

    m.os_adapters = os_adapters
    m.DesktopApp = Shown  # type: ignore[misc]
    m.QApplication = Timed  # type: ignore[misc]
    argv = [
        "--server",
        "http://127.0.0.1:9",  # never reached: the start ends at the window
        "--packs-from",
        "http://127.0.0.1:9",  # nor the packs' storage: a pack is already here
        "--data",
        str(data),
        "--dictionaries",
        str(dictionaries),
        "--updates",
        str(data / "no-feed"),
    ]
    begin = threading.Thread.start

    def noted(thread: threading.Thread) -> None:
        begun.append(thread.name)
        begin(thread)

    threading.Thread.start = noted  # type: ignore[assignment, method-assign]
    others = busy_pc.OthersMeanwhile()
    started = time.perf_counter()
    m.main(argv)
    raise SystemExit("main() returned without showing its window")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--child", nargs=3, type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--until-pack", help=argparse.SUPPRESS)
    parser.add_argument(
        "--dictionaries",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "build" / "dictionaries",
    )
    parser.add_argument("--words", type=int, default=10_000)
    parser.add_argument(
        "--english-words",
        type=int,
        default=0,
        help="English learned too, with this many words met (306); 0: Chinese alone",
    )
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument(
        "--real-windows",
        action="store_true",
        help="with real windows on a private desktop, on to the first moment"
        " a click is answered (nothing reaches the screen)",
    )
    args = parser.parse_args(argv)
    if args.child:
        data, dictionaries, report = args.child
        _child(data, dictionaries, report, until_pack=args.until_pack)
        return 1  # not reached
    with tempfile.TemporaryDirectory(prefix="learner-start-") as folder:
        learning = Path(folder) / "learning.sqlite"
        started = time.perf_counter()
        made_up_learner(args.dictionaries / "cedict.sqlite", args.words, learning)
        english = None
        if args.english_words:
            english = Path(folder) / "learning-en.sqlite"
            made_up_learner(
                args.dictionaries / "ecdict.sqlite", args.english_words, english
            )
        made = time.perf_counter() - started
        print(f"made-up learner of {args.words:,} words met: {made:.1f} s")
        if english is not None:
            print(f"and English, {args.english_words:,} words met: both open")
        runs = []
        starts = []
        for n in range(1, args.runs + 1):
            data = returning_learner(Path(folder) / f"start-{n}", learning, english)
            start = timed_start(data, args.dictionaries, args.real_windows)
            runs.append(start.window_ms)
            starts.append(start)
            said = f"start {n}: {start.window_ms:.0f} ms"
            if start.answers_ms is not None:
                said += f", answering {start.answers_ms:.0f} ms after"
            if start.busy is not None:
                said += f", the rest of the PC {start.busy:.0%} busy"
            print(said)
        print(
            f"median {statistics.median(runs):.0f} ms,"
            f" {min(runs):.0f}-{max(runs):.0f} ms"
        )
        # each part's median, beside main's last record if this PC has one
        kind = (
            start_record.REAL_WINDOWS if args.real_windows else start_record.OFFSCREEN
        )
        parts = start_record.typical(
            [start_record.with_after(s.parts, s.answers_ms) for s in starts]
        )
        print(start_record.table(parts, start_record.load(kind)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
