"""The budget tests beside main's record on this PC (decision 0136,
polyglotic-hq 344): on a pull request a test over its budget but not
`timing_record.SLOWER` than main is "over its budget as main is", not a
failure; twice as slow fails; main's own runs and the starts are held to
the budget alone. Windows only: the record is this PC's Windows runs'."""

import os
import sys
from pathlib import Path

import pytest
from tests import budget_judge
from tests.budget_judge import Sampled, within

from polyglotic_desktop.perf import budgets
from tools import busy_pc, timing_record

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="main's record is kept on Windows only"
)


@pytest.fixture(autouse=True)
def pull_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_REF", "refs/pull/1/merge")
    monkeypatch.setenv("GITHUB_SHA", "abcdef1234")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(busy_pc, "busy_share", lambda seconds=0.2: 0.1)  # calm
    monkeypatch.setattr(budget_judge, "JUDGED", [])  # not in the run's summary


def this_test() -> str:
    return os.environ["PYTEST_CURRENT_TEST"].split(" (")[0]


def mains(median: float, longest: float) -> None:
    timing_record.save(
        budget_judge.RECORD_KIND,
        {this_test(): timing_record.Timing(median, longest)},
        "1234abcd",
    )


def frames(ms: float) -> Sampled:
    return Sampled((ms,) * 9)


def test_over_as_main_is_is_said_not_failed() -> None:
    """The three-column resize step: 8.2-9.1 ms against its 8 on a calm PC
    (2026-11-13/14), failing pull requests that hadn't touched it."""
    mains(8.6, 9.0)
    within(budgets.FRAME, lambda: frames(9.1))
    (judged,) = budget_judge.JUDGED
    assert judged.passed and judged.as_main.startswith("main's (1234abcd) median 8.6")
    assert judged.verdict().startswith("over its budget as main is: main's")


def test_twice_as_slow_as_main_fails() -> None:
    mains(4.5, 5.0)
    with pytest.raises(AssertionError, match="frame over its 8 ms"):
        within(budgets.FRAME, lambda: frames(9.0))


def test_without_a_record_the_budget_is_the_gate() -> None:
    with pytest.raises(AssertionError, match="frame over its 8 ms"):
        within(budgets.FRAME, lambda: frames(9.1))


def test_main_is_held_to_the_budget_and_keeps_its_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    mains(9.1, 9.1)
    with pytest.raises(AssertionError, match="frame over its 8 ms"):
        within(budgets.FRAME, lambda: frames(9.1))
    within(budgets.CLICK, lambda: frames(3.0))
    assert budget_judge.keep_mains_record()
    record = timing_record.load(budget_judge.RECORD_KIND)
    assert record is not None and record.commit == "abcdef1234"
    assert record.timings[this_test()] == timing_record.Timing(3.0, 3.0)  # the last


def test_a_start_keeps_its_own_judging() -> None:
    """Decision 0103: a start over its budget fails, beside main or not."""
    mains(420.0, 420.0)
    with pytest.raises(AssertionError, match="start_from_source over its 400 ms"):
        within(budgets.START_FROM_SOURCE, lambda: Sampled((430.0,)))
