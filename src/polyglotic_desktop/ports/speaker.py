"""Speaker - a word said aloud, in a voice the PC has (polyglotic-hq 286).

The lookup card's "say it" asks a `Speaker` which voices exist, then to say
the word in one of them; the voice's language is what the word is in, chosen
outside the speaker (`ui_next.views.speech.voice_for`). The first speaker is
Windows' own voices (`platform.speaking.SpeakerThread` over
`platform.windows.voices`, decision 0077): on the PC, offline, free. A better
voice later - a neural voice from our server, a cloud voice, one bundled with
the app - is another speaker listing its own voices, and a setting; nothing
that asks changes. The second kind is here: recorded words
(`RECORDED`), made ahead of time by a speech model we run ourselves, so a
PC without a voice for a language still says its commonest words.

Times are on the app's clock (`time.perf_counter`, the captures' clock too):
`sounding` says when the app's own sound plays, so the captions can leave it
out (`SpeechPipeline.hush`).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Protocol

RECORDED = "recorded:"
"""How the id of a recorded voice starts: a language's words spoken ahead of
time and shipped beside its dictionary (decision 0133;
`platform.recorded_voices`), not a voice that can say anything. Whoever
picks a voice asks whether the word is recorded before picking one."""

Sounding = Callable[[float, float], None]
"""Told as a word's sound starts: when (`time.perf_counter`) and for how many
seconds. From the speaker's own thread."""

Spoken = Callable[[int, int, int], None]
"""Told as a reading's words sound (`Reader.read`): the chunk, and the
characters `[start, end)` of its text now said - a word, when the voice says
when each sounds; the whole chunk as it starts when it doesn't. From the
speaker's own thread."""

Ended = Callable[[bool], None]
"""Told once when a `say` is over: True if it was heard to its end; False if
it was stopped, replaced by another, or couldn't be said (no output device,
the voice gone). From the speaker's own thread."""


class Quality(IntEnum):
    """How good a voice sounds, as its OS ranks it (polyglotic-hq 518): a
    Mac's `AVSpeechSynthesisVoiceQuality`, whose numbers these are."""

    BASIC = 1
    """A compact voice, where the OS offers a better one of its language to
    add for free: a Mac's default quality (Tingting as macOS ships it)."""
    GOOD = 2
    """The best kind the OS lets an app use - every Windows voice (Narrator's
    natural voices aren't open to apps) - or a Mac's enhanced."""
    PREMIUM = 3
    """A Mac's premium."""


@dataclass(frozen=True)
class Voice:
    """A voice the PC can speak in: the speaker's own id for it, its name as
    the OS shows it ("Microsoft Huihui"), its language as a BCP 47 tag
    ("zh-CN", "zh-TW", "zh-HK", "en-US"), and how good it sounds."""

    id: str
    name: str
    language: str
    quality: Quality = Quality.GOOD


class Speaker(Protocol):
    """Says text aloud in one of the PC's voices; one at a time."""

    def voices(self) -> tuple[Voice, ...]:
        """The voices found on this PC, at once (never waits for the OS): the
        speaker looks again in the background when the list is old, so a
        voice added in the OS's settings is found without a restart."""
        ...

    def say(
        self,
        text: str,
        voice: Voice,
        rate: float,
        sounding: Sounding,
        ended: Ended,
    ) -> None:
        """Starts saying `text` in `voice` - stopping anything it says now
        (that one's `ended` is told False). `rate`: 1.0 is the voice's own
        pace, under 1 slower. Returns at once."""
        ...

    def stop(self) -> None:
        """Stops what it says now, if anything (its `ended` is told False)."""
        ...


class Reader(Protocol):
    """Reads a selection aloud (polyglotic-hq 495, decision 0229): the same
    voices as `Speaker`, one thing at a time across both - a reading stops
    a word being said, and a word stops a reading."""

    def voices(self) -> tuple[Voice, ...]:
        """As `Speaker.voices`."""
        ...

    def read(
        self,
        chunks: Sequence[str],
        voice: Voice,
        rate: float,
        sounding: Sounding,
        ended: Ended,
        spoken: Spoken,
    ) -> None:
        """Starts reading `chunks` in turn (a selection's sentences), each a
        sound of its own - `sounding` told as each starts, so the captions'
        hush covers what is heard and no more once it's stopped - and
        `spoken` as each word sounds. Stops anything said now. Returns at
        once; `ended` is told True when the last chunk was heard to its
        end."""
        ...

    def stop(self) -> None:
        """As `Speaker.stop`."""
        ...
