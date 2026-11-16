"""Listening time: how long the learner listened with captions on, per day
and source category, counted on this PC (glossary: listening day).

Counted from finished captions, as a run of them: the time from one
finished caption to the next counts as listening, to the next one's day
and source category, unless the gap was `STILL_LISTENING_SEC` or more -
then a new run begins, and the gap doesn't count. So a show with a quiet
minute counts whole, the app left on overnight with nothing playing
counts nothing, and pausing stops the count. Two sources at once count
the time once. The first caption of a run counts nothing - a few seconds
short, never long.

Why not the listening session's own time (its summary counts the time
in each capture mode): a session left running counts hours nobody
listened; the whole system's audio has no category; and the session
summarises once, at its end, on its own thread - a crash or a session
over midnight would lose or misplace its day (polyglotic-hq project 163).

Captions from the user's own mic don't count: what they said isn't what
they listened to. Days are UTC days, like exposures. The seconds stay on
this PC; they're never sent (the server counts the account's minutes
itself).
"""

from dataclasses import dataclass
from datetime import date, datetime

STILL_LISTENING_SEC = 120.0
"""A gap between finished captions shorter than this is still listening
(a quiet stretch); this long or longer, the listening stopped (a guess,
to tune - 155 suggested none)."""


@dataclass(frozen=True)
class Listened:
    """Seconds of listening to add to a day's source category."""

    day: date
    category: str
    seconds: float


class ListeningCounter:
    """Turns finished captions, as they arrive, into listening time."""

    def __init__(self) -> None:
        self._last: datetime | None = None

    def heard(self, at: datetime, category: str) -> Listened | None:
        """A finished caption from `category` arrived `at` (timezone-aware):
        the listening since the one before, or None - the first of a run."""
        last, self._last = self._last, at
        if last is None:
            return None
        gap = (at - last).total_seconds()
        if not 0 < gap < STILL_LISTENING_SEC:
            return None
        return Listened(at.date(), category, gap)
