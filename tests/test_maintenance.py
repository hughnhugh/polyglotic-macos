"""Planned maintenance: when the app says it, and how it waits (polyglotic-hq 319, decision 0110)."""

from datetime import UTC, datetime, timedelta

import pytest

from polyglotic_desktop.connection import protocol
from polyglotic_desktop.connection.failures import why_refused
from polyglotic_desktop.connection.reconnect import Ended, Reconnects, RetryIn
from polyglotic_desktop.core.listening import maintenance as planned
from polyglotic_desktop.core.listening.maintenance import Maintenance, Phase
from polyglotic_desktop.core.listening.unreachable import Side, Unreachable, side

NOW = datetime(2026, 11, 15, 3, 30, tzinfo=UTC)
START = datetime(2026, 11, 15, 4, 0, tzinfo=UTC)
END = datetime(2026, 11, 15, 4, 30, tzinfo=UTC)
WINDOW = Maintenance(START, END)


def test_said_a_day_ahead_then_during_then_not_at_all() -> None:
    assert planned.phase(None, NOW) is Phase.NONE
    assert planned.phase(WINDOW, START - timedelta(hours=25)) is Phase.NONE
    assert planned.phase(WINDOW, START - timedelta(hours=24)) is Phase.AHEAD
    assert planned.phase(WINDOW, NOW) is Phase.AHEAD
    assert planned.phase(WINDOW, START) is Phase.DURING
    assert planned.phase(WINDOW, END - timedelta(seconds=1)) is Phase.DURING
    assert planned.phase(WINDOW, END) is Phase.NONE


def test_a_pc_clock_three_hours_fast_doesnt_claim_maintenance_early() -> None:
    """Placed with the server's time from `welcome`: the PC's clock says
    06:30 while the server's says 03:30 - not inside 04:00-04:30."""
    fast = Maintenance(START, END, pc_ahead=timedelta(hours=3))
    pc_now = NOW + timedelta(hours=3)
    assert planned.phase(WINDOW, pc_now) is Phase.NONE  # by the PC's clock alone
    assert planned.phase(fast, pc_now) is Phase.AHEAD
    assert planned.phase(fast, START + timedelta(hours=3)) is Phase.DURING
    assert not planned.explains(fast, pc_now)
    assert planned.during_maintenance(Unreachable.DOWN, fast, pc_now) is (
        Unreachable.DOWN
    )


def test_the_caption_windows_line_is_due_five_minutes_before() -> None:
    assert not planned.soon(WINDOW, START - timedelta(minutes=6))
    assert planned.soon(WINDOW, START - timedelta(minutes=5))
    assert planned.soon(WINDOW, START - timedelta(seconds=1))
    assert not planned.soon(WINDOW, START)
    assert not planned.soon(None, NOW)


@pytest.mark.parametrize(
    "why",
    [
        Unreachable.DOWN,
        Unreachable.NO_ANSWER,
        Unreachable.SERVER_ERROR,
        Unreachable.RESTARTING,
        Unreachable.MAINTENANCE,
    ],
)
def test_our_server_away_in_the_window_is_the_maintenance(why: Unreachable) -> None:
    assert planned.during_maintenance(why, WINDOW, START) is Unreachable.MAINTENANCE
    early = START - planned.LEAD
    assert planned.during_maintenance(why, WINDOW, early) is Unreachable.MAINTENANCE
    late = END + planned.GRACE - timedelta(seconds=1)
    assert planned.during_maintenance(why, WINDOW, late) is Unreachable.MAINTENANCE


def test_the_learners_side_is_said_as_it_is_even_in_the_window() -> None:
    for why in (Unreachable.OFFLINE, Unreachable.BLOCKED, Unreachable.CLOCK):
        assert planned.during_maintenance(why, WINDOW, START) is why


def test_after_the_window_a_server_still_away_is_said_as_today() -> None:
    after = END + planned.GRACE
    assert planned.during_maintenance(Unreachable.DOWN, WINDOW, after) is (
        Unreachable.DOWN
    )
    before = START - planned.LEAD - timedelta(seconds=1)
    assert planned.during_maintenance(Unreachable.DOWN, WINDOW, before) is (
        Unreachable.DOWN
    )


def test_waiting_tries_every_two_minutes_then_spreads_out_at_the_end() -> None:
    assert planned.wait(WINDOW, START, 0.0) == 120.0
    assert planned.wait(WINDOW, START, 1.0) == 180.0
    assert planned.wait(WINDOW, END - timedelta(seconds=30), 0.0) == 30.0
    assert planned.wait(WINDOW, END - timedelta(seconds=30), 0.5) == 60.0
    assert planned.wait(WINDOW, END, 0.5) is None  # over: the usual backoff
    assert planned.wait(WINDOW, START - timedelta(minutes=10), 0.5) is None


def test_the_maintenance_is_ours_to_fix() -> None:
    assert side(Unreachable.MAINTENANCE) is Side.OURS


def test_the_window_as_the_server_wrote_it() -> None:
    told = planned.told("2026-11-15T04:00:00Z", "2026-11-15T04:30:00Z", timedelta(0))
    assert told == WINDOW
    assert planned.told(None, "2026-11-15T04:30:00Z", timedelta(0)) is None
    assert planned.told("soon", "2026-11-15T04:30:00Z", timedelta(0)) is None
    assert (
        planned.told("2026-11-15T04:30:00Z", "2026-11-15T04:00:00Z", timedelta(0))
        is None
    )
    assert (
        planned.told("2026-11-15T04:00:00", "2026-11-15T04:30:00", timedelta(0)) is None
    )


def test_the_clock_difference_from_welcome() -> None:
    ahead = planned.pc_ahead_of("2026-11-15T03:30:00.000Z", NOW + timedelta(hours=2))
    assert ahead == timedelta(hours=2)
    assert planned.pc_ahead_of(None, NOW) is None  # a server before 2026-11-14
    # each welcome's network delay differs: the same window, not a moved one
    told = "2026-11-15T03:30:00.000Z"
    quick = planned.pc_ahead_of(told, NOW + timedelta(milliseconds=40))
    slow = planned.pc_ahead_of(told, NOW + timedelta(milliseconds=310))
    assert quick == slow == timedelta(0)


def test_a_refusal_moves_the_end_or_makes_a_window_from_it() -> None:
    later = "2026-11-15T05:00:00Z"
    moved = planned.ends_at(WINDOW, later, START)
    assert moved is not None and moved.ends_at == datetime(2026, 11, 15, 5, tzinfo=UTC)
    assert moved.starts_at == START
    made = planned.ends_at(None, later, START + timedelta(minutes=5))
    assert made is not None and made.starts_at == START + timedelta(minutes=5)
    assert planned.ends_at(WINDOW, None, START) == WINDOW  # an older server's: kept


def test_kept_between_starts_and_dropped_once_over() -> None:
    fast = Maintenance(START, END, pc_ahead=timedelta(minutes=-7))
    assert planned.from_stored(planned.stored(fast), NOW) == fast
    assert planned.stored(None) == {}
    assert planned.from_stored({}, NOW) is None
    assert planned.from_stored(planned.stored(WINDOW), END + timedelta(hours=1)) is None
    assert planned.from_stored({"starts_at": 1, "ends_at": 2}, NOW) is None
    assert planned.from_stored("junk", NOW) is None
    assert planned.from_stored({**planned.stored(WINDOW), "pc_ahead": "x"}, NOW) is None


def test_a_refusal_for_maintenance_isnt_a_full_server() -> None:
    busy = protocol.ServerBusy(
        retry_after=120, reason="maintenance", until="2026-11-15T04:30:00Z"
    )
    assert why_refused(busy) is Unreachable.MAINTENANCE
    assert why_refused(protocol.ServerBusy(retry_after=30)) is None  # busy, as before
    step = Reconnects(random=lambda: 0.5).after(Ended(4013, busy))
    assert step == RetryIn(150.0)  # the time left, plus half of the 60 s spread
    full = Reconnects(random=lambda: 0.5).after(
        Ended(4013, protocol.ServerBusy(retry_after=30))
    )
    assert full == RetryIn(37.5)  # a full server: 30 s plus a quarter, as before
