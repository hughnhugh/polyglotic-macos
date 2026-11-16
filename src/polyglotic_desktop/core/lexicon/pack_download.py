"""A dictionary pack's download as the learner sees it (decision 0122):
what it is doing, how far along, and each way it can stand still - plain
facts the Learning page words - with the rules for trying again and for a
time left that is honest.

Nothing ever just spins: every state names what it waits for. A
connection lost, the server failing or a download making no progress for
`STALL_SEC` is tried again by itself, `RETRY_AFTER` apart, up to `TRIES`
tries, each from where the last stopped; then it stops and offers Retry.
A metered connection pauses it (Download anyway); no room, a refused list
or file, or a pack this app can't read stop it and say why.
"""

from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class Step(StrEnum):
    """Where a download is."""

    WAITING = "waiting"
    """Behind another pack's download (one at a time)."""
    LIST = "list"
    """Checking the list of packs and its signature."""
    DOWNLOADING = "downloading"
    CHECKING = "checking"
    """The whole file against the list's size and SHA-256."""
    OPENING = "opening"
    """Opened as the dictionary the list says it is."""
    DONE = "done"
    CANCELLED = "cancelled"
    """Stopped by the learner: what was downloaded is deleted."""


class Problem(StrEnum):
    """Why a download stands still."""

    OFFLINE = "offline"
    """No connection, or it dropped: tried again by itself."""
    SERVER = "server"
    """The storage answered with an error (its status said)."""
    STALLED = "stalled"
    """No data for `STALL_SEC`: tried again by itself."""
    METERED = "metered"
    """Windows calls the connection metered: paused until the learner says
    to go on, or the connection changes."""
    NO_ROOM = "no_room"
    LIST_REFUSED = "list_refused"
    """The list didn't pass its signature check: nothing downloaded."""
    FILE_REFUSED = "file_refused"
    """The file wasn't the list's size or SHA-256: deleted."""
    UNREADABLE = "unreadable"
    """It passed its checks but isn't the language's dictionary: deleted."""
    NEEDS_NEWER_APP = "needs_newer_app"
    NOT_OFFERED = "not_offered"
    """The list has no pack for the language (yet)."""


RETRIED = frozenset({Problem.OFFLINE, Problem.SERVER, Problem.STALLED})
"""Tried again by themselves."""
RETRY_AFTER = (5.0, 15.0, 30.0, 60.0, 120.0)
"""Seconds before each try after a failed one."""
TRIES = len(RETRY_AFTER) + 1
STALL_SEC = 30.0
"""A download with no data for this long is stalled."""


def retry_after(tries: int, problem: Problem) -> float | None:
    """Seconds before the next try, after `tries` tries have failed with
    `problem`: None when it isn't tried again by itself, or after the last
    try."""
    if problem not in RETRIED or not 1 <= tries < TRIES:
        return None
    return RETRY_AFTER[tries - 1]


@dataclass(frozen=True)
class PackProgress:
    """One language's pack download, now."""

    language: str
    step: Step
    done: int = 0
    """Bytes downloaded (or checked, while `CHECKING`)."""
    total: int = 0
    problem: Problem | None = None
    tries: int = 0
    """Tries made so far, this one included."""
    retry_in: float | None = None
    """Seconds to the next try by itself, if one is coming."""
    seconds_left: float | None = None
    """Only when it can be said honestly (`Rate`)."""
    status: int | None = None
    """The storage's HTTP status, for `SERVER`."""
    needed: int = 0
    """Bytes of free space it needs, for `NO_ROOM`."""
    update: bool = False
    """A newer version of a pack on this PC, fetched quietly."""

    @property
    def stopped(self) -> bool:
        """Standing still with nothing coming by itself: Retry (or Download
        anyway, for `METERED`) is the way on."""
        return self.problem is not None and self.retry_in is None

    @property
    def share(self) -> float:
        """How far along, 0-1: the step's own share of the whole."""
        if self.step is Step.DONE:
            return 1.0
        if self.total <= 0:
            return 0.0
        return min(1.0, self.done / self.total)


MIN_SECONDS = 5.0
"""A time left is said only after this long of downloading..."""
MIN_BYTES = 1_000_000
"""... and this much."""
WINDOW_SECONDS = 10.0
"""The rate is over the last this many seconds, not since the start: a
connection that slows shows it."""


class Rate:
    """A download's rate over its last `WINDOW_SECONDS`, and the time left
    at it - None until there's enough to say it honestly (`MIN_SECONDS`
    and `MIN_BYTES` into this try), or while nothing arrives."""

    def __init__(self) -> None:
        self._points: deque[tuple[float, int]] = deque()
        self._start: tuple[float, int] | None = None

    def add(self, at: float, done: int) -> None:
        if self._start is None:
            self._start = (at, done)
        self._points.append((at, done))
        while len(self._points) > 2 and at - self._points[0][0] > WINDOW_SECONDS:
            self._points.popleft()

    def seconds_left(self, total: int) -> float | None:
        if self._start is None or len(self._points) < 2:
            return None
        (first_at, first_done), (last_at, last_done) = self._points[0], self._points[-1]
        start_at, start_done = self._start
        if last_at - start_at < MIN_SECONDS or last_done - start_done < MIN_BYTES:
            return None
        if last_at - first_at <= 0 or last_done <= first_done:
            return None
        rate = (last_done - first_done) / (last_at - first_at)
        return max(0.0, (total - last_done) / rate)
