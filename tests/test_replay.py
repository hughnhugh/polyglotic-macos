"""The replay source (platform.replay): audio files played into the app.

Synthetic audio only; files are written to pytest's temporary folder.
"""

import time
from pathlib import Path

import numpy as np
import soundfile as sf

from polyglotic_desktop.platform.replay import (
    LEAD_IN_SEC,
    TRAILING_SEC,
    ReplayCapture,
    join,
    read_clip,
)

SR = 16000


def tone(seconds: float, rate: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def collect(capture: ReplayCapture) -> list[tuple[float, bytes]]:
    pieces: list[tuple[float, bytes]] = []
    capture.start(lambda start, samples: pieces.append((start, samples)))
    assert capture.finished.wait(10)
    capture.stop()
    return pieces


def test_fast_replay_delivers_every_sample_in_10ms_pieces_on_one_clock() -> None:
    audio = tone(1.0)
    pieces = collect(ReplayCapture(audio, speed=None))
    assert len(pieces) == 100
    got = np.concatenate([np.frombuffer(p, np.float32) for _, p in pieces])
    assert np.array_equal(got, audio)
    starts = [s for s, _ in pieces]
    assert np.allclose(np.diff(starts), 0.01)


def test_real_time_replay_takes_as_long_as_the_audio() -> None:
    capture = ReplayCapture(tone(0.5), speed=1.0)
    began = time.perf_counter()
    pieces = collect(capture)
    took = time.perf_counter() - began
    assert 0.45 <= took < 1.0
    assert abs(pieces[0][0] - began) < 0.05  # stamped on the app's clock


def test_stopping_ends_it_early() -> None:
    capture = ReplayCapture(tone(5.0), speed=1.0)
    pieces: list[float] = []
    capture.start(lambda start, samples: pieces.append(start))
    time.sleep(0.2)
    capture.stop()
    assert capture.finished.is_set() and len(pieces) < 100
    assert capture.capturing is None and capture.error is None


def test_clips_are_read_as_16khz_mono_and_joined_with_silence(tmp_path: Path) -> None:
    stereo_8k = np.stack([tone(1.0, 8000), tone(1.0, 8000)], axis=1)
    sf.write(tmp_path / "a.wav", stereo_8k, 8000, subtype="FLOAT")
    sf.write(tmp_path / "b.wav", tone(0.5), SR, subtype="FLOAT")
    a, b = read_clip(tmp_path / "a.wav"), read_clip(tmp_path / "b.wav")
    assert a.dtype == np.float32 and a.ndim == 1 and len(a) == SR
    joined = join([a, b], gap=1.0)
    assert len(joined) == round((LEAD_IN_SEC + 1.0 + 1.0 + 0.5 + TRAILING_SEC) * SR)
    capture = ReplayCapture.from_files([tmp_path / "a.wav", tmp_path / "b.wav"], 1.0)
    assert capture.seconds == len(joined) / SR
