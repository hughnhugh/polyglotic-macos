"""Sound without speech: the stretches where a source played sound that speech detection never heard as speech (polyglotic-hq 549, decision 0256).

The user's problem report of 2026-11-20 18:11 ("Another long hang"): the
caption log showed nothing *sent* for 28.2 s, 23.9 s and 16.5 s, with
answers and drawing instant around them. Either nothing was said, or
speech detection had gone deaf - polyglotic-hq 536 found Silero's state
carried through a song's band stopped it hearing the singing (decision
0254 forgets it after 5 s). The caption timelines (`perf.trace`) see only
what was sent, so they couldn't tell which.

`SoundUnheard` watches one source's frames as speech detection judged
them. A **stretch** begins at a frame heard as not speech whose level is
at least `FLOOR_DBFS`, and goes on while nothing is heard as speech:

- quieter frames inside it - the gaps between a missed speaker's words,
  a song's breath - don't end it unless they last `QUIET_SEC`; it ends at
  the last frame at the floor or above (`quiet`);
- speech heard ends it where that speech began (`speech`) - once there
  is as much as the timing would send (`MIN_SPEECH_SEC` of frames heard as
  speech, none further apart than `SILENCE_HANGOVER_SEC`, as
  `core.listening.timing` counts them): a moment heard as speech and too
  short to send is part of the stretch, as it sent nothing either;
- the source stopping ends it (`stopped`).

One over `MIN_SEC` is a `perf.trace.Unheard`, with its frames' level at
p10, p50 and p90 (dBFS, of the root mean square as captured), the times
speech detection forgot its state in it (`FrameResult.reset`) and how
long after the last of them it ended. Levels and times only, never
audio.
"""

import math
import threading
from collections import Counter
from dataclasses import dataclass, field

from polyglotic_desktop.core.listening.timing import (
    FRAME_SEC,
    MIN_SPEECH_SEC,
    SILENCE_HANGOVER_SEC,
)
from polyglotic_desktop.perf.trace import Unheard
from polyglotic_desktop.platform.speech_detection import FrameResult

FLOOR_DBFS = -45.0
"""A frame at least this loud (root mean square) is sound. Ordinary
programme audio sits around -30 to -15 dBFS; a quiet room's hiss, a
source's noise floor and a fade's tail are below it."""
MIN_SEC = 3.0
"""A stretch over this long is counted: longer than any pause the timing
joins across, far shorter than the 16-28 s gaps reported."""
QUIET_SEC = 1.0
"""Frames under the floor for this long end a stretch: shorter, the gaps
between a missed speaker's words and sentences would cut it into pieces
under `MIN_SEC`, and a deaf detector would leave no stretch at all."""
_MIN_SPEECH_FRAMES = int(MIN_SPEECH_SEC / FRAME_SEC)
_LOWEST = -120


def dbfs(level: float | None) -> float:
    """A level (root mean square, full scale 1.0) in dBFS; None or 0 is
    the lowest counted, -120."""
    if not level or level <= 0.0:
        return float(_LOWEST)
    return max(float(_LOWEST), 20.0 * math.log10(level))


@dataclass
class _Open:
    """A stretch under way, so far."""

    began: float
    loud_until: float
    """The end of its last frame at the floor or above."""
    levels: Counter[int] = field(default_factory=Counter)
    """Its frames' levels, whole dBFS."""
    resets: int = 0
    last_reset: float | None = None
    quiet: list[tuple[int, bool, float]] = field(default_factory=list)
    """Frames under the floor since `loud_until`: (dBFS, reset, end) -
    the stretch's if sound comes back."""
    speech_first: float = 0.0
    speech_last: float | None = None
    speech_frames: int = 0
    """Frames heard as speech lately, as the timing counts a segment's."""


class SoundUnheard:
    """One source's stretches of sound without speech (module docstring).
    `frame` each of its frames in order, from its capture's thread; `stop`
    and `open` from any thread."""

    def __init__(self, source: str) -> None:
        """`source`: the source's category, what the record says (never
        its id or an app's name)."""
        self.source = source
        self._lock = threading.Lock()
        self._open: _Open | None = None
        self._stopped = False

    def frame(self, result: FrameResult) -> Unheard | None:
        """The next frame: the stretch over `MIN_SEC` it ended, if any.
        Nothing after `stop`."""
        with self._lock:
            return None if self._stopped else self._frame(result)

    def stop(self) -> Unheard | None:
        """The source stopped: the stretch under way, if over `MIN_SEC`;
        frames after this are ignored (a capture's last callback)."""
        with self._lock:
            found, self._open, self._stopped = self._open, None, True
            return None if found is None else self._made(found, "stopped")

    def open(self) -> Unheard | None:
        """The stretch under way as it stands, if already over `MIN_SEC`."""
        with self._lock:
            return None if self._open is None else self._made(self._open, "open")

    def _frame(self, result: FrameResult) -> Unheard | None:
        level = round(dbfs(result.level))
        stretch = self._open
        if stretch is None:
            if result.speech or level < FLOOR_DBFS:
                return None
            stretch = self._open = _Open(result.end - FRAME_SEC, result.end)
        if result.speech:
            if (
                stretch.speech_last is None
                or result.end - stretch.speech_last > SILENCE_HANGOVER_SEC
            ):
                stretch.speech_first, stretch.speech_frames = result.end, 0
            stretch.speech_last = result.end
            stretch.speech_frames += 1
            if stretch.speech_frames >= _MIN_SPEECH_FRAMES:  # enough to send
                self._open = None
                began = stretch.speech_first - FRAME_SEC
                return self._made(stretch, "speech", min(stretch.loud_until, began))
        if level >= FLOOR_DBFS:  # the sound goes on
            for quiet_level, reset, end in stretch.quiet:
                self._count(stretch, quiet_level, reset, end)
            stretch.quiet.clear()
            self._count(stretch, level, result.reset, result.end)
            stretch.loud_until = result.end
            return None
        stretch.quiet.append((level, result.reset, result.end))
        if result.end - stretch.loud_until >= QUIET_SEC:
            self._open = None
            return self._made(stretch, "quiet")
        return None

    @staticmethod
    def _count(stretch: _Open, level: int, reset: bool, end: float) -> None:
        stretch.levels[level] += 1
        if reset:
            stretch.resets += 1
            stretch.last_reset = end

    def _made(
        self, stretch: _Open, end: str, ended: float | None = None
    ) -> Unheard | None:
        """The stretch as a record, if over `MIN_SEC`: it ended at `ended`,
        or at its last sound."""
        ended = stretch.loud_until if ended is None else ended
        if ended - stretch.began <= MIN_SEC:
            return None
        last = stretch.last_reset
        return Unheard(
            self.source,
            stretch.began,
            ended,
            _percentiles(stretch.levels),
            stretch.resets,
            None if last is None else max(0.0, ended - last),
            end,
        )


def _percentiles(levels: Counter[int]) -> tuple[int, int, int]:
    """p10, p50 and p90 of the frames' levels (nearest rank)."""
    total = sum(levels.values())
    if not total:
        return (_LOWEST, _LOWEST, _LOWEST)
    ordered = sorted(levels.items())
    found = []
    for p in (10, 50, 90):
        rank, seen = max(1, math.ceil(p / 100 * total)), 0
        for level, count in ordered:
            seen += count
            if seen >= rank:
                found.append(level)
                break
    return (found[0], found[1], found[2])
