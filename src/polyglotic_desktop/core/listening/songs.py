"""Songs mode: a music player's singing is sent even where speech detection
doesn't hear it as speech (desktop decision 0287; polyglotic-hq 558's
option B, decided as DECISIONS.md #248's C, built by 595).

Silero, the speech detector, scores singing under a band as music, and
nothing in speech detection fixes it: with the floor filter and the bed
threshold (decision 0267) a rock song's singing was 29 % heard, and a song
went 14-86 s with nothing sent (558). So, for a music player only, sound
that goes on unheard as speech is sent anyway, a piece at a time
(`SongsMode`): after `SONGS_AFTER_SEC` of sound - every frame peaking at
`SONGS_PEAK` or louder - with no speech heard, the next `SONGS_SEND_SEC`
count as speech. On 558's bench a rock song went from 25 % to 53 % heard,
and the longest stretch with nothing sent fell to about 8 s.

**When** (`heard_as_songs`, the guard of DECISIONS.md #248): only when the
learner has turned the Lyrics switch on (off by default), only for a
known music player (the known-apps list's music category), and only while
its window hears Detect. On Detect live's speech model wrote nothing for
any of 558's 580 instrumental pieces; told a language, it turns music into
words like "The." (decision 0275). Everything else - every other app, and
a music player with the switch off - is heard exactly as before: music or
singing alone gives no captions.

Every value songs mode has is here, named, with its unit, range and why
(polyglotic-hq's "Tunables are config"). Plain Python: the speech
pipeline (`platform.speech_pipeline`) runs each source's frames through
its own `SongsMode`.
"""

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.timing import FRAME_SAMPLES, VAD_SAMPLE_RATE

SONGS_AFTER_SEC = 4.0
"""Seconds of sound heard as not speech before songs mode sends some of it
(range 2-10). 558 measured 4 with `SONGS_SEND_SEC` 3: a rock song's singing
25 % -> 53 % heard, the longest stretch unheard about 8 s. Shorter sends
more of a song's instrumental parts (the server's work, and upload);
longer leaves longer quiets."""
SONGS_SEND_SEC = 3.0
"""Seconds sent as speech each time songs mode sends (range 1-6): about a
sung line. With `SONGS_AFTER_SEC` 4, a song heard as nothing but music is
sent 3 s in every 7 - 558 measured about 78 s a minute of a song with its
live updates, about half of what a speech listener sends."""
SONGS_PEAK = 10 ** (-45 / 20)
"""A frame is sound when its loudest sample reaches this (-45 dBFS, as a
fraction of full scale; range -60 to -30 dBFS): the bed threshold's level
(`platform.speech_detection.BED_PEAK`, decision 0267), the level 558's
songs mode was measured at. A pause between songs, or a quiet fade, under
it starts the count again."""

_AFTER_FRAMES = int(SONGS_AFTER_SEC * VAD_SAMPLE_RATE / FRAME_SAMPLES)
_SEND_FRAMES = int(SONGS_SEND_SEC * VAD_SAMPLE_RATE / FRAME_SAMPLES)


def heard_as_songs(lyrics: bool, music_player: bool, spoken: Language | None) -> bool:
    """Whether a source is heard in songs mode: the Lyrics switch on
    (`lyrics`), the source a known music player's (`music_player`), and its
    window on Detect (`spoken` None). Anything else is heard as speech
    only, as before."""
    return lyrics and music_player and spoken is None


class SongsMode:
    """Songs mode for one stream of frames (`SONGS_AFTER_SEC`,
    `SONGS_SEND_SEC`): each frame's verdict as speech detection gave it,
    or True while a piece of sound unheard is sent. Off (`on` False) it
    changes nothing; turned off or on, it starts counting afresh. One
    thread at a time (the stream's capture thread)."""

    def __init__(self) -> None:
        self._on = False
        self._unheard = 0
        """Frames of sound in a row heard as not speech."""
        self._sending = 0
        """Frames left of the piece being sent."""

    @property
    def on(self) -> bool:
        return self._on

    @on.setter
    def on(self, on: bool) -> None:
        if on != self._on:
            self._on = on
            self._unheard = self._sending = 0

    @property
    def sending(self) -> bool:
        """Whether a piece of sound unheard is being sent now."""
        return self._sending > 0

    def frame(self, speech: bool, peak: float | None) -> bool:
        """The next frame's verdict: `speech`, speech detection's; `peak`,
        its loudest sample as a fraction of full scale (None: not known -
        never sound). Digital silence (a peak of 0: the player paused)
        ends a piece being sent."""
        if not self._on:
            return speech
        if speech:
            self._unheard = self._sending = 0
            return True
        sound = peak is not None and peak >= SONGS_PEAK
        if self._sending and peak:
            self._sending -= 1
            return True
        self._sending = 0
        if not sound:
            self._unheard = 0
            return False
        self._unheard += 1
        if self._unheard >= _AFTER_FRAMES:
            self._unheard = 0
            self._sending = _SEND_FRAMES
        return False
