"""What to do when a session ends: reconnect after how long, or stop (protocol.md).

"Reconnecting - with exponential backoff and full jitter, so testers don't
all come back in the same second after a restart": before attempt n (0,
1, 2, ...) wait a random time between 0 and min(8, 2^n) seconds; after a
session that lasted 60 seconds or more, start again from n = 0. Then, by
close code, protocol.md's table - some codes wait for the server's
`retry_after`, some stop until the user acts. A session that failed in the
app itself - an exception nobody foresaw - tries again too, after a longer
capped wait (`after_failure`; polyglotic-hq 557, decision 0266: it stopped
for good). No I/O: the session asks, this answers.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.core.listening.maintenance import SPREAD_SEC
from polyglotic_desktop.core.listening.unreachable import Unreachable

MAX_WAIT_SEC = 8.0
"""The longest wait between attempts - 60 s until polyglotic-hq 165. With
the server down for 30 s (each try refused at once - 184 measured 28.9 s
before captions came back), the app came back a median 13 s (p90 41 s)
after the server; at 8 s, 2.4 s (p90 5.5 s). With the network down 2
minutes (each try waits out the 10 s open timeout), 20 s (p90 46 s); at
8 s, 7 s (p90 13 s) - polyglotic-hq projects/165-reachable-from-anywhere/
scripts/backoff_sim_165.py. Attempts 0-3, a restart's herd, wait as before
(at most 1, 2, 4, 8 s)."""
FAILED_MAX_SEC = 60.0
"""The longest wait after a session failed in the app itself (decision
0266): a fault that repeats calls the server about once a minute at most,
not every few seconds."""
NO_RETRY_AFTER_SEC = 60.0  # too_many_attempts without its retry_after
RESET_AFTER_SEC = 60.0  # a session this long starts the backoff again
GOING_AWAY_MIN_SEC = 1.0  # a restarting server: wait at least this

# Close codes (protocol.md, "Keepalive and reconnecting").
NORMAL = 1000
GOING_AWAY = 1001
NO_CLOSE_FRAME = 1006
POLICY_VIOLATION = 1008
TOO_BIG = 1009
SERVER_ERROR = 1011
UPDATE_REQUIRED = 4001
PROTOCOL_NOT_SUPPORTED = 4002
AUTH_FAILED = 4003
TIMED_OUT = 4008
LIMIT_REACHED = 4009
ENDED_BY_US = 4010
LISTENING_MOVED = 4011
SERVER_BUSY = 4013
TOO_MANY_SESSIONS = 4029

BUG_CODES = {POLICY_VIOLATION, TOO_BIG}
"""Close codes that mean the app broke the protocol: reconnect, but report it."""

Refusal = (
    protocol.UpdateRequired
    | protocol.AuthFailed
    | protocol.ServerBusy
    | protocol.TooManySessions
    | protocol.LimitReached
    | protocol.AllowanceExhausted
    | protocol.RegistrationRequired
    | protocol.CrossBorderConsentRequired
)
"""The server's answers to `hello` that come just before it closes."""


@dataclass(frozen=True, slots=True)
class Ended:
    """How a session ended. `close_code` is None if no WebSocket was opened
    (the server couldn't be reached); `refusal` is the server's last word
    before it closed, if any; `lasted` is the seconds since `welcome` (0 if
    there was none); `unreachable`: why it couldn't be opened, or why the
    server ended it, if that's known (connection.failures; polyglotic-hq
    251)."""

    close_code: int | None
    refusal: Refusal | None = None
    lasted: float = 0.0
    unreachable: Unreachable | None = None
    new_hello: bool = False


class StopReason(StrEnum):
    """Why the app stopped reconnecting - each needs the user."""

    CLOSED = "closed"  # closed normally
    UPDATE_REQUIRED = "update_required"  # update the app
    SIGN_IN_NEEDED = "sign_in_needed"  # a new invite code
    LIMIT_REACHED = "limit_reached"  # Plus ended: no listening (193, 185)
    ALLOWANCE_EXHAUSTED = "allowance_exhausted"
    REGISTRATION_REQUIRED = "registration_required"
    CROSS_BORDER_CONSENT_REQUIRED = "cross_border_consent_required"
    ENDED_BY_US = "ended_by_us"  # the admin tool ended the session
    LISTENING_MOVED = "listening_moved"  # the account listens on another device


@dataclass(frozen=True, slots=True)
class RetryIn:
    seconds: float


@dataclass(frozen=True, slots=True)
class Stop:
    reason: StopReason


class Reconnects:
    """The backoff across one listening session's reconnects."""

    def __init__(self, random: Callable[[], float] = random.random) -> None:
        self.attempt = 0
        self.failures = 0
        """Sessions in a row that failed in the app itself (`after_failure`)."""
        self._random = random

    def after(self, ended: Ended) -> RetryIn | Stop:
        """What to do after `ended`."""
        if ended.lasted >= RESET_AFTER_SEC:
            self.attempt = self.failures = 0  # failures: a good run between
        code, refusal = ended.close_code, ended.refusal
        if isinstance(refusal, protocol.AllowanceExhausted):
            return Stop(StopReason.ALLOWANCE_EXHAUSTED)
        if isinstance(refusal, protocol.RegistrationRequired):
            return Stop(StopReason.REGISTRATION_REQUIRED)
        if isinstance(refusal, protocol.CrossBorderConsentRequired):
            return Stop(StopReason.CROSS_BORDER_CONSENT_REQUIRED)
        if code == NORMAL:
            return Stop(StopReason.CLOSED)
        if code in (UPDATE_REQUIRED, PROTOCOL_NOT_SUPPORTED) or isinstance(
            refusal, protocol.UpdateRequired
        ):
            return Stop(StopReason.UPDATE_REQUIRED)
        if code == AUTH_FAILED or isinstance(refusal, protocol.AuthFailed):
            if (
                isinstance(refusal, protocol.AuthFailed)
                and refusal.reason == "too_many_attempts"
            ):
                return RetryIn(float(refusal.retry_after or NO_RETRY_AFTER_SEC))
            return Stop(StopReason.SIGN_IN_NEEDED)
        if code == LIMIT_REACHED or isinstance(refusal, protocol.LimitReached):
            # Plus ended: listening waits for the plan to change (185)
            return Stop(StopReason.LIMIT_REACHED)
        if code == LISTENING_MOVED:
            # no retry: it would take listening back, and two devices would
            # trade it for ever (the user takes it back with "Listen here")
            return Stop(StopReason.LISTENING_MOVED)
        if code == ENDED_BY_US:
            return Stop(StopReason.ENDED_BY_US)
        if isinstance(refusal, protocol.ServerBusy) and refusal.reason == "maintenance":
            # a planned window: the time left (at most 2 minutes), plus a
            # random 0-60 s, so the apps come back spread out at its end (319)
            return RetryIn(refusal.retry_after + SPREAD_SEC * self._random())
        if isinstance(refusal, protocol.ServerBusy):
            # retry_after plus a random 0-50% more
            return RetryIn(refusal.retry_after * (1 + 0.5 * self._random()))
        if isinstance(refusal, protocol.TooManySessions):
            return RetryIn(float(refusal.retry_after))
        wait = self._backoff()
        if code == GOING_AWAY:
            wait = max(GOING_AWAY_MIN_SEC, wait)
        return RetryIn(wait)

    def after_failure(self, lasted: float) -> RetryIn:
        """A session failed in the app itself after `lasted` seconds - an
        exception nobody foresaw, not the network or the server (decision
        0266): try again after half to all of min(60, 2^n) seconds, n the
        failures in a row - from n = 0 again after one that lasted
        RESET_AFTER_SEC. Half at least: a fault that repeats at once never
        calls the server in a tight loop."""
        if lasted >= RESET_AFTER_SEC:
            self.failures = 0
        ceiling = min(FAILED_MAX_SEC, 2.0**self.failures)
        self.failures += 1
        return RetryIn(ceiling * (0.5 + 0.5 * self._random()))

    def random(self) -> float:
        """A random 0-1, the backoff's own (tests fix it)."""
        return self._random()

    def _backoff(self) -> float:
        """Full jitter: random between 0 and min(8, 2^n), then n + 1."""
        ceiling = min(MAX_WAIT_SEC, 2.0**self.attempt)
        self.attempt += 1
        return self._random() * ceiling
