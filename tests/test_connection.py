"""The connection (connection.client) against a stand-in server: sync sessions and the outbox.

Real WebSockets on 127.0.0.1 (tests/fake_server.py): a sync session when
the app starts and when something waits with nobody listening; what waits
going out on the listening session while it's open; nothing lost while the
server can't be reached, and nothing sent twice once it can.
"""

import socket
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
from tests.fake_server import (
    FakeServer,
    replacing,
    wait_until,
    welcome_message,
    welcome_then_silence,
)
from tests.fakes import MemoryCredentialStore
from tests.test_session import SETTINGS, SIGNED_IN, Listener, Speech, finished

from polyglotic_desktop.adapters.sqlite_outbox import SqliteOutbox
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.client import Connection
from polyglotic_desktop.connection.exchange import DataExchange
from polyglotic_desktop.connection.milestones import Milestones
from polyglotic_desktop.connection.reconnect import StopReason
from polyglotic_desktop.connection.session import SessionState, Timings
from polyglotic_desktop.core.listening.sources import Capture, CaptureMode
from polyglotic_desktop.core.listening.summary import SessionAction
from polyglotic_desktop.core.listening.timing import LIVE_UPDATE_INTERVAL_SEC
from polyglotic_desktop.core.shared import (
    EntryId,
    LearningEvent,
    WordLookedUp,
    WordSaved,
    WordStatus,
    WordStatusChanged,
)
from polyglotic_desktop.ports.outbox import Waiting

AT = datetime(2026, 11, 4, 9, 15, 2, tzinfo=UTC)
WORD = EntryId("cedict:y7p98nwvxq")


class Heard:
    def __init__(self) -> None:
        self.arrived: list[LearningEvent] = []
        self.deleted = 0

    def learning_arrived(self, events: Sequence[LearningEvent]) -> None:
        self.arrived.extend(events)

    def learning_deleted(self) -> None:
        self.deleted += 1


class App:
    def __init__(self, url: str, outbox: SqliteOutbox | None = None) -> None:
        self.outbox = outbox or SqliteOutbox(":memory:")
        self.heard = Heard()
        self.exchange = DataExchange(self.outbox, self.outbox, self.heard, "cedict")
        self.listener = Listener()
        self.speech = Speech()
        self.restarts = 0  # the captures' restarts not yet taken (566)
        self.connection = Connection(
            url,
            MemoryCredentialStore(SIGNED_IN),
            AppInfo("0.1.0", "windows-11"),
            self.exchange,
            self.listener,
            timings=Timings(answer_within=2, close_within=1, sync_within=1.5),
            sync_delay=0.1,
            retry_waits=(0.3,),
            capture_restarts=self.take_restarts,
        )

    def take_restarts(self) -> int:
        taken, self.restarts = self.restarts, 0
        return taken


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


def test_a_sync_session_when_the_app_starts(server: FakeServer) -> None:
    app = App(server.url)
    app.exchange.choose_consent(usage=False, crashes=False, exposures=False)
    app.exchange.learning(WordSaved(WORD, AT))
    app.connection.start()
    wait_until(lambda: server.app_closes == [1000])
    assert server.hellos[0]["purpose"] == "sync"
    assert server.types() == ["consent", "learning", "learning_sync"]
    assert not app.exchange.has_waiting()
    assert server.connections == 1
    app.connection.close()


def test_whats_new_while_nobody_listens_goes_in_a_sync_session(
    server: FakeServer,
) -> None:
    app = App(server.url)
    app.connection.start()
    wait_until(lambda: server.app_closes == [1000])
    for _ in range(3):
        app.exchange.learning(WordLookedUp(WORD, AT))
    wait_until(lambda: len(server.app_closes) == 2)
    (learning,) = server.of_type("learning")  # one burst, one message
    assert len(learning["events"]) == 3
    app.connection.close()


def test_learning_from_the_server_reaches_the_app(server: FakeServer) -> None:
    server.learning_states = [
        {
            "type": "learning_state",
            "cursor": "12",
            "more": False,
            "statuses": [
                {"entry_id": WORD, "status": "known", "at": "2026-11-04T09:00:00Z"}
            ],
            "saved_words": [],
        }
    ]
    app = App(server.url)
    app.connection.start()
    wait_until(lambda: bool(app.heard.arrived))
    assert app.heard.arrived == [
        WordStatusChanged(WORD, WordStatus.KNOWN, datetime(2026, 11, 4, 9, tzinfo=UTC))
    ]
    app.connection.close()


def test_a_change_of_sources_doesnt_drop_the_captions_in_flight(
    server: FakeServer,
) -> None:
    """polyglotic-hq 277 (271's finding): a source removed and another
    added mid-speech leaves nothing chosen for a moment, so the app stops
    its listening session and opens another at once (`main.follow_choice`).
    The server closes the old one (1000) as the new one's `hello` arrives,
    and the old one's wait for its last answers ended then (64 ms in the
    user's log): its unanswered finished speech was lost. Now the new
    session sends it again - and every finished caption is answered and
    shown once."""
    server.script = [welcome_then_silence, replacing]  # the first never answers
    app = App(server.url)
    app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    session = app.connection.listening
    assert session is not None
    app.speech.put(finished("in-flight"), b"opus")
    session.speech_ready()
    wait_until(lambda: len(server.speech) == 1)  # sent; never answered there
    # the old source removed, then another added: nothing chosen for a moment
    app.connection.stop_listening()
    app.speech.put(finished("while-switching", start=13.0), b"opus")
    new = app.connection.start_listening(SETTINGS, app.speech.take)
    new.speech_ready()
    app.speech.put(finished("after", start=16.0), b"opus")
    new.speech_ready()

    def shown() -> list[str]:
        return [u.caption_id for u in app.listener.captions if u.kind == "finished"]

    wait_until(lambda: len(shown()) == 3)
    time.sleep(0.3)  # anything shown twice would have come by now
    assert sorted(shown()) == ["after", "in-flight", "while-switching"]
    assert server.closes(1) == [1000]  # the old session, closed by the server
    assert len(app.connection.listening.unanswered) == 0  # type: ignore[union-attr]
    app.connection.close()


def test_while_listening_everything_goes_on_the_listening_session(
    server: FakeServer,
) -> None:
    app = App(server.url)
    session = app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    app.exchange.learning(WordLookedUp(WORD, AT))
    wait_until(lambda: bool(server.of_type("learning")))
    assert server.connections == 1 and server.hellos[0]["purpose"] == "listen"
    assert server.types()[0] == "settings"
    app.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    app.connection.stop_listening()
    assert app.connection.listening is None  # at once; it closes on its own thread
    wait_until(lambda: not session._thread.is_alive())  # type: ignore[union-attr]
    wait_until(lambda: not app.exchange.has_waiting())
    app.connection.close()


def test_after_listening_moved_what_waits_goes_in_a_sync_session(
    server: FakeServer,
) -> None:
    """117 Low 2: close 4011 stops the listening session, which stays - Home
    offers "Listen here", and nothing else takes listening back - but a
    lookup or a save doesn't wait for the user: it goes in a sync session."""
    app = App(server.url)
    session = app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    server.close_all(4011)
    wait_until(lambda: app.listener.last().stopped is StopReason.LISTENING_MOVED)
    assert app.connection.listening is session  # kept until "Listen here"
    app.exchange.learning(WordSaved(WORD, AT))
    wait_until(lambda: not app.exchange.has_waiting())
    assert [h["purpose"] for h in server.hellos] == ["listen", "sync"]
    (learning,) = server.of_type("learning")
    assert [e["kind"] for e in learning["events"]] == ["saved"]
    assert app.connection.listening is session  # still: the sync didn't touch it
    # "Listen here": the stopped session goes and listening starts again
    app.connection.stop_listening()
    app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(lambda: app.listener.listening(times=2))
    assert server.hellos[-1]["purpose"] == "listen"
    app.connection.close()


def test_learning_sync_stays_available_after_the_listening_allowance_ends(
    server: FakeServer,
) -> None:
    app = App(server.url)
    app.connection.start_listening(SETTINGS, app.speech.take)
    try:
        wait_until(app.listener.listening)
        server.send_to_all({"type": "allowance_exhausted", "allowance_percent": 0})
        wait_until(
            lambda: app.listener.last().stopped is StopReason.ALLOWANCE_EXHAUSTED
        )
        app.exchange.learning(WordSaved(WORD, AT))
        wait_until(lambda: not app.exchange.has_waiting())
        assert [hello["purpose"] for hello in server.hellos] == ["listen", "sync"]
    finally:
        app.connection.close()


def test_nothing_lost_offline_and_nothing_sent_twice(tmp_path: object) -> None:
    with socket.socket() as probe:  # a free port, nobody listening on it yet
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    outbox = SqliteOutbox(":memory:")
    app = App(f"http://127.0.0.1:{port}", outbox)
    app.connection.start()
    app.exchange.learning(WordSaved(WORD, AT))
    app.exchange.learning(WordLookedUp(WORD, AT))
    wait_until(lambda: app.connection._failures >= 2, timeout=5)
    assert len(outbox.waiting()) == 2  # kept while offline
    server = FakeServer(port)
    try:
        wait_until(lambda: not app.exchange.has_waiting(), timeout=5)
        (learning,) = server.of_type("learning")
        assert [e["kind"] for e in learning["events"]] == ["saved", "looked_up"]
    finally:
        app.connection.close()
        server.stop()


def test_what_the_server_doesnt_answer_waits_for_the_next_session(
    server: FakeServer,
) -> None:
    server.script = [welcome_then_silence]
    app = App(server.url)
    app.exchange.learning(WordSaved(WORD, AT))
    app.connection.start()
    wait_until(lambda: len(server.app_closes) == 2, timeout=6)
    sent = server.of_type("learning")
    assert len(sent) == 2 and sent[0]["events"] == sent[1]["events"]
    assert not app.exchange.has_waiting()
    app.connection.close()


def test_a_session_on_another_account_sends_nothing_of_the_last_ones(
    server: FakeServer,
) -> None:
    """polyglotic-hq 208: an account can change without signing out (the
    server refusing the token, then a new invite code). What waited was the
    last account's, and none of it reaches the next."""
    server.welcome = welcome_message(account_id="4f6a8c0e-2d4f-4a6b-8c0e-1f2a3b4c5d6e")
    first = App(server.url)
    first.connection.start()
    wait_until(lambda: server.app_closes == [1000])
    first.connection.close()
    first.exchange.learning(WordSaved(WORD, AT))  # waits: no session open
    server.welcome = welcome_message(account_id="9b1d3f5a-7c9e-4b2d-8f0a-6c8e0a2c4e6f")
    again = App(server.url, first.outbox)
    again.connection.start()
    wait_until(lambda: len(server.app_closes) == 2)
    assert server.of_type("learning") == []
    assert not again.exchange.has_waiting()
    again.connection.close()


def test_not_signed_in_stops_syncing_until_signed_in(server: FakeServer) -> None:
    app = App(server.url)
    app.connection._credentials = MemoryCredentialStore(None)
    app.connection.start()
    wait_until(lambda: app.connection.sync_stopped is not None)
    assert server.connections == 0
    app.connection._credentials = MemoryCredentialStore(SIGNED_IN)
    app.connection.start()
    wait_until(lambda: server.app_closes == [1000])
    app.connection.close()


@pytest.mark.parametrize("usage", [True, False])
def test_a_listening_session_leaves_a_summary_only_with_consent(
    server: FakeServer, usage: bool
) -> None:
    app = App(server.url)
    app.exchange.choose_consent(usage=usage, crashes=False, exposures=False)
    session = app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    app.speech.put(finished("c1"), b"OggS")
    session.speech_ready()
    wait_until(lambda: len(app.listener.captions) == 1)
    app.connection.stop_listening()
    if not usage:  # nothing waits: no sync session, no summary
        wait_until(lambda: server.app_closes == [1000])
        time.sleep(0.5)
        assert server.connections == 1 and server.of_type("usage") == []
    else:
        wait_until(lambda: len(server.app_closes) == 2)  # a sync session after it
        assert [h["purpose"] for h in server.hellos] == ["listen", "sync"]
        sent = [e for m in server.of_type("usage") for e in m["events"]]
        (event,) = sent
        assert event["name"] == "listening_session_ended" and event["v"] == 1
        props = event["props"]
        assert (props["captions"], props["source_category"]) == (1, "video")
        assert props["speech_minutes"] == round(2 / 60, 2)
        assert props["dropped"] == 0 and props["reconnects"] == 0
        assert props["live_interval_seconds"] == LIVE_UPDATE_INTERVAL_SEC
        assert props["platform"] == "windows"  # content-free (051)
    app.connection.close()


def test_the_summary_carries_the_preset_in_use(server: FakeServer) -> None:
    """polyglotic-hq 556: the preset in use and what differs in it, as the
    summary's optional properties - sent with it, so only with consent."""
    app = App(server.url)
    app.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    preset = {"preset": "video", "preset_word_links": "arrows"}
    session = app.connection.start_listening(SETTINGS, app.speech.take, preset=preset)
    wait_until(app.listener.listening)
    app.speech.put(finished("c1"), b"OggS")
    session.speech_ready()
    wait_until(lambda: len(app.listener.captions) == 1)
    app.connection.stop_listening()
    wait_until(lambda: len(server.app_closes) == 2)  # a sync session after it
    (event,) = [e for m in server.of_type("usage") for e in m["events"]]
    assert event["name"] == "listening_session_ended" and event["v"] == 1
    assert event["props"]["preset"] == "video"
    assert event["props"]["preset_word_links"] == "arrows"
    app.connection.close()


def test_a_listening_session_with_nothing_captioned_leaves_a_summary_too(
    server: FakeServer,
) -> None:
    app = App(server.url)
    app.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    app.restarts = 2  # a capture failed twice, and started again (566)
    app.connection.stop_listening()

    def summaries() -> list[dict[str, Any]]:
        events = [e for m in server.of_type("usage") for e in m["events"]]
        return [e["props"] for e in events if e["name"] == "listening_session_ended"]

    wait_until(lambda: len(summaries()) == 1)  # before: none was sent
    (props,) = summaries()
    assert (props["captions"], props["source_category"]) == (0, "none")
    assert "delay_p50_ms" not in props and "delay_p95_ms" not in props
    recovered = ("capture_restarts", "session_failures", "unreadable_dropped")
    assert [props[name] for name in recovered] == [2, 0, 0]
    app.connection.close()


def test_lookups_and_saves_while_listening_are_counted_in_its_summary(
    server: FakeServer,
) -> None:
    """polyglotic-hq DECISIONS.md #20: counts per listening session, and no
    usage event per lookup or save. Before and after the session they're
    learning data only."""
    app = App(server.url)
    app.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    app.connection.learned(WordLookedUp(WORD, AT))  # nobody listening: not counted
    app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    for learned in (
        WordLookedUp(WORD, AT),
        WordLookedUp(WORD, AT),
        WordSaved(WORD, AT),
    ):
        app.exchange.learning(learned)
        app.connection.learned(learned)
    app.connection.learned(WordStatusChanged(WORD, WordStatus.KNOWN, AT))
    app.connection.stop_listening()

    def usage() -> list[dict[str, Any]]:
        return [e for m in server.of_type("usage") for e in m["events"]]

    wait_until(lambda: len(usage()) == 1)
    (event,) = usage()
    assert event["name"] == "listening_session_ended"
    assert (event["props"]["lookups"], event["props"]["saves"]) == (2, 1)
    app.connection.close()


def test_what_was_captured_and_the_first_caption_reach_the_server(
    server: FakeServer,
) -> None:
    """polyglotic-hq project 134: what is captured goes into the session's
    summary across a change; the joined window and a transcript opened are
    counted; the install's first caption is a milestone - all usage
    statistics, with consent."""
    app = App(server.url)
    app.exchange.choose_consent(usage=True, crashes=False, exposures=False)
    milestones = Milestones(app.outbox, app.exchange, AppInfo("0.1.0", "windows-11"))
    milestones.started(fresh=True)
    app.connection.milestones = milestones
    app.connection.captured(Capture(CaptureMode.APPS, 2, my_speech=False))
    app.connection.joined(True)
    session = app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    app.speech.put(finished("c1"), b"OggS")
    session.speech_ready()
    wait_until(lambda: len(app.listener.captions) == 1)
    time.sleep(0.2)  # long enough to show in tenths of a second
    app.connection.captured(Capture(CaptureMode.WHOLE_SYSTEM, 0, my_speech=False))
    app.connection.did(SessionAction.TRANSCRIPT_OPENED)
    app.connection.stop_listening()

    def usage() -> dict[str, dict[str, Any]]:
        events = [e for m in server.of_type("usage") for e in m["events"]]
        return {e["name"]: e["props"] for e in events}

    wait_until(lambda: "listening_session_ended" in usage())
    sent = usage()
    assert {"app_installed", "first_caption_shown"} <= set(sent)
    props = sent["listening_session_ended"]
    assert props["mode_switches"] == 1 and props["apps_max"] == 2
    assert props["apps_seconds"] > 0 and "whole_system_seconds" in props
    assert props["joined_window"] is True and props["transcripts_opened"] == 1
    app.connection.close()


def test_a_closing_sessions_stopped_doesnt_overwrite_its_successors_state(
    server: FakeServer,
) -> None:
    """The user's live testing, 2026-11-10 01:12 (polyglotic-hq 271): what's
    captured changed, so one listening session closed and the next opened.
    The old one waited for its last answer, and its "stopped" arrived after
    the new one's "listening": "Stopped - quit from the tray and start
    again" over working captions."""
    server.script = [welcome_then_silence]  # the first never answers speech
    app = App(server.url)
    app.connection._timings = Timings(answer_within=2, close_within=1, drain_within=1)
    old = app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    app.speech.put(finished("c1"), b"OggS finished")
    old.speech_ready()
    wait_until(lambda: len(server.speech) == 1)
    app.connection.stop_listening()  # it waits for c1's answer, a second
    app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(lambda: app.listener.listening(2))
    wait_until(lambda: not old._thread.is_alive(), timeout=5)  # type: ignore[union-attr]
    assert app.listener.states() == [
        SessionState.CONNECTING,
        SessionState.LISTENING,
        SessionState.CONNECTING,
        SessionState.LISTENING,
    ]
    app.connection.close()
    assert app.listener.last().state is SessionState.STOPPED  # the last one's own


def test_signing_out_while_listening_says_sign_in_is_needed(
    server: FakeServer,
) -> None:
    """The listening session's last word after a sign-out is "sign in", not
    "stopped" - Home shows Not signed in (polyglotic-hq project 062: it
    showed Stopped, which the help says to fix by restarting the app)."""
    app = App(server.url)
    app.connection._credentials = MemoryCredentialStore(SIGNED_IN)
    app.connection.start_listening(SETTINGS, app.speech.take)
    wait_until(app.listener.listening)
    app.connection.sign_out()
    last = app.listener.last()
    assert last.state is SessionState.STOPPED
    assert last.stopped is StopReason.SIGN_IN_NEEDED
    app.connection.close()


def test_signing_out_forgets_the_token_and_stops_syncing(server: FakeServer) -> None:
    app = App(server.url)
    store = MemoryCredentialStore(SIGNED_IN)
    app.connection._credentials = store
    app.connection.start()
    wait_until(lambda: server.app_closes == [1000])
    app.outbox.add(Waiting("learning", "made-offline", "{}"), keep=10)  # never sent
    app.connection.sign_out()
    assert store.saved is None
    assert not app.exchange.has_waiting()  # dropped: not the next account's
    app.exchange.learning(WordLookedUp(WORD, AT))  # kept for after signing in again
    time.sleep(0.4)
    assert server.connections == 1 and app.connection.idle
    assert app.exchange.has_waiting()
    app.connection.close()
