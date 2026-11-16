"""A stand-in polyglotic-server for the connection's tests: protocol v1 over a real WebSocket.

Runs `websockets`' server on 127.0.0.1 in a thread of its own. Each
connection reads `hello`, then follows the next behaviour in `script` (or
`welcome` once the script has run out): answering speech frames with
caption updates, `ping` with `pong`, `learning` / `usage` / `exposures` /
`consent` with `received` (unless `answer_received` is off),
`learning_sync` with the next of `learning_states` (an empty one when they
run out) and `learning_delete` with `learning_deleted`. Everything the app
sends is recorded.
The real server is tried by hand (project 022's report); this one makes
the app's side testable in CI.
"""

import asyncio
import json
import ssl
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from tests.test_protocol import example
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from polyglotic_desktop.connection import protocol

Behaviour = Callable[["FakeServer", ServerConnection], Awaitable[None]]


def welcome_message(**changes: Any) -> dict[str, Any]:
    welcome = example("welcome")
    limits = changes.pop("limits", {})
    welcome["limits"] = welcome["limits"] | limits
    return welcome | changes


def caption_for(header: protocol.SpeechHeader) -> dict[str, Any]:
    """A stand-in caption update for a speech frame, as S1's stand-ins make."""
    text = f"Stand-in caption, {header.kind}."
    return {
        "type": "caption_update",
        "caption_id": header.caption_id,
        "source_id": header.source.id,
        "kind": header.kind,
        "language": "en",
        "languages_heard": ["en"],
        "clauses": [{"original": text, "translations": {"zh": f"[zh] {text}"}}],
        "replaces": list(header.replaces),
        "processing_ms": 5,
    }


async def welcome(server: "FakeServer", websocket: ServerConnection) -> None:
    """`welcome`, then serve: pong each ping, a caption for each speech frame."""
    await websocket.send(json.dumps(server.welcome))
    await server.serve(websocket)


def refuse(message: dict[str, Any], code: int) -> Behaviour:
    async def behaviour(server: "FakeServer", websocket: ServerConnection) -> None:
        await websocket.send(json.dumps(message))
        await websocket.close(code)

    return behaviour


async def welcome_then_silence(
    server: "FakeServer", websocket: ServerConnection
) -> None:
    """`welcome`, then read everything and answer nothing."""
    await websocket.send(json.dumps(server.welcome))
    async for data in websocket:
        server.record(data)


async def replacing(server: "FakeServer", websocket: ServerConnection) -> None:
    """As the real server does with a new session from the same install for
    the same purpose: the old one closed with 1000 as this one's `hello`
    arrives (protocol.md, `too_many_sessions`) - then `welcome`."""
    for other in list(server._open):
        if other is not websocket:
            await other.close(1000)
    await welcome(server, websocket)


class FakeServer:
    def __init__(self, port: int = 0, tls: ssl.SSLContext | None = None) -> None:
        """`tls`: a server context, for `https://` (wss) - 313's tests."""
        self.script: list[Behaviour] = []
        self.welcome = welcome_message()
        self.hellos: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.speech: list[tuple[protocol.SpeechHeader, bytes]] = []
        self.rechecks: list[tuple[protocol.RecheckHeader, bytes]] = []
        self.app_closes: list[int | None] = []
        """Each connection's close code, recorded on the server's thread once
        it's closed - which can be after the app's side has finished closing
        and its `stop()` returned (229): read it with `closes`."""
        self._closed = threading.Condition()
        self.answer_received = True
        self.learning_states: list[dict[str, Any]] = []
        self.connections = 0
        self.user_agents: list[str | None] = []
        """Each connection's User-Agent, as its handshake said (287)."""
        self._open: set[ServerConnection] = set()
        self._port = port
        self._tls = tls
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._server: Server | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)
        assert self._server is not None
        self.port: int = self._server.sockets[0].getsockname()[1]
        scheme = "https" if tls is not None else "http"
        self.url: str = f"{scheme}://127.0.0.1:{self.port}"

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)

        async def start() -> None:
            self._server = await serve(
                self._handle,
                "127.0.0.1",
                self._port,
                ping_interval=None,
                ssl=self._tls,
            )
            self._ready.set()

        self._loop.run_until_complete(start())
        self._loop.run_forever()

    async def _handle(self, websocket: ServerConnection) -> None:
        self.connections += 1
        self.user_agents.append(
            websocket.request.headers.get("User-Agent") if websocket.request else None
        )
        self._open.add(websocket)
        try:
            hello = json.loads(await websocket.recv())
            self.hellos.append(hello)
            behaviour = self.script.pop(0) if self.script else welcome
            await behaviour(self, websocket)
        except ConnectionClosed:
            pass
        finally:
            self._open.discard(websocket)
            await websocket.wait_closed()
            with self._closed:
                self.app_closes.append(websocket.close_code)
                self._closed.notify_all()

    def record(self, data: str | bytes) -> protocol.SpeechHeader | dict[str, Any]:
        if isinstance(data, bytes) and b'"type":"recheck"' in data[:64]:
            length = int.from_bytes(data[:4], "big")
            recheck = protocol.validate(
                protocol.RecheckHeader, json.loads(data[4 : 4 + length])
            )
            self.rechecks.append((recheck, data[4 + length :]))
            self.messages.append({"type": "recheck", "caption_id": recheck.caption_id})
            return {"type": "recheck", "caption_id": recheck.caption_id}
        if isinstance(data, bytes):
            header, audio = protocol.read_speech_frame(data)
            self.speech.append((header, audio))
            self.messages.append({"type": "speech", "caption_id": header.caption_id})
            return header
        message: dict[str, Any] = json.loads(data)
        self.messages.append(message)
        return message

    async def serve(self, websocket: ServerConnection) -> None:
        async for data in websocket:
            received = self.record(data)
            if isinstance(received, protocol.SpeechHeader):
                await websocket.send(json.dumps(caption_for(received)))
                continue
            for answer in self.answers(received):
                await websocket.send(json.dumps(answer))

    def answers(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        kind = message.get("type")
        if kind == "ping":
            return [{"type": "pong"}]
        if kind in ("learning", "usage", "exposures") and self.answer_received:
            return [{"type": "received", "batch": message["batch"]}]
        if kind == "consent" and self.answer_received:
            return [{"type": "received", "id": message["id"]}]
        if kind == "learning_sync":
            if self.learning_states:
                return [self.learning_states.pop(0)]
            empty = {"cursor": message.get("since") or "0", "more": False}
            return [
                {"type": "learning_state", "statuses": [], "saved_words": []} | empty
            ]
        if kind == "learning_delete":
            return [{"type": "learning_deleted"}]
        if kind == "recheck":  # checked on "the best models": the example's line
            return [example("recheck_result") | {"caption_id": message["caption_id"]}]
        return []

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["type"] == kind]

    def send_to_all(self, message: dict[str, Any]) -> None:
        """Sends a message to every open connection (from the test's thread)."""

        async def send() -> None:
            for websocket in list(self._open):
                await websocket.send(json.dumps(message))

        asyncio.run_coroutine_threadsafe(send(), self._loop).result(5)

    def close_all(self, code: int) -> None:
        """Closes every open connection with `code` (1001: a restart)."""

        async def close() -> None:
            for websocket in list(self._open):
                await websocket.close(code)

        asyncio.run_coroutine_threadsafe(close(), self._loop).result(5)

    def closes(self, count: int = 1, timeout: float = 5.0) -> list[int | None]:
        """The close codes recorded once at least `count` connections have
        closed: the record is made on the server's thread, and the app's
        `stop()` can return before it is (229: a test read `[]` for
        `[1000]`)."""
        with self._closed:
            if not self._closed.wait_for(
                lambda: len(self.app_closes) >= count, timeout
            ):
                raise AssertionError(
                    f"timed out waiting for {count} closes: {self.app_closes}"
                )
            return list(self.app_closes)

    def types(self) -> list[str]:
        return [m["type"] for m in self.messages]

    def stop(self) -> None:
        async def shut() -> None:
            if self._server is not None:
                self._server.close()
                await self._server.wait_closed()

        asyncio.run_coroutine_threadsafe(shut(), self._loop).result(5)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting")
        time.sleep(0.02)
