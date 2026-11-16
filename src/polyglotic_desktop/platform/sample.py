"""The sample Home offers when nothing is playing (polyglotic-hq 176): a
short recording in the language being learned - FLEURS sentences, CC BY
4.0, credited in `data/samples/CREDITS.md` - played aloud by the app and
handed to the speech pipeline as a source of its own, so it's captioned
like any app.

`SampleCapture` implements the `AudioCapture` port: the recording paced in
real time (`ReplayCapture`), played aloud as it starts by whatever `play`
the platform gives (Windows: `windows.sound.PlayAloud`). It stops when the
recording ends, as a capture does when its app closes.
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE
from polyglotic_desktop.ports.capture import AudioCallback

if TYPE_CHECKING:  # numpy only once a sample plays, not before the window
    from polyglotic_desktop.platform.speech_detection import Audio

SAMPLES = Path(__file__).resolve().parent / "data" / "samples"


class SoundOut(Protocol):
    """What plays the sample aloud: the OS's (Windows: `windows.sound.
    PlayAloud`), handed over by `main.os_adapters` (decision 0038)."""

    def play(self, audio: "Audio", rate: int) -> bool:
        """`audio` (mono float) at `rate`, from now; False if it can't."""
        ...

    def stop(self) -> None: ...


def sample_file(learning: str | None) -> Path | None:
    """The sample in the language being learned ("zh" or "en"), if there
    is one."""
    if learning is None:
        return None
    found = SAMPLES / f"{learning}.flac"
    return found if found.is_file() else None


class SampleCapture:
    """`AudioCapture` of the sample at `path`. `play`: plays audio aloud
    (mono float, its rate) and returns how to stop it - None to caption it
    without a sound (tests). `speed`: real time (1.0), as it's heard; None:
    as fast as the pipeline takes it (tests)."""

    def __init__(
        self,
        path: Path,
        play: "Callable[[Audio, int], Callable[[], None]] | None" = None,
        speed: float | None = 1.0,
    ) -> None:
        from polyglotic_desktop.platform.replay import ReplayCapture, read_clip

        self.audio = read_clip(path)
        self._replay = ReplayCapture(self.audio, speed)
        self._play = play
        self._stop_playing: Callable[[], None] | None = None

    @property
    def seconds(self) -> float:
        return len(self.audio) / VAD_SAMPLE_RATE

    @property
    def finished(self) -> bool:
        """All of it has been delivered, or it was stopped."""
        return self._replay.finished.is_set()

    def start(self, on_audio: AudioCallback) -> None:
        if self._play is not None:
            self._stop_playing = self._play(self.audio, VAD_SAMPLE_RATE)
        self._replay.start(on_audio)

    def stop(self) -> None:
        if self._stop_playing is not None:
            self._stop_playing()
            self._stop_playing = None
        self._replay.stop()

    @property
    def capturing(self) -> str | None:
        return None if self.finished else "sample"

    @property
    def error(self) -> str | None:
        return None
