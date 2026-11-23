"""Capturing audio on Linux (polyglotic-hq 546, 547, 550): everything the PC
plays and the mic, through the sound server's own library (`pulse.py`) -
the `AudioCapture` port.

- **Everything the PC plays:** a record stream on the default output's
  *monitor*, found by name from the server's own answer (not the
  `@DEFAULT_MONITOR@` alias: a pipewire-pulse bug once recorded the mic
  through it) - or, with an output chosen while it's plugged in, that
  output's monitor.
- **The mic:** a record stream on the input chosen while it's plugged in,
  else the default input. A default input that is an output's monitor
  (`monitor_of`) is no microphone at all: a PC without one gets its
  output's monitor as the default source (547) - captioning that as the
  learner's own speech would caption the game. Nothing is captured then,
  and the capture says why.
- **Following changes:** each capture subscribes to the server's changes
  (`PulseServer.watch`) and checks what it should record whenever one
  comes - and every DEVICE_POLL_SEC anyway - so a new default output,
  headphones plugged in or the server restarted move the capture on
  within a moment. A stream is never moved by the server itself
  (`PA_STREAM_DONT_MOVE`): it ends with its device, and is opened again
  on what's wanted now.
- **One app** (561, decision 0268): a record stream on each stream the
  app plays (a sink input), from the monitor of the output it plays to,
  with `pa_stream_set_monitor_stream` - only that stream's sound, about
  109 dB clear of the others (547) - each fixed to its stream
  (`PA_STREAM_DONT_MOVE`): when the app's stream ends the record stream
  ends too (`FAILED`), rather than WirePlumber moving it to the mic (547),
  and the capture takes the app's next stream. Several streams are summed
  on the app's clock (`Mixer`); one alone goes straight on. The app is
  known by its key (`apps.app_key`: its executable's name), its streams
  followed through the server's subscription; it has closed once it plays
  nothing and its process is gone.
- **Everything else:** every other app's streams the same way, summed,
  leaving out the one app (known by its process) and Polyglotic's own.

The server delivers 16kHz mono float32 itself, so nothing is converted
here: each piece is stamped on the app's clock (`Stamper`) and kept
continuous (`Timeline`). Linux asks no permission for either.

Each capture runs on a thread of its own, with a connection of its own
made on that thread (libpulse's loop is driven there: `pulse.PulseServer`).
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE
from polyglotic_desktop.platform.linux import apps, pulse
from polyglotic_desktop.platform.timeline import BYTES_PER_SAMPLE, Timeline
from polyglotic_desktop.ports.capture import (
    AppCaptureSupport,
    AppCaptureTrial,
    AudioCallback,
    TrialOutcome,
)

DEVICE_POLL_SEC = 1.0
WAKE_SEC = 0.05
"""How long one pass of the connection's loop may wait for audio."""
RESYNC_SEC = 0.2
"""How far a piece's arrival may stray from the time its samples count to
before the stamps start again from its arrival (a stall, a lost piece)."""
RECONNECT_SEC = 2.0
NO_MIC = "No microphone is plugged in."
NO_OUTPUT = "No speakers or headphones are plugged in."
APP_CLOSED = "The app has closed."
MIX_BEHIND_SEC = 0.1
"""How long several streams' audio waits to be summed: a piece of one
arriving that late still counts (each comes about every 20 ms, 547)."""


class Recording(Protocol):
    @property
    def failed(self) -> bool: ...

    def take(self) -> list[tuple[float, bytes]]: ...

    def close(self) -> None: ...


class Server(Protocol):
    """What a capture asks the sound server (`pulse.PulseServer`)."""

    changes: int

    @property
    def alive(self) -> bool: ...

    def server_info(self) -> pulse.Defaults: ...

    def sinks(self) -> list[pulse.Device]: ...

    def sources(self) -> list[pulse.Device]: ...

    def streams(self) -> list[pulse.PlayingStream]: ...

    def watch(self, what: int = pulse.DEVICES) -> None: ...

    def record(self, source: str, monitor_of: int | None = None) -> Recording: ...

    def run(self, seconds: float) -> None: ...

    def close(self) -> None: ...


def connect() -> Server:
    return pulse.PulseServer()


class Stamper:
    """When each piece's first sample was captured, on the app's clock: the
    first from its arrival less its length, the rest counted on in samples
    - so stamps don't jitter with the threads - until a piece's arrival
    strays more than RESYNC_SEC from its count (then from its arrival)."""

    def __init__(self) -> None:
        self._next: float | None = None

    def __call__(self, arrival: float, seconds: float) -> float:
        guess = arrival - seconds
        if self._next is None or abs(guess - self._next) > RESYNC_SEC:
            start = guess
        else:
            start = self._next
        self._next = start + seconds
        return start


def output_monitor(
    server: Server, chosen: str | None, *, strict_device: bool = False
) -> tuple[str, str] | None:
    """The monitor to record for everything an output plays, with the
    output's description: the output `chosen` (by name) while it's there,
    else the default output; None if there's no output at all."""
    outputs = server.sinks()
    by_name = {sink.name: sink for sink in outputs}
    sink = by_name.get(chosen or "")
    if sink is None and (chosen is None or not strict_device):
        sink = by_name.get(server.server_info().output or "")
    if sink is None or not sink.monitor:
        return None
    return sink.monitor, sink.description


def microphone(server: Server, chosen: str | None) -> tuple[str, str] | None:
    """The input to record as the mic, with its description: `chosen` (by
    name) while it's there, else the default input - unless that is an
    output's monitor, which means there is no microphone (547)."""
    inputs = {source.name: source for source in server.sources()}
    found = inputs.get(chosen or "")
    if found is None or found.monitor_of is not None:
        found = inputs.get(server.server_info().input or "")
    if found is None or found.monitor_of is not None:
        return None
    return found.name, found.description


class _Capture:
    """The thread that runs one capture: connects to the sound server,
    records what `_wanted` names, delivers it continuous, and records
    something else when what's wanted changes."""

    MISSING = ""
    """What `error` says while there's nothing to record."""

    def __init__(
        self,
        device_id: str | None = None,
        connect: Callable[[], Server] = connect,
    ) -> None:
        self.device_id = device_id
        """The device the learner chose (the server's name for it), or None
        for the default."""
        self._connect = connect
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._capturing: str | None = None
        self._error: str | None = None
        self._restarts = 0

    @property
    def restarts(self) -> int:
        return self._restarts

    @property
    def capturing(self) -> str | None:
        return self._capturing

    @property
    def error(self) -> str | None:
        return self._error

    def start(self, on_audio: AudioCallback) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(on_audio,), name=type(self).__name__, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _wanted(self, server: Server) -> tuple[str, str] | None:
        """The source to record now and its name for the learner."""
        raise NotImplementedError

    def _run(self, on_audio: AudioCallback) -> None:
        timeline = Timeline()
        try:
            while not self._stop.is_set():
                try:
                    server = self._connect()
                except OSError as e:
                    self._capturing, self._error = None, str(e)
                    self._restarts += 1
                    self._stop.wait(RECONNECT_SEC)
                    continue
                try:
                    self._connected(server, timeline, on_audio)
                except OSError as e:  # the server went: connect again
                    self._capturing, self._error = None, str(e)
                    self._restarts += 1
                    self._stop.wait(RECONNECT_SEC)
                finally:
                    server.close()
        except Exception as e:  # noqa: BLE001 - the thread must not die quietly
            # Report it by its type, never its text: it could hold anything.
            self._error = f"Capture stopped: {type(e).__name__}"
        finally:
            self._capturing = None

    def _connected(
        self, server: Server, timeline: Timeline, on_audio: AudioCallback
    ) -> None:
        server.watch()
        while not self._stop.is_set():
            seen = server.changes
            wanted = self._wanted(server)
            if wanted is None:
                self._capturing, self._error = None, self.MISSING
                self._idle(server, timeline, on_audio, seen)
                continue
            source, name = wanted
            try:
                recording = server.record(source)
            except OSError as e:  # it went as it was opened: look again
                if not server.alive:
                    raise
                self._restarts += 1
                self._capturing, self._error = None, str(e)
                self._idle(server, timeline, on_audio, seen)
                continue
            try:
                self._capturing, self._error = name, None
                self._pump(server, recording, wanted, timeline, on_audio)
            finally:
                recording.close()

    def _idle(
        self, server: Server, timeline: Timeline, on_audio: AudioCallback, seen: int
    ) -> None:
        """Nothing to record: silence, until the server changes or a poll."""
        until = time.perf_counter() + DEVICE_POLL_SEC
        while not self._stop.is_set() and time.perf_counter() < until:
            server.run(WAKE_SEC)
            for piece in timeline.idle(time.perf_counter()):
                on_audio(*piece)
            if server.changes != seen:
                return
        if not server.alive:
            raise OSError("The sound server went away")

    def _pump(
        self,
        server: Server,
        recording: Recording,
        wanted: Hashable,
        timeline: Timeline,
        on_audio: AudioCallback,
    ) -> None:
        stamper = Stamper()
        seen = server.changes
        next_check = time.perf_counter() + DEVICE_POLL_SEC
        while not self._stop.is_set():
            server.run(WAKE_SEC)
            delivered = False
            for arrival, data in recording.take():
                usable = data[: len(data) - len(data) % BYTES_PER_SAMPLE]
                seconds = len(usable) / BYTES_PER_SAMPLE / VAD_SAMPLE_RATE
                for piece in timeline.packet(stamper(arrival, seconds), usable):
                    on_audio(*piece)
                    delivered = True
            now = time.perf_counter()
            if not delivered:
                for piece in timeline.idle(now):
                    on_audio(*piece)
            if recording.failed:  # its device went: what's wanted now?
                if not server.alive:
                    raise OSError("The sound server went away")
                self._restarts += 1
                return
            if server.changes != seen or now >= next_check:
                seen, next_check = server.changes, now + DEVICE_POLL_SEC
                if self._wanted(server) != wanted:
                    return


class SystemCapture(_Capture):
    """Everything the PC plays: the default output's monitor as the default
    changes - or the output the learner chose, while it's plugged in."""

    MISSING = NO_OUTPUT

    def __init__(
        self,
        device_id: str | None = None,
        connect: Callable[[], Server] = connect,
        *,
        strict_device: bool = False,
    ) -> None:
        super().__init__(device_id, connect)
        self._strict_device = strict_device

    def _wanted(self, server: Server) -> tuple[str, str] | None:
        return output_monitor(server, self.device_id, strict_device=self._strict_device)


class MicCapture(_Capture):
    """A microphone: the one chosen while it's plugged in, else the default
    input - never an output's monitor (no microphone, then)."""

    MISSING = NO_MIC

    def _wanted(self, server: Server) -> tuple[str, str] | None:
        return microphone(server, self.device_id)


# -- one app at a time (561) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tap:
    """One stream an app plays (a sink input, by index), recorded from the
    monitor of the output it plays to."""

    stream: int
    monitor: str


class Mixer:
    """Several streams' audio summed on the app's clock: each piece added
    where its stamp puts it, and what is MIX_BEHIND_SEC old handed on,
    summed and kept within full scale. While no stream delivers, nothing
    is handed on: the timeline fills in silence."""

    def __init__(self) -> None:
        self._start: float | None = None
        self._sum = np.zeros(0, np.float32)

    def add(self, start: float, samples: np.ndarray) -> None:
        if self._start is None or (not len(self._sum) and start > self._start):
            self._start = start  # nothing waiting: from this piece on
        offset = round((start - self._start) * VAD_SAMPLE_RATE)
        if offset < 0:  # its start was handed on already: the rest of it
            samples, offset = samples[-offset:], 0
        end = offset + len(samples)
        if end > len(self._sum):
            grown = np.zeros(end, np.float32)
            grown[: len(self._sum)] = self._sum
            self._sum = grown
        self._sum[offset:end] += samples

    def take(self, now: float, everything: bool = False) -> list[tuple[float, bytes]]:
        """What's ready by `now` (all of it: `everything`) as one piece."""
        if self._start is None or not len(self._sum):
            return []
        ready = round((now - MIX_BEHIND_SEC - self._start) * VAD_SAMPLE_RATE)
        upto = len(self._sum) if everything else min(len(self._sum), ready)
        if upto <= 0:
            return []
        start, out = self._start, np.clip(self._sum[:upto], -1.0, 1.0)
        self._sum = self._sum[upto:]
        self._start += upto / VAD_SAMPLE_RATE
        return [(start, out.astype("<f4").tobytes())]


Wanted = Callable[[str, list[pulse.PlayingStream]], bool]
"""Whether an app's streams are recorded, by its key and its streams."""


def taps_of(
    server: Server, wanted: Wanted
) -> tuple[frozenset[Tap], dict[str, list[pulse.PlayingStream]]]:
    """The streams of the apps `wanted` picks, each from its output's
    monitor; and every app's streams, by key (`apps.grouped`)."""
    monitors = {sink.index: sink.monitor for sink in server.sinks() if sink.monitor}
    groups = apps.grouped(server.streams())
    taps = frozenset(
        Tap(stream.index, monitors[stream.sink])
        for key, members in groups.items()
        if wanted(key, members)
        for stream in members
        if stream.sink in monitors
    )
    return taps, groups


class _Streams(_Capture):
    """Apps' streams: a record stream on each (`Tap`), summed (`Mixer`) -
    opened as the app's streams come and closed as they go, each fixed to
    its stream (`PA_STREAM_DONT_MOVE`: it ends with the stream, 547). One
    stream alone is delivered as it comes, without the mixer's wait."""

    def _taps(self, server: Server) -> frozenset[Tap] | None:
        """The streams to record now; None once the capture has ended."""
        raise NotImplementedError

    def _name(self) -> str:
        """What's captured, for the learner's eyes (`capturing`)."""
        raise NotImplementedError

    def _connected(
        self, server: Server, timeline: Timeline, on_audio: AudioCallback
    ) -> None:
        server.watch(pulse.STREAMS)
        recording: dict[Tap, tuple[Recording, Stamper]] = {}
        mixer = Mixer()
        seen, next_check = server.changes - 1, 0.0
        try:
            while not self._stop.is_set():
                server.run(WAKE_SEC)
                now = time.perf_counter()
                ended = any(kept.failed for kept, _ in recording.values())
                if ended or server.changes != seen or now >= next_check:
                    if not server.alive:
                        raise OSError("The sound server went away")
                    seen, next_check = server.changes, now + DEVICE_POLL_SEC
                    taps = self._taps(server)
                    if taps is None:  # the app has closed
                        self._end(mixer, timeline, on_audio, now)
                        return
                    self._follow(server, taps, recording)
                if not self._deliver(recording, mixer, timeline, on_audio, now):
                    for piece in timeline.idle(now):
                        on_audio(*piece)
        finally:
            for kept, _ in recording.values():
                kept.close()

    def _follow(
        self,
        server: Server,
        taps: frozenset[Tap],
        recording: dict[Tap, tuple[Recording, Stamper]],
    ) -> None:
        """Closes the streams that went, opens the ones that came."""
        for tap in [t for t, (r, _) in recording.items() if t not in taps or r.failed]:
            if tap in taps:
                self._restarts += 1
            recording.pop(tap)[0].close()
        for tap in sorted(taps - recording.keys(), key=lambda t: t.stream):
            try:
                recording[tap] = (server.record(tap.monitor, tap.stream), Stamper())
            except OSError as e:  # it went as it was opened: the next look
                self._restarts += 1
                if not server.alive:
                    raise
                self._error = str(e)
        self._capturing = self._name() if recording else None
        if recording:
            self._error = None

    def _deliver(
        self,
        recording: dict[Tap, tuple[Recording, Stamper]],
        mixer: Mixer,
        timeline: Timeline,
        on_audio: AudioCallback,
        now: float,
    ) -> bool:
        """What the streams delivered, on: one stream's as it came, several
        summed. Whether anything was."""
        alone = len(recording) == 1
        pieces = mixer.take(now, everything=alone)  # what waited, before it
        for kept, stamper in recording.values():
            for arrival, data in kept.take():
                usable = data[: len(data) - len(data) % BYTES_PER_SAMPLE]
                samples = np.frombuffer(usable, "<f4")
                start = stamper(arrival, len(samples) / VAD_SAMPLE_RATE)
                if alone:
                    pieces.append((start, usable))
                else:
                    mixer.add(start, samples)
        pieces += mixer.take(now)
        delivered = False
        for start, data in pieces:
            for piece in timeline.packet(start, data):
                on_audio(*piece)
                delivered = True
        return delivered

    def _end(
        self, mixer: Mixer, timeline: Timeline, on_audio: AudioCallback, now: float
    ) -> None:
        for start, data in mixer.take(now, everything=True):
            for piece in timeline.packet(start, data):
                on_audio(*piece)
        for piece in timeline.ending():
            on_audio(*piece)
        self._capturing, self._error = None, APP_CLOSED
        self._stop.set()  # ended: not connected again


class AppCapture(_Streams):
    """One app's audio: a record stream on each stream it plays (by its
    key, `PlayingApp.name`), summed - re-attached to the app's next stream
    when one ends (547: `FAILED` there means the app's stream ended),
    silence while it plays none, and ended once the app has closed (no
    stream, the process it was chosen by gone, and no other process of it
    running: `apps.running`)."""

    def __init__(
        self,
        process_id: int,
        name: str,
        trial: AppCaptureTrial | None = None,
        connect: Callable[[], Server] = connect,
        alive: Callable[[int], bool] = apps.alive,
        running: Callable[[str], bool] = apps.running,
    ) -> None:
        super().__init__(None, connect)
        self._process_id = process_id
        self._app = name
        self._alive = alive
        self._running = running

    def _name(self) -> str:
        return self._app

    def _taps(self, server: Server) -> frozenset[Tap] | None:
        taps, groups = taps_of(server, lambda key, _members: key == self._app)
        if not groups.get(self._app) and not (
            self._alive(self._process_id) or self._running(self._app)
        ):
            return None
        return taps


class EverythingElseCapture(_Streams):
    """Everything the PC plays but one app (all its streams) and
    Polyglotic's own sounds - captured beside that app's own capture, so
    nothing is heard twice: every other app's streams, summed. The app is
    known by its process; if it closes, this goes on hearing the rest."""

    NAME = "everything else"

    def __init__(
        self,
        process_id: int,
        trial: AppCaptureTrial | None = None,
        connect: Callable[[], Server] = connect,
    ) -> None:
        super().__init__(None, connect)
        self._process_id = process_id
        self._left_out: str | None = None
        """The app's key, once a stream of its process has been seen."""

    def _name(self) -> str:
        return self.NAME

    def _taps(self, server: Server) -> frozenset[Tap]:
        this = os.getpid()

        def wanted(key: str, members: list[pulse.PlayingStream]) -> bool:
            if any(s.process_id == self._process_id for s in members):
                self._left_out = key
            return not apps.is_polyglotic(key, members, this)

        taps, groups = taps_of(server, wanted)
        left_out = groups.get(self._left_out or "", [])
        return taps - {t for t in taps if t.stream in {s.index for s in left_out}}


def app_capture_support(
    load: Callable[[], object] = pulse.library,
) -> AppCaptureSupport:
    """One app alone (polyglotic-hq 561): wherever the sound server's
    library is - PipeWire's pulse server and PulseAudio both give each
    app's stream a monitor of its own; without it nothing is captured."""
    try:
        load()
    except OSError:
        return AppCaptureSupport.NO
    return AppCaptureSupport.YES


def no_windows_build() -> str:
    """`OsAdapters.windows_build`: none on Linux."""
    return ""


class Trial:
    """The `AppCaptureTrial` port: never needed (Linux promises one app
    alone wherever it has a sound server), kept so `main` can ask the same."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._outcome: TrialOutcome | None = None

    @property
    def outcome(self) -> TrialOutcome | None:
        return self._outcome

    def tell(self, outcome: TrialOutcome) -> None:
        with self._lock:
            if self._outcome is None:
                self._outcome = outcome
