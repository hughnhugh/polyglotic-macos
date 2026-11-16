"""Mic bleed: the PC's own audio picked up by the mic, caught by cancelling it.

Mic speech that is mostly what the PC was playing is the PC's audio
leaking from speakers or headphones into the mic, not the user talking.
What played is cancelled out of the mic, as an echo canceller does, and
what's left is judged (decision 0154, polyglotic-hq 363) - only to judge:
the audio sent is never changed. Pure numpy:
- the delay is found from the two signals (GCC-PHAT: their
  cross-correlation with each frequency weighted equally, sharp at the
  speakers' direct path however the room colours it), the mic up to 1s
  behind the PC (decision 0082: Bluetooth speakers and wireless mics);
- the room is fitted per frequency (32ms STFT bins, 150-5000Hz) as a short
  filter over CANCEL_TAPS frames from that delay, by least squares, and
  taken out of the mic;
- it's bleed when that takes away at least BLEED_CANCELLED of the mic's
  sound above its own noise floor (a low percentile of the last
  FLOOR_SEC of the mic, per bin): faint bleed sits near the floor, where
  a share of the whole mic can't tell it from the user. The user's voice
  is left whole however loud the speakers are under it;
- or when the mic's loudness follows what played (the proof of
  concept's check, `overlay_core.is_bleed`, alone until decision 0154):
  loudness envelopes in 20ms frames, in log terms, a 5-frame running
  median on the mic taking out clicks and taps, a correlation of at least
  0.65 (decision 0082). It still catches the speakers when typing or taps
  on the mic leave more than cancelling can take away;
- at least 0.35s of audio is needed (BLEED_MIN_SEC), and nothing is bleed
  when the PC was nearly silent (under about -66 dBFS: Windows' loopback
  of an output can be at its volume slider's level while the speakers are
  turned up, decision 0082).

What the PC played is the whole system's loopback on the output device,
whatever is being captioned - decision 0004.

**Seen without content** (polyglotic-hq 290): each stretch compared is
kept with its numbers (`BleedMeasure`: the best correlation, the lag it
was found at, whether what played was nearly silent) for the caption
log's line (`log_line`); `survey` runs the check over a few seconds for
the harness's `bleed`, a learner's own 20-second check. A stretch that
couldn't be compared gets its line too, saying why (`NotCompared`,
polyglotic-hq 363: 14 of the mic's finished captions in a learner's log
had no line, 9 of them phantoms).
"""

from collections import deque
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from polyglotic_desktop.platform.audio_buffer import AudioBuffer
from polyglotic_desktop.platform.speech_detection import Audio

BLEED_CANCELLED = 0.6
"""Bleed when cancelling what played takes away at least this share of the
mic's sound above its noise floor (decision 0154)."""
BLEED_CORRELATION = 0.65
"""Bleed, too, when the mic's loudness follows what played this closely
(0.6 until decision 0082)."""
CANCEL_TAPS = 6
"""The room's filter, in 16ms hops before the delay found: about 100ms of
its echo."""
DELAY_FROM_SEC = 4.0
"""The delay is found on this much of the end of a stretch at most."""
FLOOR_SEC = 10.0
"""The mic's noise floor is measured over this much of it before a
stretch's end."""
BLEED_MAX_LAG_SEC = 1.0
"""How far the mic can trail the PC's output: the output device's latency
(Bluetooth's alone is typically 0.1-0.3s) and the mic's. 0.5s until
decision 0082."""
BLEED_MIN_SEC = 0.35
"""The shortest stretch compared: under the shortest a finished caption can
be (12 speech frames of 32ms, 0.384s), so none is sent unchecked. 0.4s
until polyglotic-hq 363: those 0.384s stretches went out with no check, 9
of the 11 in a learner's log phantoms."""
SILENT_PLAYBACK_RMS = 0.0005
"""What the PC played is nearly silent below this loudness (20ms frames,
about -66 dBFS). 0.005 (-46 dBFS) until decision 0082."""
CHECKED_KEPT = 32  # stretches checked, kept until the caption log takes them
_ENVELOPE_FRAME = 320  # 20ms at 16kHz
_FRAME_SEC = 0.02
_SILENT_PLAYBACK = float(np.log(SILENT_PLAYBACK_RMS))
_FFT = 512  # 32ms
_HOP = 256
_BAND = (150.0, 5000.0)


def _in_band(hz: np.ndarray) -> np.ndarray:
    in_band: np.ndarray = (hz >= _BAND[0]) & (hz <= _BAND[1])
    return in_band


_IN_BAND = _in_band(np.fft.rfftfreq(_FFT, 1 / 16000))
_WINDOW = np.hanning(_FFT).astype(np.float32)
_FLOOR_PERCENTILE = 20.0


class NotCompared(StrEnum):
    """Why a stretch of the mic wasn't compared with what the PC played."""

    SHORT = "short"
    """Under BLEED_MIN_SEC (or under 0.2s of loudness to compare)."""
    NO_MIC_AUDIO = "no_mic_audio"
    """The mic's buffer has none of the stretch."""
    NO_PLAYED_AUDIO = "no_played_audio"
    """The buffer of what the PC played has none of it."""
    PLAYED_SHORT = "played_short"
    """What the PC played covers less of the time than the mic does."""
    FLAT = "flat"
    """The mic's loudness doesn't move at all."""


@dataclass(frozen=True, slots=True)
class BleedMeasure:
    """What the check found for one stretch of the mic - numbers only: the
    best correlation of the loudness envelopes (None: not compared), how
    far the mic trailed what played at the best (seconds), whether what
    played was nearly silent, when not compared, why, and the share of
    the mic's sound above its floor that cancelling what played took away
    (None: not cancelled). Bleed when either is high enough."""

    correlation: float | None
    lag: float | None
    played_silent: bool = False
    not_compared: NotCompared | None = None
    cancelled: float | None = None

    @property
    def bleed(self) -> bool:
        cancelled = self.cancelled is not None and self.cancelled >= BLEED_CANCELLED
        follows = self.correlation is not None and self.correlation >= BLEED_CORRELATION
        return cancelled or follows


def _not_compared(why: NotCompared) -> BleedMeasure:
    return BleedMeasure(None, None, not_compared=why)


def _envelope(audio: Audio) -> Audio:
    """Loudness over time, 20ms frames, in log terms - comparable between a
    loud original and a quiet copy of it."""
    n = len(audio) // _ENVELOPE_FRAME
    frames = audio[: n * _ENVELOPE_FRAME].reshape(n, _ENVELOPE_FRAME)
    envelope: Audio = np.log(np.sqrt((frames**2).mean(axis=1)) + 1e-4).astype(
        np.float32
    )
    return envelope


def _median5(values: Audio) -> Audio:
    if len(values) < 5:
        return values
    padded = np.pad(values, 2, mode="edge")
    median: Audio = np.median(
        np.lib.stride_tricks.sliding_window_view(padded, 5), axis=1
    )
    return median


def correlate(mic: Audio, played: Audio) -> BleedMeasure:
    """How much `mic`'s loudness moves with what the PC played (`played`,
    ending when `mic` ends and starting earlier - by BLEED_MAX_LAG_SEC in
    the check): the best correlation over each lag of the mic behind the
    PC, and that lag - half the verdict (`measure` cancels too)."""
    # A running median over 100ms takes out clicks, taps and bumps on the
    # mic - the light noise that opened the speech segment - while
    # syllables of real speech, a few times longer, come through.
    m, p = _median5(_envelope(mic)), _envelope(played)
    if len(m) < 10:
        return _not_compared(NotCompared.SHORT)  # too short to tell
    if len(p) < len(m):
        return _not_compared(NotCompared.PLAYED_SHORT)
    if p.max() < _SILENT_PLAYBACK:
        return BleedMeasure(None, None, played_silent=True)
    if m.std() < 1e-6:
        return _not_compared(NotCompared.FLAT)
    best, at = -1.0, 0
    for offset in range(len(p) - len(m) + 1):  # each lag of the mic behind the PC
        window = p[offset : offset + len(m)]
        if window.std() < 1e-6:
            continue
        correlation = float(np.corrcoef(m, window)[0, 1])
        if correlation > best:
            best, at = correlation, offset
    # both end together: the window `at` frames in is the mic's, that far behind
    return BleedMeasure(best, (len(p) - len(m) - at) * _FRAME_SEC, played_silent=False)


def _stft(audio: Audio) -> np.ndarray:
    """32ms frames every 16ms, the band's bins only."""
    frames = 1 + (len(audio) - _FFT) // _HOP
    if frames <= 0:
        return np.zeros((0, int(_IN_BAND.sum())), np.complex64)
    at = np.arange(_FFT)[None, :] + _HOP * np.arange(frames)[:, None]
    spectrum: np.ndarray = np.fft.rfft(audio[at] * _WINDOW, axis=1)[:, _IN_BAND]
    return spectrum


def floor_power(history: Audio | None) -> np.ndarray | None:
    """The mic's noise floor per bin: a low percentile of its power over
    `history`, as the mean of noise that sits there (None: under half a
    second to tell from)."""
    if history is None or len(history) < _FFT + 30 * _HOP:
        return None
    power = np.abs(_stft(history)) ** 2
    low = np.percentile(power, _FLOOR_PERCENTILE, axis=0)
    # noise's power in a bin is exponential: its p-th percentile is
    # -ln(1 - p) of its mean
    floor: np.ndarray = low / -np.log(1 - _FLOOR_PERCENTILE / 100)
    return floor


def _delay(mic: Audio, played: Audio) -> int:
    """GCC-PHAT: how many samples the mic trails `played`, both ending
    together, from 0 to as far as `played` starts earlier - found on the
    last DELAY_FROM_SEC of the mic (the delay doesn't change within a
    stretch, and a long one's transforms cost ten times as much)."""
    early = len(played) - len(mic)
    keep = min(len(mic), int(DELAY_FROM_SEC * 16000))
    mic, played = mic[len(mic) - keep :], played[len(played) - keep - early :]
    size = 1 << (len(played) + len(mic)).bit_length()
    cross = np.fft.rfft(mic, size) * np.conj(np.fft.rfft(played, size))
    cross /= np.abs(cross) + 1e-12
    hz = np.fft.rfftfreq(size, 1 / 16000)
    cross[~_in_band(hz)] = 0
    correlation = np.fft.irfft(cross, size)
    # the mic `d` behind: its sample i is played's i + early - d, which
    # puts the peak at shift d - early
    shifts = np.arange(-early, 1)
    return early + int(shifts[int(np.argmax(correlation[shifts % size]))])


def cancel(mic: Audio, played: Audio, floor: np.ndarray | None) -> float | None:
    """The share of `mic`'s sound above its noise floor (`floor_power`; the
    whole of it when None) that cancelling what played takes away: near 1
    for the speakers alone, however faint; near 0 for the user's voice,
    however loud the speakers under it. None: too short to fit."""
    delay = _delay(mic, played)
    start = len(played) - len(mic) - delay  # the mic's start in `played`
    # the aligned reference, with CANCEL_TAPS hops of history before it
    # (the room's echo) and one after (slack in the delay found)
    lo, hi = start - _HOP * CANCEL_TAPS, start + len(mic) + _HOP
    reference = np.concatenate(
        [
            np.zeros(max(0, -lo), np.float32),
            played[max(0, lo) : min(len(played), hi)],
            np.zeros(max(0, hi - len(played)), np.float32),
        ]
    )
    heard, sound = _stft(mic), _stft(reference)
    frames, taps = heard.shape[0], CANCEL_TAPS + 2
    if frames < 3 * taps:
        return None
    # per bin, x[bin, t, c] = sound[t + c, bin]: c = CANCEL_TAPS is the
    # aligned frame; the filter is least squares, x's weights making the mic
    x = np.ascontiguousarray(
        np.lib.stride_tricks.sliding_window_view(
            sound[: frames + taps - 1], frames, axis=0
        ).transpose(1, 2, 0)
    )
    xh = x.conj().transpose(0, 2, 1)
    xx = xh @ x
    ridge = 1e-6 * np.trace(xx, axis1=1, axis2=2).real / taps + 1e-12
    mic_by_bin = np.ascontiguousarray(heard.T)[..., None]
    weights = np.linalg.solve(xx + ridge[:, None, None] * np.eye(taps), xh @ mic_by_bin)
    left = float((np.abs(mic_by_bin - x @ weights) ** 2).sum())
    total = float((np.abs(heard) ** 2).sum()) + 1e-12
    if floor is None:
        return 1.0 - left / total
    noise = float(floor.sum()) * frames
    # a fit of `taps` weights to `frames` frames takes about taps/frames of
    # any noise away by chance: that much less of the floor is left
    noise_left = noise * (1 - taps / frames)
    share = 1.0 - max(left - noise_left, 0.0) / max(total - noise, 1e-12)
    return float(min(max(share, -1.0), 1.0))


def measure(mic: Audio, played: Audio, history: Audio | None = None) -> BleedMeasure:
    """The check on `mic` against what the PC played (`played`, ending when
    `mic` ends and starting earlier - by BLEED_MAX_LAG_SEC in the check),
    the mic's floor from `history` (the mic before, up to `mic`'s end):
    the loudness correlation and its lag, and what cancelling took away."""
    found = correlate(mic, played)
    if found.correlation is None:
        return found
    taken = cancel(mic, played, floor_power(history))
    return BleedMeasure(found.correlation, found.lag, cancelled=taken)


@dataclass(frozen=True, slots=True)
class Checked:
    """One stretch of the mic checked: how long, and what was found."""

    seconds: float
    found: BleedMeasure


def log_line(checked: Checked, outputs_playing: int | None) -> str:
    """The caption log's line for one stretch of the mic checked - numbers
    only: its seconds, the best correlation and its lag, the share
    cancelling took away, whether what played was nearly silent (or why it
    wasn't compared), how many outputs were playing (None: not known), and
    the verdict."""
    found = checked.found
    fields = {
        "seconds": f"{checked.seconds:.2f}",
        "correlation": None
        if found.correlation is None
        else f"{found.correlation:.2f}",
        "lag_ms": None if found.lag is None else round(found.lag * 1000),
        "cancelled": None if found.cancelled is None else f"{found.cancelled:.2f}",
        "not_compared": found.not_compared and found.not_compared.value,
        "played": None
        if found.not_compared
        else "silent"
        if found.played_silent
        else "sound",
        "outputs_playing": outputs_playing,
        "bleed": "yes" if found.bleed else "no",
    }
    said = [f"{name}={value}" for name, value in fields.items() if value is not None]
    return " ".join(["mic bleed_check", *said])


class MicBleed:
    """The mic's bleed check for `core.listening.timing` (the
    `MicBleedCheck` port): the mic's audio against what the PC played.
    Each stretch checked is kept (`checked`) until taken, for the caption
    log, compared or not: the check runs under the speech pipeline's lock,
    the log is written after it."""

    def __init__(self, mic: AudioBuffer, played: AudioBuffer) -> None:
        self._mic = mic
        self._played = played
        self._checked: deque[Checked] = deque(maxlen=CHECKED_KEPT)

    def __call__(self, start: float, end: float, /) -> bool:
        found = self.measure(start, end)
        self._checked.append(Checked(end - start, found))
        return found.bleed

    def measure(self, start: float, end: float) -> BleedMeasure:
        """The check's numbers for the mic's audio from `start` to `end`."""
        if end - start < BLEED_MIN_SEC:
            return _not_compared(NotCompared.SHORT)
        mic = self._mic.slice(start, end)
        if mic is None:
            return _not_compared(NotCompared.NO_MIC_AUDIO)
        played = self._played.slice(start - BLEED_MAX_LAG_SEC, end)
        if played is None:
            return _not_compared(NotCompared.NO_PLAYED_AUDIO)
        history = self._mic.slice(end - FLOOR_SEC, end, pad=0.0)
        return measure(mic, played, history)

    def checked(self) -> list[Checked]:
        """The stretches checked since last asked, oldest first."""
        taken = []
        while self._checked:
            taken.append(self._checked.popleft())
        return taken


SURVEY_STRETCH_SEC = 3.0
SURVEY_STEP_SEC = 1.0
SURVEY_MAX_LAG_SEC = 2.0
"""How late the survey looks for the speakers in the mic: past the check's
own range, to say how far past it they are."""


@dataclass(frozen=True, slots=True)
class BleedSurvey:
    """The bleed check over a few seconds of the mic beside what the PC
    played, in SURVEY_STRETCH_SEC stretches - numbers only (the harness's
    `bleed`, for a learner whose speakers' sound is captioned as theirs).
    Loudness is the loudest 20ms, in dBFS; correlations, shares cancelled
    and lags are the stretches' medians (None: none compared)."""

    stretches: int
    played_db: float
    mic_db: float
    played_silent: int
    caught: int
    correlation: float | None
    cancelled: float | None
    lag: float | None
    """Where the best match is, the mic up to SURVEY_MAX_LAG_SEC late."""
    best: float | None
    """The best match's correlation."""


def _loudest_db(audio: Audio | None) -> float:
    if audio is None or len(audio) < _ENVELOPE_FRAME:
        return -120.0
    n = len(audio) // _ENVELOPE_FRAME
    rms = np.sqrt((audio[: n * _ENVELOPE_FRAME].reshape(n, -1) ** 2).mean(axis=1))
    return float(20 * np.log10(rms.max() + 1e-6))


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def survey(
    mic: AudioBuffer, played: AudioBuffer, start: float, end: float
) -> BleedSurvey:
    """The check on every SURVEY_STRETCH_SEC of the mic from `start` to
    `end`, a stretch every SURVEY_STEP_SEC; and where the mic best matches
    what played, up to SURVEY_MAX_LAG_SEC late."""
    check = MicBleed(mic, played)
    found: list[BleedMeasure] = []
    wide: list[BleedMeasure] = []
    at = start
    while at + SURVEY_STRETCH_SEC <= end + 1e-9:
        stop = at + SURVEY_STRETCH_SEC
        found.append(check.measure(at, stop))
        heard, sound = mic.slice(at, stop), played.slice(at - SURVEY_MAX_LAG_SEC, stop)
        if heard is not None and sound is not None:
            wide.append(correlate(heard, sound))
        at += SURVEY_STEP_SEC
    return BleedSurvey(
        stretches=len(found),
        played_db=_loudest_db(played.slice(start, end, pad=0.0)),
        mic_db=_loudest_db(mic.slice(start, end, pad=0.0)),
        played_silent=sum(f.played_silent for f in found),
        caught=sum(f.bleed for f in found),
        correlation=_median(
            [f.correlation for f in found if f.correlation is not None]
        ),
        cancelled=_median([f.cancelled for f in found if f.cancelled is not None]),
        lag=_median([w.lag for w in wide if w.lag is not None]),
        best=_median([w.correlation for w in wide if w.correlation is not None]),
    )
