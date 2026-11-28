"""The sound server through libpulse, by ctypes (polyglotic-hq 546, 547):
the system's own copy, which PipeWire's pulse server (every current
desktop) and PulseAudio both serve - never PortAudio, which Ubuntu doesn't
install, nor `pactl`/`parec`, which it doesn't either.

`PulseServer` is one connection, on the thread that made it: libpulse's
own main loop driven by hand (`run`: prepare, poll, dispatch), so every
callback runs on that thread and Python never blocks the sound server.
It answers what capture and the device lists ask:
- `server_info` - the defaults by name (the output, the input);
- `sinks`, `sources` - the outputs and inputs; a source that is an
  output's monitor says so (`monitor_of`);
- `record` - a record stream on a source by name: 16kHz mono float32 (the
  server converts), about 20 ms a piece, never moved by the server to
  another device (`PA_STREAM_DONT_MOVE`: without it WirePlumber moved a
  stream whose device went to the mic, 547) - or only one app's stream
  (`monitor_of`, 561), from its output's monitor;
- `streams` - the streams apps play now (sink inputs), each with its app,
  from the stream or else its client (`PlayingStream`, 561);
- `changes` - how many times the server, an output or an input changed
  (its subscription) - or, watched with `STREAMS`, an app's stream or
  client - so a capture re-checks what it should record;
- `play` - a playback stream on the default output: 16-bit sound written
  as the server asks for it, then drained, so it says when the last of it
  has played (`Playback`, 591: a recorded word, Home's sample).

The library is loaded on first use: the module imports on any OS. Every
failure is an `OSError` naming the call, never what was heard.
"""

from __future__ import annotations

import ctypes
import re
import time
from dataclasses import dataclass
from typing import Any

SAMPLE_FLOAT32LE = 5
"""`PA_SAMPLE_FLOAT32LE`: as `AudioCallback` takes it."""
SAMPLE_S16LE = 3
"""`PA_SAMPLE_S16LE`: as a `speaking.Clip` holds its sound."""
SEEK_RELATIVE = 0
RATE = 16_000
PIECE_BYTES = 1280
"""20 ms of 16kHz mono float32: the fragment asked for."""
STREAM_DONT_MOVE = 0x0200
STREAM_ADJUST_LATENCY = 0x2000
CONTEXT_NOAUTOSPAWN = 0x0001
INVALID_INDEX = 0xFFFFFFFF
NO_VALUE = 0xFFFFFFFF
"""`(uint32_t) -1`: "the server's choice" in a buffer's attributes."""
CONTEXT_READY, CONTEXT_FAILED, CONTEXT_TERMINATED = 4, 5, 6
STREAM_CREATING, STREAM_READY, STREAM_FAILED, STREAM_TERMINATED = 1, 2, 3, 4
OPERATION_RUNNING = 0
STATE_RUNNING = 0
"""A sink's or source's state: playing or recording now."""
SUBSCRIBE_SINK, SUBSCRIBE_SOURCE, SUBSCRIBE_SERVER = 0x0001, 0x0002, 0x0080
SUBSCRIBE_SINK_INPUT, SUBSCRIBE_CLIENT = 0x0004, 0x0020
DEVICES = SUBSCRIBE_SINK | SUBSCRIBE_SOURCE | SUBSCRIBE_SERVER
"""What a capture of a device follows: the outputs, the inputs, the defaults."""
STREAMS = DEVICES | SUBSCRIBE_SINK_INPUT | SUBSCRIBE_CLIENT
"""What a capture of apps follows too: the streams apps play, and their clients."""
CONNECT_SEC = 5.0
ANSWER_SEC = 5.0

_vp = ctypes.c_void_p


class _SampleSpec(ctypes.Structure):
    _fields_ = [
        ("format", ctypes.c_int),
        ("rate", ctypes.c_uint32),
        ("channels", ctypes.c_uint8),
    ]


class _ChannelMap(ctypes.Structure):
    _fields_ = [("channels", ctypes.c_uint8), ("map", ctypes.c_int * 32)]


class _Volume(ctypes.Structure):
    _fields_ = [("channels", ctypes.c_uint8), ("values", ctypes.c_uint32 * 32)]


class _BufferAttr(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint32)
        for name in ("maxlength", "tlength", "prebuf", "minreq", "fragsize")
    ]


class _ServerInfo(ctypes.Structure):
    _fields_ = [
        ("user_name", ctypes.c_char_p),
        ("host_name", ctypes.c_char_p),
        ("server_version", ctypes.c_char_p),
        ("server_name", ctypes.c_char_p),
        ("sample_spec", _SampleSpec),
        ("default_sink_name", ctypes.c_char_p),
        ("default_source_name", ctypes.c_char_p),
        ("cookie", ctypes.c_uint32),
        ("channel_map", _ChannelMap),
    ]


def _device_fields(monitor: str) -> list[tuple[str, Any]]:
    """`pa_sink_info`'s and `pa_source_info`'s leading fields, as far as
    `state` (read through a pointer: the rest is never touched). They
    differ only in the monitor's field names."""
    return [
        ("name", ctypes.c_char_p),
        ("index", ctypes.c_uint32),
        ("description", ctypes.c_char_p),
        ("sample_spec", _SampleSpec),
        ("channel_map", _ChannelMap),
        ("owner_module", ctypes.c_uint32),
        ("volume", _Volume),
        ("mute", ctypes.c_int),
        (f"{monitor}", ctypes.c_uint32),
        (f"{monitor}_name", ctypes.c_char_p),
        ("latency", ctypes.c_uint64),
        ("driver", ctypes.c_char_p),
        ("flags", ctypes.c_int),
        ("proplist", _vp),
        ("configured_latency", ctypes.c_uint64),
        ("base_volume", ctypes.c_uint32),
        ("state", ctypes.c_int),
    ]


class _SinkInfo(ctypes.Structure):
    _fields_ = _device_fields("monitor_source")


class _SourceInfo(ctypes.Structure):
    _fields_ = _device_fields("monitor_of_sink")


class _SinkInputInfo(ctypes.Structure):
    """`pa_sink_input_info`'s leading fields, as far as `corked`."""

    _fields_ = [
        ("index", ctypes.c_uint32),
        ("name", ctypes.c_char_p),
        ("owner_module", ctypes.c_uint32),
        ("client", ctypes.c_uint32),
        ("sink", ctypes.c_uint32),
        ("sample_spec", _SampleSpec),
        ("channel_map", _ChannelMap),
        ("volume", _Volume),
        ("buffer_usec", ctypes.c_uint64),
        ("sink_usec", ctypes.c_uint64),
        ("resample_method", ctypes.c_char_p),
        ("driver", ctypes.c_char_p),
        ("mute", ctypes.c_int),
        ("proplist", _vp),
        ("corked", ctypes.c_int),
    ]


class _ClientInfo(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("name", ctypes.c_char_p),
        ("owner_module", ctypes.c_uint32),
        ("driver", ctypes.c_char_p),
        ("proplist", _vp),
    ]


_SERVER_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.POINTER(_ServerInfo), _vp)
_SINK_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.POINTER(_SinkInfo), ctypes.c_int, _vp)
_SOURCE_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.POINTER(_SourceInfo), ctypes.c_int, _vp)
_SUCCESS_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.c_int, _vp)
_SUBSCRIBE_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.c_int, ctypes.c_uint32, _vp)
_SINK_INPUT_CB = ctypes.CFUNCTYPE(
    None, _vp, ctypes.POINTER(_SinkInputInfo), ctypes.c_int, _vp
)
_CLIENT_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.POINTER(_ClientInfo), ctypes.c_int, _vp)
_STREAM_CB = ctypes.CFUNCTYPE(None, _vp, _vp)
_READ_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.c_size_t, _vp)
_WRITE_CB = _READ_CB
"""`pa_stream_request_cb_t`: the same shape for writing as for reading."""
_STREAM_SUCCESS_CB = ctypes.CFUNCTYPE(None, _vp, ctypes.c_int, _vp)

_SIGNATURES: dict[str, tuple[Any, list[Any]]] = {
    "pa_mainloop_new": (_vp, []),
    "pa_mainloop_free": (None, [_vp]),
    "pa_mainloop_get_api": (_vp, [_vp]),
    "pa_mainloop_prepare": (ctypes.c_int, [_vp, ctypes.c_int]),
    "pa_mainloop_poll": (ctypes.c_int, [_vp]),
    "pa_mainloop_dispatch": (ctypes.c_int, [_vp]),
    "pa_proplist_new": (_vp, []),
    "pa_proplist_free": (None, [_vp]),
    "pa_proplist_sets": (ctypes.c_int, [_vp, ctypes.c_char_p, ctypes.c_char_p]),
    "pa_proplist_gets": (ctypes.c_char_p, [_vp, ctypes.c_char_p]),
    "pa_context_new_with_proplist": (_vp, [_vp, ctypes.c_char_p, _vp]),
    "pa_context_connect": (ctypes.c_int, [_vp, ctypes.c_char_p, ctypes.c_int, _vp]),
    "pa_context_disconnect": (None, [_vp]),
    "pa_context_unref": (None, [_vp]),
    "pa_context_get_state": (ctypes.c_int, [_vp]),
    "pa_context_errno": (ctypes.c_int, [_vp]),
    "pa_strerror": (ctypes.c_char_p, [ctypes.c_int]),
    "pa_context_get_server_info": (_vp, [_vp, _SERVER_CB, _vp]),
    "pa_context_get_sink_info_list": (_vp, [_vp, _SINK_CB, _vp]),
    "pa_context_get_source_info_list": (_vp, [_vp, _SOURCE_CB, _vp]),
    "pa_context_get_sink_input_info_list": (_vp, [_vp, _SINK_INPUT_CB, _vp]),
    "pa_context_get_client_info_list": (_vp, [_vp, _CLIENT_CB, _vp]),
    "pa_context_set_subscribe_callback": (None, [_vp, _SUBSCRIBE_CB, _vp]),
    "pa_context_subscribe": (_vp, [_vp, ctypes.c_int, _SUCCESS_CB, _vp]),
    "pa_operation_get_state": (ctypes.c_int, [_vp]),
    "pa_operation_cancel": (None, [_vp]),
    "pa_operation_unref": (None, [_vp]),
    "pa_stream_new": (_vp, [_vp, ctypes.c_char_p, ctypes.POINTER(_SampleSpec), _vp]),
    "pa_stream_set_monitor_stream": (ctypes.c_int, [_vp, ctypes.c_uint32]),
    "pa_stream_set_state_callback": (None, [_vp, _STREAM_CB, _vp]),
    "pa_stream_set_read_callback": (None, [_vp, _READ_CB, _vp]),
    "pa_stream_connect_record": (
        ctypes.c_int,
        [_vp, ctypes.c_char_p, ctypes.POINTER(_BufferAttr), ctypes.c_int],
    ),
    "pa_stream_peek": (
        ctypes.c_int,
        [_vp, ctypes.POINTER(_vp), ctypes.POINTER(ctypes.c_size_t)],
    ),
    "pa_stream_drop": (ctypes.c_int, [_vp]),
    "pa_stream_set_write_callback": (None, [_vp, _WRITE_CB, _vp]),
    "pa_stream_connect_playback": (
        ctypes.c_int,
        [_vp, ctypes.c_char_p, ctypes.POINTER(_BufferAttr), ctypes.c_int, _vp, _vp],
    ),
    "pa_stream_write": (
        ctypes.c_int,
        [_vp, ctypes.c_char_p, ctypes.c_size_t, _vp, ctypes.c_int64, ctypes.c_int],
    ),
    "pa_stream_drain": (_vp, [_vp, _STREAM_SUCCESS_CB, _vp]),
    "pa_stream_get_state": (ctypes.c_int, [_vp]),
    "pa_stream_disconnect": (ctypes.c_int, [_vp]),
    "pa_stream_unref": (None, [_vp]),
}

_lib: Any = None


class MissingLibrary(OSError):
    """The Pulse client library or one of its dependencies could not load."""


def library() -> Any:
    """libpulse, its calls typed - loaded once; OSError where there's none."""
    global _lib
    if _lib is None:
        try:
            found = ctypes.CDLL("libpulse.so.0")
        except OSError as e:
            raise MissingLibrary("libpulse isn't installed (libpulse.so.0)") from e
        for name, (result, arguments) in _SIGNATURES.items():
            call = getattr(found, name)
            call.restype = result
            call.argtypes = arguments
        _lib = found
    return _lib


def _text(value: bytes | None) -> str | None:
    return value.decode("utf-8", "replace") if value is not None else None


@dataclass(frozen=True, slots=True)
class Defaults:
    """The server's name ("PulseAudio (on PipeWire 1.0.5)") and its default
    output and input, by name (None: none)."""

    server: str
    output: str | None
    input: str | None
    version: str = ""

    def log_identity(self) -> str:
        """Recognized server software and numeric versions only, never host/user data."""
        version = (
            self.version
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", self.version)
            else "unknown"
        )
        pw = re.fullmatch(
            r"PulseAudio \(on PipeWire ([0-9]+(?:\.[0-9]+)*)\)", self.server
        )
        if pw:
            return f"PipeWire {pw[1]} (PulseAudio {version})"
        if self.server.lower() == "pulseaudio":
            return f"PulseAudio {version}"
        return f"other (Pulse protocol server version {version})"


@dataclass(frozen=True, slots=True)
class Device:
    """An output (sink) or input (source) the server has now: its name -
    the id the server knows it by, kept to choose it again - its
    description, for the learner's eyes ("Built-in Audio Analog Stereo"),
    and whether it's playing or recording now. `monitor`: an output's
    monitor source, by name; `monitor_of`: for a source that is an
    output's monitor, that output's index (None: a real input)."""

    name: str
    description: str
    index: int
    running: bool
    monitor: str | None = None
    monitor_of: int | None = None


@dataclass(frozen=True, slots=True)
class PlayingStream:
    """A stream an app plays now (a sink input), as the app list and one
    app's capture need it: its index, the output it plays to (`sink`, by
    index), whether it's paused (`corked`), and its app - the name the app
    gives itself (`application.name`), its executable's name
    (`application.process.binary`) and its process - each from the stream,
    else from its client: a native PipeWire player puts them only on its
    client (547). The process is the one the sound server saw connect
    (`pipewire.sec.pid`) where it says, which is the PC's own number for a
    sandboxed app, else the one the app gave. Never the stream's own name
    (`media.name`): a file's path, a tab's or a song's title."""

    index: int
    sink: int
    corked: bool
    app_name: str | None
    binary: str | None
    process_id: int | None


def _number(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


_APP_KEYS = (
    "application.name",
    "application.process.binary",
    "application.process.id",
    "pipewire.sec.pid",
)


def playing_stream(
    index: int, sink: int, corked: bool, own: dict[str, str], client: dict[str, str]
) -> PlayingStream:
    """A stream's app from its own properties, else its client's; the
    process the server saw connect (`pipewire.sec.pid`) before the one the
    app gave (`application.process.id`: a sandboxed app's own number)."""

    def found(key: str) -> str | None:
        return own.get(key) or client.get(key)

    process = _number(client.get("pipewire.sec.pid") or own.get("pipewire.sec.pid"))
    return PlayingStream(
        index,
        sink,
        corked,
        found("application.name"),
        found("application.process.binary"),
        process or _number(found("application.process.id")),
    )


def server_failure(lib: Any, context: Any, message: str) -> OSError:
    if context and lib.pa_context_errno(context) == 1:  # PA_ERR_ACCESS
        return PermissionError(message)
    return OSError(message)


class Recording:
    """A record stream on one source, made by `PulseServer.record`: what
    it delivered, as (arrival on `time.perf_counter`, float32 bytes), taken
    by `take` on the connection's thread. `monitor_of`: one app's stream
    (a sink input's index) - only its sound, from its output's monitor."""

    def __init__(
        self, lib: Any, context: Any, source: str, monitor_of: int | None = None
    ) -> None:
        self._lib = lib
        self._pieces: list[tuple[float, bytes]] = []
        spec = _SampleSpec(SAMPLE_FLOAT32LE, RATE, 1)
        self._stream = lib.pa_stream_new(
            context, b"Polyglotic", ctypes.byref(spec), None
        )
        if not self._stream:
            raise OSError("The sound server wouldn't make a record stream")
        # one app's stream: set before connecting; with DONT_MOVE below, the
        # record stream ends with the app's stream rather than being moved
        # to the mic by WirePlumber (547)
        if (
            monitor_of is not None
            and lib.pa_stream_set_monitor_stream(self._stream, monitor_of) < 0
        ):
            lib.pa_stream_unref(self._stream)
            self._stream = None
            raise OSError("The sound server wouldn't record that app's stream")
        self._callbacks = (_STREAM_CB(self._state_changed), _READ_CB(self._readable))
        lib.pa_stream_set_state_callback(self._stream, self._callbacks[0], None)
        lib.pa_stream_set_read_callback(self._stream, self._callbacks[1], None)
        attributes = _BufferAttr(NO_VALUE, NO_VALUE, NO_VALUE, NO_VALUE, PIECE_BYTES)
        flags = STREAM_ADJUST_LATENCY | STREAM_DONT_MOVE
        if (
            lib.pa_stream_connect_record(
                self._stream, source.encode(), ctypes.byref(attributes), flags
            )
            < 0
        ):
            error = server_failure(
                lib, context, "The sound server wouldn't record that device"
            )
            self.close()
            raise error

    def _state_changed(self, _stream: Any, _data: Any) -> None:
        pass  # read by `state` when asked

    def _readable(self, _stream: Any, _size: int, _data: Any) -> None:
        arrival = time.perf_counter()
        data, size = _vp(), ctypes.c_size_t(0)
        while (
            self._lib.pa_stream_peek(
                self._stream, ctypes.byref(data), ctypes.byref(size)
            )
            >= 0
        ):
            if size.value == 0:
                return
            if data.value:  # a hole (nothing for a while) has no data: dropped
                self._pieces.append((arrival, ctypes.string_at(data.value, size.value)))
            self._lib.pa_stream_drop(self._stream)

    @property
    def state(self) -> int:
        return int(self._lib.pa_stream_get_state(self._stream)) if self._stream else 4

    @property
    def ready(self) -> bool:
        return self.state == STREAM_READY

    @property
    def failed(self) -> bool:
        """The server ended it: its device went, or the server did."""
        return self.state in (STREAM_FAILED, STREAM_TERMINATED)

    def take(self) -> list[tuple[float, bytes]]:
        pieces, self._pieces = self._pieces, []
        return pieces

    def close(self) -> None:
        """Disconnected (while it's being made or recording), its callbacks
        taken away - nothing calls into Python after this - and let go. A
        callback taken away is a null function pointer (`_READ_CB()`): ctypes
        refuses None for a callback's type, which made closing raise, the
        stream never let go and the capture's thread end (561)."""
        if self._stream:
            if self.state in (STREAM_CREATING, STREAM_READY):
                self._lib.pa_stream_disconnect(self._stream)
            self._lib.pa_stream_set_read_callback(self._stream, _READ_CB(), None)
            self._lib.pa_stream_set_state_callback(self._stream, _STREAM_CB(), None)
            self._lib.pa_stream_unref(self._stream)
            self._stream = None


class Playback:
    """A playback stream on the default output, made by `PulseServer.play`:
    `pcm` (16-bit little-endian, `rate` per second, `channels` interleaved)
    written as the server asks for it, then drained - `done` once the
    server says the last of it has played. Moved with the default output
    if that changes (no `DONT_MOVE`: a word follows the speakers)."""

    def __init__(
        self, lib: Any, context: Any, pcm: bytes, rate: int, channels: int
    ) -> None:
        self._lib = lib
        self._pcm = pcm
        self._at = 0
        self._drain: Any = None
        self.done = False
        """The server said all of it has played."""
        spec = _SampleSpec(SAMPLE_S16LE, rate, channels)
        self._stream = lib.pa_stream_new(
            context, b"Polyglotic", ctypes.byref(spec), None
        )
        if not self._stream:
            raise OSError("The sound server wouldn't make a playback stream")
        self._callbacks = (
            _STREAM_CB(self._state_changed),
            _WRITE_CB(self._writable),
            _STREAM_SUCCESS_CB(self._drained),
        )
        lib.pa_stream_set_state_callback(self._stream, self._callbacks[0], None)
        lib.pa_stream_set_write_callback(self._stream, self._callbacks[1], None)
        if lib.pa_stream_connect_playback(self._stream, None, None, 0, None, None) < 0:
            self.close()
            raise OSError("The sound server wouldn't play to the default output")

    def _state_changed(self, _stream: Any, _data: Any) -> None:
        pass  # read by `state` when asked

    def _writable(self, _stream: Any, size: int, _data: Any) -> None:
        """The server has room for `size` bytes: the next of the sound, and
        once it's all written, the drain that says when it has played."""
        piece = self._pcm[self._at : self._at + size]
        if piece:
            self._lib.pa_stream_write(
                self._stream, piece, len(piece), None, 0, SEEK_RELATIVE
            )
            self._at += len(piece)
        if self._at >= len(self._pcm) and self._drain is None:
            self._drain = self._lib.pa_stream_drain(
                self._stream, self._callbacks[2], None
            )

    def _drained(self, _stream: Any, _success: int, _data: Any) -> None:
        self.done = True  # played, or the stream ended: either way, over

    @property
    def state(self) -> int:
        return int(self._lib.pa_stream_get_state(self._stream)) if self._stream else 4

    @property
    def ready(self) -> bool:
        return self.state == STREAM_READY

    @property
    def failed(self) -> bool:
        """The server ended it: its output went, or the server did."""
        return self.state in (STREAM_FAILED, STREAM_TERMINATED)

    def close(self) -> None:
        """Stopped where it is, its callbacks taken away (null functions, as
        `Recording.close` does) and let go."""
        if self._drain is not None:
            self._lib.pa_operation_unref(self._drain)
            self._drain = None
        if self._stream:
            if self.state in (STREAM_CREATING, STREAM_READY):
                self._lib.pa_stream_disconnect(self._stream)
            self._lib.pa_stream_set_write_callback(self._stream, _WRITE_CB(), None)
            self._lib.pa_stream_set_state_callback(self._stream, _STREAM_CB(), None)
            self._lib.pa_stream_unref(self._stream)
            self._stream = None


class PulseServer:
    """One connection to the sound server, used only on the thread that
    made it. OSError if there's no server, or it doesn't answer within
    `wait` seconds."""

    def __init__(
        self, name: str = "Polyglotic", lib: Any = None, wait: float = CONNECT_SEC
    ) -> None:
        self._lib = lib if lib is not None else library()
        self._loop = self._lib.pa_mainloop_new()
        if not self._loop:
            raise OSError("libpulse wouldn't make a main loop")
        self._context: Any = None
        self._keep: list[Any] = []
        self.changes = 0
        """How many times the server, an output or an input changed since
        `watch` (counted while `run` runs)."""
        properties = self._lib.pa_proplist_new()
        self._lib.pa_proplist_sets(properties, b"application.name", name.encode())
        self._lib.pa_proplist_sets(
            properties, b"application.id", b"io.polyglotic.Polyglotic"
        )
        api = self._lib.pa_mainloop_get_api(self._loop)
        self._context = self._lib.pa_context_new_with_proplist(
            api, name.encode(), properties
        )
        self._lib.pa_proplist_free(properties)
        try:
            if not self._context or (
                self._lib.pa_context_connect(
                    self._context, None, CONTEXT_NOAUTOSPAWN, None
                )
                < 0
            ):
                raise server_failure(
                    self._lib, self._context, "No sound server to connect to"
                )
            if not self._until(lambda: self._state() >= CONTEXT_READY, wait) or (
                self._state() != CONTEXT_READY
            ):
                raise server_failure(
                    self._lib, self._context, "The sound server didn't answer"
                )
        except OSError:
            self.close()
            raise

    def _state(self) -> int:
        return int(self._lib.pa_context_get_state(self._context))

    def _error(self) -> str:
        message = self._lib.pa_strerror(self._lib.pa_context_errno(self._context))
        return _text(message) or "unknown"

    @property
    def alive(self) -> bool:
        return self._context is not None and self._state() == CONTEXT_READY

    def run(self, seconds: float) -> None:
        """Runs the connection's callbacks for up to `seconds` (at least one
        pass): reading what streams delivered, and the server's changes."""
        end = time.perf_counter() + seconds
        while True:
            left = end - time.perf_counter()
            wait = max(0, int(min(left, 0.05) * 1_000_000))
            if self._lib.pa_mainloop_prepare(self._loop, wait) < 0:
                raise OSError("libpulse's main loop stopped")
            if self._lib.pa_mainloop_poll(self._loop) < 0:
                raise OSError("libpulse's main loop stopped")
            self._lib.pa_mainloop_dispatch(self._loop)
            if left <= 0:
                return

    def _until(self, done: Any, seconds: float) -> bool:
        end = time.perf_counter() + seconds
        while not done():
            if time.perf_counter() >= end:
                return bool(done())
            self.run(0.01)
        return True

    def _answer(self, operation: Any) -> None:
        """Waits for an operation's answer (its callbacks have run then)."""
        if not operation:
            raise OSError(f"The sound server refused: {self._error()}")
        finished = False
        try:
            finished = self._until(
                lambda: (
                    self._lib.pa_operation_get_state(operation) != OPERATION_RUNNING
                ),
                ANSWER_SEC,
            )
        finally:
            if not finished:
                self._lib.pa_operation_cancel(operation)
            self._lib.pa_operation_unref(operation)
        if not finished:
            raise OSError("The sound server didn't answer in time")
        if not self.alive:
            raise OSError(f"The sound server went away: {self._error()}")

    def server_info(self) -> Defaults:
        found: list[Defaults] = []

        def answered(_context: Any, info: Any, _data: Any) -> None:
            if info:
                i = info.contents
                found.append(
                    Defaults(
                        _text(i.server_name) or "",
                        _text(i.default_sink_name),
                        _text(i.default_source_name),
                        _text(i.server_version) or "",
                    )
                )

        callback = _SERVER_CB(answered)
        self._answer(
            self._lib.pa_context_get_server_info(self._context, callback, None)
        )
        if not found:
            raise OSError("The sound server said nothing about itself")
        return found[0]

    def sinks(self) -> list[Device]:
        found: list[Device] = []

        def listed(_context: Any, info: Any, last: int, _data: Any) -> None:
            if last or not info:
                return
            i = info.contents
            found.append(
                Device(
                    _text(i.name) or "",
                    _text(i.description) or _text(i.name) or "",
                    int(i.index),
                    i.state == STATE_RUNNING,
                    monitor=_text(i.monitor_source_name),
                )
            )

        callback = _SINK_CB(listed)
        self._answer(
            self._lib.pa_context_get_sink_info_list(self._context, callback, None)
        )
        return found

    def sources(self) -> list[Device]:
        found: list[Device] = []

        def listed(_context: Any, info: Any, last: int, _data: Any) -> None:
            if last or not info:
                return
            i = info.contents
            of = int(i.monitor_of_sink)
            found.append(
                Device(
                    _text(i.name) or "",
                    _text(i.description) or _text(i.name) or "",
                    int(i.index),
                    i.state == STATE_RUNNING,
                    monitor_of=None if of == INVALID_INDEX else of,
                )
            )

        callback = _SOURCE_CB(listed)
        self._answer(
            self._lib.pa_context_get_source_info_list(self._context, callback, None)
        )
        return found

    def watch(self, what: int = DEVICES) -> None:
        """Counts the server's changes from now on (`changes`): by default a
        new default, an output or input added, changed or removed; with
        `STREAMS`, the streams apps play and their clients too."""

        def changed(_context: Any, _kind: int, _index: int, _data: Any) -> None:
            self.changes += 1

        callback = _SUBSCRIBE_CB(changed)
        done = _SUCCESS_CB(lambda *_a: None)
        self._keep += [callback, done]
        self._lib.pa_context_set_subscribe_callback(self._context, callback, None)
        self._answer(self._lib.pa_context_subscribe(self._context, what, done, None))

    def record(self, source: str, monitor_of: int | None = None) -> Recording:
        """A record stream on `source`, once the server has started it - only
        the stream `monitor_of` (a sink input's index) if given, `source`
        then being its output's monitor; OSError if it couldn't (the source
        or the stream went, or the server refused)."""
        recording = Recording(self._lib, self._context, source, monitor_of)
        if not self._until(lambda: recording.ready or recording.failed, ANSWER_SEC) or (
            not recording.ready
        ):
            error = server_failure(
                self._lib,
                self._context,
                "The sound server didn't start recording that device",
            )
            recording.close()
            raise error
        return recording

    def play(self, pcm: bytes, rate: int, channels: int = 1) -> Playback:
        """`pcm` playing on the default output, once the server has started
        the stream (`run` keeps it going); OSError if it couldn't (no
        output, the server refused)."""
        playback = Playback(self._lib, self._context, pcm, rate, channels)
        if not self._until(lambda: playback.ready or playback.failed, ANSWER_SEC) or (
            not playback.ready
        ):
            playback.close()
            raise OSError("The sound server didn't start playing")
        return playback

    def _properties(self, proplist: Any) -> dict[str, str]:
        """The few properties of a stream or client the app reads."""
        found = {}
        for key in _APP_KEYS:
            value = _text(self._lib.pa_proplist_gets(proplist, key.encode()))
            if value:
                found[key] = value
        return found

    def streams(self) -> list[PlayingStream]:
        """The streams apps play now, each with its app: from the stream's
        own properties, else its client's (`PlayingStream`)."""
        clients: dict[int, dict[str, str]] = {}

        def client(_context: Any, info: Any, last: int, _data: Any) -> None:
            if not last and info:
                i = info.contents
                clients[int(i.index)] = self._properties(i.proplist)

        listed: list[tuple[int, int, int, bool, dict[str, str]]] = []

        def stream(_context: Any, info: Any, last: int, _data: Any) -> None:
            if not last and info:
                i = info.contents
                listed.append(
                    (int(i.index), int(i.sink), int(i.client), bool(i.corked),
                     self._properties(i.proplist))
                )  # fmt: skip

        on_client, on_stream = _CLIENT_CB(client), _SINK_INPUT_CB(stream)
        self._answer(
            self._lib.pa_context_get_client_info_list(self._context, on_client, None)
        )
        self._answer(
            self._lib.pa_context_get_sink_input_info_list(
                self._context, on_stream, None
            )
        )
        return [
            playing_stream(index, sink, corked, own, clients.get(client_index, {}))
            for index, sink, client_index, corked, own in listed
        ]

    def close(self) -> None:
        if self._context:
            self._lib.pa_context_disconnect(self._context)
            self._lib.pa_context_unref(self._context)
            self._context = None
        if self._loop:
            self._lib.pa_mainloop_free(self._loop)
            self._loop = None
