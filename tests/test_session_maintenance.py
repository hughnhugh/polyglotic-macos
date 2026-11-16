"""The session holds the planned maintenance window and waits through it (polyglotic-hq 319).

Against the tests' FakeServer: the window and the server's time in
`welcome` (as server decision 0066 sends them), a `maintenance` message
while the session is open, a refusal for it, the close at its start, and
the server gone while the window is on - and a server from before
2026-11-14 (v0.1.2's `welcome`, without either field).
"""

import asyncio
import json
import socket
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import pytest
from tests.fake_server import FakeServer, refuse, wait_until, welcome_message
from tests.fakes import MemoryCredentialStore
from tests.test_session import SETTINGS, SIGNED_IN, Listener, Speech
from websockets.asyncio.server import ServerConnection

from polyglotic_desktop.connection.app import AppInfo
from polyglotic_desktop.connection.reconnect import Reconnects
from polyglotic_desktop.connection.session import (
    ListeningSession,
    SessionState,
    Status,
    Timings,
)
from polyglotic_desktop.core.listening import maintenance as planned
from polyglotic_desktop.core.listening.maintenance import Maintenance, Phase
from polyglotic_desktop.core.listening.unreachable import Unreachable


def at(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class App:
    """A listening session holding `maintenance`, on a PC whose clock is `ahead`."""

    def __init__(
        self,
        url: str,
        maintenance: Maintenance | None = None,
        ahead: timedelta = timedelta(0),
        jitter: float = 0.0,
    ) -> None:
        self.listener = Listener()
        self.speech = Speech()
        self.clock: Callable[[], datetime] = lambda: datetime.now(UTC) + ahead
        self.session = ListeningSession(
            url,
            MemoryCredentialStore(SIGNED_IN),
            AppInfo("0.1.0", "windows-11"),
            SETTINGS,
            self.speech.take,
            self.listener,
            timings=Timings(answer_within=5, close_within=1),
            reconnects=Reconnects(random=lambda: jitter),
            maintenance=maintenance,
            wall_clock=self.clock,
        )

    def __enter__(self) -> Self:
        self.session.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.session.stop()

    def waiting(self, timeout: float = 10.0) -> Status:
        def found() -> bool:
            return any(s.state is SessionState.WAITING for s in self.listener.statuses)

        wait_until(found, timeout)
        return next(
            s for s in self.listener.statuses if s.state is SessionState.WAITING
        )


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


def window_in(
    starts: timedelta, lasts: timedelta = timedelta(minutes=30)
) -> dict[str, str]:
    return {"starts_at": at(now() + starts), "ends_at": at(now() + starts + lasts)}


def test_welcome_tells_the_window_placed_by_the_servers_time(
    server: FakeServer,
) -> None:
    """The PC's clock 3 hours fast: the window two hours off is still ahead,
    not on - the server's time in `welcome` places it."""
    server.welcome = welcome_message(
        server_time=at(datetime.now(UTC)), maintenance=window_in(timedelta(hours=2))
    )
    with App(server.url, ahead=timedelta(hours=3)) as app:
        wait_until(app.listener.listening)
        wait_until(lambda: bool(app.listener.windows))
        window = app.listener.windows[-1]
        assert window is not None
        assert abs(window.pc_ahead - timedelta(hours=3)) < timedelta(seconds=5)
        assert planned.phase(window, app.clock()) is Phase.AHEAD


def test_an_open_session_is_told_when_it_is_set_moved_and_cleared(
    server: FakeServer,
) -> None:
    first, moved = window_in(timedelta(hours=1)), window_in(timedelta(hours=2))

    async def told(server: FakeServer, websocket: ServerConnection) -> None:
        await websocket.send(json.dumps(server.welcome))
        for window in (first, moved, None):
            await asyncio.sleep(0.1)
            await websocket.send(json.dumps({"type": "maintenance", "window": window}))
        await server.serve(websocket)

    server.script = [told]
    server.welcome = welcome_message(server_time=at(datetime.now(UTC)))
    with App(server.url) as app:
        wait_until(lambda: len(app.listener.windows) == 3)
        set_, changed, cleared = app.listener.windows
        assert set_ is not None and at(set_.starts_at) == first["starts_at"]
        assert changed is not None and at(changed.starts_at) == moved["starts_at"]
        assert cleared is None
        assert app.listener.states().count(SessionState.LISTENING) == 1  # no reconnect


def test_a_refusal_for_maintenance_says_so_and_waits_its_time(
    server: FakeServer,
) -> None:
    until = at(now() + timedelta(minutes=20))
    busy = {
        "type": "server_busy",
        "retry_after": 120,
        "reason": "maintenance",
        "until": until,
    }
    server.script = [refuse(busy, 4013)]
    with App(server.url, jitter=0.5) as app:
        status = app.waiting()
        assert status.unreachable is Unreachable.MAINTENANCE
        assert not status.server_busy  # not "The server is busy"
        assert status.retry_in == 150.0  # 120 s, then half of the 60 s spread
        held = app.listener.windows[-1]
        assert held is not None and at(held.ends_at) == until  # until when, kept


def test_at_its_start_the_session_ends_and_waits_for_the_window(
    server: FakeServer,
) -> None:
    async def started(server: FakeServer, websocket: ServerConnection) -> None:
        await websocket.send(json.dumps(server.welcome))
        await asyncio.sleep(0.2)
        notice = {"type": "notice", "code": "maintenance_started"}
        await websocket.send(json.dumps(notice))
        await websocket.close(1001)

    server.script = [started]
    server.welcome = welcome_message(
        server_time=at(datetime.now(UTC)),
        maintenance=window_in(-timedelta(seconds=1), timedelta(minutes=10)),
    )
    with App(server.url) as app:
        status = app.waiting()
        assert status.close_code == 1001
        assert status.unreachable is Unreachable.MAINTENANCE
        assert status.retry_in == 120.0  # at most every 2 minutes, not 0-8 s
        assert app.listener.notices == ["maintenance_started"]


def closed_port() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{s.getsockname()[1]}"


def test_a_window_held_from_before_says_maintenance_while_the_server_is_away() -> None:
    """The app restarted inside the window, and the server is down (a
    deploy): it can't ask, so the window it kept says it."""
    held = Maintenance(now() - timedelta(minutes=5), now() + timedelta(seconds=40))
    with App(closed_port(), maintenance=held) as app:
        status = app.waiting()
        assert status.unreachable is Unreachable.MAINTENANCE
        # its end (Windows takes about 2 s to refuse a closed port)
        assert status.retry_in is not None and 30 <= status.retry_in <= 40


def test_once_the_window_has_passed_the_server_away_is_said_as_today() -> None:
    over = Maintenance(now() - timedelta(minutes=40), now() - timedelta(minutes=2))
    with App(closed_port(), maintenance=over) as app:
        status = app.waiting()
        assert status.unreachable is Unreachable.DOWN
        assert status.retry_in is not None and status.retry_in <= 8


def test_a_server_from_before_it_lets_a_held_window_go(server: FakeServer) -> None:
    """v0.1.2's `welcome` has neither field: no window is planned there, and
    the app listens as before."""
    old: dict[str, Any] = welcome_message()
    assert "server_time" not in old and "maintenance" not in old
    held = Maintenance(now() + timedelta(hours=1), now() + timedelta(hours=2))
    with App(server.url, maintenance=held) as app:
        wait_until(app.listener.listening)
        wait_until(lambda: app.listener.windows == [None])


def test_finished_speech_unanswered_before_the_window_isnt_sent_after_it(
    server: FakeServer,
) -> None:
    """The window starts with a caption in flight: it's given up (counted
    dropped), not sent again minutes later with every other app's."""
    from tests.test_session import finished

    async def unanswered_then_closed(
        server: FakeServer, websocket: ServerConnection
    ) -> None:
        await websocket.send(json.dumps(server.welcome))
        async for message in websocket:
            if isinstance(message, bytes):  # the finished speech: never answered
                notice = {"type": "notice", "code": "maintenance_started"}
                await websocket.send(json.dumps(notice))
                await websocket.close(1001)
                return

    server.script = [unanswered_then_closed]
    server.welcome = welcome_message(
        server_time=at(datetime.now(UTC)),
        maintenance=window_in(-timedelta(seconds=1), timedelta(minutes=10)),
    )
    with App(server.url) as app:
        wait_until(app.listener.listening)
        app.speech.put(finished("c1"), b"OggS one")
        app.session.speech_ready()
        status = app.waiting()
        assert status.unreachable is Unreachable.MAINTENANCE
        assert app.session.unanswered.to_send_again() == []
