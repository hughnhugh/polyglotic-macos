"""A replay source: audio played into the app as if an app were playing it.

`ReplayCapture` implements the `AudioCapture` port, so the whole desktop
path - speech detection, the timing rules, Ogg Opus, the connection - runs
headless with no audio device: in CI, by hand against a local server, and
as the benchmark's load (polyglotic-hq project 023). It delivers 16kHz
mono float audio in 10ms pieces, stamped on the app's clock, like Windows
capture does; when the audio runs out it stops, as a capture does when its
app closes.

- `speed=1.0` paces it in real time (what a server sees from a real app);
  `speed=None` delivers it as fast as the pipeline takes it - the timing
  rules only read the stamps, so captions come out the same.
- `from_files` joins clips with gaps of silence, as the harness's test
  player does. Use public test audio (FLEURS, CC BY 4.0) or synthetic
  audio - never someone's real recording. Nothing is written anywhere.
"""

import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import soundfile as sf

from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE
from polyglotic_desktop.platform.speech_detection import Audio
from polyglotic_desktop.ports.capture import AudioCallback

PIECE_SEC = 0.01  # Windows' capture delivers about 10ms at a time
LEAD_IN_SEC = 0.5  # silence before the first clip
TRAILING_SEC = 2.0  # silence after the last, so its caption finishes


def read_clip(path: str | Path) -> Audio:
    """A clip as 16kHz mono float audio (mixed down and resampled if need be)."""
    audio, rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono: Audio = audio.mean(axis=1).astype(np.float32)
    if rate != VAD_SAMPLE_RATE:
        count = round(len(mono) * VAD_SAMPLE_RATE / rate)
        positions = np.arange(count) * (rate / VAD_SAMPLE_RATE)
        mono = np.interp(positions, np.arange(len(mono)), mono).astype(np.float32)
    return mono


def join(clips: Sequence[Audio], gap: float) -> Audio:
    """The clips with `gap` seconds of silence between them, a little before
    the first and enough after the last for its caption to finish."""
    silence = np.zeros(round(gap * VAD_SAMPLE_RATE), dtype=np.float32)
    parts: list[Audio] = [np.zeros(round(LEAD_IN_SEC * VAD_SAMPLE_RATE), np.float32)]
    for i, clip in enumerate(clips):
        if i:
            parts.append(silence)
        parts.append(clip)
    parts.append(np.zeros(round(TRAILING_SEC * VAD_SAMPLE_RATE), np.float32))
    return np.concatenate(parts)


class ReplayCapture:
    """`AudioCapture` playing `audio` (16kHz mono float) into the app."""

    def __init__(
        self,
        audio: Audio,
        speed: float | None = 1.0,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._audio = audio.astype(np.float32)
        self._speed = speed
        self._clock = clock
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self.finished = threading.Event()
        """Set once all the audio has been delivered (or capture stopped)."""

    @classmethod
    def from_files(
        cls, paths: Sequence[str | Path], gap: float = 1.2, speed: float | None = 1.0
    ) -> "ReplayCapture":
        return cls(join([read_clip(p) for p in paths], gap), speed)

    @property
    def seconds(self) -> float:
        return len(self._audio) / VAD_SAMPLE_RATE

    def start(self, on_audio: AudioCallback) -> None:
        self._thread = threading.Thread(
            target=self._play, args=(on_audio,), name="replay", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(5)

    @property
    def capturing(self) -> str | None:
        return None if self.finished.is_set() else "replay"

    @property
    def error(self) -> str | None:
        return None

    @property
    def restarts(self) -> int:
        return 0

    def _play(self, on_audio: AudioCallback) -> None:
        piece = round(PIECE_SEC * VAD_SAMPLE_RATE)
        started = self._clock()
        try:
            for first in range(0, len(self._audio), piece):
                if self._stopping.is_set():
                    return
                offset = first / VAD_SAMPLE_RATE
                if self._speed is not None:
                    # each piece is delivered once it has "played", as capture does
                    due = started + (offset + PIECE_SEC) / self._speed
                    wait = due - self._clock()
                    if wait > 0:
                        time.sleep(wait)
                samples = self._audio[first : first + piece]
                on_audio(started + offset, samples.tobytes())
        finally:
            self.finished.set()
