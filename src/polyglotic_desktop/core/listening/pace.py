"""Speaking pace over spoken span, with a hold and fade during silence."""

import re
from bisect import bisect_right
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

type WordCount = Callable[[str, str | None], int]

_WORD_RUN = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


def spaced_word_count(text: str, language: str | None) -> int:
    """Count word runs when the platform supplies no dictionary word boundaries."""
    return sum(1 for _ in _WORD_RUN.finditer(text))


WINDOW_SECONDS = 5.0
"""Seconds (> 0) shared by the spoken window, silence hold and linear fade."""

MIN_CAPTION_SECONDS = 1.0
"""Seconds (> 0) of spoken span needed to avoid extrapolating very short clips."""

PACE_BANDS = ("1_60", "61_120", "121_180", "181_240", "241_plus")


def _wpm(words: float, seconds: float) -> int:
    return round(words * 60 / seconds) if seconds > 0 else 0


def caption_pace(words: int, seconds: float) -> int | None:
    """A finished caption's pace, when its spoken span is long enough to measure."""
    if words > 0 and seconds >= MIN_CAPTION_SECONDS:
        return _wpm(words, seconds)
    return None


@dataclass(frozen=True, slots=True)
class PaceReading:
    """A pace value plus the counts needed to combine visible own speech."""

    now: int
    mean: int
    recent_words: float
    recent_seconds: float
    total_words: int
    total_seconds: float
    fade: float = 0.0
    """Remaining fraction of the current pace. Recent counts are weighted by it."""

    def combined(self, other: "PaceReading") -> "PaceReading":
        recent_words = self.recent_words + other.recent_words
        recent_seconds = self.recent_seconds + other.recent_seconds
        total_words = self.total_words + other.total_words
        total_seconds = self.total_seconds + other.total_seconds
        fade = max(self.fade, other.fade)
        return PaceReading(
            _wpm(recent_words * fade, recent_seconds),
            _wpm(total_words, total_seconds),
            recent_words,
            recent_seconds,
            total_words,
            total_seconds,
            fade,
        )


def _band(wpm: int) -> str | None:
    if wpm <= 0:
        return None
    if wpm <= 60:
        return PACE_BANDS[0]
    if wpm <= 120:
        return PACE_BANDS[1]
    if wpm <= 180:
        return PACE_BANDS[2]
    if wpm <= 240:
        return PACE_BANDS[3]
    return PACE_BANDS[4]


@dataclass(slots=True)
class PaceMeter:
    """Current and window-average WPM over finished captions' spoken spans."""

    _recent: deque[tuple[float, float, float]] = field(default_factory=deque)
    _recent_words: float = 0.0
    _recent_duration: float = 0.0
    _total_words: int = 0
    _total_duration: float = 0.0
    _peak: int = 0
    _last_spoken_at: float | None = None
    _bands: dict[str, float] = field(
        default_factory=lambda: dict.fromkeys(PACE_BANDS, 0.0)
    )

    def add(
        self,
        count: int,
        seconds: float,
        at: float,
        *,
        new_words: int | None = None,
    ) -> int:
        """Add one finished caption; dictionary words and spoken span count once."""
        count = max(0, count)
        duration = max(0.0, seconds)
        if not count or not duration:
            return self.now(at)
        current = self.extend(count if new_words is None else new_words, duration, at)
        self._total_words += count
        self._total_duration += duration
        self._peak = max(self._peak, current)
        band = _band(current)
        if band is not None:
            self._bands[band] += duration
        return current

    def extend(self, count: int, duration: float, at: float) -> int:
        """Advance the live window without counting the speech in the average."""
        last = self._last_spoken_at
        self._last_spoken_at = at if last is None else max(last, at)
        kept = min(duration, WINDOW_SECONDS)
        words = count * kept / duration
        piece = (at, words, kept)
        if self._recent and at < self._recent[-1][0]:
            # A delayed answer still belongs before more recent speech.
            index = bisect_right(self._recent, at, key=lambda sample: sample[0])
            self._recent.insert(index, piece)
        else:
            self._recent.append(piece)
        self._recent_words += words
        self._recent_duration += kept
        while self._recent_duration > WINDOW_SECONDS:
            end, old_words, old_duration = self._recent.popleft()
            trim = min(old_duration, self._recent_duration - WINDOW_SECONDS)
            removed = old_words * trim / old_duration
            self._recent_duration -= trim
            self._recent_words -= removed
            if trim < old_duration:
                self._recent.appendleft((end, old_words - removed, old_duration - trim))
        return _wpm(self._recent_words, self._recent_duration)

    def _fade(self, at: float) -> float:
        if self._last_spoken_at is None:
            return 0.0
        quiet = at - self._last_spoken_at
        return max(0.0, min(1.0, 2.0 - quiet / WINDOW_SECONDS))

    def now(self, at: float) -> int:
        """Current WPM, held through a pause and then faded linearly."""
        return _wpm(self._recent_words * self._fade(at), self._recent_duration)

    def reading(self, at: float) -> PaceReading:
        """Current and lifetime pace, retaining only content-free counts."""
        fade = self._fade(at)
        return PaceReading(
            _wpm(self._recent_words * fade, self._recent_duration),
            self.mean,
            self._recent_words * fade,
            self._recent_duration * fade,
            self._total_words,
            self._total_duration,
            fade,
        )

    @property
    def peak(self) -> int:
        return self._peak

    @property
    def mean(self) -> int:
        return _wpm(self._total_words, self._total_duration)

    @property
    def seconds(self) -> dict[str, int]:
        return {key: round(value) for key, value in self._bands.items()}
