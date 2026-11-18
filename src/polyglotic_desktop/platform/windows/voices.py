"""Windows' own voices, through ctypes (polyglotic-hq 286, decision 0077):
the voices listed and a word made into sound by WinRT's
`Windows.Media.SpeechSynthesis.SpeechSynthesizer`, played by winmm's
`waveOut` on the default output device.

- **Which voices:** WinRT lists Windows' OneCore voices - every voice
  Settings > Time & language > Speech > Add voices installs. The older SAPI
  list is a subset (on the user's PC, 2026-11-11: 4 voices against 10 - no
  Vietnamese, no Kangkang, Yaoyao, Yating, Zhiwei or Mark). Narrator's
  natural voices are Narrator's own and aren't listed.
- **Making the sound:** `SynthesizeTextToStreamAsync`, waited for on the
  speaker's thread (60-110 ms for a word on the user's PC, 2026-11-11),
  read out as a WAV file (16 kHz mono 16-bit) - nothing is played by
  Windows' speech itself, so the app has the samples: their length for the
  captions' hush, and silence trimmed (`speaking.trimmed`). The pace is the
  synthesizer's `SpeakingRate` (Windows 10 1803+); the silence after the
  word is Windows' shortest (`AppendedSilence.Min`) where it can be set.
- **Playing it:** `waveOut` on `WAVE_MAPPER` - Windows' default output as it
  is when the word starts - beside any other sound the app plays (the
  sample's PlaySound is one sound at a time per process; this isn't).

Everything here runs on the speaker's thread, in the multithreaded COM
apartment. Words are never logged.
"""

import ctypes
import time
from ctypes import POINTER, byref, c_double, c_int32, c_uint32, c_void_p, wintypes
from dataclasses import replace

from polyglotic_desktop.platform.speaking import Clip, WordTime, clip_of_wav
from polyglotic_desktop.platform.windows.com import (
    GUID,
    ensure_com,
    method,
    query_interface,
    release,
)
from polyglotic_desktop.ports.speaker import Voice

SYNTHESIS_TIMEOUT_SEC = 5.0
"""A word not made by then fails: the speaker isn't held by Windows."""
MIN_RATE, MAX_RATE = 0.5, 6.0
"""`SpeakingRate`'s range (Microsoft's documentation)."""

_combase = ctypes.WinDLL("combase")
_combase.WindowsCreateString.argtypes = [
    wintypes.LPCWSTR,
    c_uint32,
    POINTER(c_void_p),
]
_combase.WindowsCreateString.restype = ctypes.HRESULT
_combase.WindowsDeleteString.argtypes = [c_void_p]
_combase.WindowsDeleteString.restype = ctypes.HRESULT
_combase.WindowsGetStringRawBuffer.argtypes = [c_void_p, POINTER(c_uint32)]
_combase.WindowsGetStringRawBuffer.restype = c_void_p
_combase.RoActivateInstance.argtypes = [c_void_p, POINTER(c_void_p)]
_combase.RoActivateInstance.restype = ctypes.HRESULT
_combase.RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
_combase.RoGetActivationFactory.restype = ctypes.HRESULT
_shcore = ctypes.WinDLL("shcore")
_shcore.CreateStreamOverRandomAccessStream.argtypes = [
    c_void_p,
    POINTER(GUID),
    POINTER(c_void_p),
]
_shcore.CreateStreamOverRandomAccessStream.restype = ctypes.HRESULT

_SYNTHESIZER = "Windows.Media.SpeechSynthesis.SpeechSynthesizer"
# interface ids, each checked by QueryInterface on build 26200 (2026-11-11)
_IID_INSTALLED_VOICES = GUID.parse("{7D526ECC-7533-4C3F-85BE-888C2BAEEBDC}")
_IID_SYNTHESIZER = GUID.parse("{CE9F7C76-97F4-4CED-AD68-D51C458E45C6}")
_IID_SYNTHESIZER2 = GUID.parse("{A7C5ECB2-4339-4D6A-BBF8-C7A4F1544C2E}")
_IID_VOICE = GUID.parse("{B127D6A4-1291-4604-AA9C-83134083352C}")
_IID_OPTIONS = GUID.parse("{A0E23871-CC3D-43C9-91B1-EE185324D83D}")
_IID_OPTIONS2 = GUID.parse("{1CBEF60E-119C-4BED-B118-D250C3A25793}")
_IID_OPTIONS3 = GUID.parse("{401ED877-902C-4814-A582-A5D0C0769FA8}")
_IID_ASYNC_INFO = GUID.parse("{00000036-0000-0000-C000-000000000046}")
_IID_STREAM = GUID.parse("{0000000C-0000-0000-C000-000000000046}")
# the word timings (polyglotic-hq 495; each checked on build 26200, 2026-11-18,
# with Windows PowerShell's WinRT projection - `work/iids495.ps1`)
_IID_TRACK_PROVIDER = GUID.parse("{3B7F2024-F74E-4ADE-93C5-219DA05B6856}")
_IID_MEDIA_TRACK = GUID.parse("{03E1FAFC-C931-491A-B46B-C10EE8C256B7}")
_IID_METADATA_TRACK = GUID.parse("{9E6AED9E-F67A-49A9-B330-CF03B0E9CF07}")
_IID_CUE = GUID.parse("{C7D15E5D-59DC-431F-A0EE-27744323B36D}")
_IID_SPEECH_CUE = GUID.parse("{AEE254DC-1725-4BAD-8043-A98499B017A2}")
# vtable slots: IInspectable's six, then each interface's own in order
_ALL_VOICES = 6  # IInstalledVoicesStatic.get_AllVoices
_VECTOR_GET_AT, _VECTOR_SIZE = 6, 7  # IVectorView<VoiceInformation>
_VOICE_NAME, _VOICE_ID, _VOICE_LANGUAGE = 6, 7, 8  # IVoiceInformation
_SYNTHESIZE_TEXT, _PUT_VOICE = 6, 8  # ISpeechSynthesizer
_OPTIONS = 6  # ISpeechSynthesizer2.get_Options
_PUT_WORD_BOUNDARIES = 7  # ISpeechSynthesizerOptions.put_IncludeWordBoundaryMetadata
_PUT_SPEAKING_RATE = 9  # ISpeechSynthesizerOptions2
_PUT_APPENDED_SILENCE = 7  # ISpeechSynthesizerOptions3
_APPENDED_SILENCE_MIN = 1
_ASYNC_STATUS, _ASYNC_ERROR = 7, 8  # IAsyncInfo
_STARTED, _COMPLETED = 0, 1
_GET_RESULTS = 8  # IAsyncOperation<SpeechSynthesisStream>
_STREAM_READ = 3  # IStream::Read
_TRACKS = 6  # ITimedMetadataTrackProvider.get_TimedMetadataTracks
_TRACK_ID = 6  # IMediaTrack.get_Id: "SpeechWord" for the words' track
_CUES = 12  # ITimedMetadataTrack.get_Cues
_CUE_START = 7  # IMediaCue.get_StartTime (100 ns units)
_CUE_FROM, _CUE_TO = 8, 10  # ISpeechCue.get_Start/EndPositionInInput
_REFERENCE_VALUE = 6  # IReference<int>.get_Value
_WORDS_TRACK = "SpeechWord"
_TICKS_PER_SEC = 10_000_000


class _HString:
    """A WinRT string made from Python's, deleted when done with."""

    def __init__(self, text: str) -> None:
        self.handle = c_void_p()
        units = len(text.encode("utf-16-le")) // 2
        _combase.WindowsCreateString(text, units, byref(self.handle))

    def __enter__(self) -> c_void_p:
        return self.handle

    def __exit__(self, *_: object) -> None:
        _combase.WindowsDeleteString(self.handle)


def _text_of(handle: c_void_p) -> str:
    """A WinRT string returned to us, read and deleted."""
    length = c_uint32()
    raw = _combase.WindowsGetStringRawBuffer(handle, byref(length))
    text = ctypes.wstring_at(raw, length.value) if raw else ""
    _combase.WindowsDeleteString(handle)
    return text


def _string_property(obj: c_void_p, slot: int) -> str:
    handle = c_void_p()
    method(obj, slot, POINTER(c_void_p))(byref(handle))
    return _text_of(handle)


class WindowsVoices:
    """`speaking.Voices` from WinRT: the OneCore voices, and a word made into
    a WAV by one of them. Only ever used on one thread (the speaker's)."""

    def __init__(self) -> None:
        self._synthesizer: c_void_p | None = None

    def found(self) -> tuple[Voice, ...]:
        ensure_com()
        found = []
        for item in self._all():
            try:
                voice = query_interface(item, _IID_VOICE)
                try:
                    found.append(
                        Voice(
                            _string_property(voice, _VOICE_ID),
                            _string_property(voice, _VOICE_NAME),
                            _string_property(voice, _VOICE_LANGUAGE),
                        )
                    )
                finally:
                    release(voice)
            finally:
                release(item)
        return tuple(found)

    def _all(self) -> list[c_void_p]:
        """Every installed voice's object (each to be released)."""
        statics = c_void_p()
        with _HString(_SYNTHESIZER) as name:
            _combase.RoGetActivationFactory(
                name, byref(_IID_INSTALLED_VOICES), byref(statics)
            )
        vector = c_void_p()
        try:
            method(statics, _ALL_VOICES, POINTER(c_void_p))(byref(vector))
            size = c_uint32()
            method(vector, _VECTOR_SIZE, POINTER(c_uint32))(byref(size))
            items = []
            for index in range(size.value):
                item = c_void_p()
                method(vector, _VECTOR_GET_AT, c_uint32, POINTER(c_void_p))(
                    index, byref(item)
                )
                items.append(item)
            return items
        finally:
            release(vector)
            release(statics)

    def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
        ensure_com()
        synthesizer = self._synthesizer_now()
        self._use_voice(synthesizer, voice)
        self._set_rate(synthesizer, rate)
        operation = c_void_p()
        with _HString(text) as words:
            method(synthesizer, _SYNTHESIZE_TEXT, c_void_p, POINTER(c_void_p))(
                words, byref(operation)
            )
        try:
            _wait_for(operation)
            stream = c_void_p()
            method(operation, _GET_RESULTS, POINTER(c_void_p))(byref(stream))
            try:
                clip = clip_of_wav(_read_all(stream))
                return replace(clip, words=_word_times(stream, text))
            finally:
                release(stream)
        finally:
            release(operation)

    def _synthesizer_now(self) -> c_void_p:
        if self._synthesizer is None:
            made = c_void_p()
            with _HString(_SYNTHESIZER) as name:
                _combase.RoActivateInstance(name, byref(made))
            try:
                self._synthesizer = query_interface(made, _IID_SYNTHESIZER)
            finally:
                release(made)
        return self._synthesizer

    def _use_voice(self, synthesizer: c_void_p, wanted: Voice) -> None:
        """The synthesizer speaks in `wanted`; OSError if it's gone."""
        chosen = None
        items = self._all()
        try:
            for item in items:
                voice = query_interface(item, _IID_VOICE)
                if _string_property(voice, _VOICE_ID) == wanted.id and chosen is None:
                    chosen = voice
                else:
                    release(voice)
        finally:
            for item in items:
                release(item)
        if chosen is None:
            raise OSError(f"the {wanted.language} voice isn't installed any more")
        try:
            method(synthesizer, _PUT_VOICE, c_void_p)(chosen)
        finally:
            release(chosen)

    @staticmethod
    def _set_rate(synthesizer: c_void_p, rate: float) -> None:
        """The pace, and the least silence after the word - each where this
        Windows has it."""
        try:
            second = query_interface(synthesizer, _IID_SYNTHESIZER2)
        except OSError:
            return  # before Windows 10 1709: the voice's own pace
        options = c_void_p()
        try:
            method(second, _OPTIONS, POINTER(c_void_p))(byref(options))
            try:
                pace = query_interface(options, _IID_OPTIONS2)
                method(pace, _PUT_SPEAKING_RATE, c_double)(
                    min(MAX_RATE, max(MIN_RATE, rate))
                )
                release(pace)
            except OSError:
                pass  # before 1803
            try:
                silence = query_interface(options, _IID_OPTIONS3)
                method(silence, _PUT_APPENDED_SILENCE, c_int32)(_APPENDED_SILENCE_MIN)
                release(silence)
            except OSError:
                pass  # before 1809
            try:  # when each word sounds: a reading's moving highlight (495)
                words = query_interface(options, _IID_OPTIONS)
                method(words, _PUT_WORD_BOUNDARIES, ctypes.c_bool)(True)
                release(words)
            except OSError:
                pass  # before 1703: no word timings
        finally:
            release(options)
            release(second)


def _wait_for(operation: c_void_p) -> None:
    """Until WinRT's operation has finished; OSError if it failed or took
    longer than `SYNTHESIS_TIMEOUT_SEC`."""
    info = query_interface(operation, _IID_ASYNC_INFO)
    try:
        status = c_int32()
        give_up = time.monotonic() + SYNTHESIS_TIMEOUT_SEC
        while True:
            method(info, _ASYNC_STATUS, POINTER(c_int32))(byref(status))
            if status.value != _STARTED:
                break
            if time.monotonic() > give_up:
                raise OSError("Windows' speech took too long")
            time.sleep(0.002)
        if status.value != _COMPLETED:
            code = ctypes.c_long()
            method(info, _ASYNC_ERROR, POINTER(ctypes.c_long))(byref(code))
            raise OSError(f"Windows' speech failed: {code.value & 0xFFFFFFFF:#x}")
    finally:
        release(info)


def _word_times(stream: c_void_p, text: str) -> tuple[WordTime, ...]:
    """When each word of `text` sounds in the synthesized `stream`: its
    "SpeechWord" track's cues (polyglotic-hq 495) - none if Windows gave
    none, or they can't be read (a reading is still heard, unlit)."""
    try:
        provider = query_interface(stream, _IID_TRACK_PROVIDER)
    except OSError:
        return ()
    found: list[WordTime] = []
    units = _utf16_index(text)
    try:
        for track in _items(provider, _TRACKS):
            try:
                if _track_id(track) == _WORDS_TRACK:
                    found.extend(_cue_times(track, units))
            except OSError:
                pass  # a track that can't be read: its words unlit
            finally:
                release(track)
    except OSError:
        return ()
    finally:
        release(provider)
    return tuple(sorted(found, key=lambda w: w.at))


def _items(obj: c_void_p, slot: int) -> list[c_void_p]:
    """The objects of the `IVectorView` property at `slot` of `obj` (each to
    be released)."""
    vector = c_void_p()
    method(obj, slot, POINTER(c_void_p))(byref(vector))
    try:
        size = c_uint32()
        method(vector, _VECTOR_SIZE, POINTER(c_uint32))(byref(size))
        items = []
        for index in range(size.value):
            item = c_void_p()
            method(vector, _VECTOR_GET_AT, c_uint32, POINTER(c_void_p))(
                index, byref(item)
            )
            items.append(item)
        return items
    finally:
        release(vector)


def _track_id(track: c_void_p) -> str:
    media = query_interface(track, _IID_MEDIA_TRACK)
    try:
        return _string_property(media, _TRACK_ID)
    finally:
        release(media)


def _cue_times(track: c_void_p, units: list[int]) -> list[WordTime]:
    """A words track's cues as word times; `units`: where each UTF-16 unit
    of the text falls in Python's string (WinRT counts in UTF-16)."""
    metadata = query_interface(track, _IID_METADATA_TRACK)
    try:
        cues = _items(metadata, _CUES)
    finally:
        release(metadata)
    found = []
    for cue in cues:
        try:
            timed = query_interface(cue, _IID_CUE)
            speech = query_interface(cue, _IID_SPEECH_CUE)
            try:
                ticks = ctypes.c_int64()
                method(timed, _CUE_START, POINTER(ctypes.c_int64))(byref(ticks))
                first = _reference_int(speech, _CUE_FROM)
                last = _reference_int(speech, _CUE_TO)
            finally:
                release(speech)
                release(timed)
            if first is None or last is None or not 0 <= first <= last < len(units):
                continue
            found.append(
                WordTime(  # Windows' end is the word's last unit, not past it
                    units[first], units[last] + 1, ticks.value / _TICKS_PER_SEC
                )
            )
        finally:
            release(cue)
    return found


def _reference_int(obj: c_void_p, slot: int) -> int | None:
    """An `IReference<int>` property's value; None when it has none."""
    reference = c_void_p()
    method(obj, slot, POINTER(c_void_p))(byref(reference))
    if not reference:
        return None
    try:
        value = c_int32()
        method(reference, _REFERENCE_VALUE, POINTER(c_int32))(byref(value))
        return value.value
    finally:
        release(reference)


def _utf16_index(text: str) -> list[int]:
    """For each UTF-16 unit of `text`, the index of its character in the
    Python string (a character past the BMP is two units)."""
    found = []
    for index, char in enumerate(text):
        found.extend([index] * (2 if ord(char) > 0xFFFF else 1))
    return found


def _read_all(stream: c_void_p) -> bytes:
    """A WinRT stream's bytes, through a COM IStream over it."""
    classic = c_void_p()
    _shcore.CreateStreamOverRandomAccessStream(
        stream, byref(_IID_STREAM), byref(classic)
    )
    try:
        data = bytearray()
        chunk = ctypes.create_string_buffer(65536)
        got = c_uint32()
        read = method(classic, _STREAM_READ, c_void_p, c_uint32, POINTER(c_uint32))
        while True:
            read(chunk, len(chunk), byref(got))
            if not got.value:
                return bytes(data)
            data += chunk.raw[: got.value]
    finally:
        release(classic)


# -- playing: winmm's waveOut -------------------------------------------------------------

_WAVE_MAPPER = 0xFFFFFFFF  # Windows' default output, as it is when opened
_WAVE_FORMAT_PCM = 1
_WAVE_FORMAT_QUERY = 0x1
_CALLBACK_NULL = 0
_WHDR_DONE = 0x1
_MMSYSERR_NOERROR = 0


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


class _WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", c_void_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


_winmm = ctypes.WinDLL("winmm")
_winmm.waveOutOpen.argtypes = [
    POINTER(c_void_p),
    wintypes.UINT,
    POINTER(_WAVEFORMATEX),
    ctypes.c_size_t,
    ctypes.c_size_t,
    wintypes.DWORD,
]
_winmm.waveOutOpen.restype = wintypes.UINT
for _name in ("waveOutPrepareHeader", "waveOutWrite", "waveOutUnprepareHeader"):
    getattr(_winmm, _name).argtypes = [c_void_p, POINTER(_WAVEHDR), wintypes.UINT]
    getattr(_winmm, _name).restype = wintypes.UINT
for _name in ("waveOutReset", "waveOutClose"):
    getattr(_winmm, _name).argtypes = [c_void_p]
    getattr(_winmm, _name).restype = wintypes.UINT


def _format(clip: Clip) -> _WAVEFORMATEX:
    block = 2 * clip.channels
    return _WAVEFORMATEX(
        _WAVE_FORMAT_PCM, clip.channels, clip.rate, clip.rate * block, block, 16, 0
    )


def can_play(clip: Clip) -> bool:
    """Whether Windows' default output takes this clip's format - asked with
    `WAVE_FORMAT_QUERY`: nothing is opened or played."""
    fmt = _format(clip)
    return (
        _winmm.waveOutOpen(
            None, _WAVE_MAPPER, byref(fmt), 0, 0, _CALLBACK_NULL | _WAVE_FORMAT_QUERY
        )
        == _MMSYSERR_NOERROR
    )


class WaveOut:
    """`speaking.Output`: one clip on Windows' default output through
    winmm's waveOut, opened when it starts and closed when it stops."""

    def __init__(self) -> None:
        self._device = c_void_p()
        self._header: _WAVEHDR | None = None
        self._data: ctypes.Array[ctypes.c_char] | None = None  # held while it plays

    def start(self, clip: Clip) -> bool:
        fmt = _format(clip)
        if (
            _winmm.waveOutOpen(
                byref(self._device), _WAVE_MAPPER, byref(fmt), 0, 0, _CALLBACK_NULL
            )
            != _MMSYSERR_NOERROR
        ):
            self._device = c_void_p()
            return False
        self._data = ctypes.create_string_buffer(clip.pcm, len(clip.pcm))
        header = _WAVEHDR()
        header.lpData = ctypes.cast(self._data, c_void_p)
        header.dwBufferLength = len(clip.pcm)
        size = ctypes.sizeof(_WAVEHDR)
        if _winmm.waveOutPrepareHeader(self._device, byref(header), size):
            self.stop()
            return False
        self._header = header
        if _winmm.waveOutWrite(self._device, byref(header), size):
            self.stop()
            return False
        return True

    def playing(self) -> bool:
        header = self._header
        return header is not None and not header.dwFlags & _WHDR_DONE

    def stop(self) -> None:
        if not self._device:
            return
        _winmm.waveOutReset(self._device)  # marks the header done
        if self._header is not None:
            _winmm.waveOutUnprepareHeader(
                self._device, byref(self._header), ctypes.sizeof(_WAVEHDR)
            )
        _winmm.waveOutClose(self._device)
        self._device = c_void_p()
        self._header = None
        self._data = None
