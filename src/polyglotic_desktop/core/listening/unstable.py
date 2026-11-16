"""A connection that keeps dropping: said, and over once it has held.

polyglotic-hq 165: on hotel, train and campus Wi-Fi - and from the
mainland at its evening peak (159: up to ~7 % loss) - a listening session
can drop and come back again and again. While it's down the notice line
says "Reconnecting"; between drops the captions just come late or in
bursts, and nothing says why. `UNSTABLE_AFTER` drops within `WITHIN_SEC`
are said on the caption windows and Home - "Connection unstable -
captions may come late" - until the connection has held `HELD_SEC` since
the last drop, or listening stops.

A connection can also stall without dropping: 165 measured a 30-second
outage that never closed it - "Listening" the whole time, then three
captions 10-24 s late. `stalled` says so while it lasts: finished speech
unanswered for `STALL_SEC`, or nothing from the server for a ping's
interval and `STALL_SEC` more (it answers each ping at once). Times are
seconds on one clock; nothing here reads it.

A stall is over when its cause is: the speech answered, or known lost.
Finished speech the server will never answer isn't waited for
(`connection.unanswered`, "Given up"; polyglotic-hq 271: on the user's
own PC one caption lost on the server kept "Connection unstable" up for
the rest of the session).

"""

UNSTABLE_AFTER = 2
"""Drops before the learner is told: one is a blip the "Reconnecting" line
already covered; a second within minutes is a pattern."""

WITHIN_SEC = 300.0
"""Drops further apart than this don't add up."""

HELD_SEC = 120.0
"""How long the connection holds after its last drop before the notice
comes off by itself - the server's resume window (its decision 0040)."""


STALL_SEC = 8.0
"""Late enough to be stuck, not slow: a finished caption's answer takes
0.3-0.6 s on a good line and 165 measured a p95 of 2.1 s at 7 % loss."""


def stalled(
    waiting_since: float | None, last_heard: float, ping_every: float, now: float
) -> bool:
    """Whether the connection is stalled now: the oldest finished speech
    still unanswered was sent at `waiting_since` (None: none is), and the
    server was last heard at `last_heard`."""
    if waiting_since is not None and now - waiting_since >= STALL_SEC:
        return True
    return now - last_heard >= ping_every + STALL_SEC


class UnstableConnection:
    """Whether the listening session's connection is unstable now."""

    def __init__(self) -> None:
        self._drops: list[float] = []

    def unstable(self, now: float) -> bool:
        recent = [at for at in self._drops if now - at <= WITHIN_SEC]
        return len(recent) >= UNSTABLE_AFTER and now - recent[-1] < HELD_SEC

    def dropped(self, now: float) -> bool:
        """The connection dropped (listening, then reconnecting): True if
        it's unstable from now (and wasn't before)."""
        before = self.unstable(now)
        self._drops = [at for at in self._drops if now - at <= WITHIN_SEC]
        self._drops.append(now)
        return self.unstable(now) and not before

    def clears_at(self) -> float | None:
        """When the notice comes off if nothing drops again (None: no drop)."""
        return self._drops[-1] + HELD_SEC if self._drops else None

    def stopped(self, now: float) -> bool:
        """Listening stopped: the drops are forgotten. True if that ends an
        unstable time."""
        before = self.unstable(now)
        self._drops = []
        return before
