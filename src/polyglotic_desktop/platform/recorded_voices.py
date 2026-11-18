"""Recorded words beside the OS's voices (decision 0133; polyglotic-hq 341).

A PC says a word only in the voices it has. A language's audio file
(`adapters.audio_file`) holds its commonest words spoken ahead of time, so
they are said on any PC. `RecordedVoices` is the speaker's source of
voices (`speaking.Voices`) over both:

- each language with recordings is a voice of its own (its id starts
  `ports.speaker.RECORDED`), listed before the OS's;
- asked for a word in a recorded voice, it plays the recording, as it is
  at any pace asked (polyglotic-hq 518: a word sounds the same at every
  press - an OS voice for the slower press sounded robotic);
- a word that isn't recorded is said by an OS voice of the language, or
  not at all (OSError, as a voice that has gone).

`Recordings` is which languages have recordings now: packs arrive and go
while the app runs (`main.PackDelivery`), on another thread than the
speaker's. The lookup card asks it whether a word is recorded
(`ui_next.word_speech`), so a word nothing can say shows as that.
"""

import io
import threading
from collections.abc import Callable
from typing import Protocol

from polyglotic_desktop.platform.speaking import Clip, Voices
from polyglotic_desktop.ports.speaker import RECORDED, Voice


class WordClips(Protocol):
    """A language's recorded words (`adapters.audio_file.SqliteAudio`)."""

    def clip(self, word: str) -> bytes | None:
        """The word's recording, a whole Ogg Opus file; None: not recorded."""
        ...


def clip_of_ogg(data: bytes) -> Clip:
    """An Ogg Opus file's sound as 16-bit PCM; OSError if it can't be read.
    libsndfile (the app's own, through soundfile) decodes it."""
    import soundfile

    try:
        samples, rate = soundfile.read(io.BytesIO(data), dtype="int16")
    except (RuntimeError, ValueError) as error:  # soundfile.LibsndfileError
        raise OSError(
            f"a recording that can't be read: {type(error).__name__}"
        ) from None
    channels = 1 if samples.ndim == 1 else samples.shape[1]
    return Clip(samples.tobytes(), int(rate), channels)


class Recordings:
    """The languages with recorded words now, each with its voice: set and
    asked from any thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: dict[str, tuple[Voice, WordClips]] = {}

    def use(self, language: str, tag: str, name: str, clips: WordClips | None) -> None:
        """`language`'s recordings from now on (None: none): `tag` is the
        voice's BCP 47 tag ("fr-FR"), `name` what it's called."""
        with self._lock:
            if clips is None:
                self._held.pop(language, None)
            else:
                voice = Voice(f"{RECORDED}{language}", name, tag)
                self._held[language] = (voice, clips)

    def voices(self) -> tuple[Voice, ...]:
        with self._lock:
            return tuple(voice for voice, _ in self._held.values())

    def clip(self, voice: Voice, word: str) -> bytes | None:
        """`word` as recorded for `voice`; None: not recorded, or the
        voice's recordings are gone."""
        with self._lock:
            held = self._held.get(voice.id.removeprefix(RECORDED))
        return held[1].clip(word) if held is not None else None

    def has(self, voice: Voice, word: str) -> bool:
        return self.clip(voice, word) is not None


def _primary(tag: str) -> str:
    return tag.split("-")[0].lower()


class RecordedVoices:
    """`speaking.Voices`: the recorded voices, then the OS's (`os_voices`)."""

    def __init__(
        self,
        os_voices: Voices,
        recordings: Recordings,
        decode: Callable[[bytes], Clip] = clip_of_ogg,
    ) -> None:
        self._os = os_voices
        self._recordings = recordings
        self._decode = decode

    def found(self) -> tuple[Voice, ...]:
        recorded = self._recordings.voices()
        try:
            return (*recorded, *self._os.found())
        except OSError:
            if recorded:
                return recorded  # the OS's can't be listed: ours still speak
            raise

    def _os_voice(self, tag: str) -> Voice | None:
        """An OS voice of the language - never Cantonese for Mandarin, nor
        the other way: the same region, for Chinese."""
        try:
            found = self._os.found()
        except OSError:
            return None
        same = [v for v in found if v.language.lower() == tag.lower()]
        if same or _primary(tag) == "zh":
            return same[0] if same else None
        return next((v for v in found if _primary(v.language) == _primary(tag)), None)

    def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
        if not voice.id.startswith(RECORDED):
            return self._os.synthesize(text, voice, rate)
        data = self._recordings.clip(voice, text)
        if data is not None:
            return self._decode(data)
        instead = self._os_voice(voice.language)
        if instead is None:
            raise OSError("not recorded, and no voice of the language")
        return self._os.synthesize(text, instead, rate)
