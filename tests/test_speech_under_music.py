"""Speech over music (platform.speech_detection, decision 0267,
polyglotic-hq 558): every source but the mic hears through a floor filter,
and under a steady bed of sound takes a lower threshold - never for speech
alone or the mic.

The rules are checked through a stand-in for the model that gives every
frame the same probability; the whole on a recorded mix - FLEURS speech with
a CC BY instrumental under it (tests/audio/README.md) - through the app's
own detection and caption timing.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
import pytest
import soundfile as sf

from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    FRAME_SAMPLES,
    MAX_WAIT_FOR_TEXT_SEC,
    CaptionTiming,
    SpeechKind,
    TranscriptionRequest,
    default_caption_mode,
)
from polyglotic_desktop.platform.speech_detection import (
    BED_HOLD_SEC,
    BED_PEAK,
    BED_THRESHOLD,
    MIC_GAIN_MAX,
    SPEECH_THRESHOLD,
    FloorFilter,
    SpeechDetector,
    load_model,
)
from polyglotic_desktop.ports.capture import SourceCategory

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

SR = 16000
AUDIO = Path(__file__).parent / "audio"


class FixedModel:
    """Stands in for the model: every frame gets `p`; what it was given to
    hear is kept."""

    def __init__(self, p: float) -> None:
        self.p = p
        self.heard: list[npt.NDArray[np.float32]] = []

    def run(self, _outputs: None, feed: dict) -> tuple:
        self.heard.append(feed["input"][0, -FRAME_SAMPLES:].copy())
        return np.array([[self.p]], dtype=np.float32), feed["state"]


def _frames(count: int, peak: float) -> npt.NDArray[np.float32]:
    """`count` frames of noise peaking at `peak` (never exact zeros)."""
    rng = np.random.default_rng(1)
    x = rng.uniform(-1, 1, count * FRAME_SAMPLES).astype(np.float32)
    return x * np.float32(peak / np.max(np.abs(x)))


def _rms(x: npt.NDArray[np.float32]) -> float:
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


_HOLD = int(np.ceil(BED_HOLD_SEC * SR / FRAME_SAMPLES))
_BETWEEN = (BED_THRESHOLD + SPEECH_THRESHOLD) / 2


def test_under_a_steady_bed_a_frame_is_heard_at_the_bed_threshold() -> None:
    """A probability between the two thresholds: not speech until every
    frame of BED_HOLD_SEC has been as loud as a bed, speech from then on."""
    detector = SpeechDetector(FixedModel(_BETWEEN))
    results = detector.feed(0.0, _frames(_HOLD + 5, BED_PEAK * 4))
    heard = [r.speech for r in results]
    assert heard[: _HOLD - 1] == [False] * (_HOLD - 1)
    assert all(heard[_HOLD:])


def test_quiet_sound_between_never_makes_a_bed() -> None:
    """Sound under BED_PEAK - the quiet between words, room tone - once in
    every BED_HOLD_SEC is enough: the threshold stays SPEECH_THRESHOLD."""
    detector = SpeechDetector(FixedModel(_BETWEEN))
    loud = _frames(_HOLD - 1, BED_PEAK * 4)
    quiet = _frames(1, BED_PEAK / 2)
    stream = np.concatenate([loud, quiet] * 4)
    assert not any(r.speech for r in detector.feed(0.0, stream))


def test_speech_alone_is_heard_at_the_usual_threshold() -> None:
    detector = SpeechDetector(FixedModel(SPEECH_THRESHOLD))
    assert all(r.speech for r in detector.feed(0.0, _frames(10, BED_PEAK / 2)))
    detector = SpeechDetector(FixedModel(_BETWEEN))
    assert not any(r.speech for r in detector.feed(0.0, _frames(10, BED_PEAK / 2)))


def test_the_mic_never_takes_the_bed_threshold() -> None:
    model = FixedModel(_BETWEEN)
    detector = SpeechDetector(model, MIC_GAIN_MAX, beds=False)
    assert not any(
        r.speech for r in detector.feed(0.0, _frames(_HOLD * 3, BED_PEAK * 4))
    )


def test_the_mic_hears_its_audio_as_captured_and_other_sources_through_the_filter() -> (
    None
):
    """Loud frames (no gain): the mic's model hears each frame as it came;
    any other source's hears it through the floor filter."""
    audio = _frames(40, 0.5)
    mic = FixedModel(0.0)
    SpeechDetector(mic, MIC_GAIN_MAX, beds=False).feed(0.0, audio)
    assert np.array_equal(np.concatenate(mic.heard), audio)
    app = FixedModel(0.0)
    SpeechDetector(app).feed(0.0, audio)
    assert not np.allclose(np.concatenate(app.heard), audio)


def _tone(seconds: float, hz: float, amplitude: float) -> npt.NDArray[np.float32]:
    t = np.arange(int(seconds * SR)) / SR
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def test_the_floor_filter_takes_a_steady_bed_down_and_lets_a_new_sound_through() -> (
    None
):
    """A steady tone becomes floor: after a second it is heard about 10 dB
    down (FLOOR_KEEP). A new sound over it - a word over a bed - is heard
    almost as it was, so it stands out from the bed by more than before."""
    floor = FloorFilter()
    bed = _tone(3.0, 440.0, 0.1)
    word = _tone(0.3, 1000.0, 0.1)
    stream = bed.copy()
    stream[int(2.5 * SR) : int(2.8 * SR)] += word
    given = stream.copy()
    frames = len(stream) // FRAME_SAMPLES
    out = np.concatenate(
        [
            floor.apply(stream[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES])
            for i in range(frames)
        ]
    )
    assert np.array_equal(stream, given)  # the audio given is never changed
    before = out[int(1.5 * SR) : int(2.4 * SR)]
    during = out[int(2.6 * SR) : int(2.8 * SR)]
    assert _rms(before) < 0.4 * _rms(bed[int(1.5 * SR) : int(2.4 * SR)])
    assert _rms(during) > 2.5 * _rms(before)


def test_the_floor_filter_starts_afresh_after_digital_silence() -> None:
    """Digital silence starts the stream afresh (SILENCE_RESET_SEC): the
    filter forgets the bed too, as the gain does."""
    model = FixedModel(0.0)
    detector = SpeechDetector(model)
    bed = _tone(64 * FRAME_SAMPLES / SR, 440.0, 0.1)  # whole frames: none left over
    detector.feed(0.0, bed)
    detector.feed(2.0, np.zeros(16 * FRAME_SAMPLES, np.float32))
    model.heard.clear()
    detector.feed(2.5, bed[: 4 * FRAME_SAMPLES])
    fresh = FixedModel(0.0)
    SpeechDetector(fresh).feed(0.0, bed[: 4 * FRAME_SAMPLES])
    assert np.allclose(np.concatenate(model.heard), np.concatenate(fresh.heard))


# --- a recorded mix, through the app's own detection and timing --------------

SPEECH = "fleurs-en-558-speech.opus"
"""30 s of FLEURS English, each clip at -26 dBFS, 1.5 s of silence between
(tests/audio/README.md)."""
BED = "music-bed-rock-558.opus"
"""The 30 s of a rock instrumental under it, at the speech's level."""
ALIGNMENTS = (0, 128, 256, 384)
"""Samples of silence put ahead of the mix: where the 512-sample frames
fall changes Silero's verdicts on speech over music (polyglotic-hq 536,
558), so each mix is judged at four."""


@pytest.fixture(scope="module")
def model() -> "InferenceSession":
    return load_model()


def _read(name: str) -> npt.NDArray[np.float32]:
    audio, rate = sf.read(str(AUDIO / name), dtype="float32")
    assert rate == SR
    return np.asarray(audio, dtype=np.float32)


def _sent(
    model: "InferenceSession", mix: npt.NDArray[np.float32], beds: bool = True
) -> list[tuple[float, float]]:
    """What the app sends of `mix` as finished captions (its detection and
    the default caption timing): each caption's audio, start and end (s)."""
    mode = default_caption_mode()
    timing = CaptionTiming(
        mode.live_update_interval(1.0), rules=mode.rules, max_wait=MAX_WAIT_FOR_TEXT_SEC
    )
    source = Source(SourceId("app"), SourceCategory.VIDEO)
    timing.add_source(source)
    detector = SpeechDetector(model, beds=beds)
    finished: dict[str, tuple[float, float]] = {}
    audio = np.concatenate([mix, np.zeros(3 * SR, np.float32)])
    for start in range(0, len(audio), SR // 10):
        for r in detector.feed(start / SR, audio[start : start + SR // 10]):
            for d in timing.frame(source.id, r.end, r.speech, r.level):
                if (
                    isinstance(d, TranscriptionRequest)
                    and d.kind is not SpeechKind.LIVE
                ):
                    for old in d.replaces:
                        finished.pop(old, None)
                    before, after = d.pads
                    finished[d.caption_id] = (
                        d.speech_start - before,
                        d.speech_end + after,
                    )
    return list(finished.values())


def _heard(
    model: "InferenceSession", db: float | None, pad: int, beds: bool = True
) -> tuple[float, float]:
    """The speech with the bed `db` dB under it (0: as loud; None: no bed,
    the speech alone with its digital silence between clips), after `pad`
    samples of silence: the share of its speech frames (those the plain
    detector, without decision 0267's rules, hears as
    speech in the speech alone) inside a finished caption's audio, and the
    longest unheard stretch (s) - from a speech frame not sent to the last
    one after it with none sent between: what a learner sits through with
    nothing shown while people talk."""
    silence = np.zeros(pad, np.float32)
    speech = np.concatenate([silence, _read(SPEECH)])
    bed = np.concatenate([silence, _read(BED)])
    mix = speech if db is None else speech + bed * np.float32(10 ** (db / 20))
    plain = SpeechDetector(
        model, beds=False
    )  # the truth never takes the rules under test
    truth = np.array([r.speech for r in plain.feed(0.0, speech)])
    mid = (np.arange(len(truth)) + 0.5) * FRAME_SAMPLES / SR
    sent = np.zeros(len(truth), bool)
    for a, b in _sent(model, mix, beds):
        sent |= (mid >= a) & (mid <= b)
    longest, first = 0.0, -1
    for i in map(int, np.flatnonzero(truth)):
        if sent[i]:
            first = -1
        else:
            first = i if first < 0 else first
            longest = max(longest, (i - first + 1) * FRAME_SAMPLES / SR)
    return float(sent[truth].mean()), longest


def test_speech_as_loud_as_a_rock_bed_is_heard(model: "InferenceSession") -> None:
    """A rock band as loud as the voices: before decision 0267 the app sent
    55-78 % of the speech, with 5.7-9.5 s unheard in a row, at every
    alignment (polyglotic-hq 558, 2026-11-20); through the floor filter and
    the bed threshold, 83-100 % and at most 1.8 s."""
    results = [_heard(model, 0.0, pad) for pad in ALIGNMENTS]
    assert np.mean([heard for heard, _ in results]) >= 0.85, results
    assert max(longest for _, longest in results) < 2.5, results


def test_speech_10_db_over_a_rock_bed_has_no_gap_of_2_s(
    model: "InferenceSession",
) -> None:
    """The brief's mark (polyglotic-hq 558): 10 dB over the bed, no stretch
    of speech of 2 s or more unheard, at any alignment."""
    for pad in ALIGNMENTS:
        heard, longest = _heard(model, -10.0, pad)
        assert heard >= 0.95 and longest < 2.0, (pad, heard, longest)


def test_the_speech_alone_is_heard_as_before(model: "InferenceSession") -> None:
    """No bed: all but a frame or two of the speech sent at every alignment,
    and as much over the four as with neither rule (`beds=False`, the rules
    before decision 0267: on this mix 99.95 % against 99.9 %)."""
    after = [_heard(model, None, pad) for pad in ALIGNMENTS]
    before = [_heard(model, None, pad, beds=False) for pad in ALIGNMENTS]
    for heard, longest in after:
        assert heard >= 0.99 and longest < 0.5, after
    assert np.mean([h for h, _ in after]) >= np.mean([h for h, _ in before]) - 0.005
