"""A hidden caption window's timer (core.listening.hidden; polyglotic-hq
335): on a made-up clock, in seconds."""

from polyglotic_desktop.core.listening.hidden import (
    PAUSE_AFTER_MIN,
    QUIET_SEC,
    HiddenWindows,
    Sight,
)

MIN = 60.0


def test_hidden_14_minutes_still_listens_and_16_is_paused() -> None:
    hidden = HiddenWindows()
    assert hidden.limit == PAUSE_AFTER_MIN == 15
    hidden.hide("game", 0.0)
    assert hidden.tick(14 * MIN) == frozenset()
    assert hidden.sight("game", 14 * MIN) is Sight.HIDDEN
    assert hidden.tick(16 * MIN) == {"game"}
    assert hidden.sight("game", 16 * MIN) is Sight.PAUSED
    assert hidden.paused() == {"game": 15}
    assert hidden.tick(17 * MIN) == frozenset()  # paused once


def test_shown_again_listens_again_and_its_timer_goes() -> None:
    hidden = HiddenWindows()
    hidden.hide("game", 0.0)
    hidden.tick(16 * MIN)
    assert hidden.show("game")  # it was paused: listening starts again
    assert hidden.sight("game", 16 * MIN) is Sight.SHOWN
    assert hidden.paused() == {}
    assert not hidden.any_hidden
    assert hidden.tick(60 * MIN) == frozenset()
    hidden.hide("game", 20 * MIN)  # hidden again: a new 15 minutes
    assert hidden.tick(34 * MIN) == frozenset()
    assert hidden.tick(35 * MIN) == {"game"}


def test_shown_before_the_limit_was_never_paused() -> None:
    hidden = HiddenWindows()
    hidden.hide("game", 0.0)
    assert not hidden.show("game")
    assert not hidden.show("game")  # shown twice: nothing to start


def test_never_is_never_paused() -> None:
    hidden = HiddenWindows(limit=None)
    hidden.hide("game", 0.0)
    assert hidden.tick(10 * 60 * MIN) == frozenset()
    assert hidden.next_due(0.0) is None
    assert hidden.sight("game", 10 * 60 * MIN) is Sight.HIDDEN


def test_two_windows_each_have_their_own_timer() -> None:
    hidden = HiddenWindows(limit=5)
    hidden.hide("game", 0.0)
    hidden.hide("call", 3 * MIN)
    assert hidden.next_due(0.0) == 5 * MIN
    assert hidden.tick(6 * MIN) == {"game"}
    assert hidden.sight("call", 6 * MIN) is Sight.HIDDEN
    assert hidden.next_due(6 * MIN) == 2 * MIN
    assert hidden.tick(8 * MIN) == {"call"}
    assert hidden.show("game")
    assert hidden.paused() == {"call": 5}


def test_hidden_again_while_hidden_keeps_the_first_time() -> None:
    hidden = HiddenWindows()
    hidden.hide("game", 0.0)
    hidden.hide("game", 10 * MIN)
    assert hidden.tick(15 * MIN) == {"game"}


def test_a_shorter_limit_counts_from_when_it_was_hidden() -> None:
    hidden = HiddenWindows(limit=60)
    hidden.hide("game", 0.0)
    assert hidden.tick(20 * MIN) == frozenset()
    hidden.limit = 15
    assert hidden.tick(20 * MIN) == {"game"}
    assert hidden.paused() == {"game": 15}
    hidden.limit = None  # paused stays paused until it's shown
    assert hidden.sight("game", 21 * MIN) is Sight.PAUSED


def test_captioning_while_hidden_lasts_while_speech_is_captioned() -> None:
    hidden = HiddenWindows()
    hidden.captioned("game", 0.0)  # shown: nothing said
    assert hidden.sight("game", 1.0) is Sight.SHOWN
    hidden.hide("game", 10.0)
    assert hidden.sight("game", 11.0) is Sight.HIDDEN  # its caption was before
    hidden.captioned("game", 20.0)
    assert hidden.sight("game", 20.0 + QUIET_SEC - 1) is Sight.CAPTIONING
    assert hidden.sight("game", 20.0 + QUIET_SEC) is Sight.HIDDEN


def test_speech_starts_after_a_quiet_spell_and_after_hiding() -> None:
    hidden = HiddenWindows()
    hidden.hide("game", 0.0)
    # hidden mid-speech: its next captions aren't speech starting
    assert not hidden.captioned("game", 5.0)
    assert not hidden.captioned("game", 10.0)
    # quiet a while, then talk again: speech starts
    assert hidden.captioned("game", 10.0 + QUIET_SEC)
    assert not hidden.captioned("game", 12.0 + QUIET_SEC)  # still talking


def test_speech_in_a_window_hidden_a_while_starts_at_its_first_caption() -> None:
    hidden = HiddenWindows()
    hidden.hide("game", 0.0)
    assert hidden.captioned("game", 2 * MIN)


def test_a_paused_or_shown_window_has_no_speech_starting() -> None:
    hidden = HiddenWindows(limit=5)
    assert not hidden.captioned("game", 0.0)  # shown
    hidden.hide("game", 1.0)
    hidden.tick(10 * MIN)
    assert not hidden.captioned("game", 11 * MIN)  # paused: nothing heard
    assert hidden.sight("game", 11 * MIN) is Sight.PAUSED


def test_a_window_whose_transcript_is_open_is_not_paused() -> None:
    hidden = HiddenWindows()
    hidden.hide("lecture", 0.0)
    for minute in range(1, 40):  # read in its transcript the whole time
        assert not hidden.read("lecture", minute * MIN)
        assert hidden.tick(minute * MIN) == frozenset()
    # the transcript closed at 39 minutes: the limit counts from then
    assert hidden.tick(53 * MIN) == frozenset()
    assert hidden.next_due(53 * MIN) == 1 * MIN
    assert hidden.tick(54 * MIN) == {"lecture"}


def test_opening_the_transcript_of_a_paused_window_starts_it_again() -> None:
    hidden = HiddenWindows()
    hidden.hide("lecture", 0.0)
    assert hidden.tick(16 * MIN) == {"lecture"}
    assert hidden.read("lecture", 20 * MIN)  # it was paused
    assert hidden.sight("lecture", 20 * MIN) is Sight.HIDDEN
    assert hidden.paused() == {}
    assert hidden.tick(34 * MIN) == frozenset()
    assert hidden.tick(35 * MIN) == {"lecture"}
    assert not hidden.read("shown", 0.0)  # not hidden: nothing to do


def test_a_closed_window_is_forgotten() -> None:
    hidden = HiddenWindows()
    hidden.hide("game", 0.0)
    hidden.forget("game")
    assert hidden.tick(20 * MIN) == frozenset()
    assert not hidden.any_hidden
