"""Speech detection (platform.speech_detection) and the audio buffer.

Synthetic audio only: Silero on silence and on noise, the frame timing, and
slicing. Whether it detects real speech was checked by hand on public
FLEURS clips (project 016's report), not here.
"""

import hashlib

import numpy as np
import pytest

from polyglotic_desktop.core.listening.timing import FRAME_SAMPLES, FRAME_SEC
from polyglotic_desktop.platform.audio_buffer import AudioBuffer
from polyglotic_desktop.platform.speech_detection import (
    GAIN_HOLD_SEC,
    GAIN_MAX,
    GAIN_TARGET_PEAK,
    MIC_GAIN_MAX,
    MODEL_SHA256,
    QUIET_RESET_SEC,
    SILENCE_RESET_SEC,
    DetectionGain,
    ModelOnDemand,
    SpeechDetector,
    load_model,
    model_path,
)

SR = 16000


@pytest.fixture(scope="module")
def detector() -> SpeechDetector:
    return SpeechDetector(load_model())


def test_the_model_is_the_pinned_file() -> None:
    assert hashlib.sha256(model_path().read_bytes()).hexdigest() == MODEL_SHA256


def test_the_model_on_demand_loads_nothing_until_wanted_then_once() -> None:
    """polyglotic-hq 513: the app's start makes the loader, and an app with
    nothing captioned never loads the model; `start` loads it on a thread of
    its own, once, however often it's called; `result` waits for it."""
    import threading

    loads: list[str] = []
    release = threading.Event()

    def load() -> object:
        loads.append(threading.current_thread().name)
        release.wait(5)
        return "the model"

    model = ModelOnDemand(load)
    assert not model.started and loads == []
    model.start()
    model.start()
    release.set()
    assert model.result() == "the model"
    assert model.result() == "the model"
    assert len(loads) == 1 and loads[0].startswith("speech-model")


def test_the_model_on_demand_loads_at_its_first_result_if_not_started() -> None:
    model = ModelOnDemand(lambda: "the model")
    assert model.result() == "the model"
    assert model.started


def test_silence_and_noise_are_not_speech(detector: SpeechDetector) -> None:
    detector.reset()
    rng = np.random.default_rng(0)
    audio = np.concatenate(
        [np.zeros(SR, dtype=np.float32), rng.normal(0, 0.01, SR).astype(np.float32)]
    )
    results = detector.feed(0.0, audio)
    assert len(results) == len(audio) // FRAME_SAMPLES
    assert not any(r.speech for r in results)


def test_frames_carry_over_between_chunks_with_their_times(
    detector: SpeechDetector,
) -> None:
    detector.reset()
    chunk = np.zeros(300, dtype=np.float32)  # not a multiple of 512
    ends: list[float] = []
    for i in range(20):
        ends.extend(r.end for r in detector.feed(10.0 + i * 300 / SR, chunk))
    assert len(ends) == 20 * 300 // FRAME_SAMPLES
    assert ends == pytest.approx([10.0 + (i + 1) * FRAME_SEC for i in range(len(ends))])


def test_probability_is_between_0_and_1(detector: SpeechDetector) -> None:
    detector.reset()
    rng = np.random.default_rng(1)
    p = detector.probability(rng.uniform(-0.5, 0.5, FRAME_SAMPLES).astype(np.float32))
    assert 0.0 <= p <= 1.0


def test_buffer_slices_sample_exact_with_padding() -> None:
    buffer = AudioBuffer()
    audio = np.arange(SR * 3, dtype=np.float32)
    for i in range(0, len(audio), 1000):
        buffer.append(100.0 + i / SR, audio[i : i + 1000])
    cut = buffer.slice(101.0, 102.0)
    assert cut is not None
    assert cut[0] == round(0.8 * SR) and len(cut) == round(1.4 * SR)
    assert np.all(np.diff(cut) == 1)  # continuous across chunks


def test_each_frame_carries_its_loudness_as_captured(detector: SpeechDetector) -> None:
    """Where a caption is cut while the speech goes on (polyglotic-hq 291):
    the frame's root mean square, before the detection gain."""
    detector.reset()
    quiet = np.full(FRAME_SAMPLES, 0.001, dtype=np.float32)
    loud = np.full(FRAME_SAMPLES, 0.3, dtype=np.float32)
    results = detector.feed(0.0, np.concatenate([quiet, loud]))
    assert [r.level for r in results] == pytest.approx([0.001, 0.3])


def test_a_slice_has_no_margin_where_it_is_cut() -> None:
    buffer = AudioBuffer()
    audio = np.arange(SR * 3, dtype=np.float32)
    buffer.append(100.0, audio)
    cut = buffer.slice(101.0, 102.0, 0.0, pad_after=0.2)
    assert cut is not None
    assert cut[0] == SR and len(cut) == round(1.2 * SR)


def test_buffer_keeps_only_its_window() -> None:
    buffer = AudioBuffer(window=1.0)
    for i in range(30):
        buffer.append(i * 0.1, np.ones(1600, dtype=np.float32))
    assert buffer.slice(0.0, 0.5) is None
    assert buffer.slice(2.0, 2.5) is not None


def _talk(seconds: float, seed: int) -> np.ndarray:
    """Made-up audio with some shape to it - a few tones under noise, rising
    and falling - so the model's state moves (not speech, and not judged)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    tones = sum(np.sin(2 * np.pi * f * t) for f in (180, 360, 1100))
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)
    return (0.02 * envelope * tones + rng.normal(0, 0.003, len(t))).astype(np.float32)


def test_after_digital_silence_the_detector_starts_afresh() -> None:
    """Windows' capture delivers exact zeros while an app plays nothing.
    Carried through them, the state stopped the model hearing quiet speech
    that followed (145: FLEURS clips at -30 to -50 dBFS lost up to 5s, or
    all of it). After SILENCE_RESET_SEC of zeros the next frame is judged
    as at the start of a stream."""
    model = load_model()
    after = _talk(0.1, 7)[:FRAME_SAMPLES]
    fresh = SpeechDetector(model)
    expected = fresh.probability(after)

    detector = SpeechDetector(model)
    detector.feed(0.0, _talk(2.0, 8))
    zeros = np.zeros(int(SILENCE_RESET_SEC * SR) + FRAME_SAMPLES, dtype=np.float32)
    results = detector.feed(2.0, zeros)
    assert not any(r.speech for r in results)
    assert detector.probability(after) == pytest.approx(expected, abs=1e-6)


def test_a_moment_of_zeros_inside_speech_keeps_the_state() -> None:
    """Zeros shorter than SILENCE_RESET_SEC (a codec's gap between words)
    don't start the stream afresh: the state carries on."""
    model = load_model()
    after = _talk(0.1, 7)[:FRAME_SAMPLES]
    fresh = SpeechDetector(model)
    expected = fresh.probability(after)

    detector = SpeechDetector(model)
    detector.feed(0.0, _talk(2.0, 8))
    detector.feed(2.0, np.zeros(FRAME_SAMPLES * 2, dtype=np.float32))
    assert detector.probability(after) != pytest.approx(expected, abs=1e-6)


def _not_speech(frames: int) -> np.ndarray:
    """Sound the model hears as not speech, never exact zeros: noise, as a
    song's band or a game's music never goes digitally silent."""
    rng = np.random.default_rng(0)
    return rng.normal(0, 0.01, frames * FRAME_SAMPLES).astype(np.float32)


def test_after_a_long_stretch_heard_as_not_speech_the_model_starts_afresh() -> None:
    """A song's band never goes digitally silent, so the reset after zeros
    never comes. Carried through it, the state stopped the model hearing the
    singing after a song's intro, though the same stretch started afresh was
    heard (536: Swansong's 2:00-2:20, 0 % speech carried, 42 % afresh).
    After QUIET_RESET_SEC of frames heard as not speech, the next frame is
    judged as at the start of a stream."""
    model = load_model()
    after = _talk(0.1, 7)[:FRAME_SAMPLES]
    expected = SpeechDetector(model).probability(after)

    detector = SpeechDetector(model)
    frames = int(np.ceil(QUIET_RESET_SEC * SR / FRAME_SAMPLES))
    results = detector.feed(0.0, _not_speech(frames))
    assert len(results) == frames
    assert not any(r.speech for r in results)
    assert detector.probability(after) == pytest.approx(expected, abs=1e-6)
    # the frame it happened after says so (polyglotic-hq 549: the
    # stretches of sound without speech count it)
    assert [r.reset for r in results] == [False] * (frames - 1) + [True]


def test_a_shorter_stretch_heard_as_not_speech_keeps_the_state() -> None:
    """A pause in speech, or a few seconds of a song's band, shorter than
    QUIET_RESET_SEC: the state carries on, as it always did."""
    model = load_model()
    after = _talk(0.1, 7)[:FRAME_SAMPLES]
    expected = SpeechDetector(model).probability(after)

    detector = SpeechDetector(model)
    frames = int(np.ceil(QUIET_RESET_SEC * SR / FRAME_SAMPLES)) - 1
    results = detector.feed(0.0, _not_speech(frames))
    assert detector.probability(after) != pytest.approx(expected, abs=1e-6)
    assert not any(r.reset for r in results)


def _frame(peak: float) -> np.ndarray:
    """A frame of noise whose loudest sample is `peak`."""
    x = np.random.default_rng(3).uniform(-1, 1, FRAME_SAMPLES)
    return (x / np.abs(x).max() * peak).astype(np.float32)


def test_the_gain_leaves_ordinary_audio_as_it_is() -> None:
    frame = _frame(GAIN_TARGET_PEAK * 2)
    assert DetectionGain().apply(frame) is frame


def test_the_gain_raises_quiet_audio_to_its_target_and_no_further() -> None:
    quiet = _frame(GAIN_TARGET_PEAK / 30)
    kept = quiet.copy()
    raised = DetectionGain().apply(quiet)
    assert float(np.abs(raised).max()) == pytest.approx(GAIN_TARGET_PEAK, rel=1e-5)
    assert np.array_equal(quiet, kept)  # a new array: the audio given is unchanged

    hiss = _frame(GAIN_TARGET_PEAK / GAIN_MAX / 10)  # -80 dBFS
    assert float(np.abs(DetectionGain().apply(hiss)).max()) == pytest.approx(
        float(np.abs(hiss).max()) * GAIN_MAX, rel=1e-5
    )
    assert not DetectionGain().apply(np.zeros(FRAME_SAMPLES, np.float32)).any()


def test_the_gain_holds_after_loud_audio_then_rises() -> None:
    """A pause between a loud speaker's words isn't raised; a quiet
    speaker GAIN_HOLD_SEC after them is."""
    gain = DetectionGain()
    gain.apply(_frame(0.5))
    quiet = _frame(GAIN_TARGET_PEAK / 30)
    hold = round(GAIN_HOLD_SEC / FRAME_SEC)
    peaks = [float(np.abs(gain.apply(quiet)).max()) for _ in range(hold)]
    assert peaks[: hold - 1] == pytest.approx([float(np.abs(quiet).max())] * (hold - 1))
    assert peaks[-1] == pytest.approx(GAIN_TARGET_PEAK, rel=1e-5)

    gain.apply(_frame(0.5))
    gain.reset()
    assert float(np.abs(gain.apply(quiet)).max()) == pytest.approx(
        GAIN_TARGET_PEAK, rel=1e-5
    )


def test_the_mics_gain_raises_quiet_audio_by_mic_gain_max_at_most() -> None:
    """polyglotic-hq 352, decision 0145: what is quiet on the mic is the
    room, so its gain stops at MIC_GAIN_MAX (+6 dB); ordinary audio is
    heard as it is, as on every source."""
    quiet = _frame(GAIN_TARGET_PEAK / 30)
    raised = DetectionGain(MIC_GAIN_MAX).apply(quiet)
    assert float(np.abs(raised).max()) == pytest.approx(
        float(np.abs(quiet).max()) * MIC_GAIN_MAX, rel=1e-5
    )
    loud = _frame(GAIN_TARGET_PEAK * 2)
    assert DetectionGain(MIC_GAIN_MAX).apply(loud) is loud
    near = _frame(GAIN_TARGET_PEAK / 1.5)  # needs less than the ceiling
    assert float(np.abs(DetectionGain(MIC_GAIN_MAX).apply(near)).max()) == (
        pytest.approx(GAIN_TARGET_PEAK, rel=1e-5)
    )
