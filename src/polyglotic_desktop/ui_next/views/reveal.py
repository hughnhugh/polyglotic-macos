"""A new caption's lines shown one at a time (the Lab's "Gap between new
lines", polyglotic-hq 309; the user, 2026-11-14: a finished caption's lines
"land together" - "when a finished caption brings several lines at once,
they are shown one after another a short moment apart ... never all
together, and never falling behind speech by more than the longest wait
for text").

A caption new to a window starts with none of its lines shown; one line -
of the oldest caption that still has lines to show - is shown every `gap`
seconds. The first comes at once when nothing was shown within the gap, so
a caption on its own is never later than it is today.

- **Only new captions are paced.** A caption already in the window that
  grows (live text wrapping onto its next line, a translation arriving
  under its clause) shows what it has at once, as today: its new line can
  be in the middle, and holding back its last one would take away text
  that was already there.
- **When it pulls against the longest wait for text** (decision 0068): no
  caption waits here longer than `longest` - past it, all its lines are
  shown at once, however many are still to come (as `views.pacing` does
  for whole captions).
- **Everything at once** (`settle`) when the mouse comes over the window
  (nothing moves under it), on a resize, and scrolled back.

Plain Python, no Qt: times are seconds on whatever clock the window
keeps. Holds no caption text - keys and counts only.
"""

from collections.abc import Callable

EARLY = 0.002
"""Seconds a timer may wake early and still show the next line (as
`views.pacing.EARLY`)."""


class Reveal:
    """A window's captions with lines still to show: how many of each show
    now, and since when it has waited."""

    def __init__(self) -> None:
        self._partial: dict[int, tuple[int, float]] = {}
        self.last: float | None = None
        """When a line was last shown."""

    @property
    def pending(self) -> bool:
        """Whether any caption has lines still to show."""
        return bool(self._partial)

    def add(self, key: int, now: float) -> None:
        """Caption `key` is new: none of its lines shown yet (`step` shows
        the first - at once, if nothing was shown within the gap)."""
        self._partial.setdefault(key, (0, now))

    def shown(self, key: int) -> int | None:
        """How many of caption `key`'s lines show; None: all of them."""
        found = self._partial.get(key)
        return None if found is None else found[0]

    def step(
        self,
        now: float,
        gap: float,
        longest: float,
        total_of: Callable[[int], int | None],
    ) -> bool:
        """Shows what's due at `now`: all of a caption that has waited
        `longest`; and one more line of the oldest caption with lines to
        show, if the last line was shown `gap` ago. `total_of`: how many
        lines a caption has now (None: it's gone). True if what shows
        changed."""
        changed = False
        for key, (count, since) in sorted(self._partial.items()):
            total = total_of(key)
            if total is None or count >= total or now - since >= longest - EARLY:
                del self._partial[key]
                changed = changed or (total is not None and count < total)
        if not self._partial:
            return changed
        if self.last is not None and now - self.last < gap - EARLY:
            return changed
        key = min(self._partial)
        count, since = self._partial[key]
        self.last = now
        if count + 1 >= (total_of(key) or 0):
            del self._partial[key]
        else:
            self._partial[key] = (count + 1, since)
        return True

    def wait_for(self, now: float, gap: float, longest: float) -> float | None:
        """Seconds until `step` next has something to show (None: nothing
        waits)."""
        if not self._partial:
            return None
        spaced = 0.0 if self.last is None else self.last + gap - now
        deadline = min(since for _, since in self._partial.values()) + longest - now
        return max(0.0, min(spaced, deadline))

    def settle(self) -> bool:
        """Every line shown at once. True if any wasn't."""
        pending = bool(self._partial)
        self._partial.clear()
        return pending
