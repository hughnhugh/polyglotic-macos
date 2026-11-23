"""Quiet speech, on real speech: the app's speech detection and Steady's
timing rules over one public FLEURS clip (`tests/audio/README.md`).

polyglotic-hq project 145 found quiet speech after digital silence missed
(the reset, #219); project 180 found it missed again after a quiet noise
floor, and project 186 what sets it off: a loud speaker before the noise.
The clip peaks at -44.9 dBFS as recorded; played loud (-3 dBFS) and then,
after 1.5s of pink noise, as recorded, today's detector never heard the
second one. The gain (`DetectionGain`, decision 0039) hears it as it would
on its own.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
import soundfile as sf

from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    FRAME_SAMPLES,
    FRAME_SEC,
    CaptionMode,
    CaptionTiming,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.platform.speech_detection import (
    SILENCE_RESET_SEC,
    SpeechDetector,
    load_model,
)
from polyglotic_desktop.ports.capture import SourceCategory

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

SR = 16000
CHUNK = 480  # 10 ms, as Windows' capture delivers
APP = Source(SourceId("app"), SourceCategory.VIDEO)
CLIP = Path(__file__).parent / "audio" / "fleurs-en-10098964113747380446.flac"
AS_RECORDED_DBFS = -44.9
LOUD_DBFS = -3.0
GAP_SEC = 1.5
LATE_SEC = 1.0
"""Heard more than this after the clip heard on its own is late (180)."""


@pytest.fixture(scope="module")
def model() -> "InferenceSession":
    return load_model()


def _clip(dbfs: float) -> np.ndarray:
    audio, sr = sf.read(str(CLIP), dtype="float32")
    assert sr == SR
    return (audio / np.abs(audio).max() * 10 ** (dbfs / 20)).astype(np.float32)


def _noise(
    seconds: float, dbfs: float, alpha: float = 1.0, seed: int = 1
) -> np.ndarray:
    """Noise with a 1/f^alpha spectrum (0 white, 1 pink, 2 brown) at `dbfs` RMS."""
    n = int(seconds * SR)
    f = np.fft.rfftfreq(n, 1 / SR)
    rng = np.random.default_rng(seed)
    spec = rng.standard_normal(len(f)) + 1j * rng.standard_normal(len(f))
    spec[1:] /= f[1:] ** (alpha / 2)
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return (x / np.sqrt(np.mean(x**2)) * 10 ** (dbfs / 20)).astype(np.float32)


def _finished(
    model: "InferenceSession", audio: np.ndarray
) -> list[TranscriptionRequest]:
    """The finished captions Steady's rules send for `audio`, fed as
    capture feeds it, with a second of silence after."""
    detector = SpeechDetector(model)
    timing = CaptionTiming(None, rules=CaptionMode.WHOLE.rules)
    timing.add_source(APP)
    audio = np.concatenate([audio, np.zeros(SR, np.float32)])
    out = []
    for i in range(0, len(audio), CHUNK):
        for frame in detector.feed(i / SR, audio[i : i + CHUNK]):
            for d in timing.frame(APP.id, frame.end, frame.speech):
                if (
                    isinstance(d, TranscriptionRequest)
                    and d.kind is SpeechKind.FINISHED
                ):
                    out.append(d)
    return out


def _first_speech(model: "InferenceSession", audio: np.ndarray) -> float:
    frames = SpeechDetector(model).feed(0.0, audio)
    return next(f.end - FRAME_SEC for f in frames if f.speech)


def _heard_from(captions: list[TranscriptionRequest], start: float) -> float | None:
    """Where the captions sent start covering speech from `start` on,
    seconds after it; None if nothing after `start` was sent."""
    starts = [c.speech_start for c in captions if c.speech_end > start]
    return max(0.0, min(starts) - start) if starts else None


@pytest.mark.parametrize("floor_dbfs", [-60.0, -50.0])
def test_quiet_speech_after_a_loud_speaker_and_a_noise_floor_is_heard(
    model: "InferenceSession", floor_dbfs: float
) -> None:
    quiet = _clip(AS_RECORDED_DBFS)
    alone = _first_speech(model, quiet)
    loud = _clip(LOUD_DBFS)
    stream = np.concatenate([loud, _noise(GAP_SEC, floor_dbfs), quiet])
    start = (len(loud) / SR) + GAP_SEC

    heard = _heard_from(_finished(model, stream), start)

    assert heard is not None, "the quiet speaker was never sent"
    assert heard <= alone + LATE_SEC


def test_quiet_speech_after_a_loud_speaker_and_digital_silence_is_heard(
    model: "InferenceSession",
) -> None:
    """145's case on real speech (#219's reset): still heard with the gain."""
    quiet = _clip(AS_RECORDED_DBFS)
    alone = _first_speech(model, quiet)
    loud = _clip(LOUD_DBFS)
    silence = np.zeros(int((SILENCE_RESET_SEC + 0.25) * SR), np.float32)
    stream = np.concatenate([loud, silence, quiet])
    start = (len(loud) + len(silence)) / SR

    heard = _heard_from(_finished(model, stream), start)

    assert heard is not None
    assert heard <= alone + LATE_SEC


def test_after_digital_silence_the_gain_starts_afresh_too(
    model: "InferenceSession",
) -> None:
    """After #219's reset the stream is heard exactly as a new one: the
    model's state and the gain both forget the loud speaker."""
    quiet = _clip(AS_RECORDED_DBFS)
    loud = _clip(LOUD_DBFS)
    zeros = int(SILENCE_RESET_SEC * SR) + FRAME_SAMPLES
    zeros += -(len(loud) + zeros) % FRAME_SAMPLES  # the quiet clip on a frame
    stream = np.concatenate([loud, np.zeros(zeros, np.float32), quiet])

    heard = SpeechDetector(model).feed(0.0, stream)
    alone = SpeechDetector(model).feed(0.0, quiet)

    after = [f.speech for f in heard[-len(alone) :]]
    assert after == [f.speech for f in alone]


def test_the_audio_given_is_never_changed(model: "InferenceSession") -> None:
    """The gain is for the model only: what the app buffers and sends is
    the audio as captured."""
    quiet = _clip(AS_RECORDED_DBFS)
    kept = quiet.copy()
    SpeechDetector(model).feed(0.0, quiet)
    assert np.array_equal(quiet, kept)


def _noises() -> dict[str, np.ndarray]:
    """Project 180's sounds that aren't speech, 6s each, at 0 dBFS RMS."""
    n = 6 * SR
    t = np.arange(n) / SR
    rng = np.random.default_rng(180)
    hum = sum(np.sign(np.sin(2 * np.pi * 82 * k * t)) / k for k in (1, 2, 3))
    bursts = np.zeros(n)
    for s in rng.uniform(0, 5.7, 14):
        i, m = int(s * SR), int(0.25 * SR)
        bursts[i : i + m] += rng.standard_normal(m) * np.exp(
            -np.arange(m) / (0.03 * SR)
        )
    music = np.zeros(n)
    chords = [(220, 277, 330), (196, 247, 294), (175, 220, 262), (196, 247, 294)]
    for k in range(8):
        i0, i1 = k * n // 8, (k + 1) * n // 8
        for f0 in chords[k % 4]:
            for h in (1, 2, 3, 4):
                music[i0:i1] += np.sin(2 * np.pi * f0 * h * t[i0:i1]) / h**1.5
        music[i0 : i0 + 800] += (
            2 * rng.standard_normal(800) * np.exp(-np.arange(800) / 200)
        )
    clicks = np.zeros(n)
    clicks[:: SR // 2] = 1.0
    sounds = {
        "white": _noise(6, 0, 0.0, 2),
        "pink": _noise(6, 0, 1.0, 3),
        "brown": _noise(6, 0, 2.0, 4),
        "engine hum": hum + 0.3 * _noise(6, 0, 1.0, 5),
        "gunfire bursts": bursts + 0.05 * _noise(6, 0, 2.0, 6),
        "chords and drums": music,
        "clicks": np.convolve(clicks, np.exp(-np.arange(80) / 10), mode="same"),
        "a 440 Hz tone": np.sin(2 * np.pi * 440 * t),
    }
    return {
        k: (v / np.sqrt(np.mean(v**2))).astype(np.float32) for k, v in sounds.items()
    }


@pytest.mark.parametrize("dbfs", [-60.0, -45.0, -30.0])
def test_sounds_that_arent_speech_are_never_sent(
    model: "InferenceSession", dbfs: float
) -> None:
    """Quiet noise is what the gain raises most (+40 dB at -60): it must
    still not be speech. 186's probe ran these at -70 to -18 dBFS."""
    for name, sound in _noises().items():
        assert _finished(model, sound * np.float32(10 ** (dbfs / 20))) == [], name


@pytest.mark.parametrize("dbfs", [-50.0, -20.0])
def test_speech_like_sounds_are_sent_as_speech(
    model: "InferenceSession", dbfs: float
) -> None:
    """Known, with the gain or without (180): a voice played backwards and
    babble are speech to the detector, at any level. What the server's
    speech model makes of them is the server's to filter."""
    voice = _clip(0.0)[::-1]
    babble = np.sum([np.roll(voice, k * SR) for k in range(4)], axis=0)
    for name, sound in (("reversed voice", voice), ("babble", babble)):
        rms = float(np.sqrt(np.mean(sound**2)))
        level = np.float32(10 ** (dbfs / 20) / rms)
        assert _finished(model, (sound * level).astype(np.float32)), name
