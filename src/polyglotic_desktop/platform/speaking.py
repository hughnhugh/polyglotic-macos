"""The `Speaker` port on a thread of its own, over an OS's voices and sound
output (polyglotic-hq 286, decision 0077) - Windows': `windows.voices`.

`SpeakerThread` lists the voices in the background - first when asked
(`voices`) or told to (`look_for_voices`: `main`, once the app has
started, so the start never waits on it), again when the list is older
than `VOICES_STALE_SEC` and someone asks - makes each word's sound
(`Voices.synthesize`, tens of milliseconds - never on the interface
thread), trims the silence the voice puts before it, plays it through a new
`Output` (the OS's default device as it is now), and says when the sound
starts (`sounding`) and when it's over (`ended`). One word at a time: a new
`say` stops the one before, and a `say` made while another word was still
being made replaces it before it's heard - ten fast clicks say the last.

A reading (`read`, the `Reader` port - polyglotic-hq 495, decision 0229) is
the same, a chunk at a time: each chunk (a sentence) made, played and
hushed on its own (`sounding` per chunk: a reading stopped half-way leaves
the captions hushed no longer than the chunk it was in), the next made
while one plays, a short pause between; and each word told as it sounds
(`spoken`), from the voice's own word times. Readings and words share the
one speaker: either stops the other.

Holds the words it says only while saying them: never logged.
"""

import io
import logging
import threading
import time
import wave
from array import array
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from polyglotic_desktop.ports.speaker import Ended, Sounding, Spoken, Voice

log = logging.getLogger(__name__)

VOICES_STALE_SEC = 5.0
"""The voices are looked for again when asked about after this long: a voice
added in Windows' settings is found while the app runs."""
POLL_SEC = 0.02
"""How often a word playing is checked for its end."""
LEAD_SEC = 0.02
"""Silence kept before a word's first sound: the voice puts 0.13-0.18 s
there (Windows' voices, measured 2026-11-11) - trimmed, the word comes
sooner after the click, and the captions leave out less (`hush`)."""
TAIL_SEC = 0.08
"""Silence kept after a word's last sound."""
SILENT = 330
"""A 16-bit sample this loud or quieter is silence (about -40 dBFS)."""
OVERRUN_SEC = 2.0
"""A word whose output never says it's done is stopped this long after its
length: a device that stops answering doesn't hold the speaker."""
CHUNK_PAUSE_SEC = 0.15
"""Silence between a reading's chunks, beside the `TAIL_SEC` and `LEAD_SEC`
kept: about a sentence's pause (polyglotic-hq 488 used 0.25 s in all)."""
KEPT_BYTES = 10_000_000
"""The readings' sound kept in memory to play again without making it again
- about the last 20 readings (488: 7 s each at 16 kHz is about 0.22 MB a
voice that keeps 16-bit mono; more for a voice at 24 kHz or 48 kHz).
Memory only: never written anywhere, gone when the app closes."""


@dataclass(frozen=True)
class WordTime:
    """A word of the text said: characters `[start, end)` of the text the
    voice was given, sounding from `at` seconds into the clip."""

    start: int
    end: int
    at: float


@dataclass(frozen=True)
class Clip:
    """A word's sound: 16-bit little-endian PCM, `rate` per second,
    `channels` interleaved; `words`: when each word of its text sounds, if
    the voice says (Windows' do, decision 0229) - else none."""

    pcm: bytes
    rate: int
    channels: int = 1
    words: tuple[WordTime, ...] = ()

    @property
    def frames(self) -> int:
        return len(self.pcm) // (2 * self.channels)

    @property
    def seconds(self) -> float:
        return self.frames / self.rate


def clip_of_wav(data: bytes) -> Clip:
    """A WAV file's 16-bit PCM as a clip; ValueError if it's another kind."""
    try:
        with wave.open(io.BytesIO(data)) as read:
            if read.getsampwidth() != 2:
                raise ValueError(f"{read.getsampwidth() * 8}-bit audio")
            frames = read.readframes(read.getnframes())
            return Clip(frames, read.getframerate(), read.getnchannels())
    except (wave.Error, EOFError) as error:
        raise ValueError(f"not a WAV file: {error}") from error


def trimmed(clip: Clip) -> Clip:
    """`clip` with its silence before the first sound cut to `LEAD_SEC` and
    after the last to `TAIL_SEC` - its word times moved with it; a silent
    clip as it is."""
    samples = array("h")
    samples.frombytes(clip.pcm[: clip.frames * 2 * clip.channels])
    count = len(samples)
    start = next((i for i in range(count) if abs(samples[i]) > SILENT), None)
    if start is None:
        return clip
    end = next(i for i in range(count - 1, -1, -1) if abs(samples[i]) > SILENT)
    step = clip.channels
    first = max(0, start // step - round(LEAD_SEC * clip.rate))
    last = min(clip.frames, end // step + 1 + round(TAIL_SEC * clip.rate))
    width = 2 * step
    cut = first / clip.rate  # the word times move with the start
    words = tuple(WordTime(w.start, w.end, max(0.0, w.at - cut)) for w in clip.words)
    return Clip(clip.pcm[first * width : last * width], clip.rate, clip.channels, words)


class Voices(Protocol):
    """An OS's voices (`windows.voices.WindowsVoices`), asked only on the
    speaker's thread."""

    def found(self) -> tuple[Voice, ...]:
        """The voices installed now; OSError if they can't be listed."""
        ...

    def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
        """`text` said in `voice` at `rate`; OSError if it can't be (the
        voice gone, the OS's speech failing)."""
        ...


class Output(Protocol):
    """One clip played on the OS's default output (`windows.voices.WaveOut`):
    made for each word, so it follows the default device as it changes."""

    def start(self, clip: Clip) -> bool:
        """Starts playing it; False if it can't (no output device)."""
        ...

    def playing(self) -> bool: ...

    def stop(self) -> None:
        """Stops it if it still plays, and lets the device go."""
        ...


@dataclass
class _Said:
    chunks: tuple[str, ...]
    voice: Voice
    rate: float
    sounding: Sounding
    ended: Ended
    spoken: Spoken | None = None


class SpeakerThread:
    """The `Speaker` and `Reader` ports: `voices`, `say`, `read`, `stop`
    from any thread; the work on the speaker's own. `close` ends it."""

    def __init__(
        self,
        voices: Voices,
        output: Callable[[], Output],
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._source = voices
        self._new_output = output
        self._clock = clock
        self._found: tuple[Voice, ...] = ()
        self._found_at: float | None = None
        self._cond = threading.Condition()
        self._relist = False  # until asked: never during the app's start
        self._wanted: _Said | None = None
        self._current: _Said | None = None
        self._interrupt = False
        self._to_end: list[_Said] = []
        self._closing = False
        self._kept: OrderedDict[tuple[str, float, str], Clip] = OrderedDict()
        """Readings' chunks made lately, newest last (`KEPT_BYTES`): only
        the speaker's thread uses it."""
        self._thread = threading.Thread(target=self._run, name="speaker", daemon=True)
        self._thread.start()

    # -- the port --------------------------------------------------------------------

    def voices(self) -> tuple[Voice, ...]:
        with self._cond:
            stale = (
                self._found_at is None
                or self._clock() - self._found_at > VOICES_STALE_SEC
            )
            if stale and not self._relist:
                self._relist = True
                self._cond.notify_all()
            return self._found

    def look_for_voices(self) -> None:
        """Lists the voices now, in the background (`main`: once the app has
        started, so a word's card has them when it's first pinned)."""
        with self._cond:
            self._relist = True
            self._cond.notify_all()

    def say(
        self,
        text: str,
        voice: Voice,
        rate: float,
        sounding: Sounding,
        ended: Ended,
    ) -> None:
        self._want(_Said((text,), voice, rate, sounding, ended))

    def read(
        self,
        chunks: Sequence[str],
        voice: Voice,
        rate: float,
        sounding: Sounding,
        ended: Ended,
        spoken: Spoken,
    ) -> None:
        self._want(_Said(tuple(chunks), voice, rate, sounding, ended, spoken))

    def _want(self, said: _Said) -> None:
        with self._cond:
            if self._wanted is not None:
                self._to_end.append(self._wanted)  # replaced before it was heard
            self._wanted = said
            self._interrupt = self._current is not None
            self._cond.notify_all()

    def stop(self) -> None:
        with self._cond:
            if self._wanted is not None:
                self._to_end.append(self._wanted)
                self._wanted = None
            self._interrupt = self._current is not None
            self._cond.notify_all()

    def close(self, timeout: float = 2.0) -> None:
        """Stops what it says and ends the thread (the app quitting)."""
        with self._cond:
            self._closing = True
            self._interrupt = True
            self._cond.notify_all()
        self._thread.join(timeout)

    @property
    def listed(self) -> bool:
        """Whether the voices have been looked for at least once."""
        with self._cond:
            return self._found_at is not None

    # -- the speaker's thread ------------------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(
                    lambda: (
                        self._closing
                        or self._relist
                        or self._wanted is not None
                        or bool(self._to_end)
                    )
                )
                ends, self._to_end = self._to_end, []
                if self._closing and self._wanted is not None:
                    ends.append(self._wanted)
                    self._wanted = None
                closing = self._closing
                relist, self._relist = self._relist and not closing, False
                said, self._wanted = self._wanted, None
                self._current = said
                self._interrupt = False
            for done in ends:
                _tell(done.ended, False)
            if closing:
                self._kept.clear()
                return
            if relist:
                self._list()
            if said is not None:
                heard = self._say(said)
                with self._cond:
                    self._current = None
                _tell(said.ended, heard)

    def _list(self) -> None:
        try:
            found = self._source.found()
        except OSError as error:
            log.warning("couldn't list the voices: %s", error)
            found = ()
        with self._cond:
            self._found = found
            self._found_at = self._clock()

    def _interrupted(self) -> bool:
        with self._cond:
            return self._interrupt or self._closing

    def _say(self, said: _Said) -> bool:
        """Says it, a chunk at a time; whether it was heard to its end."""
        clip = self._made(said, 0)
        for index in range(len(said.chunks)):
            if clip is None or self._interrupted() or not clip.frames:
                return False
            if index and not self._pause(CHUNK_PAUSE_SEC):
                return False
            output = self._new_output()
            try:
                start = self._clock()
                if not output.start(clip):
                    log.warning("couldn't play a word: no output device")
                    return False
                _tell(said.sounding, start, clip.seconds)
                if said.spoken is not None and not clip.words:
                    _tell(said.spoken, index, 0, len(said.chunks[index]))
                playing = clip
                last = index == len(said.chunks) - 1
                clip = None if last else self._made(said, index + 1)  # while it plays
                if not self._wait(output, start, playing, said, index):
                    return False
            finally:
                output.stop()
        return True

    def _made(self, said: _Said, index: int) -> Clip | None:
        """Chunk `index`'s sound, its silence trimmed - a reading's from
        those kept if it was made lately; None if it can't be made."""
        text = said.chunks[index]
        key = (said.voice.id, said.rate, text)
        if said.spoken is not None and key in self._kept:
            self._kept.move_to_end(key)
            return self._kept[key]
        try:
            made = trimmed(self._source.synthesize(text, said.voice, said.rate))
        except (OSError, ValueError) as error:  # never the word itself
            log.warning("couldn't say a word in %s: %s", said.voice.language, error)
            return None
        if said.spoken is not None:  # a reading's (a word's may become recorded)
            self._keep(key, made)
        return made

    def _keep(self, key: tuple[str, float, str], clip: Clip) -> None:
        self._kept[key] = clip
        while sum(len(c.pcm) for c in self._kept.values()) > KEPT_BYTES:
            self._kept.popitem(last=False)

    def _pause(self, seconds: float) -> bool:
        """Waits `seconds`; False if stopped or replaced meanwhile."""
        with self._cond:
            self._cond.wait_for(lambda: self._interrupt or self._closing, seconds)
            return not (self._interrupt or self._closing)

    def _wait(
        self, output: Output, start: float, clip: Clip, said: _Said, index: int
    ) -> bool:
        """Until the clip has played (True), it's stopped or replaced
        (False), or it overruns (False) - telling each word as it sounds."""
        give_up = start + clip.seconds + OVERRUN_SEC
        words = list(clip.words)
        while True:
            now = self._clock()
            while words and start + words[0].at <= now:
                word = words.pop(0)
                if said.spoken is not None:
                    _tell(said.spoken, index, word.start, word.end)
            with self._cond:
                self._cond.wait_for(
                    lambda: self._interrupt or self._closing, timeout=POLL_SEC
                )
                if self._interrupt or self._closing:
                    return False
            if not output.playing():
                return True
            if self._clock() > give_up:
                log.warning("a word's sound never ended: stopped")
                return False


def _tell(callback: Callable[..., None], *args: object) -> None:
    """Calls the app's own callback; a failure in it never ends the thread."""
    try:
        callback(*args)
    except Exception:
        log.exception("a speaker callback failed")
