"""Budget debts: the timed cases known to be over their budget on the
reference PC, each named with what it measured, the milestone that pays it
and a ceiling it may not pass (polyglotic-hq 933, ADR-015: the budgets
stay; an over-budget case is a debt owed at a named milestone).

`budget_judge.within` reads this list. A listed test whose last try is over
its budget but within its ceiling passes as "known debt: over by X ms",
named in the summary and as a warning on the run's page, never skipped; one
over its ceiling - worse than when it was listed - fails as any other. A
test that isn't listed is judged as before, so a debt is only ever added
here, by a change someone reviews. Each entry goes once its test is within
its budget on the reference PC (gpubox): the judge says so in the summary
when a listed test passes.
"""

from __future__ import annotations

from dataclasses import dataclass

from polyglotic_desktop.perf import budgets
from polyglotic_desktop.perf.budgets import Budget


@dataclass(frozen=True)
class Debt:
    """One known over-budget case."""

    test: str
    """The test's pytest node id, as `PYTEST_CURRENT_TEST` names it."""
    budget: Budget
    """The budget it's judged against, unchanged (ADR-015)."""
    ceiling_ms: float
    """The highest median it may take and still pass as the debt, in ms:
    above the worst it measured when listed, so a regression past it fails."""
    measured: str
    """What it measured when listed: machines, figures and runs."""
    milestone: str
    """The milestone that pays it (ADR-011, ADR-015)."""
    source: str
    """Where it was listed and why."""


DEBTS: tuple[Debt, ...] = (
    Debt(
        test="tests/ui/test_look_drag.py::test_a_step_of_a_look_drag_within_a_frame",
        budget=budgets.FRAME,
        # 10 ms: 1.25 times the budget; 12 % over gpubox's worst median and
        # 11 % over GitHub's Linux's - under "20 % worse" on both
        ceiling_ms=10.0,
        measured=(
            "median 8.3-8.9 ms (longest 8.7-9.0) on gpubox's Windows runner:"
            " 8.3-8.6 on this train 2026-11-27 (run 45960755121), 8.5-8.9 on"
            " main 2026-11-25 (run 45591369744); 8.8-9.0 on GitHub's Linux (polyglotic-linux-spike"
            " run 45964667112); 5.3-7.3 on the user's PC. About 70 % of a step"
            " is the three caption windows' paint (their text, edges at low"
            " opacity, the panel's picture drawn again for each new opacity)"
        ),
        milestone="M1",
        source=(
            "polyglotic-hq 994; 933 ADR-015 (the display's debts, exit"
            " criteria of the first milestone: the hot paint path)"
        ),
    ),
)
"""Every debt. Adding one is a reviewed change; each names its source."""


def debt_of(test: str, budget: Budget) -> Debt | None:
    """`test`'s debt against `budget`, if it's listed."""
    return next(
        (debt for debt in DEBTS if debt.test == test and debt.budget == budget),
        None,
    )
