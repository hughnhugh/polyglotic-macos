"""A connection that keeps dropping (core.listening.unstable, polyglotic-hq 165)."""

from polyglotic_desktop.core.listening.unstable import (
    HELD_SEC,
    STALL_SEC,
    WITHIN_SEC,
    UnstableConnection,
    stalled,
)


def test_one_drop_is_a_blip_two_within_minutes_are_unstable() -> None:
    drops = UnstableConnection()
    assert not drops.dropped(100.0)
    assert not drops.unstable(101.0)
    assert drops.dropped(160.0)  # newly unstable: say it
    assert drops.unstable(161.0)
    assert not drops.dropped(170.0)  # still unstable: nothing new to say


def test_it_clears_itself_once_the_connection_has_held() -> None:
    drops = UnstableConnection()
    drops.dropped(100.0)
    drops.dropped(130.0)
    assert drops.clears_at() == 130.0 + HELD_SEC
    assert drops.unstable(130.0 + HELD_SEC - 1)
    assert not drops.unstable(130.0 + HELD_SEC)


def test_drops_far_apart_dont_add_up() -> None:
    drops = UnstableConnection()
    drops.dropped(100.0)
    assert not drops.dropped(100.0 + WITHIN_SEC + 1)


def test_stopping_forgets_the_drops() -> None:
    drops = UnstableConnection()
    drops.dropped(100.0)
    drops.dropped(110.0)
    assert drops.stopped(111.0)  # it was unstable: take the notice off
    assert not drops.unstable(112.0)
    assert not drops.dropped(113.0)  # a fresh start
    assert not drops.stopped(114.0)


def test_finished_speech_unanswered_too_long_is_a_stall() -> None:
    assert not stalled(
        waiting_since=100.0, last_heard=100.0, ping_every=25.0, now=101.0
    )
    assert stalled(
        waiting_since=100.0, last_heard=105.0, ping_every=25.0, now=100.0 + STALL_SEC
    )


def test_a_silent_server_past_its_ping_is_a_stall() -> None:
    assert not stalled(
        None, last_heard=100.0, ping_every=25.0, now=125.0
    )  # a ping's wait
    assert stalled(None, last_heard=100.0, ping_every=25.0, now=125.0 + STALL_SEC)
