"""Captions arriving together, let into a caption window one at a time
(the Lab's "Gap between new captions"; polyglotic-hq 284, the user's live
testing, 270's FEEDBACK.md line 51: "If multiple lines land at the same
time, it creates a very large chunk of text appearing at the same time and
it makes it hard to catch up. Should separate them by 0.5 seconds at
least").

A new caption - one not in the window yet - is let in at least `gap`
seconds after the last new one; every update waits its turn behind it, so
nothing is dropped and the order holds (a caption's own later updates
come after it). Updates to captions already shown pass at once while
nothing waits.

**When it pulls against the longest wait for text** (decision 0068): the
wait bounds how long speech runs before text is asked for; a gap holds
text that has already come back. They pull apart in a burst - more
captions at once than `longest / gap` (after a reconnect, or the mouse
leaving a window that held them). Then the wait wins: no caption waits
here longer than `longest`; past it, it's let in at once, closer than the
gap to the one before.

Plain Python, no Qt: times are seconds on whatever clock the window keeps.
"""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from polyglotic_desktop.core.listening.captions import CaptionUpdate

EARLY = 0.002
"""Seconds a timer may wake early and still let the front in: a timer due
on the gap's edge (`wait_for`) mustn't find it a hair short and wait
again."""


@dataclass(frozen=True, slots=True)
class _Waiting:
    update: CaptionUpdate
    since: float


class Pacing:
    """A caption window's updates waiting their turn, and when the last new
    caption was let in."""

    def __init__(self) -> None:
        self._waiting: deque[_Waiting] = deque()
        self.last_new: float | None = None

    def __len__(self) -> int:
        return len(self._waiting)

    def waits(self, update: CaptionUpdate) -> bool:
        """Whether `update` still waits its turn (perf.trace: held by the gap)."""
        return any(w.update is update for w in self._waiting)

    def add(self, update: CaptionUpdate, now: float) -> None:
        self._waiting.append(_Waiting(update, now))

    def next(
        self,
        now: float,
        gap: float,
        longest: float,
        is_new: Callable[[CaptionUpdate], bool],
    ) -> CaptionUpdate | None:
        """The update to let in now, if the one at the front may come: one
        to a caption already shown, or a new caption `gap` seconds after
        the last new one - or once it has waited `longest`. None: wait
        (`wait_for`). Call again after showing each: what's new depends on
        what's shown."""
        if not self._waiting:
            return None
        head = self._waiting[0]
        if is_new(head.update):
            spaced = self.last_new is None or now - self.last_new >= gap - EARLY
            if not spaced and now - head.since < longest - EARLY:
                return None
            self.last_new = now
        return self._waiting.popleft().update

    def wait_for(self, now: float, gap: float, longest: float) -> float | None:
        """Seconds until the front may come (None: nothing waits)."""
        if not self._waiting:
            return None
        head = self._waiting[0]
        spaced = 0.0 if self.last_new is None else self.last_new + gap - now
        return max(0.0, min(spaced, head.since + longest - now))
