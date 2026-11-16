"""Live updates held back: when to tell the learner, and what the log says.

Live updates are held back in two ways (decision 0097): the app makes one
wait its turn under the server's speech ceiling (`CaptionTiming`, the
request says so: `held`), and the server refuses one over it
(`speech_limit_reached`) - an older app's way, or the two counts
disagreeing. Either way finished captions still come; the learner chose
how often live updates come, though, so they are told once, calmly - not
at the first one held (a moment's burst is nothing to read about), and not
again for a while. The log gets one line a minute, not one per live update
(polyglotic-hq 300: 75 WARNING lines in two minutes).

Nothing here reads a clock or logs: the session asks.
"""

from collections import deque
from dataclasses import dataclass

TELL_AFTER = 8
"""Live updates held back within `WITHIN_SEC` before the learner is told:
a few seconds of several apps talking at once isn't worth a notice."""
WITHIN_SEC = 20.0
TELL_AGAIN_AFTER_SEC = 600.0
"""The learner isn't told again for this long, however many are held."""
LOG_EVERY_SEC = 60.0

LIVE_UPDATES_HELD_BACK = "live_updates_held_back"
"""The notice's code, as the server's notices have codes (protocol.md):
the interface says it in the learner's language."""


@dataclass(frozen=True, slots=True)
class Counted:
    """What a minute's log line says: how many live updates waited their
    turn in the app, and how many the server refused."""

    waited: int = 0
    refused: int = 0


class HeldBack:
    """Follows the live updates held back in one listening session."""

    def __init__(self) -> None:
        self._recent: deque[float] = deque()
        self._told_at: float | None = None
        self._waited = 0
        self._refused = 0
        self._logged_at: float | None = None

    def waited(self, now: float) -> bool:
        """A live update went out after waiting its turn in the app.
        Whether the learner should be told now."""
        self._waited += 1
        return self._tell(now)

    def refused(self, now: float) -> bool:
        """The server refused a live update at its speech limit. Whether
        the learner should be told now."""
        self._refused += 1
        return self._tell(now)

    def to_log(self, now: float) -> Counted | None:
        """The counts since the last line, if there's something to say and
        the last line is `LOG_EVERY_SEC` old (or there was none); the
        counts start again."""
        if not (self._waited or self._refused):
            return None
        if self._logged_at is not None and now - self._logged_at < LOG_EVERY_SEC:
            return None
        counted = Counted(self._waited, self._refused)
        self._waited = self._refused = 0
        self._logged_at = now
        return counted

    def left_to_log(self) -> Counted | None:
        """The counts not yet logged, as the session ends."""
        if not (self._waited or self._refused):
            return None
        counted = Counted(self._waited, self._refused)
        self._waited = self._refused = 0
        return counted

    def _tell(self, now: float) -> bool:
        self._recent.append(now)
        while now - self._recent[0] > WITHIN_SEC:
            self._recent.popleft()
        if len(self._recent) < TELL_AFTER:
            return False
        if self._told_at is not None and now - self._told_at < TELL_AGAIN_AFTER_SEC:
            return False
        self._told_at = now
        return True
