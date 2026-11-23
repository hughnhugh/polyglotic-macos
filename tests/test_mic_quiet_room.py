"""The mic hears the learner, not the room: real speech, quiet, under a mic's hiss.

polyglotic-hq 352 (decision 0145): speakers turned down, or headphones'
leak, reach the mic as speech far under the learner's voice - near or under
the mic's own hiss. Raised +40 dB for speech detection (the gain that hears
a quiet speaker after a loud one in an app, decision 0039), it was heard as
speech and captioned as the learner's ("You"); the mic's gain now stops at
MIC_GAIN_MAX. The learner's own quiet speech, over the same hiss, is still
sent. One public FLEURS clip (`tests/audio/README.md`), as
`test_quiet_speech.py` uses it.
"""

from typing import TYPE_CHECKING

import numpy as np
import pytest
from tests.test_quiet_speech import AS_RECORDED_DBFS, CHUNK, SR, _clip, _noise

from polyglotic_desktop.core.listening.sources import Source, SourceId
from polyglotic_desktop.core.listening.timing import (
    CaptionMode,
    CaptionTiming,
    SpeechKind,
    TranscriptionRequest,
)
from polyglotic_desktop.platform.speech_detection import (
    MIC_GAIN_MAX,
    SpeechDetector,
    load_model,
)
from polyglotic_desktop.ports.capture import SourceCategory

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

MIC = Source(SourceId("mic"), SourceCategory.MIC)
HISS_DBFS = -70.0
"""A headset's mic, quiet: its own hiss (RMS)."""
ROOM_DBFS = -62.0
"""Speech from the room at this peak: 8 dB over the hiss's RMS, about the
hiss's own peaks - the speakers turned down, or headphones' leak."""


@pytest.fixture(scope="module")
def model() -> "InferenceSession":
    return load_model()


def _sent(detector: SpeechDetector, audio: np.ndarray) -> list[TranscriptionRequest]:
    """The finished captions Steady's rules send from the mic for `audio`,
    fed as capture feeds it, with a second of hiss after."""
    timing = CaptionTiming(None, rules=CaptionMode.WHOLE.rules)
    timing.add_source(MIC)
    tail = _noise(1.0, HISS_DBFS, alpha=0.5, seed=4)
    audio = np.concatenate([audio, tail])
    out = []
    for i in range(0, len(audio), CHUNK):
        for frame in detector.feed(i / SR, audio[i : i + CHUNK]):
            for d in timing.frame(MIC.id, frame.end, frame.speech):
                if (
                    isinstance(d, TranscriptionRequest)
                    and d.kind is SpeechKind.FINISHED
                ):
                    out.append(d)
    return out


def _over_hiss(peak_dbfs: float) -> np.ndarray:
    speech = _clip(peak_dbfs)
    lead = _noise(1.0, HISS_DBFS, alpha=0.5, seed=2)
    hiss = _noise(len(speech) / SR, HISS_DBFS, alpha=0.5, seed=3)
    return np.concatenate([lead, speech + hiss]).astype(np.float32)


def test_speech_from_the_room_near_the_mics_hiss_is_not_sent(
    model: "InferenceSession",
) -> None:
    assert _sent(SpeechDetector(model, MIC_GAIN_MAX), _over_hiss(ROOM_DBFS)) == []


def test_the_learners_quiet_speech_over_the_same_hiss_is_sent(
    model: "InferenceSession",
) -> None:
    """The clip as recorded peaks at -44.9 dBFS: quiet for a learner at the
    mic, 25 dB over its hiss."""
    sent = _sent(SpeechDetector(model, MIC_GAIN_MAX), _over_hiss(AS_RECORDED_DBFS))
    assert sent
    heard = sum(r.speech_end - r.speech_start for r in sent)
    assert heard >= 0.6 * len(_clip(AS_RECORDED_DBFS)) / SR


def test_an_apps_quiet_speaker_is_still_heard_raised(
    model: "InferenceSession",
) -> None:
    """Every other source keeps decision 0039's gain: the same quiet speech,
    in an app, is content the learner chose to hear."""
    assert _sent(SpeechDetector(model), _over_hiss(ROOM_DBFS))
