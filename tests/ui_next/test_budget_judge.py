"""The budget tests' judge (`tests/budget_judge.py`, polyglotic-hq project 140):
a slow moment of a busy PC passes on a second try, shown with both, and a
saturated PC gets up to two tries more (decision 0040); a real slowdown -
every run slower, or one run over 50 ms in every try - fails. Actions are
made up: a sleep stands in for slow work, and the PC's load is set."""

import gc
import itertools
import time
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests import budget_judge
from tests.budget_judge import Sampled, sampled, within

from polyglotic_desktop.perf import budgets
from tools import busy_pc

SLOW = 0.06
"""Seconds: over the slot budget (50 ms) and the click budget."""


class Action:
    """Quick, except on the calls numbered in `slow` (from 1)."""

    def __init__(self, *slow: int) -> None:
        self.slow = set(slow)
        self.calls = itertools.count(1)

    def __call__(self) -> None:
        if next(self.calls) in self.slow:
            time.sleep(SLOW)


@pytest.fixture(autouse=True)
def judged(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[budget_judge.Judged]]:
    """This file's judgements, kept out of the run's summary; judged as on
    any machine but GitHub's Mac (decision 0195 has a test of its own)."""
    monkeypatch.delenv("RUNNER_ENVIRONMENT", raising=False)
    mine: list[budget_judge.Judged] = []
    monkeypatch.setattr(budget_judge, "JUDGED", mine)
    yield mine


@pytest.fixture(autouse=True)
def load(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """The PC's load as the judge reads it: 40 % (busy, not saturated)
    unless a test says otherwise; every reading taken, in `load[1:]`."""
    readings = [0.4]

    def busy_share(seconds: float = busy_pc.SAMPLE_SECONDS) -> float:
        readings.append(readings[0])
        return readings[0]

    monkeypatch.setattr(busy_pc, "busy_share", busy_share)
    return readings


def test_a_slow_moment_passes_on_the_second_try_and_both_are_shown(
    qapp: QApplication, judged: list[budget_judge.Judged]
) -> None:
    action = Action(4)  # the first try's first timed run (after 3 warm-up)
    within(budgets.CLICK, lambda: sampled(qapp, [action] * 3))
    (verdict,) = judged
    assert verdict.passed and len(verdict.tries) == 2
    assert verdict.tries[0].longest >= SLOW * 1000 > verdict.tries[1].longest
    assert verdict.verdict().startswith("ok on try 2 (try 1: median")
    table = budget_judge.summary_markdown()
    assert (
        f"| click {budgets.CLICK.ms:.0f} |" in table and "ok on try 2 (try 1:" in table
    )


def test_one_slow_run_in_every_try_fails_naming_both(
    qapp: QApplication, judged: list[budget_judge.Judged]
) -> None:
    action = Action(4, 10)  # the first timed run of each try
    with pytest.raises(AssertionError, match=r"both tries: try 1: .*; try 2: "):
        within(budgets.CLICK, lambda: sampled(qapp, [action] * 3))
    assert not judged[0].passed
    assert "| **over in both tries (try 1: median" in budget_judge.summary_markdown()


def test_a_saturated_pc_gets_two_tries_more_and_says_so(
    qapp: QApplication, judged: list[budget_judge.Judged], load: list[float]
) -> None:
    load[0] = 0.97
    action = Action(4, 10, 16)  # the first timed run of tries 1-3
    within(budgets.CLICK, lambda: sampled(qapp, [action] * 3))
    (verdict,) = judged
    assert verdict.passed and len(verdict.tries) == 4
    assert verdict.verdict().startswith("ok on try 4 (try 1: median")
    assert verdict.verdict().endswith("; the PC 97% busy)")


def test_a_real_slowdown_fails_on_a_saturated_pc_too(
    qapp: QApplication, load: list[float]
) -> None:
    load[0] = 0.97
    action = Action(*range(1, 9))  # warm-up and timed, all four tries
    with pytest.raises(AssertionError, match=r"in all 4 tries: .*; the PC 97% busy"):
        within(budgets.CLICK, lambda: sampled(qapp, [action]))


def test_a_calm_pc_is_read_only_once_a_second_try_is_over(
    qapp: QApplication, judged: list[budget_judge.Judged], load: list[float]
) -> None:
    quick, slow_once, slow_twice = Action(), Action(2), Action(2, 4)
    within(budgets.CLICK, lambda: sampled(qapp, [quick]))
    within(budgets.CLICK, lambda: sampled(qapp, [slow_once]))  # ok on try 2
    assert load[1:] == []  # never read: no try was over twice
    with pytest.raises(AssertionError, match=r"both tries: .*; the PC 40% busy"):
        within(budgets.CLICK, lambda: sampled(qapp, [slow_twice]))
    assert load[1:] == [0.4]  # read once, and no third try
    assert len(judged[-1].tries) == 2


def test_every_run_slower_fails_on_its_median(qapp: QApplication) -> None:
    action = Action(*range(1, 5))  # warm-up and timed, both tries
    with pytest.raises(
        AssertionError, match=f"click over its {budgets.CLICK.ms:.0f} ms"
    ):
        within(budgets.CLICK, lambda: sampled(qapp, [action]))


def test_the_warm_up_is_recorded_not_judged_unless_a_first_time_is(
    qapp: QApplication, judged: list[budget_judge.Judged]
) -> None:
    within(budgets.CLICK, lambda: sampled(qapp, [Action(1)]))
    assert judged[0].tries[0].warm_up[0] >= SLOW * 1000  # recorded
    assert len(judged[0].tries) == 1  # not judged
    with pytest.raises(AssertionError):  # a first time, every try
        within(budgets.CLICK, lambda: sampled(qapp, [Action(1)], warm=False))


def test_the_garbage_collector_is_held_off_while_timing(qapp: QApplication) -> None:
    seen: list[bool] = []
    sampled(qapp, [lambda: seen.append(gc.isenabled())])
    assert seen == [False, False] and gc.isenabled()
    gc.disable()
    try:
        sampled(qapp, [lambda: None])
        assert not gc.isenabled()  # left as it was
    finally:
        gc.enable()


def test_a_start_is_one_run_judged_against_its_own_budget() -> None:
    """A budget over 50 ms holds any one run to itself (a start: 400 ms)."""
    start = budgets.START_FROM_SOURCE.ms
    assert budget_judge.fits(budgets.START_FROM_SOURCE, Sampled((start,)))
    assert not budget_judge.fits(budgets.START_FROM_SOURCE, Sampled((start + 1,)))
    assert not budget_judge.fits(budgets.CLICK, Sampled((1.0, 1.0, 51.0)))


def test_over_in_every_try_on_a_busy_pc_is_its_own_outcome(
    qapp: QApplication, judged: list[budget_judge.Judged], load: list[float]
) -> None:
    """Every reading busy: "over on a busy PC", still a failure, told apart
    at a glance from "over" - a reading calm, so the action itself."""
    load[0] = 0.97
    action = Action(*range(1, 9))
    with pytest.raises(AssertionError, match=r"^OVER ON A BUSY PC \(every reading"):
        within(budgets.CLICK, lambda: sampled(qapp, [action]))
    assert judged[-1].on_a_busy_pc
    assert judged[-1].verdict().startswith("over on a busy PC in all 4 tries")
    load[0] = 0.4
    with pytest.raises(AssertionError, match=r"^click over its"):
        within(budgets.CLICK, lambda: sampled(qapp, [Action(*range(1, 5))]))
    assert not judged[-1].on_a_busy_pc
    assert judged[-1].verdict().startswith("over in both tries")


def test_a_test_may_count_the_pc_busy_from_a_lower_share(
    qapp: QApplication, judged: list[budget_judge.Judged]
) -> None:
    """The start counts the PC busy from 30 % (decision 0103): at 40 % it
    gets the tries a saturated PC gets, and fails "on a busy PC"."""
    action = Action(*range(1, 9))
    with pytest.raises(AssertionError, match=r"^OVER ON A BUSY PC \(every reading 30%"):
        within(budgets.CLICK, lambda: sampled(qapp, [action]), busy_from=busy_pc.CALM)
    assert len(judged[-1].tries) == 4


def test_a_try_that_read_the_load_during_its_runs_is_judged_by_that(
    judged: list[budget_judge.Judged], load: list[float]
) -> None:
    """A start reads how busy the rest of the PC was during its runs; that
    reading is the try's, and the PC isn't read again after it."""
    tries = iter([Sampled((450.0,), busy=0.45), Sampled((430.0,), busy=0.12)])
    with pytest.raises(AssertionError, match=r"^start_from_source over its .*12% busy"):
        within(budgets.START_FROM_SOURCE, lambda: next(tries), busy_from=busy_pc.CALM)
    assert load[1:] == []  # never read: each try brought its own
    assert judged[-1].busy == (0.12,) and not judged[-1].on_a_busy_pc
