"""When to reconnect, and when to stop (connection.reconnect; protocol.md's table)."""

import pytest

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.reconnect import (
    Ended,
    Reconnects,
    RetryIn,
    Stop,
    StopReason,
)


def always(value: float) -> Reconnects:
    return Reconnects(random=lambda: value)


def test_backoff_doubles_to_8_seconds_with_full_jitter() -> None:
    """8, not 60 (polyglotic-hq 165, 184): after an outage the app comes back
    within seconds of the server or the network, not up to a minute later."""
    top = always(1.0)  # the longest each wait can be
    waits = [top.after(Ended(1006)) for _ in range(7)]
    assert waits == [RetryIn(s) for s in (1, 2, 4, 8, 8, 8, 8)]
    assert always(0.0).after(Ended(1006)) == RetryIn(0.0)
    assert always(0.5).after(Ended(None)) == RetryIn(0.5)  # couldn't connect


def test_a_long_session_starts_the_backoff_again() -> None:
    reconnects = always(1.0)
    for _ in range(5):
        reconnects.after(Ended(1006, lasted=10))
    assert reconnects.after(Ended(1006, lasted=59)) == RetryIn(8)
    assert reconnects.after(Ended(1006, lasted=60)) == RetryIn(1)


@pytest.mark.parametrize("code", [1006, 1008, 1009, 1011, 4008, 4999])
def test_codes_that_reconnect_with_backoff(code: int) -> None:
    assert always(0.25).after(Ended(code)) == RetryIn(0.25)


def test_a_restarting_server_waits_at_least_a_second() -> None:
    assert always(0.0).after(Ended(1001)) == RetryIn(1.0)
    assert always(1.0).after(Ended(1001)) == RetryIn(1.0)
    reconnects = always(1.0)
    reconnects.attempt = 3
    assert reconnects.after(Ended(1001)) == RetryIn(8.0)


@pytest.mark.parametrize(
    ("ended", "reason"),
    [
        (Ended(1000), StopReason.CLOSED),
        (
            Ended(4001, protocol.UpdateRequired(min_app_version="0.2.0")),
            StopReason.UPDATE_REQUIRED,
        ),
        (Ended(4002), StopReason.UPDATE_REQUIRED),
        (
            Ended(4003, protocol.AuthFailed(reason="token_not_valid")),
            StopReason.SIGN_IN_NEEDED,
        ),
        (Ended(4003), StopReason.SIGN_IN_NEEDED),
        (Ended(4009), StopReason.LIMIT_REACHED),
        # 193's limit_reached at hello, its close not seen in time (185)
        (
            Ended(None, protocol.LimitReached(kind="plus_ended")),
            StopReason.LIMIT_REACHED,
        ),
        (Ended(4010), StopReason.ENDED_BY_US),
        (Ended(4011), StopReason.LISTENING_MOVED),
    ],
)
def test_codes_that_stop_until_the_user_acts(ended: Ended, reason: StopReason) -> None:
    assert always(0.5).after(ended) == Stop(reason)


def test_too_many_attempts_waits_as_told() -> None:
    failed = protocol.AuthFailed(reason="too_many_attempts", retry_after=420)
    assert always(0.5).after(Ended(4003, failed)) == RetryIn(420)


@pytest.mark.parametrize(("jitter", "wait"), [(0.0, 30.0), (0.5, 37.5), (1.0, 45.0)])
def test_server_busy_waits_retry_after_plus_up_to_half(
    jitter: float, wait: float
) -> None:
    busy = protocol.ServerBusy(retry_after=30)
    assert always(jitter).after(Ended(4013, busy)) == RetryIn(wait)


def test_too_many_sessions_waits_retry_after() -> None:
    refusal = protocol.TooManySessions(limit=2, retry_after=60)
    assert always(0.9).after(Ended(4029, refusal)) == RetryIn(60)


def test_refusals_dont_count_towards_the_backoff() -> None:
    reconnects = always(1.0)
    reconnects.after(Ended(4013, protocol.ServerBusy(retry_after=30)))
    assert reconnects.after(Ended(1006)) == RetryIn(1.0)
