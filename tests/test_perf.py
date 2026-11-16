"""perf: named spans, timings as JSON, and the interface-thread watchdog -
names and durations only, never caption text."""

import json
import logging
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.perf import spans, watchdog
from polyglotic_desktop.perf.spans import Timings, checked_name
from polyglotic_desktop.perf.watchdog import Watchdog

CAPTION = "我们周末一起去打游戏吧"  # made-up; must never reach a log


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    yield app


def test_spans_record_nothing_unless_recording() -> None:
    spans.TIMINGS.clear()
    with spans.span("caption_window.paint"):
        pass
    assert spans.TIMINGS.summary() == {}


def test_spans_recorded_by_name() -> None:
    with spans.recorded() as timings:
        for _ in range(3):
            with spans.span("caption_window.paint"):
                time.sleep(0.001)
    (paint,) = timings.summary().values()
    assert paint["n"] == 3
    assert paint["median_ms"] >= 1
    assert not spans.recording()


@pytest.mark.parametrize("name", [CAPTION, "Caption window", "a b", "", "x" * 65])
def test_a_span_name_is_a_constant_never_text(name: str) -> None:
    with pytest.raises(ValueError):
        checked_name(name)
    with pytest.raises(ValueError), spans.recorded(), spans.span(name):
        pass


def test_timings_written_as_json(tmp_path: Path) -> None:
    timings = Timings()
    for ms in (1.0, 2.0, 3.0, 10.0):
        timings.record("transcript.resize_step", ms)
    timings.write(tmp_path / "t.json", state="transcript_1000")
    written = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert written["state"] == "transcript_1000"
    assert written["spans"]["transcript.resize_step"] == {
        "n": 4,
        "median_ms": 2.5,
        "p90_ms": 3.0,
        "max_ms": 10.0,
    }


def run_loop(qapp: QApplication, ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.mark.xfail(
    sys.platform != "win32",
    reason="Linux's event dispatcher (GLib) doesn't give the watchdog its"
    " awake / about-to-block pairs: it sees no slow slot there (179's Linux"
    " checks, 2026-11-08; 171 saw the same); a Mac's sometimes does (421)",
    strict=sys.platform == "linux",
)
def test_the_watchdog_names_a_slow_slot_and_its_duration(
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(watchdog, "PACKAGE", "tests")  # name this file's frames
    reported: list[tuple[float, str]] = []
    dog = Watchdog(report=lambda ms, where: reported.append((ms, where)))
    dog.start()

    def slow_slot() -> None:
        line = CAPTION  # caption text in a local: must not be logged
        time.sleep(0.12)
        assert line

    try:
        with caplog.at_level(logging.WARNING, logger=watchdog.__name__):
            QTimer.singleShot(10, slow_slot)
            run_loop(qapp, 300)
    finally:
        dog.stop()
    assert dog.slow == 1
    ((ms, where),) = reported
    assert ms >= 120
    assert where.startswith("test_perf.py:slow_slot (from test_perf.py:test_")
    assert "test_perf.py:slow_slot" in caplog.text
    assert CAPTION not in caplog.text


def test_the_watchdog_lets_fast_slots_be(
    qapp: QApplication, caplog: pytest.LogCaptureFixture
) -> None:
    dog = Watchdog()
    dog.start()
    try:
        with caplog.at_level(logging.WARNING, logger=watchdog.__name__):
            for n in range(20):
                QTimer.singleShot(n * 5, lambda: time.sleep(0.002))
            run_loop(qapp, 200)
    finally:
        dog.stop()
    assert dog.slow == 0
    assert caplog.text == ""


ON_WINDOWS_ONLY = pytest.mark.xfail(
    sys.platform != "win32",
    reason="Linux's event dispatcher gives the watchdog no stretches (above);"
    " a Mac's sometimes does: one passed in 421's Mac run, none in 420's",
    strict=sys.platform == "linux",
)


def loop_outside_qt(seconds: float, stuck_for: float = 0.0) -> None:
    """What a loop of Windows' own does - its Save dialog, a window being
    moved: it runs Qt's posted events (the watchdog's questions among them)
    but never Qt's event dispatcher, which says nothing until it ends.
    Halfway, `stuck` works `stuck_for` seconds and answers nothing; then
    the loop goes straight back to its messages, as Windows' do (they wait
    on the next message, not a clock). A 2 ms sleep there first left the
    thread unanswered in `loop_outside_qt`, and a look by the watchdog then
    named the loop, not the work: 8 of 40 runs, the PC 47-65 % busy
    (polyglotic-hq 312, 2026-11-14; 305 saw it in 2 of 4 full runs)."""
    end = time.perf_counter() + seconds
    halfway = time.perf_counter() + seconds / 2
    while time.perf_counter() < end:
        QCoreApplication.sendPostedEvents()
        if stuck_for and time.perf_counter() >= halfway:
            stuck(stuck_for)
            stuck_for = 0.0
            continue  # answers at once
        time.sleep(0.002)


def stuck(seconds: float) -> None:
    time.sleep(seconds)


@ON_WINDOWS_ONLY
def test_a_loop_outside_qts_that_answers_isnt_a_busy_thread(
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows' Save dialog, open while the learner chooses where to save
    (words_page.py:_export_deck): the thread answered all along. Logged at
    INFO, not as a slow stretch (302: a tester's log said the interface
    thread was busy 10,530 ms in _export_deck; the export itself already
    ran on a thread of its own)."""
    monkeypatch.setattr(watchdog, "PACKAGE", "tests")
    reported: list[tuple[float, str]] = []
    dog = Watchdog(report=lambda ms, where: reported.append((ms, where)))
    dog.start()
    try:
        with caplog.at_level(logging.INFO, logger=watchdog.__name__):
            QTimer.singleShot(10, lambda: loop_outside_qt(0.4))
            run_loop(qapp, 600)
    finally:
        dog.stop()
    assert reported == []
    assert (dog.slow, dog.answering) == (0, 1)
    assert "answered in a loop outside Qt's" in caplog.text
    assert "test_perf.py:loop_outside_qt" in caplog.text


@ON_WINDOWS_ONLY
def test_work_inside_a_loop_outside_qts_is_still_a_busy_thread(
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A spell of work in such a loop - Windows filling its dialog - is
    reported by itself, with where it was and how long the loop ran."""
    monkeypatch.setattr(watchdog, "PACKAGE", "tests")
    reported: list[tuple[float, str]] = []
    dog = Watchdog(report=lambda ms, where: reported.append((ms, where)))
    dog.start()
    try:
        with caplog.at_level(logging.WARNING, logger=watchdog.__name__):
            QTimer.singleShot(10, lambda: loop_outside_qt(0.4, stuck_for=0.15))
            run_loop(qapp, 800)
    finally:
        dog.stop()
    assert dog.slow == 1
    ((ms, where),) = reported
    assert 150 <= ms < 400  # the spell stuck, not the whole loop (550 ms)
    assert where.startswith("test_perf.py:stuck (from test_perf.py:")
    assert "in a loop outside Qt's" in caplog.text


def went_back(seconds: float) -> None:
    """The code the thread goes back to after slow work, before it answers
    or waits: Qt's own loop, `run_loop`, `loop_outside_qt`."""
    time.sleep(seconds)


@ON_WINDOWS_ONLY
def test_slow_work_is_named_for_itself_not_where_the_thread_went_after(
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """polyglotic-hq 344: CI named "run_loop" for a slow slot and
    "loop_outside_qt" for stuck work (10 failed runs, 2026-11-13/14): the
    helper's last look came after the work had ended, before the thread got
    back to answering. Here the thread spends 45 ms elsewhere after 150 ms
    of work - one or two looks there, five or six in the work - and the
    work is still what's named."""
    monkeypatch.setattr(watchdog, "PACKAGE", "tests")
    reported: list[tuple[float, str]] = []
    dog = Watchdog(report=lambda ms, where: reported.append((ms, where)))
    dog.start()

    def work_then_back() -> None:
        stuck(0.15)
        went_back(0.045)

    try:
        with caplog.at_level(logging.WARNING, logger=watchdog.__name__):
            QTimer.singleShot(10, work_then_back)
            run_loop(qapp, 400)
    finally:
        dog.stop()
    ((ms, where),) = reported
    assert ms >= 195
    assert where.startswith("test_perf.py:stuck (from test_perf.py:")


@ON_WINDOWS_ONLY
def test_a_slow_stretch_just_after_a_short_one_is_named(
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper counts from the slow stretch's own start, not from the
    short one that woke it: that left it looking too late, and the slow
    stretch went down as "a stretch the watchdog didn't catch" (302: about
    400 of those in a tester's log). A 200 ms budget, for wide margins."""
    monkeypatch.setattr(watchdog, "PACKAGE", "tests")
    reported: list[tuple[float, str]] = []
    dog = Watchdog(threshold_ms=200, report=lambda ms, w: reported.append((ms, w)))
    dog.start()
    try:
        with caplog.at_level(logging.WARNING, logger=watchdog.__name__):
            QTimer.singleShot(0, lambda: stuck(0.04))  # wakes the helper
            QTimer.singleShot(60, lambda: stuck(0.24))  # ends before 0 + 2 x 200
            run_loop(qapp, 600)
    finally:
        dog.stop()
    ((ms, where),) = reported
    assert ms >= 240
    assert where.startswith("test_perf.py:stuck")
