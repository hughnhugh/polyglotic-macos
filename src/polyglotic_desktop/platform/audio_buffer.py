"""A source's recent audio by capture time, for cutting speech out of it.

Every live update and finished caption is cut again from the last
`BUFFER_WINDOW_SEC` of its source's audio, padded `SLICE_PAD_SEC` each side
(the proof of concept's `_slice_timestamped_buffer`); the mic-bleed check
reads what the PC played from one too. Audio stays in memory only.
"""

import threading
from collections import deque

import numpy as np

from polyglotic_desktop.core.listening.timing import SLICE_PAD_SEC, VAD_SAMPLE_RATE
from polyglotic_desktop.platform.speech_detection import Audio

BUFFER_WINDOW_SEC = 30.0


class AudioBuffer:
    """The last BUFFER_WINDOW_SEC of one source's 16kHz mono audio, as
    chunks stamped with their start on the app's clock. One thread appends;
    any thread may cut from it."""

    def __init__(self, window: float = BUFFER_WINDOW_SEC) -> None:
        self._window = window
        self._chunks: deque[tuple[float, Audio]] = deque()
        self._lock = threading.Lock()

    def append(self, start: float, audio: Audio) -> None:
        with self._lock:
            self._chunks.append((start, audio))
            while self._chunks and self._chunks[0][0] < start - self._window:
                self._chunks.popleft()

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()

    def peak(self, seconds: float = 0.1) -> float | None:
        """The loudest sample over the newest `seconds` of audio, 0.0 to
        1.0 of full scale: a level meter's reading (polyglotic-hq 372).
        None while the buffer has nothing."""
        with self._lock:
            newest = list(self._chunks)[-8:]  # a capture's chunks are short
        if not newest:
            return None
        want = round(seconds * VAD_SAMPLE_RATE)
        tail = np.concatenate([audio for _, audio in newest])[-want:]
        return float(np.max(np.abs(tail))) if len(tail) else 0.0

    def slice(
        self,
        start: float,
        end: float,
        pad: float = SLICE_PAD_SEC,
        pad_after: float | None = None,
    ) -> Audio | None:
        """The audio from `start - pad` to `end + pad_after` (`pad` again if
        not given), as far as the buffer has it; None if it has none of it."""
        lo, hi = start - pad, end + (pad if pad_after is None else pad_after)
        with self._lock:
            chunks = list(self._chunks)
        parts = []
        for chunk_start, audio in chunks:
            first = max(0, round((lo - chunk_start) * VAD_SAMPLE_RATE))
            last = min(len(audio), round((hi - chunk_start) * VAD_SAMPLE_RATE))
            if last > first:
                parts.append(audio[first:last])
        return np.concatenate(parts) if parts else None
