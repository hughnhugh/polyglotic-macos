"""Speech detection: Silero VAD v6.2 on ONNX Runtime, without PyTorch.

The same model and streaming interface as the silero-vad package's
`OnnxWrapper` (v6.2.x, `src/silero_vad/utils_vad.py`), which needs torch;
this is the small part of it the app needs (from polyglotic-hq project
005's spike):
- 16kHz mono float audio, cut into 512-sample frames (32ms, the frames
  `core.listening.timing` counts in);
- each frame is given with the last 64 samples of the one before (the
  "context"), and the model's recurrent state (2 x 1 x 128) carries on, so
  each stream of audio needs its own `SpeechDetector`, fed in order;
- digital silence - frames of exact zeros, what Windows' capture delivers
  while an app plays nothing - for `SILENCE_RESET_SEC` starts the stream
  afresh: the state and context are forgotten, and those frames aren't
  run through the model (they're never speech). Carried through silence,
  the state stopped the model hearing quiet speech that followed:
  polyglotic-hq project 145 (2026-11-07) played FLEURS clips with 1.5s of
  silence between them, and 7 of 56 English clips - the quietest, peaking
  around -30 to -50 dBFS - lost their first 1.5-5s of speech, two of them
  all of it; the same clips on a fresh state were heard from 0.4-1.4s in;
- the model hears each frame through a gain (`DetectionGain`, decision
  0039): audio whose loudest sample in the last `GAIN_HOLD_SEC` is
  quieter than `GAIN_TARGET_PEAK` (-20 dBFS) is raised towards it, by at
  most `GAIN_MAX` (+40 dB); louder audio is heard as it is. Only the
  model hears it: the audio buffered and sent is never changed. The reset
  above only fires on exact zeros, and quiet speech after a quiet noise
  floor - a call's comfort noise, a video's room tone - was missed again:
  polyglotic-hq project 180 (2026-11-08) put pink noise at -60 or -50
  dBFS between 145's clips, and 7 of 56 started over 1s late or never;
  project 186 found what sets it off - a loud speaker before the noise -
  and, with a loud (-3 dBFS) and a quiet (-45 dBFS) speaker taking turns,
  missed 28 of 28 quiet English ones and 18 of 28 Mandarin. With the
  gain: none of them, and no sound that wasn't speech was sent.

- **the mic's audio is raised by `MIC_GAIN_MAX` at most** (+6 dB, not
  +40; decision 0145, polyglotic-hq 352). The gain exists for app audio,
  where a quiet speaker after a loud one is content the learner chose to
  hear. On the mic the learner is the closest, loudest voice; what is
  quiet there is the room - speakers turned down, headphones' leak, a TV -
  and raised +40 dB the model heard it as speech even under the mic's own
  hiss. Everything else about detection is the same for every source.

The model is `silero_vad_16k_op15.onnx` from Silero VAD v6.2.3 (MIT; see
THIRD_PARTY_NOTICES.md), committed with this package - decision 0003.

ONNX Runtime is imported when the model is loaded, not with this module
(about 70 ms; the app's window shows first - polyglotic-hq project 110).
"""

import threading
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from polyglotic_desktop.core.listening.timing import FRAME_SAMPLES, VAD_SAMPLE_RATE

if TYPE_CHECKING:
    import onnxruntime as ort

MODEL_FILE = "silero_vad_16k_op15.onnx"
MODEL_SHA256 = "7ed98ddbad84ccac4cd0aeb3099049280713df825c610a8ed34543318f1b2c49"
SPEECH_THRESHOLD = 0.5  # a frame is speech at this probability or above
CONTEXT_SAMPLES = 64
SILENCE_RESET_SEC = 0.25
"""Digital silence this long starts the stream afresh (the module's
docstring): longer than the zeros a codec can leave between words, so the
state carries on through speech, and far shorter than a pause between
sentences."""
_SILENCE_RESET_FRAMES = int(
    np.ceil(SILENCE_RESET_SEC * VAD_SAMPLE_RATE / FRAME_SAMPLES)
)
GAIN_TARGET_PEAK = 0.1
"""The model hears audio quieter than this peak (-20 dBFS) raised towards
it (decision 0039). Ordinary speech peaks above it, so it is heard as it
is: the gain changes nothing for it. Project 180's -6 dBFS also found the
missed speech, but raised ordinary speech too, and finished captions about
30 ms later at the median on FLEURS as recorded (project 186)."""
GAIN_MAX = 100.0
"""The most the gain raises audio: +40 dB, enough to bring the quietest of
the FLEURS English clips projects 145, 180 and 186 used (-51 dBFS at its
peak) to the target with 10 dB to spare; anything quieter than -60 dBFS -
a source's hiss - stays below it."""
GAIN_HOLD_SEC = 1.5
"""The gain follows the loudest sample of this long: shorter and it rises
in the pauses between a loud speaker's words, longer and a quiet speaker
who answers a loud one soon after is still missed (project 186: with 3s,
12 of 28 quiet speakers half a second after a loud one; with 1-2s, none)."""
_GAIN_HOLD_FRAMES = round(GAIN_HOLD_SEC * VAD_SAMPLE_RATE / FRAME_SAMPLES)
MIC_GAIN_MAX = 2.0
"""The most the gain raises the mic's audio: +6 dB (decision 0145). On
polyglotic-hq 352's bench (FLEURS speech, Wikimedia Commons noises,
synthetic rooms; the app's own detection, timing and bleed check, Live
updates) the room's sound sent from the mic as the learner's fell from 287
requests to 119, and the learner's own speech dropped as bleed from 30
stretches to 7; all 360 of the learner's clips, down to -52 dBFS, were
still heard. With no gain at all less of the room was sent, but a quiet
answer 30 dB under the learner's own loud sentence lost a quarter of its
seconds on a laptop's mic."""

Audio = npt.NDArray[np.float32]


def model_path() -> Path:
    return Path(str(files("polyglotic_desktop.platform") / "data" / MODEL_FILE))


def load_model(path: Path | None = None) -> "ort.InferenceSession":
    """The speech-detection model, on the CPU with one thread. One session
    serves every stream; each stream keeps its own state."""
    import onnxruntime as ort  # here: the app doesn't wait for it to start

    options = ort.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    options.log_severity_level = 3  # errors only
    return ort.InferenceSession(
        str(path or model_path()),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


class ModelOnDemand:
    """The speech-detection model, loaded once - on a thread of its own -
    when a source is first captioned, not at every start: an app waiting in
    the tray with nothing captioned (started with Windows) holds neither
    onnxruntime nor the model, about 19 MB of private memory and 30 MB of
    working set (polyglotic-hq 513, measured on the main PC). `start` begins
    the load (as a source is added, so it loads while the capture starts);
    `result` waits for it, from the capture's thread at its first audio."""

    def __init__(self, load: Callable[[], "ort.InferenceSession"] = load_model) -> None:
        self._load = load
        self._lock = threading.Lock()
        self._loading: Future[ort.InferenceSession] | None = None

    @property
    def started(self) -> bool:
        return self._loading is not None

    def start(self) -> None:
        """Begins loading the model, once; returns at once."""
        with self._lock:
            if self._loading is None:
                loader = ThreadPoolExecutor(1, thread_name_prefix="speech-model")
                self._loading = loader.submit(self._load)
                loader.shutdown(wait=False)

    def result(self) -> "ort.InferenceSession":
        """The model, loading it first if nothing has started it."""
        self.start()
        assert self._loading is not None
        return self._loading.result()


class DetectionGain:
    """The gain one stream's frames are heard through by the model: each
    frame raised so the loudest sample of the last `GAIN_HOLD_SEC` (this
    frame's included, so a loud frame is never raised) reaches
    `GAIN_TARGET_PEAK`, by at most `most` (`GAIN_MAX` unless given);
    never lowered. Frames are returned as new arrays - the audio given is
    never changed."""

    def __init__(self, most: float = GAIN_MAX) -> None:
        """`most`: the most it raises audio (a factor) - GAIN_MAX, or
        MIC_GAIN_MAX for the mic."""
        self._most = most
        self._peaks: deque[float] = deque(maxlen=_GAIN_HOLD_FRAMES)

    def reset(self) -> None:
        """Forgets the audio heard so far."""
        self._peaks.clear()

    def apply(self, frame: Audio) -> Audio:
        """The next frame of the stream, as the model is to hear it."""
        self._peaks.append(float(np.max(np.abs(frame))))
        peak = max(self._peaks)
        if peak <= 0.0 or peak >= GAIN_TARGET_PEAK:
            return frame
        return frame * np.float32(min(self._most, GAIN_TARGET_PEAK / peak))


@dataclass(frozen=True, slots=True)
class FrameResult:
    """One frame's speech detection: when it ended (the app's clock),
    whether it was speech, and its `level` - its loudness as captured (root
    mean square, before the gain): where a caption is cut while the speech
    goes on (`CaptionTiming.frame`, polyglotic-hq 291)."""

    end: float
    speech: bool
    level: float | None = None


class SpeechDetector:
    """Speech detection for one stream of 16kHz mono audio."""

    def __init__(
        self, model: "ort.InferenceSession", gain_max: float = GAIN_MAX
    ) -> None:
        """`gain_max`: the most quiet audio is raised for the model -
        MIC_GAIN_MAX for the mic (decision 0145)."""
        self._model = model
        self._sample_rate = np.array(VAD_SAMPLE_RATE, dtype=np.int64)
        self._gain = DetectionGain(gain_max)
        self.reset()

    def reset(self) -> None:
        """Forgets the stream so far (a new device, a new stream)."""
        self._afresh()
        self._leftover: Audio = np.zeros(0, dtype=np.float32)
        self._silent_frames = 0

    def _afresh(self) -> None:
        """The model's state and context, and the gain, as at the start of
        a stream."""
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)
        self._gain.reset()

    def _is_speech(self, frame: Audio) -> bool:
        """The next frame's verdict, heard through the gain - after
        `SILENCE_RESET_SEC` of digital silence, not run through the model,
        the stream started afresh."""
        if frame.any():
            self._silent_frames = 0
        else:
            self._silent_frames += 1
            if self._silent_frames >= _SILENCE_RESET_FRAMES:
                self._afresh()
                return False
        return self.probability(self._gain.apply(frame)) >= SPEECH_THRESHOLD

    def probability(self, frame: Audio) -> float:
        """The speech probability (0-1) of the next 512-sample frame, as
        given (no gain)."""
        x = np.concatenate([self._context, frame.reshape(1, FRAME_SAMPLES)], axis=1)
        out, self._state = self._model.run(
            None, {"input": x, "state": self._state, "sr": self._sample_rate}
        )
        self._context = x[:, -CONTEXT_SAMPLES:]
        return float(out[0, 0])

    def feed(self, start: float, audio: Audio) -> list[FrameResult]:
        """Audio starting at `start` (the app's clock), continuing the
        stream: the result of every frame it completes."""
        buffer = np.concatenate([self._leftover, audio.astype(np.float32, copy=False)])
        count = len(buffer) // FRAME_SAMPLES
        self._leftover = buffer[count * FRAME_SAMPLES :]
        # Frame i ends (i + 1) frames into the buffer, which began before
        # `start` by the leftover's length.
        first_end = (
            start + (FRAME_SAMPLES - (len(buffer) - len(audio))) / VAD_SAMPLE_RATE
        )
        results = []
        for i in range(count):
            frame = buffer[i * FRAME_SAMPLES : (i + 1) * FRAME_SAMPLES]
            end = first_end + i * FRAME_SAMPLES / VAD_SAMPLE_RATE
            level = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
            results.append(FrameResult(end, self._is_speech(frame), level))
        return results
