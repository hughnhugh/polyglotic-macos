"""What Listening needs from the operating system to capture a source.

Small interfaces each OS implements in `platform/<os>/` (Windows now; macOS
and Linux later), and `main` hands over:
- `AppList` - the apps playing sound, for the app picker;
- `AudioCapture` - one source's audio: an app's, the whole system's, or
  the mic's, as 16kHz mono samples stamped on the app's clock;
- `SoundDevices` - the speakers and mics plugged in, for choosing which
  the PC's sound and the mic come from (polyglotic-hq 372);
- `HeldMic` - the mic while the dictation key is held, as pieces of
  speech ready to send (`MicPiece`; polyglotic-hq 283).

An app's name stays on the PC: only its `SourceCategory` may leave it.
`SourceCategory` lives here because the app list reports it and ports sit
below core (decision 0008); Listening's `Source` uses it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class SourceCategory(StrEnum):
    """What kind of source captions came from - all the server learns of it
    (protocol.md, `source.category`). `SYSTEM` is the whole system's audio,
    not one app's; `MUSIC` a music player."""

    BROWSER = "browser"
    VIDEO = "video"
    CALL = "call"
    GAME = "game"
    MUSIC = "music"
    SYSTEM = "system"
    OTHER = "other"
    MIC = "mic"


@dataclass(frozen=True, slots=True)
class PlayingApp:
    """An app with sound, as the app picker lists it. `name` (its
    executable's) is for the user's eyes only; `playing` is whether it is
    playing right now. `known_name` is its public name if it's on the
    known-apps list (`Discord` for Discord.exe) - the only name of an app
    that may leave the PC, and only in usage statistics the user agreed to
    share; None for any other app. `own_name`: what the executable calls
    itself (its description or product name: "VLC media player") - for
    the user's eyes only, like `name`; None if it doesn't say."""

    process_id: int
    name: str
    playing: bool
    category: SourceCategory
    known_name: str | None = None
    own_name: str | None = None

    @property
    def title(self) -> str:
        """What the app is called on screen: its public name if known, else
        its own name, else its executable's ("mygame.exe" was what an
        unknown app showed - polyglotic-hq 133)."""
        return self.known_name or self.own_name or self.name


@dataclass(frozen=True, slots=True)
class CommonApp:
    """A browser or a main app a caption window lists before it plays
    (polyglotic-hq 249, F12): its executable's name, as `PlayingApp.name`
    gives it once it plays, and its public name."""

    name: str
    title: str


@dataclass(frozen=True, slots=True)
class SoundDevice:
    """A speaker or a mic plugged in now (polyglotic-hq 372): the OS's id
    for it - kept on this PC to choose it again - and its name, for the
    learner's eyes only ("Headphones (HyperX Cloud III)")."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class SoundDevices:
    """The speakers and mics plugged in now, by name, and the ids of the
    OS's defaults (None: none, or the OS can't say)."""

    speakers: tuple[SoundDevice, ...] = ()
    mics: tuple[SoundDevice, ...] = ()
    default_speaker: str | None = None
    default_mic: str | None = None


class AppList(Protocol):
    def playing_apps(self) -> list[PlayingApp]:
        """The apps with sound open now, one entry per app."""
        ...


AudioCallback = Callable[[float, bytes], None]
"""Called with each piece of captured audio: when its first sample was
captured (seconds on the app's clock, which every source shares) and the
samples - 16kHz mono, 32-bit float, little-endian. Once audio has
started, silence while nothing plays is delivered as zeros, so the audio
is continuous; before anything has played, nothing is delivered."""


class AppCaptureSupport(StrEnum):
    """Whether this OS captures one app's audio alone (decision 0076):
    `YES` where it promises to (Windows 11; Windows' build 20348 and later),
    `TRY` where it may and doesn't promise (Windows 10 version 2004 to
    22H2) - tried, and given up on this PC if it fails - and `NO` where it
    can't (older Windows 10): everything the PC plays is the only choice."""

    YES = "yes"
    TRY = "try"
    NO = "no"


@dataclass(frozen=True, slots=True)
class TrialOutcome:
    """What trying to capture one app alone showed (`AppCaptureTrial`): it
    worked, or `why` not - content-free, for the log and a problem report:
    Windows' error code ("refused 0x88890008"), "no answer" or "silent" -
    never an app's name."""

    worked: bool
    why: str = ""


class AppCaptureTrial(Protocol):
    """Capturing one app alone, tried where the OS doesn't promise it
    (`AppCaptureSupport.TRY`): the captures tell it what they find, from
    their own threads, and the first outcome stands - an app's capture
    with sound in it, Windows refusing a capture, or an app Windows hears
    playing while its capture gets only silence."""

    @property
    def outcome(self) -> TrialOutcome | None:
        """None until a capture has shown either way."""
        ...

    def tell(self, outcome: TrialOutcome) -> None:
        """What a capture found - kept only if nothing was before."""
        ...


class AudioCapture(Protocol):
    """One source's audio. `start` begins delivering it to `on_audio` on a
    thread of the capture's own; `stop` ends it and waits for that thread.
    Captures of the mic and the whole system follow the device the user
    chose, or the system's default, as either changes."""

    def start(self, on_audio: AudioCallback) -> None: ...

    def stop(self) -> None: ...

    @property
    def capturing(self) -> str | None:
        """What is being captured right now (a device's or app's name, for
        the user's eyes only), or None if nothing is."""
        ...

    @property
    def error(self) -> str | None:
        """Why capture isn't running, if it failed - or `NOT_ALLOWED`. A
        capture that failed tries again by itself and clears it once it
        runs (decision 0266); one whose app closed says `APP_CLOSED` and is
        over."""
        ...

    @property
    def restarts(self) -> int:
        """How many times it has failed and started again by itself, or
        tried to - an error nobody foresaw, a failed open, a stream lost
        mid-way (decision 0266) - since it was made: counted in the
        listening session's summary (polyglotic-hq 566)."""
        ...


NOT_ALLOWED = "not allowed"
"""`AudioCapture.error` while the OS gives a capture only silence because
the learner hasn't allowed it - macOS records silence, not an error, when
"System Audio Recording" or the microphone isn't allowed for the app in
System Settings > Privacy & Security (polyglotic-hq 411). The capture goes
on running; the error clears if sound comes."""

APP_CLOSED = "The app has closed."
"""`AudioCapture.error` once the app a capture was for has closed: the
capture is over, not failing."""


@dataclass(frozen=True, slots=True)
class MicPiece:
    """A piece of a dictation hold's speech (polyglotic-hq 283): which hold
    (its number), from `start` to `end` on the app's clock, as Ogg Opus -
    None if the mic gave no audio (`mic_failed`: and said it had failed).
    `last`: the hold's last piece, after the key came up."""

    hold: int
    start: float
    end: float
    speech: bytes | None
    last: bool
    mic_failed: bool = False


class HeldMic(Protocol):
    """The mic while the dictation key is held: opened when it goes down,
    cut into pieces of at most 30 s, closed a moment after it comes up.
    Nothing is kept: the audio is in memory until its piece is handed on."""

    def open(self, hold: int, on_piece: Callable[[MicPiece], None]) -> None:
        """Starts listening for hold number `hold`; each piece goes to
        `on_piece`, in order, on a thread of the mic's own."""
        ...

    def close(self, tail: float) -> None:
        """The key came up: listens `tail` seconds more, then hands on the
        last piece and closes."""
        ...

    def drop(self) -> None:
        """Closes at once, handing on nothing more (cancelled, too short)."""
        ...

    def level(self) -> float:
        """How loud the mic is now, 0 to 1 (the sign's meter)."""
        ...
