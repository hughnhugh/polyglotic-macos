"""Live updates held back: when the learner is told, and the log's line a minute
(core.listening.held_back; decision 0097, polyglotic-hq 307)."""

from polyglotic_desktop.core.listening.held_back import (
    LOG_EVERY_SEC,
    TELL_AFTER,
    TELL_AGAIN_AFTER_SEC,
    WITHIN_SEC,
    Counted,
    HeldBack,
)


def test_a_few_held_back_arent_worth_telling() -> None:
    held = HeldBack()
    assert not any(held.waited(float(n)) for n in range(TELL_AFTER - 1))


def test_the_learner_is_told_once_many_are_held_in_a_short_while() -> None:
    held = HeldBack()
    told = [held.refused(n * 0.5) for n in range(TELL_AFTER * 3)]
    assert told.index(True) == TELL_AFTER - 1
    assert told.count(True) == 1  # once, however many follow


def test_spread_out_they_arent_told() -> None:
    held = HeldBack()
    step = WITHIN_SEC / (TELL_AFTER - 2)  # never TELL_AFTER within the window
    assert not any(held.waited(n * step) for n in range(60))


def test_told_again_only_after_a_long_while_and_both_kinds_count_together() -> None:
    held = HeldBack()
    for n in range(TELL_AFTER - 1):
        assert not held.waited(n * 0.1)
    assert held.refused(1.0)  # the app's and the server's together
    later = 1.0 + TELL_AGAIN_AFTER_SEC
    assert not any(held.waited(later - 5 + n * 0.1) for n in range(TELL_AFTER))
    assert any(held.waited(later + 1 + n * 0.1) for n in range(TELL_AFTER))


def test_the_log_gets_the_counts_once_a_minute() -> None:
    held = HeldBack()
    assert held.to_log(0.0) is None  # nothing held, nothing to say
    held.refused(1.0)
    assert held.to_log(1.0) == Counted(waited=0, refused=1)  # the first, at once
    for n in range(40):
        held.refused(2.0 + n)
        held.waited(2.0 + n)
        assert held.to_log(2.0 + n) is None  # within the minute: no line
    assert held.to_log(1.0 + LOG_EVERY_SEC) == Counted(waited=40, refused=40)
    assert held.to_log(2.0 + LOG_EVERY_SEC) is None


def test_whats_left_is_logged_as_the_session_ends() -> None:
    held = HeldBack()
    held.waited(1.0)
    assert held.to_log(1.0) == Counted(waited=1)
    held.waited(2.0)
    held.waited(3.0)
    assert held.left_to_log() == Counted(waited=2)
    assert held.left_to_log() is None
