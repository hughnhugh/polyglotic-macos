"""Keeping a capture's audio continuous, and which device it follows - the
parts of capture every OS shares (Windows' WASAPI and macOS' Core Audio
alike, polyglotic-hq 411).

- `Timeline`: loopback and taps deliver nothing (or a stall) while nothing
  plays; gaps become silence, overlaps are dropped, so the audio a source
  delivers is continuous on the app's clock and its times only move
  forward.
- `wanted_device`: the device the learner chose while it's plugged in,
  else the OS's default (the proof of concept's `_wanted`).

Audio here is 16kHz mono float32, little-endian, as `AudioCallback` takes it.
"""

from collections.abc import Callable

from polyglotic_desktop.core.listening.timing import VAD_SAMPLE_RATE

GAP_SEC = 0.05  # a jump bigger than this in packet times is a gap or an overlap
IDLE_FILL_BEHIND_SEC = 0.1  # with no packets, fill silence up to this long ago
MAX_FILL_SEC = 2.0  # the most silence a gap is filled with
ENDING_SILENCE_SEC = 1.0  # after an app closes: more than the 0.8s pause
BYTES_PER_SAMPLE = 4  # float32 mono


class Timeline:
    """Keeps a source's audio continuous on the app's clock: a gap between
    packets (nothing was playing) becomes silence, an overlap is dropped,
    and small jitter is ignored, so the times only move forward."""

    def __init__(self) -> None:
        self.end: float | None = None  # the end of what was delivered

    def packet(self, start: float, samples: bytes) -> list[tuple[float, bytes]]:
        """What to deliver for a packet recorded from `start`."""
        out = []
        if self.end is None:
            self.end = start
        gap = start - self.end
        if gap > GAP_SEC:
            # Silence, enough to end any speech segment; a longer outage
            # (no device for a while) jumps ahead rather than filling it all.
            out.append((self.end, silence(min(gap, MAX_FILL_SEC))))
            self.end = start
        elif gap < -GAP_SEC:
            samples = samples[bytes_for(-gap) :]
        if samples:
            out.append((self.end, samples))
            self.end += len(samples) / BYTES_PER_SAMPLE / VAD_SAMPLE_RATE
        return out

    def idle(self, now: float) -> list[tuple[float, bytes]]:
        """Silence up to shortly before `now`, while no packets come."""
        if self.end is None or now - IDLE_FILL_BEHIND_SEC - self.end <= GAP_SEC:
            return []
        upto = now - IDLE_FILL_BEHIND_SEC
        out = [(self.end, silence(upto - self.end))]
        self.end += len(out[0][1]) / BYTES_PER_SAMPLE / VAD_SAMPLE_RATE
        return out

    def ending(self) -> list[tuple[float, bytes]]:
        """The source has ended (the app closed): ENDING_SILENCE_SEC of
        silence, so speech in progress reaches its pause and is finished."""
        if self.end is None:
            return []
        out = [(self.end, silence(ENDING_SILENCE_SEC))]
        self.end += ENDING_SILENCE_SEC
        return out


def bytes_for(seconds: float) -> int:
    """How many bytes `seconds` of 16kHz mono float32 audio take."""
    return round(seconds * VAD_SAMPLE_RATE) * BYTES_PER_SAMPLE


def silence(seconds: float) -> bytes:
    """`seconds` of 16kHz mono float32 zeros."""
    return bytes(bytes_for(seconds))


def wanted_device(
    chosen: str | None,
    plugged_in: Callable[[], list[str]],
    default: Callable[[], str | None],
) -> str | None:
    """The device to capture: `chosen` if it's plugged in, else the OS's
    default; None if there's none, or the OS can't say. (The proof of
    concept's `_wanted`.)"""
    try:
        if chosen and chosen in plugged_in():
            return chosen
        return default()
    except OSError:
        return None
