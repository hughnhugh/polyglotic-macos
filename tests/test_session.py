"""The listening session (connection.session) against a stand-in server.

A real WebSocket on 127.0.0.1 (tests/fake_server.py), protocol.md's
exchange step by step: hello and welcome, settings before speech, speech
frames out and caption updates in, ping and pong, the pace hint, the
refusals, the dead-connection rule and reconnecting. Timings are
shortened and the backoff's jitter is fixed so the tests run in seconds.
"""

import asyncio
import dataclasses
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, Self

import pytest
from tests.fake_server import (
    Behaviour,
    FakeServer,
    caption_for,
    refuse,
    wait_until,
    welcome_message,
    welcome_then_silence,
)
from tests.fakes import MemoryCredentialStore
from tests.test_protocol import example
from websockets.asyncio.server import ServerConnection

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.reconnect import Reconnects, StopReason
from polyglotic_desktop.connection.session import (
    ListeningSession,
    SessionState,
    Status,
    Timings,
    session_url,
)
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.maintenance import Maintenance
from polyglotic_desktop.core.listening.recheck import (
    RecheckOutcome,
    RecheckRequest,
    RecheckResult,
)
from polyglotic_desktop.core.listening.settings import ListeningSettings
from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionId,
    Decision,
    SpeechKind,
    TranscriptionRequest,
    WithdrawalReason,
    WithdrawCaption,
)
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.shared.client import USER_AGENT
from polyglotic_desktop.ports.capture import SourceCategory
from polyglotic_desktop.ports.credentials import DeviceCredentials

TOKEN = "pgd_TEST0TOKEN0" + "y" * 29
INSTALL = "3c5e7a9b-1d2f-4e6a-8b0c-2d4f6a8c0e1f"
APP = Source(SourceId("app"), SourceCategory.VIDEO)
SIGNED_IN = DeviceCredentials(INSTALL, TOKEN)
SETTINGS = ListeningSettings(targets=(Language("zh"),), spelling_hints=("Wang Fang",))


class Listener:
    def __init__(self) -> None:
        self.statuses: list[Status] = []
        self.captions: list[CaptionUpdate] = []
        self.paces: list[float | None] = []
        self.minutes: list[tuple[float, float | None]] = []
        self.notices: list[str] = []
        self.rechecks: list[RecheckResult] = []
        self.plans: list[protocol.PlanState] = []
        self.windows: list[Maintenance | None] = []
        self.failed = 0
        self.stalls: list[bool] = []

    def status_changed(self, status: Status) -> None:
        self.statuses.append(status)

    def caption_updated(self, update: CaptionUpdate) -> None:
        self.captions.append(update)

    def pace_changed(self, live_interval_min: float | None) -> None:
        self.paces.append(live_interval_min)

    def minutes_changed(self, used: float, left: float | None) -> None:
        self.minutes.append((used, left))

    def notice(self, code: str) -> None:
        self.notices.append(code)

    def caption_failed(self) -> None:
        self.failed += 1

    def connection_stalled(self, stalled: bool) -> None:
        self.stalls.append(stalled)

    def rechecked(self, result: RecheckResult) -> None:
        self.rechecks.append(result)

    def plan_changed(self, plan: protocol.PlanState) -> None:
        self.plans.append(plan)

    def maintenance_changed(self, window: Maintenance | None) -> None:
        self.windows.append(window)

    def states(self) -> list[SessionState]:
        return [s.state for s in self.statuses]

    def listening(self, times: int = 1) -> bool:
        return self.states().count(SessionState.LISTENING) >= times

    def last(self) -> Status:
        return self.statuses[-1]


class Speech:
    """A speech source like the pipeline's: decisions waiting to be taken."""

    def __init__(self) -> None:
        self.waiting: list[tuple[Decision, bytes | None]] = []
        self._lock = threading.Lock()

    def put(self, decision: Decision, audio: bytes | None) -> None:
        with self._lock:
            self.waiting.append((decision, audio))

    def take(self) -> tuple[Decision, bytes | None] | None:
        with self._lock:
            return self.waiting.pop(0) if self.waiting else None


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


class Harness:
    def __init__(
        self,
        server: FakeServer,
        credentials: DeviceCredentials | None = SIGNED_IN,
        timings: Timings | None = None,
        jitter: float = 0.0,
        url: str | None = None,
    ) -> None:
        self.store = MemoryCredentialStore(credentials)
        self.listener = Listener()
        self.speech = Speech()
        self.session = ListeningSession(
            url or server.url,
            self.store,
            AppInfo("0.1.0", "windows-11"),
            SETTINGS,
            self.speech.take,
            self.listener,
            timings=timings or Timings(answer_within=2, close_within=1),
            reconnects=Reconnects(random=lambda: jitter),
        )

    def __enter__(self) -> Self:
        self.session.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.session.stop()


def finished(caption: str, start: float = 10.0) -> TranscriptionRequest:
    return TranscriptionRequest(
        CaptionId(caption), SpeechKind.FINISHED, APP, start, start + 2.0
    )


def test_session_url() -> None:
    assert session_url("https://example.org/") == "wss://example.org/v1/session"
    assert session_url("http://127.0.0.1:8080") == "ws://127.0.0.1:8080/v1/session"
    assert session_url("http://localhost:8080") == "ws://localhost:8080/v1/session"
    assert session_url("http://[::1]:8080") == "ws://[::1]:8080/v1/session"
    with pytest.raises(ValueError):
        session_url("example.org")


def test_plain_ws_only_to_this_pc() -> None:
    """`hello` carries the device token: never in the clear to another machine."""
    for address in (
        "http://example.org",
        "ws://example.org:8080/",
        "http://192.168.1.20:8080",
        "http://10.0.0.5",
    ):
        with pytest.raises(ValueError, match="https://"):
            session_url(address)


def test_hello_welcome_settings_then_speech_and_captions(server: FakeServer) -> None:
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS one")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
    (hello,) = server.hellos
    assert hello.keys() == example("hello").keys()
    assert hello["auth"] == {"device_token": TOKEN}
    assert (hello["install_id"], hello["protocol"], hello["purpose"]) == (
        INSTALL,
        1,
        "listen",
    )
    assert server.types()[:2] == ["settings", "speech"]
    assert server.messages[0]["targets"] == ["zh"]
    ((header, audio),) = server.speech
    assert (header.caption_id, header.kind, header.source.category) == (
        "c1",
        "finished",
        "video",
    )
    assert audio == b"OggS one"
    (caption,) = app.listener.captions
    assert caption.caption_id == "c1" and caption.kind is CaptionKind.FINISHED
    assert caption.clauses[0].translations[Language("zh")].startswith("[zh] ")
    assert app.listener.paces == [None]  # welcome's pace hint: none
    assert server.closes() == [1000]
    assert app.listener.last().stopped is StopReason.CLOSED


def test_the_session_names_the_app_in_its_handshake(server: FakeServer) -> None:
    """287: the listening session's websocket said "Python/3.12 websockets/17.4"
    while every other request said the app's name (#479) - through a front
    that refuses Python's names, as Cloudflare's Browser Integrity Check
    refused urllib's on 2026-11-11, sign-in would pass and listening fail."""
    with Harness(server) as app:
        wait_until(app.listener.listening)
    assert server.user_agents and set(server.user_agents) == {USER_AGENT}


def test_speech_waiting_before_the_session_opens_is_sent_once_it_does(
    server: FakeServer,
) -> None:
    app = Harness(server)
    app.speech.put(finished("early"), b"OggS")
    with app:
        wait_until(lambda: len(server.speech) == 1)
    assert server.types()[:2] == ["settings", "speech"]


def test_ping_every_limits_ping_seconds(server: FakeServer) -> None:
    server.welcome = welcome_message(limits={"ping_seconds": 1})
    with Harness(server) as app:
        wait_until(lambda: server.types().count("ping") >= 2, timeout=4)
        assert app.listener.states()[-1] is SessionState.LISTENING  # pong kept it alive


def test_the_account_welcome_names_goes_to_the_listener(server: FakeServer) -> None:
    server.welcome = welcome_message(account_id="4f6a8c0e-2d4f-4a6b-8c0e-1f2a3b4c5d6e")
    with Harness(server) as app:
        wait_until(app.listener.listening)
    listening = [s for s in app.listener.statuses if s.state is SessionState.LISTENING]
    assert listening[0].account_id == "4f6a8c0e-2d4f-4a6b-8c0e-1f2a3b4c5d6e"


def test_the_cohort_welcome_names_goes_to_the_listener(server: FakeServer) -> None:
    # polyglotic-hq 275: alpha testers get "Report a problem" with everything
    server.welcome = welcome_message(cohort="beta")
    with Harness(server) as app:
        wait_until(app.listener.listening)
    listening = [s for s in app.listener.statuses if s.state is SessionState.LISTENING]
    assert listening[0].cohort == "beta"


def test_pace_from_welcome_then_from_pace(server: FakeServer) -> None:
    server.welcome = welcome_message(live_interval_min=1.5)
    with Harness(server) as app:
        wait_until(app.listener.listening)
        server.send_to_all({"type": "pace", "live_interval_min": 3})
        server.send_to_all({"type": "pace", "live_interval_min": None})
        wait_until(lambda: len(app.listener.paces) == 3)
    assert app.listener.paces == [1.5, 3.0, None]


def test_minutes_notices_and_errors(server: FakeServer) -> None:
    with Harness(server) as app:
        wait_until(app.listener.listening)
        server.send_to_all(example("minutes"))
        server.send_to_all(example("notice"))
        server.send_to_all({"type": "notice", "code": "a_new_one"})
        server.send_to_all(example("error"))
        server.send_to_all({"type": "fireworks"})
        wait_until(lambda: len(app.listener.notices) == 2)
    assert app.listener.minutes == [(42.5, None)]
    assert app.listener.notices == ["translator_warming_up", "a_new_one"]


def test_the_plan_in_welcome_and_when_it_changes_reaches_the_listener(
    server: FakeServer,
) -> None:
    """polyglotic-hq 185 (178's protocol): `welcome.plan`, then a `plan`
    message whenever the plan record changes."""
    server.welcome = server.welcome | {"plan": example("welcome.plan")["plan"]}
    with Harness(server) as app:
        wait_until(lambda: len(app.listener.plans) == 1)
        server.send_to_all(example("plan.ending"))
        wait_until(lambda: len(app.listener.plans) == 2)
    first, then = app.listener.plans
    assert (first.source, first.until) == ("cohort", None)
    assert (then.status, then.until) == ("ending", "2027-12-03T13:00:00.000Z")


def test_the_listening_status_names_the_tier_the_session_holds(
    server: FakeServer,
) -> None:
    """polyglotic-hq 237: the session keeps its `welcome`'s tier until it
    ends, whatever a `plan` says meanwhile (protocol.md) - so its status
    says which, for the plan line."""
    server.welcome = server.welcome | {"plan": example("welcome.plan")["plan"]}
    with Harness(server) as app:
        wait_until(app.listener.listening)
    listening = [s for s in app.listener.statuses if s.state is SessionState.LISTENING]
    assert listening[0].tier == "plus"


def test_settings_changed_before_the_session_starts_are_the_ones_sent(
    server: FakeServer,
) -> None:
    app = Harness(server)
    app.session.change_settings(ListeningSettings(targets=(Language("en"),)))
    with app:
        wait_until(lambda: server.types().count("settings") == 1)
    assert server.messages[-1]["targets"] == ["en"]


def test_changed_settings_are_sent(server: FakeServer) -> None:
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.session.change_settings(ListeningSettings(targets=(Language("en"),)))
        wait_until(lambda: server.types().count("settings") == 2)
    assert server.messages[-1]["targets"] == ["en"]


def test_each_sources_languages_on_its_speech_and_all_of_them_in_settings(
    server: FakeServer,
) -> None:
    """The server's decision 0033: a source's own languages go on its speech
    when they aren't the session's; `settings.targets` carries every
    source's, up to welcome's limit, for servers that don't know them."""
    server.welcome = welcome_message(limits={"targets": 1})
    mic = Source(SourceId("mic"), SourceCategory.MIC)
    app = Harness(server)
    app.session.change_settings(
        ListeningSettings(
            targets=(Language("zh"),),
            source_targets={mic.id: (), SourceId("other"): (Language("ja"),)},
        )
    )
    with app:
        app.speech.put(finished("c1"), b"OggS one")  # no languages of its own
        mine = TranscriptionRequest(CaptionId("c2"), SpeechKind.FINISHED, mic, 20, 22)
        app.speech.put(mine, b"OggS two")  # Original only
        app.session.speech_ready()
        wait_until(lambda: len(server.speech) == 2)
    assert server.of_type("settings")[0]["targets"] == ["zh"]  # ja: over the limit
    sent = {header.caption_id: header.source.targets for header, _ in server.speech}
    assert sent == {"c1": None, "c2": ()}


def test_a_dead_connection_is_closed_and_opened_again(server: FakeServer) -> None:
    server.script = [welcome_then_silence]
    timings = Timings(dead_after=1.0, answer_within=2, close_within=0.5)
    with Harness(server, timings=timings) as app:
        wait_until(lambda: app.listener.listening(2), timeout=6)
    assert server.connections == 2
    waiting = [s for s in app.listener.statuses if s.state is SessionState.WAITING]
    assert waiting[0].close_code == 1006


def test_a_restarting_server_is_rejoined_after_a_second(server: FakeServer) -> None:
    with Harness(server) as app:
        wait_until(app.listener.listening)
        server.send_to_all(example("notice.server_restarting"))
        server.close_all(1001)
        wait_until(lambda: app.listener.listening(2), timeout=5)
    waiting = [s for s in app.listener.statuses if s.state is SessionState.WAITING]
    assert waiting == [
        Status(
            SessionState.WAITING,
            retry_in=1.0,
            close_code=1001,
            unreachable=Unreachable.RESTARTING,  # said as one (polyglotic-hq 251)
        )
    ]
    assert "server_restarting" in app.listener.notices
    assert server.types().count("settings") == 2  # sent again on the new session


def test_update_required_stops(server: FakeServer) -> None:
    server.script = [refuse(example("update_required"), 4001)]
    with Harness(server) as app:
        wait_until(lambda: app.listener.last().state is SessionState.STOPPED)
        assert app.listener.last().stopped is StopReason.UPDATE_REQUIRED
    assert server.connections == 1 and app.store.saved is not None


def test_plus_ended_at_hello_stops_and_shows_the_plan(server: FakeServer) -> None:
    """polyglotic-hq 193 and 185: `limit_reached` in place of `welcome`, then
    4009. Before, the app read it as no answer and kept trying to connect."""
    server.script = [refuse(example("limit_reached"), 4009)]
    with Harness(server) as app:
        wait_until(lambda: app.listener.last().state is SessionState.STOPPED)
        assert app.listener.last().stopped is StopReason.LIMIT_REACHED
    assert server.connections == 1
    [plan] = app.listener.plans
    assert (plan.tier, plan.status) == ("free", "ended")


def test_update_required_asks_again_and_listens_once_the_version_is_taken(
    server: FakeServer,
) -> None:
    """polyglotic-hq 133: refused for its version with nothing to update
    to, the app stayed stopped until restarted - even once the server took
    its version again. It asks again now (every 5 minutes; 0.3 s here)."""
    server.script = [
        refuse(example("update_required"), 4001),
        refuse(example("update_required"), 4001),
    ]
    timings = Timings(answer_within=2, close_within=0.5, update_retry=0.3)
    with Harness(server, timings=timings) as app:
        wait_until(app.listener.listening, timeout=5)
    stopped = [s.stopped for s in app.listener.statuses if s.stopped is not None]
    assert stopped[:2] == [StopReason.UPDATE_REQUIRED] * 2  # each: the updater
    assert StopReason.UPDATE_REQUIRED not in stopped[2:]  # then the harness's stop
    assert server.connections == 3 and app.store.saved is not None


def test_plus_ended_asks_again_and_listens_once_the_account_has_plus(
    server: FakeServer,
) -> None:
    """polyglotic-hq 203: closed 4009 (Plus ended), the session stopped and
    never connected again - a renewal or a code redeemed on the site never
    reached the app, though Help and Home say captions "start again by
    themselves". It asks again now (every 5 minutes; 0.3 s here)."""
    timings = Timings(answer_within=2, close_within=0.5, update_retry=0.3)
    with Harness(server, timings=timings) as app:
        wait_until(app.listener.listening)
        server.close_all(4009)
        wait_until(lambda: app.listener.last().stopped is StopReason.LIMIT_REACHED)
        wait_until(lambda: app.listener.listening(2), timeout=5)
    assert server.connections == 2


def test_listening_moved_stops_without_reconnecting(server: FakeServer) -> None:
    # Close 4011: the account listens on another device now (project 095).
    with Harness(server) as app:
        wait_until(app.listener.listening)
        server.close_all(4011)
        wait_until(lambda: app.listener.last().state is SessionState.STOPPED)
        time.sleep(1.5)  # a reconnect would show within the first backoff
    assert app.listener.last() == Status(
        SessionState.STOPPED, stopped=StopReason.LISTENING_MOVED, close_code=4011
    )
    assert server.connections == 1 and app.store.saved is not None


def test_a_refused_token_is_forgotten_and_the_app_stops(server: FakeServer) -> None:
    server.script = [refuse(example("auth_failed"), 4003)]
    with Harness(server) as app:
        wait_until(lambda: app.listener.last().state is SessionState.STOPPED)
    assert app.listener.last() == Status(
        SessionState.STOPPED, stopped=StopReason.SIGN_IN_NEEDED, close_code=4003
    )
    assert app.store.saved is None and server.connections == 1
    # the install id stays: the same code signs this PC in again (288)
    assert app.store.install_id() == SIGNED_IN.install_id


def test_server_busy_waits_retry_after_then_listens(server: FakeServer) -> None:
    server.script = [refuse({"type": "server_busy", "retry_after": 1}, 4013)]
    with Harness(server, jitter=0.2) as app:
        wait_until(lambda: app.listener.listening(), timeout=5)
    (waiting,) = [s for s in app.listener.statuses if s.state is SessionState.WAITING]
    assert waiting.retry_in == pytest.approx(1.1) and waiting.close_code == 4013
    assert waiting.server_busy  # the server's, not the learner's connection (208)


def test_not_signed_in(server: FakeServer) -> None:
    with Harness(server, credentials=None) as app:
        wait_until(lambda: bool(app.listener.statuses))
    assert app.listener.last().stopped is StopReason.SIGN_IN_NEEDED
    assert server.connections == 0


def test_no_server_backs_off_and_stop_still_works(server: FakeServer) -> None:
    with Harness(server, url="http://127.0.0.1:9", jitter=1.0) as app:
        wait_until(lambda: SessionState.WAITING in app.listener.states(), timeout=5)
    waiting = [s for s in app.listener.statuses if s.state is SessionState.WAITING]
    first = waiting[0]
    assert (first.retry_in, first.close_code) == (1.0, None)
    # refused - or no answer, when Windows takes longer than the open timeout
    # to say it's refused (about 2 s here) - polyglotic-hq 251
    assert first.unreachable in (Unreachable.DOWN, Unreachable.NO_ANSWER)
    assert app.listener.last().state is SessionState.STOPPED


def test_nothing_secret_or_said_is_logged(
    server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    server.script = [welcome_then_silence]
    timings = Timings(dead_after=0.5, answer_within=2, close_within=0.5)
    with Harness(server, timings=timings) as app:
        wait_until(lambda: app.listener.listening(2), timeout=5)
        app.speech.put(finished("c1"), b"OggS secret audio")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
    assert "listening" in caplog.text  # it does log, just not content
    for secret in (TOKEN, "Stand-in caption", "Wang Fang", "secret audio"):
        assert secret not in caplog.text


async def _drop_after_speech(server: FakeServer, websocket: ServerConnection) -> None:
    """`welcome`, then read until the first speech frame and drop the
    connection without answering it."""
    await websocket.send(json.dumps(server.welcome))
    async for data in websocket:
        if isinstance(server.record(data), protocol.SpeechHeader):
            await websocket.close(1011)
            return


def test_finished_speech_unanswered_when_the_line_drops_is_sent_again(
    server: FakeServer,
) -> None:
    server.script = [_drop_after_speech]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1, timeout=5)
    assert [h.caption_id for h, _ in server.speech] == ["c1", "c1"]
    assert server.speech[1][1] == b"OggS finished"
    assert server.types()[2] == "settings"  # the new session's settings first
    assert app.listener.captions[0].caption_id == "c1"
    assert len(app.session.unanswered) == 0


def test_answered_speech_isnt_sent_again(server: FakeServer) -> None:
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
        server.close_all(1001)
        wait_until(lambda: app.listener.listening(2), timeout=5)
        wait_until(lambda: server.types().count("settings") == 2)
    assert [h.caption_id for h, _ in server.speech] == ["c1"]


def live(caption: str, start: float = 10.0) -> TranscriptionRequest:
    return TranscriptionRequest(
        CaptionId(caption), SpeechKind.LIVE, APP, start, start + 1.0, section=0
    )


def record_closes_late(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake server's record of each close made 0.2 s late, as a busy
    runner's thread can make it (229): after the app's `stop()` returned."""
    real = ServerConnection.wait_closed

    async def late(self: ServerConnection) -> None:
        await real(self)
        await asyncio.sleep(0.2)

    monkeypatch.setattr(ServerConnection, "wait_closed", late)


@pytest.mark.parametrize("record", ["at once", "late"])
def test_stopping_sends_finished_speech_still_waiting_and_awaits_it(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch, record: str
) -> None:
    """Project 031: stop() closed at once, and the last finished caption
    waiting in the pipeline was never sent. The close is read when the
    server has recorded it, which can be after stop() returns (229: on a
    busy runner this read `[]`); "late" makes it so every time."""
    if record == "late":
        record_closes_late(monkeypatch)
    app = Harness(server)
    with app:
        wait_until(app.listener.listening)
        app.speech.put(live("last"), b"OggS live")  # not woken: still waiting
        app.speech.put(finished("last"), b"OggS finished")
    # What stop() owes is the finished speech, sent last. A busy runner can
    # wake the sender between the two puts, so the live update may go first
    # (2026-11-08, main cb8a6ff: [('last', 'live'), ('last', 'finished')]),
    # which is how a live update is meant to behave.
    sent = [(h.caption_id, h.kind) for h, _ in server.speech]
    assert sent in ([("last", "finished")], [("last", "live"), ("last", "finished")])
    # and the app shows what it was answered: the live caption too, if it went
    # (#363's first run: ['last', 'last']), the finished one last
    shown = [(c.caption_id, c.kind) for c in app.listener.captions]
    assert shown in ([("last", "finished")], [("last", "live"), ("last", "finished")])
    assert len(app.session.unanswered) == 0 and server.closes() == [1000]


def test_stopping_waits_for_answers_only_a_little(server: FakeServer) -> None:
    server.script = [welcome_then_silence]
    timings = Timings(answer_within=2, close_within=0.5, drain_within=0.5)
    app = Harness(server, timings=timings)
    app.session.start()
    wait_until(app.listener.listening)
    app.speech.put(finished("unanswered"), b"OggS")
    started = time.monotonic()
    app.session.stop()
    assert time.monotonic() - started < 2.0
    assert [h.caption_id for h, _ in server.speech] == ["unanswered"]
    assert app.listener.last().stopped is StopReason.CLOSED


# -- an error naming a caption: its finished speech's answer, or a live update's
# (project 127: under server decision 0036 live updates are refused first)

Answer = Callable[[protocol.SpeechHeader], list[dict[str, Any]]]


def answering(answer: Answer, close_after_finished: int | None = None) -> Behaviour:
    """`welcome`, then each speech frame answered with `answer(header)`;
    with `close_after_finished`, the connection closed with that code once
    the first finished speech is answered."""

    async def behaviour(server: FakeServer, websocket: ServerConnection) -> None:
        await websocket.send(json.dumps(server.welcome))
        async for data in websocket:
            received = server.record(data)
            if not isinstance(received, protocol.SpeechHeader):
                for reply in server.answers(received):
                    await websocket.send(json.dumps(reply))
                continue
            for reply in answer(received):
                await websocket.send(json.dumps(reply))
            if close_after_finished is not None and received.kind == "finished":
                await websocket.close(close_after_finished)
                return

    return behaviour


def error_for(
    header: protocol.SpeechHeader, code: str = "speech_limit_reached"
) -> dict[str, Any]:
    return {
        "type": "error",
        "code": code,
        "fatal": False,
        "caption_id": header.caption_id,
        "retry_after": 2,
    }


@pytest.mark.parametrize(
    "code", ["speech_limit_reached", "speech_not_decodable", "a_new_code"]
)
def test_a_live_updates_error_after_its_finished_speech_went_doesnt_answer_it(
    server: FakeServer, code: str
) -> None:
    """A live update's refusal arriving once its caption's finished speech
    is on its way isn't that caption's answer: the finished caption that
    follows counts as captioned, not dropped."""

    def answer(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        if header.kind == "live":
            return []
        return [error_for(header, code), caption_for(header)]

    server.script = [answering(answer)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(live("c1"), b"OggS live")
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
        assert len(app.session.unanswered) == 0
    ended = app.session.ended()
    assert ended is not None
    assert (ended.captions, ended.dropped) == (1, 0)
    assert ended.speech_minutes == round(2 / 60, 2)


def test_a_live_updates_error_before_its_finished_speech_went_changes_nothing(
    server: FakeServer,
) -> None:
    def answer(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        if header.kind == "live":  # refused; then a notice, to know it's heard
            return [error_for(header), example("notice")]
        return [caption_for(header)]

    server.script = [answering(answer)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(live("c1"), b"OggS live")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.notices) == 1)
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
    ended = app.session.ended()
    assert ended is not None
    assert (ended.captions, ended.dropped) == (1, 0)


def test_refused_live_updates_are_told_once_and_logged_once_not_each(
    server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    """polyglotic-hq 300: three apps in Live updates had 75 live updates
    refused in two minutes - a WARNING each, and the learner told nothing."""

    def answer(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        if header.kind == "live":
            return [error_for(header) | {"kind": "live"}]
        return [caption_for(header)]

    server.script = [answering(answer)]
    caplog.set_level(logging.INFO)
    with Harness(server) as app:
        wait_until(app.listener.listening)
        for n in range(12):
            app.speech.put(live(f"c{n}"), b"OggS live")
            app.session.speech_ready()
        wait_until(lambda: app.listener.notices == ["live_updates_held_back"])
        app.speech.put(finished("last"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1)
    assert app.listener.notices == ["live_updates_held_back"]  # once, not 12 times
    assert app.session.ended() is not None
    lines = [r for r in caplog.records if "speech limit" in r.getMessage()]
    # the first refusal at once, and what was left as the session ended
    assert [r.levelno for r in lines] == [logging.WARNING, logging.WARNING]
    assert "refused 1 " in lines[0].getMessage()
    assert "refused 11 " in lines[1].getMessage()
    assert not [r for r in caplog.records if "the server: error" in r.getMessage()]


def test_live_updates_that_waited_their_turn_are_told_too(server: FakeServer) -> None:
    server.script = [answering(lambda header: [caption_for(header)])]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        for n in range(8):
            held = dataclasses.replace(live(f"c{n}"), held=True)
            app.speech.put(held, b"OggS live")
            app.session.speech_ready()
        wait_until(lambda: app.listener.notices == ["live_updates_held_back"])
        wait_until(lambda: len(server.speech) == 8)  # the notice comes as they're sent
    # nothing about it goes to the server: the header is as any live update's
    assert len(server.speech) == 8
    assert all("held" not in h.model_dump() for h, _ in server.speech)


def test_finished_speech_with_a_live_updates_error_is_sent_again_after_a_reconnect(
    server: FakeServer,
) -> None:
    def refused(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        return [error_for(header)] if header.kind == "finished" else []

    server.script = [answering(refused, close_after_finished=1011)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(live("c1"), b"OggS live")
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1, timeout=5)
    sent = [(h.caption_id, h.kind) for h, _ in server.speech]
    assert sent == [("c1", "live"), ("c1", "finished"), ("c1", "finished")]
    assert server.speech[2][1] == b"OggS finished"
    assert len(app.session.unanswered) == 0
    assert app.listener.failed == 0  # a refusal isn't a caption failed there
    ended = app.session.ended()
    assert ended is not None
    assert (ended.captions, ended.dropped, ended.reconnects) == (1, 0, 1)


async def _hold_finished_speech(
    server: FakeServer, websocket: ServerConnection
) -> None:
    """`welcome`, then pongs, but finished speech goes unanswered until the
    app sends a ping after it - the line stalled, then flowed again."""
    await websocket.send(json.dumps(server.welcome))
    held: list[protocol.SpeechHeader] = []
    async for data in websocket:
        message = server.record(data)
        if isinstance(message, protocol.SpeechHeader):
            held.append(message)
        elif isinstance(message, dict) and message.get("type") == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            for header in held:
                await websocket.send(json.dumps(caption_for(header)))
            held.clear()


def test_finished_speech_unanswered_too_long_is_a_stall_until_answered(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 165: a 30-second outage never closed the connection -
    "Listening" the whole time. The session says it stalled, and when it's over."""
    from polyglotic_desktop.core.listening import unstable

    monkeypatch.setattr(unstable, "STALL_SEC", 0.5)
    server.script = [_hold_finished_speech]
    timings = Timings(answer_within=2, close_within=1, ping_every=2.0)
    with Harness(server, timings=timings) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: app.listener.stalls == [True], timeout=3)
        wait_until(lambda: app.listener.stalls == [True, False], timeout=5)
        assert len(app.listener.captions) == 1


def test_a_caption_the_server_never_answers_doesnt_hold_the_stall_for_good(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The user's live testing, 2026-11-09 (polyglotic-hq 271): one finished
    caption lost on the server (dropped over the message rate) and
    "Connection unstable" never came off, on a local server answering
    everything after it. Later speech answered shows it was lost, not late."""
    from polyglotic_desktop.core.listening import unstable

    monkeypatch.setattr(unstable, "STALL_SEC", 0.5)

    def answer(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        return [] if header.caption_id == "lost" else [caption_for(header)]

    server.script = [answering(answer)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("lost"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: app.listener.stalls == [True], timeout=3)
        app.speech.put(finished("c2"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: app.listener.stalls == [True, False], timeout=3)
        assert len(app.session.unanswered) == 0
    ended = app.session.ended()
    assert ended is not None
    assert (ended.captions, ended.dropped) == (1, 1)


def test_finished_speech_the_server_says_it_refused_is_answered(
    server: FakeServer,
) -> None:
    """A server since 2026-11-11 says which speech an error refused
    (`kind`, its decision 0052): refused finished speech isn't waited for."""

    def refused(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        return [error_for(header) | {"kind": header.kind}, example("notice")]

    server.script = [answering(refused)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(live("c1"), b"OggS live")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.notices) == 1)
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.notices) == 2)
        assert len(app.session.unanswered) == 0
    ended = app.session.ended()
    assert ended is not None
    assert (ended.captions, ended.dropped) == (0, 1)


def test_a_withdrawn_captions_finished_speech_isnt_waited_for(
    server: FakeServer,
) -> None:
    def unanswered(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        return []

    server.script = [answering(unanswered)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.session.unanswered) == 1)
        app.speech.put(
            WithdrawCaption(CaptionId("c1"), APP, WithdrawalReason.MIC_BLEED), None
        )
        app.session.speech_ready()
        wait_until(lambda: len(app.session.unanswered) == 0)


def _answer_speech_after(hold: float, then_close: bool) -> Behaviour:
    """`welcome`; the first speech frame is answered after `hold` seconds -
    or the connection is closed then (1011), unanswered."""

    async def behaviour(server: FakeServer, websocket: ServerConnection) -> None:
        await websocket.send(json.dumps(server.welcome))
        async for data in websocket:
            message = server.record(data)
            if isinstance(message, protocol.SpeechHeader):
                await asyncio.sleep(hold)
                if then_close:
                    await websocket.close(1011)
                    return
                await websocket.send(json.dumps(caption_for(message)))
            elif isinstance(message, dict) and message.get("type") == "ping":
                await websocket.send(json.dumps({"type": "pong"}))

    return behaviour


def test_speech_sent_again_after_a_reconnect_isnt_a_stall_at_once(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unanswered speech keeps when it was first sent; on a new connection
    it waits from the connection's start, or the notice would come back the
    moment the line does (165's 30-second outage: on, off, on again). Here
    it waits 1.2 s on the first connection and 1.0 s on the second: never
    1.5 s on one."""
    from polyglotic_desktop.core.listening import unstable

    monkeypatch.setattr(unstable, "STALL_SEC", 1.5)
    server.script = [_answer_speech_after(1.2, True), _answer_speech_after(1.0, False)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: len(app.listener.captions) == 1, timeout=6)
        time.sleep(1.1)  # a watch tick after the answer
    assert True not in app.listener.stalls


def test_processing_failed_answers_the_finished_speech(server: FakeServer) -> None:
    """Sent only for finished speech: the caption failed - counted dropped,
    not sent again after a reconnect, and told to the listener."""

    def failed(header: protocol.SpeechHeader) -> list[dict[str, Any]]:
        return [error_for(header, "processing_failed")]

    server.script = [answering(failed, close_after_finished=1011)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS finished")
        app.session.speech_ready()
        wait_until(lambda: app.listener.listening(2), timeout=5)
        wait_until(lambda: server.types().count("settings") == 2)
    assert [(h.caption_id, h.kind) for h, _ in server.speech] == [("c1", "finished")]
    assert len(app.session.unanswered) == 0
    assert app.listener.failed == 1  # told: several in a row are said (145)
    ended = app.session.ended()
    assert ended is not None
    assert (ended.captions, ended.dropped) == (0, 1)


def test_the_channel_the_server_names_comes_with_the_listening_status(
    server: FakeServer,
) -> None:
    """`welcome.channel` is the update channel to follow (protocol.md); the
    session passes it on as it is - the updater ignores channels it doesn't
    know (decision 0017)."""
    server.welcome = welcome_message(channel="win-x64-beta")
    with Harness(server) as app:
        wait_until(app.listener.listening)
    listening = [s for s in app.listener.statuses if s.state is SessionState.LISTENING]
    assert [s.channel for s in listening] == ["win-x64-beta"]


# --- "Looks wrong?" (project 101) ------------------------------------------------


def test_a_recheck_goes_out_on_the_listening_session_and_its_answer_comes_back(
    server: FakeServer,
) -> None:
    request = RecheckRequest(
        CaptionId("c1"), APP, 10.0, 12.0, b"OggS held", None, (Language("en"),)
    )
    with Harness(server) as app:
        wait_until(app.listener.listening)
        assert app.session.recheck(request)
        wait_until(lambda: len(app.listener.rechecks) == 1)
    ((header, audio),) = server.rechecks
    assert (header.caption_id, header.targets, audio) == ("c1", ("en",), b"OggS held")
    assert server.speech == []  # not a caption's speech
    (result,) = app.listener.rechecks
    assert result.caption_id == "c1" and result.outcome is RecheckOutcome.CHECKED
    assert result.clauses[0].translations == {"en": "Let's go eat first."}
    assert app.listener.captions == []  # no caption update for it


def test_a_sync_session_or_one_not_started_sends_no_recheck(
    server: FakeServer,
) -> None:
    request = RecheckRequest(
        CaptionId("c1"), APP, 10.0, 12.0, b"OggS held", None, (Language("en"),)
    )
    harness = Harness(server)
    assert not harness.session.recheck(request)  # not started
    sync = ListeningSession(
        server.url,
        MemoryCredentialStore(SIGNED_IN),
        AppInfo("0.1.0", "windows-11"),
        SETTINGS,
        Speech().take,
        Listener(),
        purpose="sync",
    )
    assert not sync.recheck(request)


def test_a_reconnect_names_the_session_to_resume(server: FakeServer) -> None:
    """Server decision 0040: the first hello resumes nothing; after the line
    drops, the next names the session it had - the newest one each time."""
    a = "11111111-1111-4111-8111-111111111111"
    b = "22222222-2222-4222-8222-222222222222"

    def welcome_then_drop(session_id: str, resumed: bool) -> Behaviour:
        async def behaviour(server: FakeServer, websocket: ServerConnection) -> None:
            welcome = welcome_message(session_id=session_id, resumed=resumed)
            await websocket.send(json.dumps(welcome))
            await websocket.close(1011)

        return behaviour

    server.script = [welcome_then_drop(a, False), welcome_then_drop(b, True)]
    with Harness(server) as app:
        wait_until(lambda: app.listener.listening(3), timeout=8)
    assert "resume" not in server.hellos[0]
    assert server.hellos[1]["resume"] == a
    assert server.hellos[2]["resume"] == b


def test_a_sync_session_never_asks_to_resume(server: FakeServer) -> None:
    store = MemoryCredentialStore(SIGNED_IN)
    session = ListeningSession(
        server.url,
        store,
        AppInfo("0.1.0", "windows-11"),
        SETTINGS,
        lambda: None,
        Listener(),
        timings=Timings(answer_within=2, close_within=1, sync_within=0.5),
        purpose="sync",
    )
    session.start()
    wait_until(lambda: len(server.hellos) >= 1)
    session.stop()
    assert "resume" not in server.hellos[0]


def test_the_log_says_how_long_each_drop_kept_the_learner_away(
    server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    """302: a tester's log had a session end and resume about 140 times in
    two days, but not how long each session had lasted or how long the
    learner waited for captions - which the server's own log can't say."""
    caplog.set_level(logging.INFO)
    a = "11111111-1111-4111-8111-111111111111"

    async def welcome_then_drop(
        server: FakeServer, websocket: ServerConnection
    ) -> None:
        await websocket.send(json.dumps(welcome_message(session_id=a)))
        await websocket.close(1011)

    server.script = [welcome_then_drop, welcome_then_drop]
    with Harness(server) as app:
        wait_until(lambda: app.listener.listening(2), timeout=8)
    assert "session ended (close 1011, server_error) after 0s; trying again" in (
        caplog.text
    )
    assert re.search(
        r"session resumed: no, \d+\.\ds after the last one ended", caplog.text
    )


def test_the_log_says_how_long_a_failed_open_took(
    server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    """A reset at once and no answer for 10 s read alike (302)."""
    caplog.set_level(logging.INFO)
    with Harness(server, url="http://127.0.0.1:9", jitter=1.0) as app:
        wait_until(lambda: SessionState.WAITING in app.listener.states(), timeout=5)
    assert re.search(r"couldn't open a session after \d+\.\ds: \w+", caplog.text)
