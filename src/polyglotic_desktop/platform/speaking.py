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

Holds the words it says only while saying them: never logged.
"""

import io
import logging
import threading
import time
import wave
from array import array
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from polyglotic_desktop.ports.speaker import Ended, Sounding, Voice

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


@dataclass(frozen=True)
class Clip:
    """A word's sound: 16-bit little-endian PCM, `rate` per second,
    `channels` interleaved."""

    pcm: bytes
    rate: int
    channels: int = 1

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
    after the last to `TAIL_SEC`; a silent clip as it is."""
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
    return Clip(clip.pcm[first * width : last * width], clip.rate, clip.channels)


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
    text: str
    voice: Voice
    rate: float
    sounding: Sounding
    ended: Ended


class SpeakerThread:
    """The `Speaker` port: `voices`, `say`, `stop` from any thread; the work
    on the speaker's own. `close` ends it."""

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
        with self._cond:
            if self._wanted is not None:
                self._to_end.append(self._wanted)  # replaced before it was heard
            self._wanted = _Said(text, voice, rate, sounding, ended)
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
        """Says it; whether it was heard to its end."""
        try:
            clip = trimmed(self._source.synthesize(said.text, said.voice, said.rate))
        except (OSError, ValueError) as error:  # never the word itself
            log.warning("couldn't say a word in %s: %s", said.voice.language, error)
            return False
        if self._interrupted() or not clip.frames:
            return False
        output = self._new_output()
        try:
            start = self._clock()
            if not output.start(clip):
                log.warning("couldn't play a word: no output device")
                return False
            _tell(said.sounding, start, clip.seconds)
            return self._wait(output, start + clip.seconds + OVERRUN_SEC)
        finally:
            output.stop()

    def _wait(self, output: Output, give_up: float) -> bool:
        """Until the clip has played (True), it's stopped or replaced
        (False), or it overruns (False)."""
        while True:
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
