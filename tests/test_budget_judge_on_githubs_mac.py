"""On GitHub's own Mac runner a median is held to twice its budget
(decision 0195, polyglotic-hq 421): 395's pinyin caption took a median of
4.1 and 5.0 ms against its 4 ms there. Everywhere else, and every run, as
before."""

import sys

import pytest
from tests import budget_judge
from tests.budget_judge import Sampled, fits

from polyglotic_desktop.perf import budgets

OVER = Sampled(runs=(5.0, 5.0, 5.0, 9.1))  # 421's second try, roughly


def test_on_githubs_mac_a_median_may_take_twice_its_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    assert budget_judge.median_allowed(budgets.NEW_CAPTION) == 8.0
    assert fits(budgets.NEW_CAPTION, OVER)
    assert not fits(budgets.NEW_CAPTION, Sampled(runs=(8.5, 8.5, 8.5)))
    assert not fits(budgets.NEW_CAPTION, Sampled(runs=(1.0, 1.0, 60.0)))  # a run


@pytest.mark.parametrize(
    ("platform", "runner"),
    [("darwin", "self-hosted"), ("darwin", None), ("win32", "github-hosted")],
)
def test_anywhere_else_the_budget_itself(
    monkeypatch: pytest.MonkeyPatch, platform: str, runner: str | None
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    if runner is None:
        monkeypatch.delenv("RUNNER_ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("RUNNER_ENVIRONMENT", runner)
    assert budget_judge.median_allowed(budgets.NEW_CAPTION) == 4.0
    assert not fits(budgets.NEW_CAPTION, OVER)
