"""Capturing audio on Windows with WASAPI, through ctypes (decision 0006):
one app's audio (process loopback), everything else the PC plays (process
loopback leaving one app out), the whole system's (loopback on an output
device) and the mic - the `AudioCapture` port.

All three ask Windows for 16kHz mono float audio and let its audio engine
convert (AUTOCONVERTPCM with good-quality resampling), so nothing here
resamples. Each capture runs its own thread in the multithreaded COM
apartment, woken by WASAPI's event; packets are stamped with the time
Windows recorded them (their QPC position, the same clock as
`time.perf_counter`, which is the app's clock).

- **One app:** `ActivateAudioInterfaceAsync` on the virtual process
  loopback device with the app's process tree (Windows 11, and Microsoft's
  documented build 20348; tried on Windows 10 from build 19041, with a
  `Trial` that gives up on this PC if it fails - decision 0076). It works
  from any thread with an agile completion handler, checked on build 26200
  (project 016).
- **Everything else:** the same activation, leaving the app's process
  tree out (`EXCLUDE_TARGET_PROCESS_TREE`): beside the app's own capture,
  everything the PC plays is heard once (polyglotic-hq DECISIONS.md #59).
  Windows leaves out one process tree per capture, so only one app can be
  beside it. Checked on build 26200 (polyglotic-hq project 139).
- **Whole system and mic** follow the device the user chose, or Windows'
  default as it changes, as the proof of concept did (`_sync_devices`,
  `_wanted`): checked every `DEVICE_POLL_SEC`; a chosen device that's
  unplugged falls back to the default until it's back; a device that
  failed to open isn't retried until another one is wanted.
- **Silence:** loopback delivers nothing while nothing plays, so gaps are
  filled with zeros (`platform.timeline.Timeline`, shared with macOS), and
  the audio a source delivers is continuous.
"""

import contextlib
import ctypes
import sys
import threading
import time
from collections.abc import Callable
from ctypes import POINTER, byref, c_uint32, c_uint64, c_void_p, wintypes

from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE
from polyglotic_desktop.platform.timeline import BYTES_PER_SAMPLE as _BYTES_PER_SAMPLE
from polyglotic_desktop.platform.timeline import (
    MAX_FILL_SEC,  # noqa: F401 - its tests read it here
    Timeline,
    wanted_device,
)
from polyglotic_desktop.platform.windows.apps import app_peak
from polyglotic_desktop.platform.windows.com import (
    E_NOINTERFACE,
    GUID,
    VT_BLOB,
    ensure_com,
    method,
    release,
)
from polyglotic_desktop.platform.windows.devices import (
    Flow,
    activate,
    active_devices,
    default_device,
)
from polyglotic_desktop.ports.capture import (
    AppCaptureSupport,
    AppCaptureTrial,
    AudioCallback,
    TrialOutcome,
)

DEVICE_POLL_SEC = 1.0
BUFFER_SEC = 1.0  # WASAPI's buffer: room for a slow consumer
WAKE_MS = 100  # wake at least this often without packets

_mmdevapi = ctypes.WinDLL("Mmdevapi")
_mmdevapi.ActivateAudioInterfaceAsync.argtypes = [
    wintypes.LPCWSTR,
    POINTER(GUID),
    c_void_p,
    c_void_p,
    POINTER(c_void_p),
]
_mmdevapi.ActivateAudioInterfaceAsync.restype = ctypes.HRESULT
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = [
    c_void_p,
    wintypes.BOOL,
    wintypes.BOOL,
    wintypes.LPCWSTR,
]
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

_IID_IUnknown = GUID.parse("{00000000-0000-0000-C000-000000000046}")
_IID_IAgileObject = GUID.parse("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
_IID_ICompletionHandler = GUID.parse("{41D949AB-9862-444A-80F6-C261334DA5EB}")
_IID_IAudioClient = GUID.parse("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}")
_IID_IAudioCaptureClient = GUID.parse("{C8ADBD64-E71E-48A0-A4DE-185C395CD317}")

_PROCESS_LOOPBACK_DEVICE = "VAD\\Process_Loopback"
_ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
_INCLUDE_TARGET_PROCESS_TREE = 0
_EXCLUDE_TARGET_PROCESS_TREE = 1
_SHAREMODE_SHARED = 0
_STREAMFLAGS_LOOPBACK = 0x00020000
_STREAMFLAGS_EVENTCALLBACK = 0x00040000
_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
_BUFFERFLAGS_SILENT = 0x2
_WAVE_FORMAT_IEEE_FLOAT = 3
_WAIT_TIMEOUT = 0x102
_SYNCHRONIZE = 0x00100000


class _WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


_FORMAT = _WAVEFORMATEX(
    _WAVE_FORMAT_IEEE_FLOAT,
    1,
    VAD_SAMPLE_RATE,
    VAD_SAMPLE_RATE * _BYTES_PER_SAMPLE,
    _BYTES_PER_SAMPLE,
    32,
    0,
)


# -- process loopback activation ---------------------------------------------

_QueryInterface = ctypes.WINFUNCTYPE(
    ctypes.HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p)
)
_AddRef = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
_ActivateCompleted = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, c_void_p)


class _HandlerVtable(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", _QueryInterface),
        ("AddRef", _AddRef),
        ("Release", _AddRef),
        ("ActivateCompleted", _ActivateCompleted),
    ]


class _Handler(ctypes.Structure):
    _fields_ = [("vtable", POINTER(_HandlerVtable))]


class _LoopbackParams(ctypes.Structure):
    _fields_ = [
        ("ActivationType", ctypes.c_int),
        ("TargetProcessId", wintypes.DWORD),
        ("ProcessLoopbackMode", ctypes.c_int),
    ]


class _BlobVariant(ctypes.Structure):
    _fields_ = [
        ("vt", ctypes.c_ushort),
        ("reserved1", ctypes.c_ushort),
        ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort),
        ("cbSize", ctypes.c_ulong),
        ("pBlobData", c_void_p),
    ]


_activation_lock = threading.Lock()
_activation_done = threading.Event()


def _query_interface(
    this: int, riid: "ctypes._Pointer[GUID]", out: "ctypes._Pointer[c_void_p]"
) -> int:
    if any(
        riid[0].same(iid)
        for iid in (_IID_IUnknown, _IID_IAgileObject, _IID_ICompletionHandler)
    ):
        out[0] = this
        return 0
    out[0] = None
    return E_NOINTERFACE


def _completed(this: int, operation: int) -> int:
    _activation_done.set()
    return 0


# A static COM object: its reference count doesn't matter, it never dies.
_HANDLER_VTABLE = _HandlerVtable(
    _QueryInterface(_query_interface),
    _AddRef(lambda this: 1),
    _AddRef(lambda this: 1),
    _ActivateCompleted(_completed),
)
_HANDLER = _Handler(ctypes.pointer(_HANDLER_VTABLE))


def loopback_params(process_id: int, leave_out: bool = False) -> _LoopbackParams:
    """What process loopback is asked for: the audio of `process_id` and
    its children - or, with `leave_out`, the audio of everything but them."""
    mode = _EXCLUDE_TARGET_PROCESS_TREE if leave_out else _INCLUDE_TARGET_PROCESS_TREE
    return _LoopbackParams(_ACTIVATION_TYPE_PROCESS_LOOPBACK, process_id, mode)


def _activate_process_loopback(process_id: int, leave_out: bool = False) -> c_void_p:
    """An IAudioClient for the audio of `process_id` and its children - or,
    with `leave_out`, of everything else the PC plays."""
    params = loopback_params(process_id, leave_out)
    variant = _BlobVariant(
        VT_BLOB, 0, 0, 0, ctypes.sizeof(params), ctypes.cast(byref(params), c_void_p)
    )
    operation = c_void_p()
    with _activation_lock:
        _activation_done.clear()
        _mmdevapi.ActivateAudioInterfaceAsync(
            _PROCESS_LOOPBACK_DEVICE,
            byref(_IID_IAudioClient),
            byref(variant),
            byref(_HANDLER),
            byref(operation),
        )
        try:
            if not _activation_done.wait(5):
                raise OSError("Windows didn't finish starting the app's capture")
            result, client = ctypes.c_long(), c_void_p()
            method(operation, 3, POINTER(ctypes.c_long), POINTER(c_void_p))(
                byref(result), byref(client)
            )
            if result.value < 0:  # Windows' code kept, for `refusal`
                raise OSError(
                    None,
                    f"Couldn't capture the app: {result.value & 0xFFFFFFFF:#x}",
                    None,
                    result.value,
                )
            return client
        finally:
            release(operation)


# -- the capture thread ----------------------------------------------------------


class _Stream:
    """An initialised, started IAudioClient and its capture client."""

    def __init__(self, client: c_void_p, loopback: bool) -> None:
        self.client = client
        self.capture = c_void_p()
        self.event = _kernel32.CreateEventW(None, False, False, None)
        flags = (
            _STREAMFLAGS_EVENTCALLBACK
            | _STREAMFLAGS_AUTOCONVERTPCM
            | _STREAMFLAGS_SRC_DEFAULT_QUALITY
            | (_STREAMFLAGS_LOOPBACK if loopback else 0)
        )
        try:
            method(
                client,
                3,
                ctypes.c_int,
                wintypes.DWORD,
                ctypes.c_longlong,
                ctypes.c_longlong,
                c_void_p,
                c_void_p,
            )(
                _SHAREMODE_SHARED,
                flags,
                int(BUFFER_SEC * 10_000_000),
                0,
                byref(_FORMAT),
                None,
            )
            method(client, 13, wintypes.HANDLE)(self.event)  # SetEventHandle
            method(client, 14, POINTER(GUID), POINTER(c_void_p))(  # GetService
                byref(_IID_IAudioCaptureClient), byref(self.capture)
            )
            method(client, 10)()  # Start
        except OSError:
            self.close()
            raise
        self._get = method(
            self.capture,
            3,
            POINTER(c_void_p),
            POINTER(c_uint32),
            POINTER(wintypes.DWORD),
            POINTER(c_uint64),
            POINTER(c_uint64),
        )
        self._release = method(self.capture, 4, c_uint32)
        self._next = method(self.capture, 5, POINTER(c_uint32))

    def wait(self) -> bool:
        """Waits for packets; False if none came within WAKE_MS."""
        return bool(_kernel32.WaitForSingleObject(self.event, WAKE_MS) != _WAIT_TIMEOUT)

    def packets(self) -> list[tuple[float, bytes]]:
        """Every packet waiting: (capture time on the app's clock, samples)."""
        out = []
        size = c_uint32()
        self._next(byref(size))
        while size.value:
            data, frames, flags = c_void_p(), c_uint32(), wintypes.DWORD()
            position, qpc = c_uint64(), c_uint64()
            self._get(
                byref(data), byref(frames), byref(flags), byref(position), byref(qpc)
            )
            n = frames.value * _BYTES_PER_SAMPLE
            silent = flags.value & _BUFFERFLAGS_SILENT or not data
            out.append(
                (qpc.value / 1e7, bytes(n) if silent else ctypes.string_at(data, n))
            )
            self._release(frames)
            self._next(byref(size))
        return out

    def close(self) -> None:
        if self.client:
            with contextlib.suppress(OSError):
                method(self.client, 11)()  # Stop
        release(self.capture)
        release(self.client)
        self.capture = self.client = c_void_p()
        if self.event:
            _kernel32.CloseHandle(self.event)
            self.event = None


class _Capture:
    """The thread that runs one capture: opens its stream, delivers audio
    through a `Timeline`, and reopens it when it should move device."""

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
    def _target(self) -> str | None:
        """What it should be capturing now (a device id; the app's name);
        None if nothing can be."""
        raise NotImplementedError

    def _open(self, target: str) -> tuple[_Stream, str]:
        """The started stream for `target`, and its name for the user."""
        raise NotImplementedError

    def _gone(self) -> bool:
        """True when there's no point going on (the app closed)."""
        return False

    def _heard(self, samples: bytes) -> None:
        """A packet as Windows delivered it (silence as zeros)."""

    def _checked(self, seconds: float) -> None:
        """Another check while streaming, `seconds` after the last."""

    def _run(self, on_audio: AudioCallback) -> None:
        try:
            self._deliver(on_audio)
        except Exception as e:  # noqa: BLE001 - the thread must not die quietly
            # Something other than the device failed - the callback, say.
            # Report it (the exception's type, never its text: it could hold
            # anything) so `capturing` doesn't go on claiming audio flows.
            self._error = f"Capture stopped: {type(e).__name__}"
        finally:
            self._capturing = None

    def _deliver(self, on_audio: AudioCallback) -> None:
        ensure_com()
        timeline = Timeline()
        failed: str | None = None
        while not self._stop.is_set():
            target = self._target()
            if target is None or target == failed:
                self._capturing = None
                self._stop.wait(DEVICE_POLL_SEC)
                continue
            try:
                stream, name = self._open(target)
            except OSError as e:
                failed, self._capturing, self._error = target, None, str(e)
                continue
            failed, self._capturing, self._error = None, name, None
            try:
                self._pump(stream, target, timeline, on_audio)
            except OSError as e:  # the device went away mid-stream: reopen
                self._error = str(e)
            finally:
                stream.close()
            if self._gone():
                for piece in timeline.ending():
                    on_audio(*piece)
                self._error = "The app has closed."
                return

    def _pump(
        self, stream: _Stream, target: str, timeline: Timeline, on_audio: AudioCallback
    ) -> None:
        next_check = time.perf_counter() + DEVICE_POLL_SEC
        while not self._stop.is_set():
            got = stream.wait()
            delivered = False
            for start, samples in stream.packets():
                self._heard(samples)
                for piece in timeline.packet(start, samples):
                    on_audio(*piece)
                    delivered = True
            now = time.perf_counter()
            if not got or not delivered:
                for piece in timeline.idle(now):
                    on_audio(*piece)
            if now >= next_check:
                next_check = now + DEVICE_POLL_SEC
                self._checked(DEVICE_POLL_SEC)
                if self._gone() or self._target() != target:
                    return


APP_CAPTURE_MIN_BUILD = 20348
"""Microsoft's documented minimum for process loopback (Windows Server
2022's build; on a PC, Windows 11, 22000 and later): promised."""
APP_CAPTURE_TRY_BUILD = 19041
"""Windows 10 version 2004, where OBS turns its per-app capture on ("MS says
20348, but process filtering seems to work earlier") and win-capture-audio
asks for "an updated version of Windows 10 2004": tried, not promised
(polyglotic-hq 285, decision 0076)."""
SILENT_AFTER_SEC = 10.0
"""How long Windows' meter must hear an app playing, while its capture
gets only silence, before capturing one app is judged not to work here."""
HEARD_PEAK = 0.01
"""Windows' meter of an app's sessions at or above this (-40 dBFS): the app
is plainly playing, not just keeping a quiet stream open."""


def app_capture_support(build: int | None = None) -> AppCaptureSupport:
    """Whether this Windows captures one app alone (`build`: Windows'; this
    PC's if None): promised from APP_CAPTURE_MIN_BUILD, tried from
    APP_CAPTURE_TRY_BUILD, else not (everything the PC plays)."""
    if build is None:
        build = sys.getwindowsversion().build
    if build >= APP_CAPTURE_MIN_BUILD:
        return AppCaptureSupport.YES
    if build >= APP_CAPTURE_TRY_BUILD:
        return AppCaptureSupport.TRY
    return AppCaptureSupport.NO


def refusal(error: OSError) -> TrialOutcome:
    """Windows refused a capture: its code (an HRESULT), or "no answer" when
    the activation never finished - never the error's text."""
    code = getattr(error, "winerror", None)
    if isinstance(code, int):
        return TrialOutcome(False, f"refused {code & 0xFFFFFFFF:#010x}")
    return TrialOutcome(False, "no answer")


class Trial:
    """The `AppCaptureTrial` port on Windows: the first outcome any capture
    tells it stands; thread-safe."""

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


class AppCapture(_Capture):
    """One app's audio, with its child processes (process loopback).

    With a `trial` (a Windows that doesn't promise it: decision 0076) it
    tells the trial what it finds, until something has: Windows refusing
    it (`refusal`); sound in what it gets (it worked); or, for
    SILENT_AFTER_SEC of checks, Windows' meter hearing the app play
    (`peak`, from HEARD_PEAK) while it got only silence, or nothing at all.
    Without one - Windows 11 - it does exactly what it did."""

    def __init__(
        self,
        process_id: int,
        name: str,
        trial: AppCaptureTrial | None = None,
        peak: Callable[[int], float] = app_peak,
    ) -> None:
        super().__init__()
        self._process_id = process_id
        self._name = name
        self._trial = trial
        self._peak = peak
        self._heard_silent = 0.0  # seconds the app played while this got silence

    def _target(self) -> str | None:
        return self._name

    def _open(self, target: str) -> tuple[_Stream, str]:
        try:
            client = _activate_process_loopback(self._process_id)
            return _Stream(client, loopback=True), target
        except OSError as e:
            if self._trial is not None:
                self._trial.tell(refusal(e))
            raise

    def _heard(self, samples: bytes) -> None:
        if (
            self._trial is not None
            and self._trial.outcome is None
            and samples.count(0) < len(samples)  # not all zeros: sound
        ):
            self._trial.tell(TrialOutcome(True))

    def _checked(self, seconds: float) -> None:
        if self._trial is None or self._trial.outcome is not None:
            return
        if self._peak(self._process_id) >= HEARD_PEAK:
            self._heard_silent += seconds
            if self._heard_silent >= SILENT_AFTER_SEC:
                self._trial.tell(TrialOutcome(False, "silent"))

    def _gone(self) -> bool:
        handle = _kernel32.OpenProcess(_SYNCHRONIZE, False, self._process_id)
        if not handle:
            return True
        try:
            return bool(_kernel32.WaitForSingleObject(handle, 0) != _WAIT_TIMEOUT)
        finally:
            _kernel32.CloseHandle(handle)


class EverythingElseCapture(_Capture):
    """Everything the PC plays except one app and its child processes
    (process loopback, leaving the app's tree out) - captured beside that
    app's own capture, so nothing is heard twice. If the app closes it
    goes on hearing everything; `main` then moves it to the whole system's
    capture as the app list changes."""

    NAME = "everything else"

    def __init__(self, process_id: int, trial: AppCaptureTrial | None = None) -> None:
        """`trial`: as `AppCapture`'s, told only of Windows refusing it -
        the app's own capture tells whether sound comes through."""
        super().__init__()
        self._process_id = process_id
        self._trial = trial

    def _target(self) -> str | None:
        return self.NAME

    def _open(self, target: str) -> tuple[_Stream, str]:
        try:
            client = _activate_process_loopback(self._process_id, leave_out=True)
            return _Stream(client, loopback=True), target
        except OSError as e:
            if self._trial is not None:
                self._trial.tell(refusal(e))
            raise


class _DeviceCapture(_Capture):
    _flow: Flow
    _loopback: bool

    def __init__(self, device_id: str | None = None) -> None:
        super().__init__()
        self.device_id = device_id
        """The device the user chose, or None for Windows' default."""

    def _target(self) -> str | None:
        def plugged_in() -> list[str]:
            return [d.id for d in active_devices(self._flow)]

        def default() -> str | None:
            device = default_device(self._flow)
            return device.id if device else None

        return wanted_device(self.device_id, plugged_in, default)

    def _open(self, target: str) -> tuple[_Stream, str]:
        names = {d.id: d.name for d in active_devices(self._flow)}
        return _Stream(activate(target, _IID_IAudioClient), self._loopback), names.get(
            target, target
        )


class SystemCapture(_DeviceCapture):
    """Everything the PC plays on an output device (loopback)."""

    _flow = Flow.OUTPUT
    _loopback = True


class MicCapture(_DeviceCapture):
    """A microphone."""

    _flow = Flow.INPUT
    _loopback = False
