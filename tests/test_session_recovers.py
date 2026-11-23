"""A listening session that fails in the app itself tries again (polyglotic-hq 557, decision 0266).

529's B2: network errors reconnected, but any other exception - in the
session's loops, in reading the credentials, in the learning-data exchange
reading back an outbox row - logged "the session failed" and stopped the
session for good: no captions until the learner changed sources or
restarted. Faults are injected into a real session against the stand-in
server (tests/fake_server.py); each test ends with captions flowing again.
"""

import logging
import threading
from collections.abc import Iterator

import pytest
from tests.fake_server import FakeServer, wait_until
from tests.fakes import MemoryCredentialStore
from tests.test_session import SIGNED_IN, Harness, Speech, finished

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection.exchange import LEARNING, DataExchange
from polyglotic_desktop.connection.reconnect import Ended, Reconnects, RetryIn
from polyglotic_desktop.connection.session import SessionState
from polyglotic_desktop.core.listening.timing import Decision
from polyglotic_desktop.ports.credentials import DeviceCredentials
from polyglotic_desktop.ports.outbox import Waiting


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


def _said(caplog: pytest.LogCaptureFixture) -> str:
    """The log's messages, as the log file has them (no exception text)."""
    return "\n".join(r.getMessage() for r in caplog.records)


class FailsOnce:
    """Raises a secret-looking error the first time it's called."""

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self) -> None:
        with self._lock:
            self.calls += 1
            first = self.calls == 1
        if first:
            raise RuntimeError("a caption's text, or a token")


def test_an_exception_in_the_sessions_loop_reconnects_and_captions_resume(
    server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    """The send loop takes speech from the pipeline; an error there - one
    nobody foresaw - ended the session (STOPPED, closed). Now it's logged by
    its type, the session waits a moment and opens again, and the speech
    still waiting goes out and is captioned."""
    caplog.set_level(logging.INFO, logger="polyglotic_desktop.connection.session")

    class Flaky(Speech):
        fails = FailsOnce()

        def take(self) -> tuple[Decision, bytes | None] | None:
            if self.waiting:
                self.fails()
            return super().take()

    app = Harness(server, speech=Flaky())
    with app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS one")
        app.session.speech_ready()
        wait_until(lambda: app.listener.listening(2))
        wait_until(lambda: len(app.listener.captions) == 1)
    states = app.listener.states()
    # listening, waiting after the failure - never stopped - listening again
    assert states[:4] == [
        SessionState.CONNECTING,
        SessionState.LISTENING,
        SessionState.WAITING,
        SessionState.CONNECTING,
    ]
    assert SessionState.STOPPED not in states[:-1]
    said = _said(caplog)
    assert "the session failed (1 in a row); trying again in 0.5s" in said
    assert "caption's text" not in said
    summary = app.session.ended()  # counted there too (566)
    assert summary is not None and summary.session_failures == 1
    assert summary.reconnects == 1  # the welcome after it


def test_credentials_that_fail_to_load_are_read_again(
    server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    """`credentials.load()` was outside every try: Windows' credential store
    failing once stopped listening for good. Now it's read again after a
    wait, and the session opens."""

    class Flaky(MemoryCredentialStore):
        def __init__(self) -> None:
            super().__init__(SIGNED_IN)
            self.fails = FailsOnce()

        def load(self) -> DeviceCredentials | None:
            self.fails()
            return super().load()

    caplog.set_level(logging.INFO, logger="polyglotic_desktop.connection.session")
    app = Harness(server, store=Flaky())
    with app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS one")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
    assert app.listener.states()[0] is SessionState.WAITING
    assert "reading the sign-in failed (1 in a row)" in _said(caplog)
    summary = app.session.ended()
    assert summary is not None and summary.session_failures == 1


def test_an_outbox_row_this_version_cant_read_is_dropped_and_captions_flow(
    server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    """529's plausible repeating trigger: one stored learning event this
    version can't read (another version wrote it), read back at every
    session's open, failed every session. It's dropped and counted; the rest
    goes out, and captions flow."""
    outbox = SqliteOutbox(":memory:")
    good = (
        '{"id": "00000000-0000-4000-8000-000000000001", "kind": "looked_up",'
        ' "entry_id": "cedict:y7p98nwvxq", "at": "2026-11-04T09:15:02.120Z"}'
    )
    outbox.add(Waiting(LEARNING, "bad", '{"kind": "a kind from the future"}'), 100)
    outbox.add(Waiting(LEARNING, "good", good), 100)
    exchange = DataExchange(outbox, outbox, _Heard(), "cedict")
    caplog.set_level(logging.INFO, logger="polyglotic_desktop.connection")
    app = Harness(server, exchange=exchange)
    with app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS one")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
        wait_until(lambda: not exchange.has_waiting())
    (learning,) = server.of_type("learning")
    assert [e["id"] for e in learning["events"]] == [
        "00000000-0000-4000-8000-000000000001"
    ]
    assert outbox.note("unreadable_dropped") == "1"
    assert SessionState.STOPPED not in app.listener.states()[:-1]
    assert "1 waiting learning item(s) this version can't read dropped (1 ever)" in (
        _said(caplog)
    )
    summary = app.session.ended()  # in the summary, not only the log (566)
    assert summary is not None and summary.unreadable_dropped == 1
    assert exchange.take_unreadable() == 0  # counted once


def test_a_failure_waits_half_to_all_of_a_doubling_ceiling_up_to_a_minute() -> None:
    """`Reconnects.after_failure`: 0.5-1 s, then 1-2, 2-4 ... at most 60 s;
    from the start again after a session that lasted a minute."""
    lowest = Reconnects(random=lambda: 0.0)
    highest = Reconnects(random=lambda: 0.999)
    assert [lowest.after_failure(0).seconds for _ in range(4)] == [0.5, 1, 2, 4]
    assert [round(highest.after_failure(0).seconds) for _ in range(8)] == [
        1,
        2,
        4,
        8,
        16,
        32,
        60,
        60,
    ]
    assert lowest.after_failure(lasted=60.0) == RetryIn(0.5)
    assert lowest.failures == 1
    lowest.after(Ended(1006, lasted=60.0))  # a good minute's session between
    assert lowest.after_failure(lasted=1.0) == RetryIn(0.5)


class _Heard:
    def learning_arrived(self, events: object) -> None:
        pass

    def learning_deleted(self) -> None:
        pass
