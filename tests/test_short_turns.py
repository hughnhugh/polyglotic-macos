"""`perf.turns.short_turns` (polyglotic-hq 436, decision 0207): the
interpreter's switch interval short while a long stretch of Python runs
beside the interface, and back to what it was once the last one ends."""

import sys
import threading

import pytest

from polyglotic_desktop.perf.turns import SHORT_TURN, short_turns


def test_the_turns_are_short_while_it_runs_and_as_before_after() -> None:
    before = sys.getswitchinterval()
    with short_turns():
        assert sys.getswitchinterval() == SHORT_TURN
    assert sys.getswitchinterval() == before


def test_two_at_once_keep_them_short_until_the_last_ends() -> None:
    before = sys.getswitchinterval()
    first_in, second_out = threading.Event(), threading.Event()
    seen: list[float] = []

    def first() -> None:
        with short_turns():
            first_in.set()
            second_out.wait(10)
            seen.append(sys.getswitchinterval())  # the second ended first

    thread = threading.Thread(target=first)
    thread.start()
    first_in.wait(10)
    with short_turns():
        assert sys.getswitchinterval() == SHORT_TURN
    second_out.set()
    thread.join(10)
    assert seen == [SHORT_TURN]
    assert sys.getswitchinterval() == before


def test_a_failure_inside_still_sets_them_back() -> None:
    before = sys.getswitchinterval()
    with pytest.raises(ValueError), short_turns():
        raise ValueError("the split couldn't read")
    assert sys.getswitchinterval() == before
