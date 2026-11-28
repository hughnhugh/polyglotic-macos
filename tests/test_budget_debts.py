"""Known budget debts (933's ADR-015, polyglotic-hq 994): a listed test over
its budget passes as "known debt: over by X ms" within its ceiling, fails
past it, and is never skipped; an unlisted test is judged as before."""

from pathlib import Path

import pytest
from tests import budget_debts, budget_judge
from tests.budget_debts import Debt
from tests.budget_judge import Sampled, within

from polyglotic_desktop.perf import budgets

LOOK_DRAG = "tests/ui/test_look_drag.py::test_a_step_of_a_look_drag_within_a_frame"


@pytest.fixture(autouse=True)
def judged_alone(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A Windows train's run (no notice, no main's record to stand beside)
    with its own judgements and notes."""
    monkeypatch.setattr(budget_judge.sys, "platform", "win32")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("POLYGLOTIC_TIMING_RECORD", str(tmp_path))
    monkeypatch.setattr(budget_judge, "JUDGED", [])
    monkeypatch.setattr(budget_judge, "NOTES", [])


def as_test(monkeypatch: pytest.MonkeyPatch, test: str) -> None:
    monkeypatch.setenv("PYTEST_CURRENT_TEST", f"{test} (call)")


def test_a_listed_debt_over_its_budget_within_its_ceiling_is_named_not_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    as_test(monkeypatch, LOOK_DRAG)
    within(budgets.FRAME, lambda: Sampled((8.4, 8.6, 8.7), busy=0.1))
    (judged,) = budget_judge.JUDGED
    assert judged.passed and len(judged.tries) == 2  # taken again, as ever
    assert judged.verdict().startswith("known debt: over by 0.6 ms")
    assert "ceiling 10" in judged.verdict() and "M1" in judged.verdict()
    assert "known debt: over by 0.6 ms" in budget_judge.summary_lines()[0]
    assert "::warning title=Known debt::" in capsys.readouterr().out


def test_a_listed_debt_worse_than_its_ceiling_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_test(monkeypatch, LOOK_DRAG)
    with pytest.raises(AssertionError, match="worse than its known debt's ceiling"):
        within(budgets.FRAME, lambda: Sampled((10.2, 10.4, 10.5), busy=0.1))
    (judged,) = budget_judge.JUDGED
    assert not judged.passed and not judged.debt


def test_a_listed_debt_still_fails_a_run_over_the_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_test(monkeypatch, LOOK_DRAG)
    with pytest.raises(AssertionError, match="any one run 50 ms"):
        within(budgets.FRAME, lambda: Sampled((8.4, 8.6, 51.0), busy=0.1))


def test_an_unlisted_test_over_its_budget_fails_as_before(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_test(monkeypatch, "tests/ui/test_look_drag.py::another_drag")
    with pytest.raises(AssertionError, match="frame over its 8 ms"):
        within(budgets.FRAME, lambda: Sampled((8.4, 8.6, 8.7), busy=0.1))


def test_a_debt_is_its_own_budget_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The look drag's debt is the frame's; a click budget there would fail."""
    as_test(monkeypatch, LOOK_DRAG)
    with pytest.raises(AssertionError, match="click over its 30 ms"):
        within(budgets.CLICK, lambda: Sampled((31.0,), busy=0.1))


def test_a_listed_debt_within_its_budget_says_its_entry_can_go(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_test(monkeypatch, LOOK_DRAG)
    within(budgets.FRAME, lambda: Sampled((6.1, 6.4), busy=0.1))
    (judged,) = budget_judge.JUDGED
    assert judged.passed and judged.verdict() == "ok"
    (note,) = budget_judge.NOTES
    assert "known debt within its budget here" in note and LOOK_DRAG in note


def test_every_debt_is_named_with_its_figures_milestone_and_a_ceiling() -> None:
    assert budget_debts.DEBTS
    tests = [debt.test for debt in budget_debts.DEBTS]
    assert len(tests) == len(set(tests))
    for debt in budget_debts.DEBTS:
        assert isinstance(debt, Debt)
        assert "::" in debt.test
        assert (
            Path(__file__).resolve().parents[1] / debt.test.split("::")[0]
        ).is_file()
        assert debt.budget in vars(budgets).values()  # a real budget, unchanged
        assert debt.budget.ms < debt.ceiling_ms <= 1.25 * debt.budget.ms
        assert debt.measured and debt.source and debt.milestone.startswith("M")
