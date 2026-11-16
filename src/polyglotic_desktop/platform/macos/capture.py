"""Capturing audio on a Mac (polyglotic-hq 411): one app's audio, everything
else the Mac plays, the whole system's - through Core Audio process taps
(macOS 14.2+) - and the mic, through PortAudio: the `AudioCapture` port.

- **Taps through catap** (0.6.1, MIT): it builds the tap and its private
  aggregate device with PyObjC and runs Core Audio's real-time callback in
  a small native library of its own, handing buffers to Python on a thread
  of its own - Python never runs on Core Audio's real-time thread, where
  the interpreter's lock would cause drop-outs (171's research). Writing
  that ourselves would mean shipping our own native code; catap's is
  small, tested on macOS 15 and 26, and MIT.
- **One app:** one mono tap of all the app's processes (`apps.grouped`:
  Chrome's and Electron apps' helpers with them), reopened when the app's
  processes change, ended when the app has closed.
- **Everything else:** a global tap leaving out the app's processes and
  Polyglotic's own (a Mac can leave out several; Windows only one).
- **Whole system:** a global tap leaving out Polyglotic's own sounds; or,
  with an output chosen, a tap of that device leaving them out - while
  it's plugged in, else the global tap (`timeline.wanted_device`).
- **Mic:** PortAudio (sounddevice) at the device's own rate - the device
  chosen while it's plugged in, else macOS' default.

Core Audio delivers each device's rate and channels; here every piece is
mixed to mono (`mono_float`), resampled to 16kHz (`Resampler`), stamped on
the app's clock (`Stamper`: `time.perf_counter`, as on Windows) and kept
continuous (`Timeline`).

**A permission not given records silence**, not an error: a tap without
"System Audio Recording", and the mic without the microphone permission,
get zeros. `SilenceWatch` tells that from a quiet source - only zeros for
NOT_ALLOWED_AFTER_SEC while Core Audio says something plays (the mic: is
never perfectly silent) - and the capture says `NOT_ALLOWED` as its
`error`. A permission never yet asked can instead hold the tap's start
while macOS waits for the learner's answer: the watch goes on through
that wait too (`_Capture._opened`). Sound once heard proves the
permission for the app's run (a permission given takes effect when the
app restarts).
"""

import contextlib
import os
import platform
import queue
import threading
import time
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE
from polyglotic_desktop.platform.macos import apps, devices
from polyglotic_desktop.platform.timeline import Timeline, wanted_device
from polyglotic_desktop.ports.capture import (
    NOT_ALLOWED,
    AppCaptureSupport,
    AppCaptureTrial,
    AudioCallback,
    TrialOutcome,
)

DEVICE_POLL_SEC = 1.0
WAKE_SEC = 0.1  # wake at least this often without audio
RESYNC_SEC = 0.2
"""How far a piece's arrival may stray from the time its samples count to
before the stamps start again from its arrival (a stall, a lost buffer, a
device's clock drifting from the app's)."""
NOT_ALLOWED_AFTER_SEC = 10.0
"""How long a capture may get only zeros while something plays before it
says it isn't allowed."""
FILTER_TAPS = 63
"""The resampler's low-pass filter: a windowed sinc this long."""
PASS_HZ = 7200.0
"""Its cut-off: under half of 16kHz, so nothing folds back into speech."""
MAX_PENDING = 512
"""Pieces a capture may queue before catap counts it as too slow."""
MIN_TAP_VERSION = (14, 2)
"""Core Audio's process taps: macOS 14.2 and later."""


@dataclass(frozen=True, slots=True)
class Format:
    """A piece's format as Core Audio or PortAudio delivers it: interleaved
    linear PCM, `bits` per sample, float or signed integer."""

    rate: float
    channels: int
    is_float: bool = True
    bits: int = 32


def mono_float(data: bytes, form: Format) -> np.ndarray:
    """`data` (interleaved, `form`) as mono float32 samples from -1 to 1."""
    if form.is_float:
        dtype = np.dtype("<f4") if form.bits == 32 else np.dtype("<f8")
        samples = np.frombuffer(data, dtype=dtype).astype(np.float32)
    else:
        width = form.bits // 8
        if width == 3:  # packed 24-bit: widen each sample to 32 bits
            raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3)
            wide = np.zeros((len(raw), 4), dtype=np.uint8)
            wide[:, 1:] = raw
            samples = wide.view("<i4").reshape(-1).astype(np.float32)
            samples /= float(2**31)
        else:
            dtype = np.dtype(f"<i{width}")
            samples = np.frombuffer(data, dtype=dtype).astype(np.float32)
            samples /= float(2 ** (form.bits - 1))
    channels = max(1, form.channels)
    usable = len(samples) - len(samples) % channels
    if channels == 1:
        return samples[:usable]
    return samples[:usable].reshape(-1, channels).mean(axis=1, dtype=np.float32)


def _low_pass(rate: float) -> np.ndarray:
    """A windowed-sinc low-pass at PASS_HZ for audio at `rate`, unity gain."""
    cutoff = PASS_HZ / rate  # cycles per sample
    n = np.arange(FILTER_TAPS) - (FILTER_TAPS - 1) / 2
    taps = 2 * cutoff * np.sinc(2 * cutoff * n) * np.blackman(FILTER_TAPS)
    return (taps / taps.sum()).astype(np.float64)


class Resampler:
    """Audio at `rate` to 16kHz, piece by piece, as one continuous stream:
    low-passed under 8kHz (so nothing folds back), then read at 16kHz by
    linear interpolation. At 16kHz already, it passes audio through."""

    def __init__(self, rate: float) -> None:
        self.rate = rate
        self._step = rate / VAD_SAMPLE_RATE
        self._filter = _low_pass(rate) if rate > VAD_SAMPLE_RATE else None
        self._history = np.zeros(FILTER_TAPS - 1)
        self._first = 0  # the index of this piece's first sample, in the stream
        self._last: float | None = None  # the previous piece's last sample
        self._next = 0.0  # where the next 16kHz sample is read, in the stream

    def __call__(self, samples: np.ndarray) -> np.ndarray:
        if self.rate == VAD_SAMPLE_RATE:
            return samples.astype(np.float32)
        if not len(samples):
            return np.zeros(0, dtype=np.float32)
        data = samples.astype(np.float64)
        if self._filter is not None:
            joined = np.concatenate([self._history, data])
            self._history = joined[-(FILTER_TAPS - 1) :]
            data = np.convolve(joined, self._filter, mode="valid")
        start = self._first
        if self._last is not None:  # read across the join with the last piece
            data = np.concatenate([[self._last], data])
            start -= 1
        end = self._first + len(samples) - 1  # the last index readable now
        count = int(np.floor((end - self._next) / self._step)) + 1
        out = np.zeros(0, dtype=np.float32)
        if count > 0:
            at = self._next + self._step * np.arange(count)
            out = np.interp(at, np.arange(start, start + len(data)), data)
            out = out.astype(np.float32)
            self._next += self._step * count
        self._first += len(samples)
        self._last = float(data[-1])
        return out


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


class Permission:
    """Whether a permission (system audio recording, or the microphone) is
    known to be given for this run of the app: once any capture that needs
    it has heard sound, it is - for every capture after (thread-safe)."""

    def __init__(self) -> None:
        self._given = threading.Event()

    @property
    def given(self) -> bool:
        return self._given.is_set()

    def heard(self) -> None:
        self._given.set()


TAPS = Permission()
"""System Audio Recording (Privacy & Security), for every tap."""
MIC = Permission()
"""The microphone (Privacy & Security), for the mic."""


class SilenceWatch:
    """Tells a capture the OS isn't allowed to hear from a quiet one: it got
    only zeros for NOT_ALLOWED_AFTER_SEC of checks while Core Audio said
    something it taps plays. Sound proves the permission (`Permission`)."""

    def __init__(self, permission: Permission, after: float | None = None) -> None:
        self._permission = permission
        self._after = NOT_ALLOWED_AFTER_SEC if after is None else after
        self._silent = 0.0
        self.not_allowed = False

    def heard(self, samples: np.ndarray) -> None:
        """Samples as the OS delivered them."""
        if len(samples) and bool(np.any(samples)):
            self._permission.heard()
            self.not_allowed = False

    def checked(self, seconds: float, playing: bool) -> bool:
        """Another check, `seconds` after the last; `playing`: Core Audio
        says something this capture taps plays. Whether it's not allowed."""
        if self._permission.given:
            self.not_allowed = False
        elif playing:
            self._silent += seconds
            self.not_allowed = self._silent >= self._after
        return self.not_allowed


Piece = tuple[float, bytes, Format]
"""A piece as it arrived: when (the app's clock), its data, its format."""


class Stream:
    """A started tap or mic: the pieces it delivered, through a queue its
    callback fills on a thread of the OS's or catap's."""

    def __init__(self) -> None:
        self._pieces: queue.Queue[Piece] = queue.Queue()
        self.failed = False

    def put(self, data: bytes, form: Format) -> None:
        """A piece arrived, now (from the delivering thread)."""
        self._pieces.put((time.perf_counter(), data, form))

    def pieces(self, wait: float) -> list[Piece]:
        """Every piece waiting, after waiting up to `wait` seconds for one."""
        try:
            got = [self._pieces.get(timeout=wait)]
        except queue.Empty:
            return []
        while True:
            try:
                got.append(self._pieces.get_nowait())
            except queue.Empty:
                return got

    def close(self) -> None:
        """Stops it; nothing more is put."""


class _Opening:
    """`open_(target)` on a thread of its own, so the capture's thread can
    watch while it waits: `done` once it returned (or raised), `result` what
    it gave. A stream it gives after being abandoned is closed."""

    def __init__(
        self,
        open_: Callable[[Any], tuple[Stream, str]],
        target: Any,
        name: str,
    ) -> None:
        self.done = threading.Event()
        self.result: tuple[Stream, str] | BaseException | None = None
        self._lock = threading.Lock()
        self._abandoned = False
        threading.Thread(
            target=self._run, args=(open_, target), name=name, daemon=True
        ).start()

    def _run(self, open_: Callable[[Any], tuple[Stream, str]], target: Any) -> None:
        result: tuple[Stream, str] | BaseException
        try:
            result = open_(target)
        except Exception as e:  # noqa: BLE001 - handed to the capture's thread
            result = e
        with self._lock:
            self.result = result
            abandoned = self._abandoned
        self.done.set()
        if abandoned and isinstance(result, tuple):
            result[0].close()

    def abandon(self) -> None:
        """Nobody wants the stream any more: closed now if it has opened,
        else as soon as it does."""
        with self._lock:
            self._abandoned = True
            result = self.result
        if isinstance(result, tuple):
            result[0].close()


class _Capture:
    """The thread that runs one capture: opens its stream, delivers its
    audio converted and continuous, watches for silence it isn't allowed
    past, and reopens it when what it should capture changes."""

    _permission: Permission

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._capturing: str | None = None
        self._error: str | None = None

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

    # What each kind of capture decides:
    def _target(self) -> Hashable | None:
        """What it should be capturing now (processes, a device), compared
        each check; None if nothing can be."""
        raise NotImplementedError

    def _open(self, target: Any) -> tuple[Stream, str]:
        """The started stream for `target`, and its name for the user."""
        raise NotImplementedError

    def _gone(self) -> bool:
        """True when there's no point going on (the app closed)."""
        return False

    def _playing(self) -> bool:
        """Whether Core Audio says something this capture hears plays."""
        return True

    def _run(self, on_audio: AudioCallback) -> None:
        try:
            self._deliver(on_audio)
        except Exception as e:  # noqa: BLE001 - the thread must not die quietly
            # Report it by its type, never its text: it could hold anything.
            self._error = f"Capture stopped: {type(e).__name__}"
        finally:
            self._capturing = None

    def _deliver(self, on_audio: AudioCallback) -> None:
        timeline = Timeline()
        watch = SilenceWatch(self._permission)
        failed: Hashable | None = None
        while not self._stop.is_set():
            target = self._target()
            if target is None or target == failed:
                self._capturing = None
                self._stop.wait(DEVICE_POLL_SEC)
                continue
            try:
                opened = self._opened(target, watch)
            except OSError as e:
                failed, self._capturing, self._error = target, None, str(e)
                continue
            if opened is None:  # stopped while macOS still held the open
                return
            stream, name = opened
            failed, self._capturing = None, name
            self._error = NOT_ALLOWED if watch.not_allowed else None
            try:
                self._pump(stream, target, timeline, watch, on_audio)
            except OSError as e:  # the tap or device failed mid-stream: reopen
                self._error = str(e)
                self._stop.wait(DEVICE_POLL_SEC)  # not at once: it may fail again
            finally:
                stream.close()
            if self._gone():
                for piece in timeline.ending():
                    on_audio(*piece)
                self._error = "The app has closed."
                return

    def _opened(self, target: Any, watch: SilenceWatch) -> tuple[Stream, str] | None:
        """`_open(target)`, with the silence watch going on meanwhile: macOS
        can hold a tap's or the mic's start until the learner answers its
        permission prompt (polyglotic-hq 419: with the permission never
        asked, a tap of a playing app never opened on GitHub's Mac), and
        that wait says NOT_ALLOWED just as a tap's zeros do. None if the
        capture is stopped first; the stream, if it opens after, is closed."""
        opening = _Opening(self._open, target, f"{type(self).__name__} opening")
        next_check = time.perf_counter() + DEVICE_POLL_SEC
        while not opening.done.wait(WAKE_SEC):
            if self._stop.is_set():
                opening.abandon()
                return None
            now = time.perf_counter()
            if now >= next_check:
                next_check = now + DEVICE_POLL_SEC
                if watch.checked(DEVICE_POLL_SEC, self._playing()):
                    self._error = NOT_ALLOWED
        result = opening.result
        if isinstance(result, BaseException):
            raise result
        return result

    def _pump(
        self,
        stream: Stream,
        target: Hashable,
        timeline: Timeline,
        watch: SilenceWatch,
        on_audio: AudioCallback,
    ) -> None:
        resampler: Resampler | None = None
        stamper = Stamper()
        next_check = time.perf_counter() + DEVICE_POLL_SEC
        while not self._stop.is_set():
            delivered = False
            for arrival, data, form in stream.pieces(WAKE_SEC):
                samples = mono_float(data, form)
                watch.heard(samples)
                if resampler is None or resampler.rate != form.rate:
                    resampler, stamper = Resampler(form.rate), Stamper()
                start = stamper(arrival, len(samples) / form.rate)
                out = resampler(samples)
                for piece in timeline.packet(start, out.tobytes()):
                    on_audio(*piece)
                    delivered = True
            now = time.perf_counter()
            if not delivered:
                for piece in timeline.idle(now):
                    on_audio(*piece)
            if stream.failed:
                raise OSError("Core Audio stopped the capture")
            if now >= next_check:
                next_check = now + DEVICE_POLL_SEC
                if watch.checked(DEVICE_POLL_SEC, self._playing()):
                    self._error = NOT_ALLOWED
                elif self._error == NOT_ALLOWED:
                    self._error = None
                if self._gone() or self._target() != target:
                    return


# -- taps ---------------------------------------------------------------------


def taps_supported(version: str | None = None) -> bool:
    """Whether this macOS has process taps (`version`: macOS' own, "14.2.1";
    this Mac's if None)."""
    if version is None:
        version = platform.mac_ver()[0]
    try:
        found = tuple(int(part) for part in version.split(".")[:2])
    except ValueError:
        return False
    return bool(found) and (found + (0,))[:2] >= MIN_TAP_VERSION


def app_capture_support() -> AppCaptureSupport:
    """One app alone: yes from macOS 14.2 (its taps), else no - and then
    nothing is captured at all, since every capture of what the Mac plays
    is a tap (the system capture says why)."""
    return AppCaptureSupport.YES if taps_supported() else AppCaptureSupport.NO


def no_windows_build() -> str:
    """`OsAdapters.windows_build`: none on a Mac (the log's line on trying
    apps one by one is Windows' alone: taps are promised from 14.2)."""
    return ""


class Trial:
    """The `AppCaptureTrial` port: never needed on a Mac (taps are promised
    from 14.2: `app_capture_support`), kept so `main` can ask the same."""

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


@dataclass(frozen=True, slots=True)
class TapTarget:
    """What a tap captures: the processes it names (Core Audio's process
    objects) - only them, or everything but them (`leave_out`) - on one
    output device (its UID) or all of them (None)."""

    processes: frozenset[int]
    leave_out: bool
    device: str | None = None


class _TapStream(Stream):
    """A started catap session for a `TapTarget`."""

    def __init__(self, target: TapTarget) -> None:
        super().__init__()
        try:
            import catap  # macOS 14.2+ only: imported when first asked

            ids = sorted(target.processes)
            if target.device is not None:
                device = catap.find_audio_device_by_uid(target.device)
                if device is None or not device.output_streams:
                    raise OSError("The output device has gone")
                description = (
                    catap.TapDescription.excluding_processes_for_device_stream(
                        ids, device.output_streams[0]
                    )
                )
            elif target.leave_out:
                description = catap.TapDescription.mono_global_tap_excluding(ids)
            else:
                description = catap.TapDescription.mono_mixdown_of_processes(ids)
            description.name = "Polyglotic"
            description.is_private = True
            self._session = catap.RecordingSession(
                description, on_buffer=self._buffer, max_pending_buffers=MAX_PENDING
            )
            self._session.start()
        except Exception as e:  # noqa: BLE001 - catap's errors, by type only
            raise OSError(f"Couldn't start the tap: {type(e).__name__}") from None

    def _buffer(self, buffer: Any) -> None:
        form = buffer.format
        self.put(
            bytes(buffer.data),
            Format(
                float(form.sample_rate),
                int(form.num_channels),
                bool(form.is_float),
                int(form.bits_per_sample),
            ),
        )
        if self._session.capture_failed:
            self.failed = True

    def pieces(self, wait: float) -> list[Piece]:
        got = super().pieces(wait)
        if self._session.capture_failed:
            self.failed = True
        return got

    def close(self) -> None:
        with contextlib.suppress(Exception):  # closing: nothing more to do
            self._session.close()


def _own(processes: Sequence[apps.AudioProcess]) -> frozenset[int]:
    """Polyglotic's own processes' objects: its sounds are never captioned."""
    this = os.getpid()
    return frozenset(
        p.object_id
        for members in apps.grouped(processes).values()
        if apps.is_polyglotic(members, this)
        for p in members
    )


class AppCapture(_Capture):
    """One app's audio, with its helper processes: a tap of every process
    of the app (by its bundle ID, `PlayingApp.name`), reopened when they
    change, ended once the app has closed."""

    _permission = TAPS

    def __init__(
        self,
        process_id: int,
        name: str,
        trial: AppCaptureTrial | None = None,
        processes: Callable[[], list[apps.AudioProcess]] = apps.audio_processes,
        open_tap: Callable[[TapTarget], Stream] = _TapStream,
        alive: Callable[[int], bool] = apps.alive,
    ) -> None:
        super().__init__()
        self._process_id = process_id
        self._name = name
        self._processes = processes
        self._open_tap = open_tap
        self._alive = alive

    def _members(self) -> list[apps.AudioProcess]:
        return apps.grouped(self._processes()).get(self._name, [])

    def _target(self) -> Hashable | None:
        found = frozenset(p.object_id for p in self._members())
        return TapTarget(found, leave_out=False) if found else None

    def _open(self, target: Any) -> tuple[Stream, str]:
        return self._open_tap(target), self._name

    def _gone(self) -> bool:
        return not self._alive(self._process_id) and not self._members()

    def _playing(self) -> bool:
        return any(p.playing for p in self._members())


class _GlobalCapture(_Capture):
    """A global tap: everything the Mac plays but Polyglotic's own sounds
    and those of `_left_out`'s processes."""

    _permission = TAPS

    def __init__(
        self,
        processes: Callable[[], list[apps.AudioProcess]] = apps.audio_processes,
        open_tap: Callable[[TapTarget], Stream] = _TapStream,
    ) -> None:
        super().__init__()
        self._processes = processes
        self._open_tap = open_tap

    def _left_out(self, found: list[apps.AudioProcess]) -> frozenset[int]:
        return _own(found)

    def _device(self) -> str | None:
        return None

    def _target(self) -> Hashable | None:
        found = self._processes()
        return TapTarget(self._left_out(found), leave_out=True, device=self._device())

    def _playing(self) -> bool:
        found = self._processes()
        left_out = self._left_out(found)
        return any(p.playing and p.object_id not in left_out for p in found)


class EverythingElseCapture(_GlobalCapture):
    """Everything the Mac plays except one app (with its helpers) and
    Polyglotic - captured beside that app's own capture, so nothing is
    heard twice. If the app closes it goes on hearing everything."""

    NAME = "everything else"

    def __init__(
        self,
        process_id: int,
        trial: AppCaptureTrial | None = None,
        processes: Callable[[], list[apps.AudioProcess]] = apps.audio_processes,
        open_tap: Callable[[TapTarget], Stream] = _TapStream,
    ) -> None:
        super().__init__(processes, open_tap)
        self._process_id = process_id

    def _left_out(self, found: list[apps.AudioProcess]) -> frozenset[int]:
        groups = apps.grouped(found)
        app = next(
            (m for m in groups.values() if any(p.pid == self._process_id for p in m)),
            [],
        )
        return _own(found) | {p.object_id for p in app}

    def _open(self, target: Any) -> tuple[Stream, str]:
        return self._open_tap(target), self.NAME


def _output_uids() -> list[str]:
    return [d.uid for d in devices.audio_devices() if d.outputs]


def _default_output() -> str | None:
    return next(
        (d.uid for d in devices.audio_devices() if d.outputs and d.default_output),
        None,
    )


class SystemCapture(_GlobalCapture):
    """Everything the Mac plays but Polyglotic's own sounds: on the output
    the learner chose while it's plugged in, else on every output (a
    global tap, which follows macOS' default as it changes)."""

    NAME = "everything the Mac plays"

    def __init__(
        self,
        device_id: str | None = None,
        processes: Callable[[], list[apps.AudioProcess]] = apps.audio_processes,
        open_tap: Callable[[TapTarget], Stream] = _TapStream,
        outputs: Callable[[], list[str]] = _output_uids,
    ) -> None:
        super().__init__(processes, open_tap)
        self.device_id = device_id
        """The output the learner chose, or None for all of them."""
        self._outputs = outputs

    def _device(self) -> str | None:
        if self.device_id is None:
            return None
        return wanted_device(self.device_id, self._outputs, lambda: None)

    def _open(self, target: Any) -> tuple[Stream, str]:
        name = self.NAME
        if target.device is not None:
            names = {d.uid: d.name for d in devices.audio_devices()}
            name = names.get(target.device, name)
        return self._open_tap(target), name


# -- the mic ------------------------------------------------------------------


class _MicStream(Stream):
    """A started PortAudio input on the device with `uid` (None: macOS'
    default), at its own rate, one channel."""

    def __init__(self, uid: str | None) -> None:
        super().__init__()
        try:
            import sounddevice as sd  # macOS only here: imported when first asked

            found = [
                (str(d["name"]), int(d["max_input_channels"]))
                for d in sd.query_devices()
            ]
            index = devices.portaudio_index(uid, devices.audio_devices(), found)
            info = (
                sd.query_devices(index, "input")
                if index is not None
                else (sd.query_devices(kind="input"))
            )
            rate = float(info["default_samplerate"])
            self.name = str(info["name"])
            form = Format(rate, 1)

            def callback(data: Any, frames: int, when: Any, status: Any) -> None:
                self.put(data.tobytes(), form)

            self._stream = sd.InputStream(
                device=index,
                channels=1,
                samplerate=rate,
                dtype="float32",
                callback=callback,
            )
            self._stream.start()
        except Exception as e:  # noqa: BLE001 - PortAudio's errors, by type only
            raise OSError(f"Couldn't open the mic: {type(e).__name__}") from None

    def pieces(self, wait: float) -> list[Piece]:
        got = super().pieces(wait)
        if not self._stream.active:  # PortAudio stopped it: the device went
            self.failed = True
        return got

    def close(self) -> None:
        with contextlib.suppress(Exception):  # closing: nothing more to do
            self._stream.close()


def _mic_uids() -> list[str]:
    return [d.uid for d in devices.audio_devices() if d.inputs]


def _default_mic() -> str | None:
    return next(
        (d.uid for d in devices.audio_devices() if d.inputs and d.default_input),
        None,
    )


def _open_mic(uid: str) -> tuple[Stream, str]:
    stream = _MicStream(uid or None)
    return stream, stream.name


class MicCapture(_Capture):
    """A microphone: the one chosen while it's plugged in, else macOS'
    default as it changes."""

    _permission = MIC

    def __init__(
        self,
        device_id: str | None = None,
        open_mic: Callable[[str], tuple[Stream, str]] = _open_mic,
        mics: Callable[[], list[str]] = _mic_uids,
        default: Callable[[], str | None] = _default_mic,
    ) -> None:
        super().__init__()
        self.device_id = device_id
        """The mic the learner chose, or None for macOS' default."""
        self._open_mic = open_mic
        self._mics = mics
        self._default = default

    def _target(self) -> Hashable | None:
        # no device listed (Core Audio can't say): PortAudio's default
        return wanted_device(self.device_id, self._mics, self._default) or ""

    def _open(self, target: Any) -> tuple[Stream, str]:
        return self._open_mic(target)
