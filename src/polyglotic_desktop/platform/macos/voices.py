"""The Mac's own voices (polyglotic-hq 428; decision 0077's speaker, as
`platform/windows/voices.py` is Windows'): the voices listed and a word
made into sound by AVFoundation's `AVSpeechSynthesizer`, played by an
`AVAudioPlayer` on macOS's default output.

- **Which voices:** `AVSpeechSynthesisVoice.speechVoices` - every voice
  System Settings > Accessibility > Spoken Content has, the enhanced and
  premium ones a learner downloaded included - less the novelty voices
  (Bells, Zarvox...) and the learner's own Personal Voice. Within a
  language the best first (premium, enhanced, then the rest), and among
  equals the one macOS uses for the language: the card says a word in the
  first voice of its language (`ui_next.views.speech.voice_for`).
- **Making the sound:** `writeUtterance:toBufferCallback:`, waited for on
  the speaker's thread - nothing is played by macOS's speech itself, so the
  app has the samples: their length for the captions' hush, and silence
  trimmed (`speaking.trimmed`), as on Windows. The pace: macOS's own is
  0.5 on its 0-1 scale; slower is less (`av_rate`).
- **Playing it:** an `AVAudioPlayer` for each word, on the output macOS
  plays to when the word starts - it follows a change of speakers.

Everything here runs on the speaker's thread, each call inside an
autorelease pool. Words are never logged.
"""

import ctypes
import io
import threading
import time
import wave
from array import array
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from polyglotic_desktop.platform.macos import cf, objc
from polyglotic_desktop.platform.speaking import Clip
from polyglotic_desktop.ports.speaker import Quality, Voice

SYNTHESIS_TIMEOUT_SEC = 5.0
"""A word not made by then fails: the speaker isn't held by macOS."""
QUIET_SEC = 0.5
"""Sound arrived, then none for this long: the word is made (macOS doesn't
always send the empty buffer that says so)."""
NOVELTY, PERSONAL = 1, 2
"""`AVSpeechSynthesisVoiceTraits`: voices the card never uses."""
INT16, FLOAT32 = 3, 1
"""`AVAudioCommonFormat`: the formats a voice's buffers come in."""
OWN_PACE = 0.5
"""`AVSpeechUtteranceDefaultSpeechRate`: a voice's own pace, on macOS's
scale (0 slowest, 1 fastest)."""


@dataclass(frozen=True)
class Listed:
    """A voice as macOS lists it: its quality (1 default, 2 enhanced, 3
    premium) and traits (`NOVELTY`, `PERSONAL`) beside the port's facts."""

    voice: Voice
    quality: int
    traits: int


def ordered(found: Iterable[Listed], usual: Iterable[str]) -> tuple[Voice, ...]:
    """The voices the card may use, best first: no novelty or personal
    voice; within a language premium, enhanced, then the rest, and among
    equals one of `usual` (the voice ids macOS uses for their language)
    first. Otherwise macOS's order."""
    preferred = set(usual)
    kept = [v for v in found if not v.traits & (NOVELTY | PERSONAL)]
    kept.sort(key=lambda v: (-v.quality, v.voice.id not in preferred))
    return tuple(v.voice for v in kept)


def av_rate(rate: float) -> float:
    """The port's pace (1.0 the voice's own, under 1 slower) on macOS's
    scale, whose own pace is 0.5: 0.7 is 0.35."""
    return min(1.0, max(0.0, OWN_PACE * rate))


def wav_of(clip: Clip) -> bytes:
    """A clip as a WAV file, for `AVAudioPlayer`."""
    out = io.BytesIO()
    with wave.open(out, "wb") as written:
        written.setnchannels(clip.channels)
        written.setsampwidth(2)
        written.setframerate(clip.rate)
        written.writeframes(clip.pcm)
    return out.getvalue()


def int16_of_floats(samples: Sequence[float]) -> bytes:
    """Float samples (-1 to 1) as 16-bit little-endian PCM, clipped."""
    return array("h", (int(max(-1.0, min(1.0, s)) * 32767) for s in samples)).tobytes()


class _Made:
    """A word's buffers as macOS hands them over, on its own thread. macOS
    ends a word with an empty buffer (`ended`); until then it may call
    again, so the block that calls `add` is kept alive (`MacVoices`)."""

    def __init__(self) -> None:
        self.parts: list[bytes] = []
        self.rate = 0
        self.done = threading.Event()
        """Set when the word is over or a buffer couldn't be read."""
        self.ended = False
        """macOS's empty buffer came: it calls no more."""
        self.last = 0.0
        self.problem: str | None = None
        self.formats: set[str] = set()
        """Each buffer format seen ("1/22050.0/1/i": common format, rate,
        channels, interleaved) - for the parity checks' report."""

    def add(self, buffer: int) -> None:
        try:
            self._add(buffer)
        except Exception as error:  # noqa: BLE001 - said by type only, after
            self.problem = f"{type(error).__name__}: {error}"
            self.done.set()

    def _add(self, buffer: int) -> None:
        send = objc.send
        frames = send(buffer, "frameLength", restype=ctypes.c_uint32) if buffer else 0
        if not frames:
            self.ended = True
            self.done.set()
            return
        if self.problem is not None:
            return  # a word gone wrong: the rest of it isn't wanted
        form = send(buffer, "format")
        common = send(form, "commonFormat", restype=ctypes.c_ulong)
        rate = send(form, "sampleRate", restype=ctypes.c_double)
        count = send(form, "channelCount", restype=ctypes.c_uint32)
        mixed = send(form, "isInterleaved", restype=ctypes.c_bool)
        self.formats.add(f"{common}/{rate}/{count}/{'i' if mixed else 'n'}")
        self.rate = round(rate)
        step = count if mixed else 1  # one channel: the first
        if common == INT16:
            data = send(
                buffer,
                "int16ChannelData",
                restype=ctypes.POINTER(ctypes.POINTER(ctypes.c_int16)),
            )
            if not data or not data[0]:
                raise ValueError("no samples in an Int16 buffer")
            self.parts.append(array_of(data[0], frames * step, "h")[::step].tobytes())
        elif common == FLOAT32:
            data = send(
                buffer,
                "floatChannelData",
                restype=ctypes.POINTER(ctypes.POINTER(ctypes.c_float)),
            )
            if not data or not data[0]:
                raise ValueError("no samples in a Float32 buffer")
            self.parts.append(int16_of_floats(data[0][: frames * step : step]))
        else:
            raise ValueError(f"buffers in format {common}")
        self.last = time.monotonic()

    def wait(self, timeout: float) -> bool:
        """Until the word is made (True) or `timeout` passes."""
        give_up = time.monotonic() + timeout
        while not self.done.wait(0.05):
            now = time.monotonic()
            if self.parts and now - self.last > QUIET_SEC:
                return True
            if now > give_up:
                return False
        return self.problem is None


def array_of(address: Any, count: int, kind: str) -> "array[int]":
    """`count` samples at a C pointer as a Python array (a copy)."""
    made = array(kind)
    made.frombytes(ctypes.string_at(address, count * made.itemsize))
    return made


class _Slot:
    """The word a block's buffers go to now."""

    def __init__(self) -> None:
        self.word: _Made | None = None

    def add(self, buffer: int) -> None:
        if self.word is not None:
            self.word.add(buffer)


class MacVoices:
    """`speaking.Voices` through AVFoundation: asked only on the speaker's
    thread."""

    def __init__(self) -> None:
        self._synthesizer: int | None = None
        self._slot: _Slot | None = None
        """Where `_block` hands macOS's buffers: the word being made."""
        self._block: objc.Block | None = None
        """The block every word is made with. macOS releases a word's block
        some time after its last buffer: one freed by then crashed the next
        word (GitHub's Mac, 2026-11-17, two runs) - so it lives as long as
        the voices do."""
        self._retired: list[tuple[objc.Block, _Slot]] = []
        """Blocks of words given up on before their last buffer, each still
        handing buffers to its own word: macOS may call them, so they are
        kept, and never call into a new word."""
        self.formats: set[str] = set()
        """The buffer formats macOS has made words in (`_Made.formats`)."""

    def found(self) -> tuple[Voice, ...]:
        with objc.pool():
            objc.load("AVFoundation")
            kind = objc.cls("AVSpeechSynthesisVoice")
            listed = [_listed(v) for v in objc.items(objc.send(kind, "speechVoices"))]
            usual = []
            for language in sorted({v.voice.language for v in listed}):
                tag = objc.string(language)
                with cf.owned(tag):
                    chosen = objc.send(
                        kind, "voiceWithLanguage:", tag, argtypes=[ctypes.c_void_p]
                    )
                    if chosen:
                        usual.append(objc.text(objc.send(chosen, "identifier")) or "")
            return ordered(listed, usual)

    def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
        with objc.pool():
            objc.load("AVFoundation")
            send, p = objc.send, ctypes.c_void_p
            chosen = av_voice(voice)
            if not chosen:
                raise OSError("no voice for the language on this Mac now")
            said = objc.string(text)
            with cf.owned(said):
                utterance = send(
                    objc.cls("AVSpeechUtterance"),
                    "speechUtteranceWithString:",
                    said,
                    argtypes=[p],
                )
            send(utterance, "setVoice:", chosen, restype=None, argtypes=[p])
            send(
                utterance,
                "setRate:",
                av_rate(rate),
                restype=None,
                argtypes=[ctypes.c_float],
            )
            made = _Made()
            block = self._block_for(made)
            send(
                self._synthesizer_made(),
                "writeUtterance:toBufferCallback:",
                utterance,
                block.address,
                restype=None,
                argtypes=[p, p],
            )
            finished = made.wait(SYNTHESIS_TIMEOUT_SEC)
            self.formats |= made.formats
            self._done_with(made)
            if not finished or not made.parts:
                why = made.problem or ("no sound" if finished else "timed out")
                raise OSError(f"macOS's speech didn't make the word: {why}")
            return Clip(b"".join(made.parts), made.rate)

    def _done_with(self, word: _Made) -> None:
        """A word over: its block is the next word's - unless macOS may still
        call it (no last buffer yet), when it's retired with its own word."""
        if not word.ended and self._block is not None and self._slot is not None:
            self._retired.append((self._block, self._slot))
            self._block = self._slot = None

    def _block_for(self, word: _Made) -> objc.Block:
        if self._block is None or self._slot is None:
            self._slot = _Slot()
            self._block = objc.Block(self._slot.add)
        self._slot.word = word
        return self._block

    def _synthesizer_made(self) -> int:
        if self._synthesizer is None:
            kind = objc.cls("AVSpeechSynthesizer")
            made = objc.send(objc.send(kind, "alloc"), "init")  # ours: never released
            if not made:
                raise OSError("macOS's speech synthesizer couldn't be made")
            self._synthesizer = int(made)
        return self._synthesizer


def av_voice(voice: Voice) -> int | None:
    """The `AVSpeechSynthesisVoice` to say a word in `voice` with, or None if
    macOS has no voice for its language. By its id; when macOS no longer
    knows the id, the voice of the same name and language it lists now,
    else its own voice for the language. On GitHub's Mac (2026-11-17,
    polyglotic-hq 452) macOS's voices changed under a running process -
    165 listed, a second later 180, and the id it had just given Samantha
    unknown by id and in the list for the next 15 s - and the card said
    nothing ("the voice isn't on this Mac now")."""
    send, p = objc.send, ctypes.c_void_p
    kind = objc.cls("AVSpeechSynthesisVoice")
    ident = objc.string(voice.id)
    with cf.owned(ident):
        chosen = send(kind, "voiceWithIdentifier:", ident, argtypes=[p])
    if chosen:
        return int(chosen)
    for listed in objc.items(send(kind, "speechVoices")):
        named = objc.text(send(listed, "name"))
        if (
            named == voice.name
            and objc.text(send(listed, "language")) == voice.language
        ):
            return listed
    tag = objc.string(voice.language)
    with cf.owned(tag):
        usual = send(kind, "voiceWithLanguage:", tag, argtypes=[p])
    return int(usual) if usual else None


def quality_of(av: int) -> Quality:
    """The port's `Quality` for macOS's (1 default, 2 enhanced, 3 premium):
    a default voice is a compact one, which Manage Voices can replace with
    an enhanced or premium voice of its language (polyglotic-hq 518). A
    number macOS adds later counts as good."""
    return Quality(av) if av in {q.value for q in Quality} else Quality.GOOD


def _listed(voice: int) -> Listed:
    send = objc.send
    traits = send(voice, "voiceTraits", restype=ctypes.c_ulong)  # macOS 14+
    quality = int(send(voice, "quality", restype=ctypes.c_long))
    return Listed(
        Voice(
            objc.text(send(voice, "identifier")) or "",
            objc.text(send(voice, "name")) or "",
            objc.text(send(voice, "language")) or "",
            quality_of(quality),
        ),
        quality,
        int(traits),
    )


class AudioPlayer:
    """`speaking.Output`: one clip on macOS's default output through an
    `AVAudioPlayer`, made when it starts and let go when it stops."""

    def __init__(self) -> None:
        self._player: int | None = None

    def start(self, clip: Clip) -> bool:
        with objc.pool():
            objc.load("AVFoundation")
            data = cf.create_data(wav_of(clip))
            with cf.owned(data):
                error = ctypes.c_void_p()
                player = objc.send(
                    objc.send(objc.cls("AVAudioPlayer"), "alloc"),
                    "initWithData:error:",
                    data,
                    ctypes.byref(error),
                    argtypes=[ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                )
            if not player:
                return False
            self._player = int(player)
            if not objc.send(player, "play", restype=ctypes.c_bool):
                self.stop()
                return False
            return True

    def playing(self) -> bool:
        player = self._player
        if player is None:
            return False
        with objc.pool():
            return bool(objc.send(player, "isPlaying", restype=ctypes.c_bool))

    def stop(self) -> None:
        player, self._player = self._player, None
        if player is None:
            return
        with objc.pool():
            objc.send(player, "stop", restype=None)
            objc.send(player, "release", restype=None)
