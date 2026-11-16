"""Planned maintenance: when the app says it, and how it waits (polyglotic-hq 319, decision 0110).

Polyglotic's server tells the app of a planned maintenance window - in
`welcome`, and in a `maintenance` message when it is set, moved or
cleared (server decision 0066) - and refuses listening during it. The app
keeps the window, so it can say "planned maintenance until 15:30" even
while the server can't be reached at all (a deploy), and keeps it across
a restart of the app.

**Whose clock.** The window is in the server's time (UTC). A PC whose
clock is off would say it at the wrong time, so the app reads the
server's time in `welcome` and keeps how far the PC's clock is ahead of
it (`pc_ahead`); every rule here takes the PC's time and corrects it.

- **Ahead** (`AHEAD`, a day): Home says it in one quiet line; the caption
  windows say it once, `SOON` before the start.
- **During**, and a little either side (`explains`): a try Polyglotic's
  server doesn't answer, a restart, or its refusal for the window is the
  maintenance - not "down" - and the app tries again at most every
  `CHECK_EVERY_SEC`, then at the end plus a random 0-`SPREAD_SEC`, so the
  apps don't all come back in the same second (`wait`).
- **After** `GRACE`, a server still away is said as any other (today's words).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from polyglotic_desktop.core.listening.unreachable import NOT_ANSWERED, Unreachable

AHEAD = timedelta(hours=24)
"""Home says a window from a day before its start: "today" or "tomorrow"."""
SOON = timedelta(minutes=5)
"""The caption windows say it once, this long before the start."""
LEAD = timedelta(minutes=5)
"""A failed try this long before the start is the maintenance already: the
operator may start a minute or two early."""
GRACE = timedelta(seconds=60)
"""And this long after its end, while the apps come back spread out."""
CHECK_EVERY_SEC = 120.0
"""During a window, a try at most this often - a window cleared early is
noticed within about two minutes (as the server's `retry_after`)."""
SPREAD_SEC = 60.0
"""At the end, each app waits a random share of this more."""


@dataclass(frozen=True, slots=True)
class Maintenance:
    """A planned maintenance window, in the server's time (aware, UTC), and
    how far this PC's clock was ahead of the server's when it was told
    (negative: behind)."""

    starts_at: datetime
    ends_at: datetime
    pc_ahead: timedelta = timedelta(0)

    def server_now(self, pc_now: datetime) -> datetime:
        """The server's time when this PC's clock says `pc_now`."""
        return pc_now - self.pc_ahead


class Phase(StrEnum):
    NONE = "none"  # none planned within a day, or over
    AHEAD = "ahead"  # it starts within `AHEAD`
    DURING = "during"


def phase(window: Maintenance | None, pc_now: datetime) -> Phase:
    if window is None:
        return Phase.NONE
    now = window.server_now(pc_now)
    if now >= window.ends_at:
        return Phase.NONE
    if now >= window.starts_at:
        return Phase.DURING
    return Phase.AHEAD if window.starts_at - now <= AHEAD else Phase.NONE


def soon(window: Maintenance | None, pc_now: datetime) -> bool:
    """Whether the caption windows' one line is due: the start is `SOON` away or less."""
    if window is None:
        return False
    now = window.server_now(pc_now)
    return window.starts_at - SOON <= now < window.starts_at


def explains(window: Maintenance | None, pc_now: datetime) -> bool:
    """Whether a failed try now is the maintenance: from `LEAD` before the
    start until `GRACE` after the end."""
    if window is None:
        return False
    now = window.server_now(pc_now)
    return window.starts_at - LEAD <= now < window.ends_at + GRACE


SAID_AS_MAINTENANCE = (*NOT_ANSWERED, Unreachable.RESTARTING, Unreachable.MAINTENANCE)
"""The causes the maintenance shows as: Polyglotic's server not answering,
restarting, or refusing for the window."""


def during_maintenance(
    why: Unreachable, window: Maintenance | None, pc_now: datetime
) -> Unreachable:
    """What to say of a failed try: the maintenance while it `explains` it
    and Polyglotic's server is the one not serving; anything on the
    learner's side is said as it is. Outside it, the refusal still says
    maintenance (the server said so); the rest is today's words."""
    if why in SAID_AS_MAINTENANCE and explains(window, pc_now):
        return Unreachable.MAINTENANCE
    return why


def wait(window: Maintenance, pc_now: datetime, random: float) -> float | None:
    """Seconds before the next try while the window is on (None: it isn't -
    the usual backoff): until its end, at most `CHECK_EVERY_SEC`, then
    `random` (0-1) of `SPREAD_SEC` more."""
    now = window.server_now(pc_now)
    if not window.starts_at - LEAD <= now < window.ends_at:
        return None
    left = (window.ends_at - now).total_seconds()
    return min(left, CHECK_EVERY_SEC) + random * SPREAD_SEC


def told(
    starts_at: str | None,
    ends_at: str | None,
    pc_ahead: timedelta,
) -> Maintenance | None:
    """The window as the server wrote it (protocol.md's times), or None if
    there's none or it can't be read."""
    starts, ends = _time(starts_at), _time(ends_at)
    if starts is None or ends is None or ends <= starts:
        return None
    return Maintenance(starts, ends, pc_ahead)


def pc_ahead_of(server_time: str | None, pc_now: datetime) -> timedelta | None:
    """How far this PC's clock is ahead of the server's, from
    `welcome.server_time`, to the second: the network's delay differs at
    each `welcome`, and a window told again unchanged mustn't read as moved."""
    server = _time(server_time)
    if server is None:
        return None
    return timedelta(seconds=round((pc_now - server).total_seconds()))


def ends_at(
    held: Maintenance | None, until: str | None, pc_now: datetime
) -> Maintenance | None:
    """The window as a refusal for it says (`server_busy` `until`): the end
    moved to `until`, or one starting now if none was held - so an app
    that missed it still says until when."""
    end = _time(until)
    if end is None:
        return held
    if held is not None:
        return Maintenance(min(held.starts_at, end), end, held.pc_ahead)
    now = pc_now
    return Maintenance(min(now, end), end) if end > now - GRACE else None


def stored(window: Maintenance | None) -> dict[str, object]:
    """The window as the app keeps it between starts: JSON's plain values."""
    if window is None:
        return {}
    return {
        "starts_at": window.starts_at.isoformat(),
        "ends_at": window.ends_at.isoformat(),
        "pc_ahead": window.pc_ahead.total_seconds(),
    }


def from_stored(kept: object, pc_now: datetime) -> Maintenance | None:
    """The window kept, if it's whole and not over yet."""
    if not isinstance(kept, dict):
        return None
    ahead = kept.get("pc_ahead", 0.0)
    if not isinstance(ahead, int | float):
        return None
    window = told(
        _text(kept.get("starts_at")),
        _text(kept.get("ends_at")),
        timedelta(seconds=float(ahead)),
    )
    if window is None or window.server_now(pc_now) >= window.ends_at + GRACE:
        return None
    return window


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when.astimezone(UTC) if when.tzinfo is not None else None
