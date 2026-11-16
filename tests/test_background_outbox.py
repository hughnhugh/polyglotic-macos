"""The outbox on a thread of its own (adapters/background_outbox.py): writes
return at once and run in order on one other thread, reads see the writes
queued before them, nothing queued is lost when the app quits, the
consent choice is saved before what depends on it is sent, and the
interface thread never waits on the outbox's disk (polyglotic-hq projects
136 and 144)."""

import json
import logging
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.adapters.background_outbox import BackgroundOutbox
from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.core.shared import EntryId, LearningEvent, WordSaved
from polyglotic_desktop.perf.watchdog import Watchdog
from polyglotic_desktop.ports.consent import ConsentChoice
from polyglotic_desktop.ports.outbox import Waiting

AT = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
INSTALL = "3c5e7a9b-1d2f-4e6a-8b0c-2d4f6a8c0e1f"
WORD = EntryId("cedict:y7p98nwvxq")
SLOW = 0.08  # a commit while the disk is busy at start (project 136: 60-84 ms)


def item(kind: str, n: int) -> Waiting:
    return Waiting(kind, f"{kind}-{n}", f'{{"n": {n}}}')


class SlowOutbox(SqliteOutbox):
    """Every write takes as long as one on a busy disk, and notes its thread."""

    def __init__(self, path: Path | str) -> None:
        super().__init__(path)
        self.threads: set[str] = set()

    def _slow(self) -> None:
        self.threads.add(threading.current_thread().name)
        time.sleep(SLOW)

    def add(self, item: Waiting, keep: int) -> None:
        self._slow()
        super().add(item, keep)

    def remove_kind(self, kind: str) -> None:
        self._slow()
        super().remove_kind(kind)

    def save_note(self, key: str, value: str | None) -> None:
        self._slow()
        super().save_note(key, value)

    def save_consent(self, choice: ConsentChoice) -> None:
        self._slow()
        super().save_consent(choice)


class Heard:
    def learning_arrived(self, events: object) -> None: ...

    def learning_deleted(self) -> None: ...


def test_writes_return_at_once_and_run_in_order_on_one_other_thread(
    tmp_path: Path,
) -> None:
    slow: list[SlowOutbox] = []

    def open_slow() -> SlowOutbox:
        slow.append(SlowOutbox(tmp_path / "outbox.sqlite"))
        return slow[0]

    outbox = BackgroundOutbox(open_slow)
    start = time.perf_counter()
    for n in range(4):
        outbox.add(item("learning", n), keep=3)
    outbox.remove(w for w in ["learning-2"])  # a generator, read before it returns
    outbox.save_note("cursor", "50")
    assert time.perf_counter() - start < SLOW  # returned before any was written
    # a read waits for the writes before it: in order, the oldest dropped first
    assert [w.id for w in outbox.waiting()] == ["learning-1", "learning-3"]
    assert outbox.dropped() == 1
    assert outbox.note("cursor") == "50"
    (thread,) = slow[0].threads
    assert thread != threading.current_thread().name
    outbox.close()


def test_closing_writes_everything_queued_first(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite"
    outbox = BackgroundOutbox(lambda: SlowOutbox(path))
    outbox.save_consent(ConsentChoice("a", AT, True, False, False))
    for n in range(3):
        outbox.add(item("usage", n), keep=10)
    outbox.close()  # the app quits with four writes queued
    again = SqliteOutbox(path)
    assert [w.id for w in again.waiting()] == ["usage-0", "usage-1", "usage-2"]
    assert again.consent() == ConsentChoice("a", AT, True, False, False)
    again.close()


QUITS_WITHOUT_CLOSING = """
import sys, time
from datetime import UTC, datetime
from pathlib import Path
from polyglotic_desktop.adapters.background_outbox import BackgroundOutbox
from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.ports.consent import ConsentChoice
from polyglotic_desktop.ports.outbox import Waiting

class Slow(SqliteOutbox):
    def add(self, item, keep):
        time.sleep(0.05)
        super().add(item, keep)

outbox = BackgroundOutbox(lambda: Slow(Path(sys.argv[1])))
outbox.save_consent(ConsentChoice("a", datetime(2026, 11, 7, tzinfo=UTC), True, False, False))
for n in range(5):
    outbox.add(Waiting("usage", f"usage-{n}", "{}"), 10)
sys.exit(0)  # never closed: the interpreter's end still writes what's queued
"""


def test_what_is_queued_is_written_when_the_interpreter_ends(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite"
    subprocess.run(
        [sys.executable, "-c", QUITS_WITHOUT_CLOSING, str(path)],
        check=True,
        timeout=60,
    )
    again = SqliteOutbox(path)
    assert [w.id for w in again.waiting()] == [f"usage-{n}" for n in range(5)]
    choice = again.consent()
    assert choice is not None and choice.id == "a"
    again.close()


def test_the_consent_choice_is_saved_before_what_depends_on_it_is_sent(
    tmp_path: Path,
) -> None:
    """The first run: the choice and the first usage event return at once;
    a session that opens meanwhile waits for both, and sends the consent
    first - with the choice already in the file."""
    gate = threading.Event()

    class Held(SqliteOutbox):
        def save_consent(self, choice: ConsentChoice) -> None:
            gate.wait(5)  # the disk is busy
            super().save_consent(choice)

    path = tmp_path / "outbox.sqlite"
    store: list[Held] = []

    def open_held() -> Held:
        store.append(Held(path))
        return store[0]

    outbox = BackgroundOutbox(open_held)
    exchange = DataExchange(outbox, outbox, Heard(), "cedict")
    start = time.perf_counter()
    exchange.choose_consent(usage=True, crashes=False, exposures=False)
    assert exchange.usage("app_installed", {"channel": "alpha"}, AT)
    assert time.perf_counter() - start < 0.05  # neither waited for the disk

    sent: list[list[str]] = []
    session = threading.Thread(
        target=lambda: sent.append(exchange.opened(INSTALL, protocol.Limits()))
    )
    session.start()
    session.join(0.2)
    assert session.is_alive()  # waiting for the consent's write
    gate.set()
    session.join(5)
    kinds = [json.loads(message)["type"] for message in sent[0]]
    assert kinds[:2] == ["consent", "usage"]
    assert store[0].consent() is not None  # saved before either went
    outbox.close()


def test_a_failed_write_is_logged_and_the_next_goes_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class Failing(SqliteOutbox):
        def save_note(self, key: str, value: str | None) -> None:
            raise OSError("disk full")

    outbox = BackgroundOutbox(lambda: Failing(tmp_path / "outbox.sqlite"))
    with caplog.at_level(logging.ERROR):
        outbox.save_note("cursor", "50")
        outbox.add(item("learning", 0), keep=10)
        outbox.flush()
    assert "an outbox write failed" in caplog.text
    assert [w.id for w in outbox.waiting()] == ["learning-0"]
    outbox.close()


def test_a_write_after_closing_is_logged_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    outbox = BackgroundOutbox(lambda: SqliteOutbox(tmp_path / "outbox.sqlite"))
    outbox.close()
    with caplog.at_level(logging.WARNING):
        outbox.add(item("usage", 0), keep=10)  # a session's last, say
    assert "an outbox write came after it closed" in caplog.text
    outbox.close()  # twice is fine


@pytest.fixture(scope="module")
def qapp() -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    yield app


def test_the_interface_thread_never_waits_on_the_outbox(
    qapp: QApplication, tmp_path: Path
) -> None:
    """The watchdog (50 ms) over the interface thread's outbox work on a
    first run with a busy disk: the consent choice, a word saved, a usage
    event - none of it is a slow stretch."""
    outbox = BackgroundOutbox(lambda: SlowOutbox(tmp_path / "outbox.sqlite"))
    exchange = DataExchange(outbox, outbox, Heard(), "cedict")
    reported: list[tuple[float, str]] = []
    dog = Watchdog(report=lambda ms, where: reported.append((ms, where)))
    saved: LearningEvent = WordSaved(WORD, AT)

    def first_run() -> None:
        exchange.choose_consent(usage=True, crashes=False, exposures=False)
        exchange.learning(saved)
        exchange.usage("app_installed", {"channel": "alpha"}, AT)

    dog.start()
    try:
        QTimer.singleShot(10, first_run)
        loop = QEventLoop()
        QTimer.singleShot(1000, loop.quit)  # well after the slowest it could be
        loop.exec()
    finally:
        dog.stop()
    assert reported == []
    assert [w.kind for w in outbox.waiting()] == ["consent", "learning", "usage"]
    outbox.close()
