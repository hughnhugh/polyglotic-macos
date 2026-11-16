"""The session says why the server can't be reached, each case made to happen (polyglotic-hq 251).

The listening session against a stand-in for each: a closed port (the
server down), a name that never resolves (`.invalid`, RFC 6761 - DNS
failing), a tunnel's 530 and 502, a page where the WebSocket should be (a
proxy or firewall), a plain-HTTP answer to TLS (a Wi-Fi sign-in page), a
socket that never answers, a proxy setting websockets can't use, the
server restarting, failing the session (1011) and not answering `hello`.
Every one used to be a bare "Reconnecting"; the unusable proxy setting
stopped the session for good ("Stopped").
"""

import asyncio
import json
import socket
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from tests.fake_server import FakeServer, refuse, wait_until
from tests.test_session import Harness
from websockets.asyncio.server import ServerConnection

from polyglotic_desktop.connection.session import SessionState, Status, Timings
from polyglotic_desktop.core.listening.unreachable import Unreachable

SLOW_REFUSAL = Timings(answer_within=5, close_within=1)
"""Windows takes about 2 s to give up on a closed port on this PC: the
open timeout mustn't come first."""


class RawServer:
    """A TCP stand-in on 127.0.0.1 answering whatever arrives with `answer`
    (None: never answering) - a tunnel's error page, a proxy's page, a
    plain-HTTP answer to TLS, a hang."""

    def __init__(self, answer: bytes | None) -> None:
        self.answer = answer
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = int(self.sock.getsockname()[1])
        self._open: list[socket.socket] = []
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self._open.append(conn)
            threading.Thread(target=self._one, args=(conn,), daemon=True).start()

    def _one(self, conn: socket.socket) -> None:
        try:
            conn.recv(65536)
            if self.answer is not None:
                conn.sendall(self.answer)
                conn.shutdown(socket.SHUT_WR)
            else:
                self._stop.wait(10)
        except OSError:
            pass

    def stop(self) -> None:
        self._stop.set()
        self.sock.close()
        for conn in self._open:
            conn.close()


def http(status: str, body: str = "<html>error</html>") -> bytes:
    return (
        f"HTTP/1.1 {status}\r\nContent-Type: text/html\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}"
    ).encode()


@pytest.fixture
def server() -> Iterator[FakeServer]:
    fake = FakeServer()
    yield fake
    fake.stop()


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def waiting(app: Harness, timeout: float = 10.0) -> Status:
    """The first status waiting to try again."""

    def found() -> bool:
        return any(s.state is SessionState.WAITING for s in app.listener.statuses)

    wait_until(found, timeout)
    return next(s for s in app.listener.statuses if s.state is SessionState.WAITING)


def against(server: FakeServer, url: str, timings: Timings | None = None) -> Status:
    with Harness(server, url=url, timings=timings) as app:
        return waiting(app)


def test_the_server_down_refused(server: FakeServer) -> None:
    status = against(server, f"http://127.0.0.1:{closed_port()}", SLOW_REFUSAL)
    assert status.unreachable is Unreachable.DOWN
    assert status.close_code is None and not status.server_busy


@pytest.mark.parametrize("answer", ["530 <none>", "502 Bad Gateway"])
def test_the_tunnel_up_and_the_server_behind_it_down(
    server: FakeServer, answer: str
) -> None:
    """Cloudflare answers 530 (error 1033) with the tunnel down, 502 with the
    server behind it down: the learner's internet works."""
    raw = RawServer(http(answer, "error code: 1033"))
    try:
        assert against(server, f"http://127.0.0.1:{raw.port}").unreachable is (
            Unreachable.DOWN
        )
    finally:
        raw.stop()


@pytest.mark.parametrize("answer", ["200 OK", "403 Forbidden"])
def test_a_proxy_or_firewall_answering_instead(server: FakeServer, answer: str) -> None:
    """A page where the WebSocket should be: something on the network
    stripped the upgrade, or refused it."""
    raw = RawServer(http(answer, "<html>Blocked by your network</html>"))
    try:
        with Harness(server, url=f"http://127.0.0.1:{raw.port}") as app:
            assert waiting(app).unreachable is Unreachable.BLOCKED
        # still signed in (polyglotic-hq 288: Cloudflare's 403 to every
        # installed copy on 2026-11-11 signed none of them out)
        assert app.store.load() is not None
    finally:
        raw.stop()


def test_tls_answered_in_plain_http(server: FakeServer) -> None:
    """A Wi-Fi sign-in page or a proxy answering TLS with plain HTTP."""
    raw = RawServer(http("400 Bad Request"))
    try:
        assert against(server, f"https://127.0.0.1:{raw.port}").unreachable is (
            Unreachable.NOT_SECURE
        )
    finally:
        raw.stop()


def test_nothing_answers(server: FakeServer) -> None:
    raw = RawServer(None)
    try:
        status = against(
            server,
            f"http://127.0.0.1:{raw.port}",
            Timings(answer_within=0.5, close_within=0.5),
        )
        assert status.unreachable is Unreachable.NO_ANSWER
    finally:
        raw.stop()


def test_dns_failing(server: FakeServer) -> None:
    """A `.invalid` name never resolves (RFC 6761): DNS failing, or no
    network at all, reads the same."""
    status = against(server, "https://polyglotic-251.invalid")
    assert status.unreachable is Unreachable.OFFLINE


def test_a_proxy_setting_that_cant_be_used_is_said_not_stopped(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """websockets reads the PC's proxy setting, and raised InvalidProxy -
    not one of the errors the session caught - for one it can't use: the
    session ended for good, and Home said "Stopped"."""
    monkeypatch.setenv("HTTPS_PROXY", "ftp://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    with Harness(server, url="https://polyglotic-251.invalid") as app:
        status = waiting(app)
        assert status.unreachable is Unreachable.BLOCKED
        assert SessionState.STOPPED not in app.listener.states()


def welcome_then_close(code: int, notice: str | None = None) -> Any:
    async def behaviour(server: FakeServer, websocket: ServerConnection) -> None:
        await websocket.send(json.dumps(server.welcome))
        if notice:
            await websocket.send(json.dumps({"type": "notice", "code": notice}))
        await asyncio.sleep(0.2)
        await websocket.close(code)

    return behaviour


def test_a_restart_is_said_until_the_server_is_back() -> None:
    """A deploy: `server_restarting`, close 1001, then the server gone - each
    try refused - and back. Restarting throughout, not "down"."""
    first = FakeServer()
    first.script = [welcome_then_close(1001, "server_restarting")]
    port = first.port
    with Harness(first, timings=SLOW_REFUSAL) as app:
        wait_until(app.listener.listening)
        wait_until(lambda: app.listener.notices == ["server_restarting"])
        first.stop()  # the server is down while it restarts
        wait_until(
            lambda: (
                sum(s.state is SessionState.WAITING for s in app.listener.statuses) >= 2
            ),
            15,
        )
        waits = [s for s in app.listener.statuses if s.state is SessionState.WAITING]
        assert waits[0].close_code == 1001  # the restart itself
        assert waits[1].close_code is None  # a try refused while it restarts
        assert {s.unreachable for s in waits} == {Unreachable.RESTARTING}
        back = FakeServer(port)  # up again, where it was
        try:
            wait_until(lambda: app.listener.listening(2), 15)
        finally:
            app.session.stop()
            back.stop()


def test_a_close_1001_the_server_didnt_announce_isnt_said_as_a_restart() -> None:
    """368: a close 1001 with no `server_restarting` before it - not our
    server's way of restarting - read as "restarting" for three minutes of
    refused tries. Now: tried again first, then each refused try is what it
    is (can't reach), never a restart."""
    first = FakeServer()
    first.script = [welcome_then_close(1001)]
    with Harness(first, timings=SLOW_REFUSAL) as app:
        wait_until(app.listener.listening)
        first.stop()
        wait_until(
            lambda: (
                sum(s.state is SessionState.WAITING for s in app.listener.statuses) >= 2
            ),
            15,
        )
        waits = [s for s in app.listener.statuses if s.state is SessionState.WAITING]
        assert waits[0].close_code == 1001 and waits[0].unreachable is None
        assert waits[1].close_code is None
        assert waits[1].unreachable is Unreachable.DOWN
        assert Unreachable.RESTARTING not in {s.unreachable for s in waits}
        app.session.stop()


def test_the_server_failing_the_session(server: FakeServer) -> None:
    error = {"type": "error", "code": "server_error", "fatal": True}
    server.script = [refuse(error, 1011)]
    assert against(server, server.url).unreachable is Unreachable.SERVER_ERROR


def test_the_server_not_answering_hello(server: FakeServer) -> None:
    async def silent(server: FakeServer, websocket: ServerConnection) -> None:
        await websocket.wait_closed()

    server.script = [silent]
    status = against(server, server.url, Timings(answer_within=0.5, close_within=0.5))
    assert status.unreachable is Unreachable.SERVER_ERROR


def test_a_full_server_is_busy_not_unreachable(server: FakeServer) -> None:
    server.script = [refuse({"type": "server_busy", "retry_after": 30}, 4013)]
    status = against(server, server.url)
    assert status.server_busy and status.unreachable is None


def test_too_many_sessions_on_the_account(server: FakeServer) -> None:
    server.script = [
        refuse({"type": "too_many_sessions", "limit": 2, "retry_after": 60}, 4029)
    ]
    status = against(server, server.url)
    assert (status.unreachable, status.retry_in) == (
        Unreachable.TOO_MANY_SESSIONS,
        60.0,
    )


def test_too_many_failed_sign_ins_from_this_network(server: FakeServer) -> None:
    message = {"type": "auth_failed", "reason": "too_many_attempts", "retry_after": 30}
    server.script = [refuse(message, 4003)]
    status = against(server, server.url)
    assert (status.unreachable, status.retry_in) == (Unreachable.TOO_MANY_TRIES, 30.0)


def test_a_dropped_connection_says_nothing_until_a_try_fails(
    server: FakeServer,
) -> None:
    """A session closed for nothing the server says is its own doing (4008,
    timed out - or 1006, dropped) is tried again before anything is said:
    only a try that fails says why."""
    server.script = [welcome_then_close(4008)]
    with Harness(server) as app:
        wait_until(app.listener.listening)
        status = waiting(app)
        assert status.close_code == 4008 and status.unreachable is None
