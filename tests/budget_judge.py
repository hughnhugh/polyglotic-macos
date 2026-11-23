"""Timing an action against its budget (`perf.budgets`, polyglotic-hq
DECISIONS.md #53) the way the UI lab does: a budget means a typical
action, not the worst moment of a busy PC (polyglotic-hq project 140).

- `sampled` runs the actions once as a warm-up - the first paint, polish
  or font load the app pays once; timed for the record, not judged - then
  times each again with everything it queues. The garbage collector is
  held off throughout: late in the suite this process holds thousands of
  Qt objects, and a full collection landing in one run took 91-99 ms in CI
  (2026-11-07, project 115; the action: 5-20 ms). Single runs of 68-215 ms
  failed three more tests that day whose runs take 1-2 ms.
- `within` holds the median to the budget and every run to the slot budget
  (50 ms; or the budget, where that's longer). If either is over, it takes
  the samples once more, and up to twice more again while the PC measures
  saturated (`tools.busy_pc`, decision 0040); it fails only if the last try
  is over too, naming every try and how busy the PC was. A real slowdown -
  every run slower, or a run over 50 ms in each try - fails every try.
  A test may say the PC counts as busy for it from a lower share (the
  start: `busy_pc.CALM`, decision 0103) and read the load during its own
  runs (`Sampled.busy`). A failure where every reading was busy is its own
  outcome, "over on a busy PC", told apart from "over" (a calm PC: the code)
  at a glance. The shared Linux pull request runner reports a timing notice
  if the last try misses only the frame median (Polyglotic HQ 711). All
  frame samples are subject to the slot limit.
- **Beside main's record** (decision 0136, polyglotic-hq 344): on Windows
  and Linux (`BESIDE_MAIN_ON`), CI's runs on main keep every judgement's
  median and longest run (`keep_mains_record`, `tools/timing_record.py`),
  each system its own record; on a pull request a test
  still over after its tries, but not `timing_record.SLOWER` than main's
  record, is "over its budget as main is" - named, a warning on the run's
  page, not failed. Frame budgets and the starts use their own judging.
  Main's own runs are held to the budget alone.
- Each judgement is recorded in `JUDGED`: pytest's summary lists every
  one's median and longest run, the warm-up's too (`tests/conftest.py`),
  and in CI the run's page shows the table.
"""

from __future__ import annotations

import gc
import os
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from polyglotic_desktop.perf import budgets
from polyglotic_desktop.perf.budgets import Budget
from tools import busy_pc, start_record, timing_record

if TYPE_CHECKING:  # the summary (conftest) needs no Qt
    from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Sampled:
    """One try: the judged runs and the warm-up's, in milliseconds."""

    runs: tuple[float, ...]
    warm_up: tuple[float, ...] = ()
    busy: float | None = None
    """How busy the rest of the PC was during the runs, where the try read
    it (the start's: its starts' median); else it's read after the try."""

    @property
    def median(self) -> float:
        return statistics.median(self.runs)

    @property
    def longest(self) -> float:
        return max(self.runs)

    def describe(self) -> str:
        return f"median {self.median:.1f} ms, longest {self.longest:.1f} ms"


@dataclass(frozen=True)
class Judged:
    """A budget test's verdict: one try, or more if the first was over."""

    test: str
    budget: Budget
    tries: tuple[Sampled, ...]
    passed: bool
    busy: tuple[float | None, ...] = ()
    """The PC's load for each try from the second that was over."""
    busy_from: float = busy_pc.SATURATED
    """The share from which the PC counted as busy for this action."""
    as_main: str = ""
    """Over its budget, but not slower than main's record, which this says
    (decision 0136): not failed."""
    notice: str = ""
    """An over-budget median reported for review on the shared Linux runner."""

    @property
    def on_a_busy_pc(self) -> bool:
        """Over, and every reading of the PC's load said busy: the load, as
        far as the judge can tell - not told apart from a slower action."""
        return (
            not self.passed
            and bool(self.busy)
            and all(busy_pc.saturated(b, self.busy_from) for b in self.busy)
        )

    def verdict(self) -> str:
        """The verdict, with the first try's numbers if there were more."""
        n = len(self.tries)
        if n == 1:
            return "ok"  # a first try over is always taken again
        first = f"try 1: {self.tries[0].describe()}"
        if self.busy:
            first += f"; {busy_pc.describe(self.busy[-1])}"
        if self.as_main:
            return f"{OVER_AS_MAIN_IS}: {self.as_main} ({first})"
        if self.notice:
            return f"timing notice: {self.notice} ({first})"
        if self.passed:
            return f"ok on try {n} ({first})"
        if self.on_a_busy_pc:
            return f"{OVER_ON_A_BUSY_PC} in {_all(n)} ({first})"
        return f"over in {_all(n)} ({first})"


OVER_AS_MAIN_IS = "over its budget as main is"
"""The verdict's words for a pull request's test over its budget but not
slower than main's record here (decision 0136): not failed."""

OVER_ON_A_BUSY_PC = "over on a busy PC"
"""The verdict's words when every reading said busy (`Judged.on_a_busy_pc`)."""


def _all(tries: int) -> str:
    return "both tries" if tries == 2 else f"all {tries} tries"


JUDGED: list[Judged] = []
"""Every judgement of this run, in order, for the summary."""

NOTES: list[str] = []
"""What a budget test found beside its judgement, for the summary after
the judgements, pass or fail: the start's parts beside main's (`tools/
start_record.py`, polyglotic-hq 314). Names and numbers only."""


def timed(qapp: QApplication, action: Callable[[], object]) -> float:
    """Milliseconds for `action` and everything it queues."""
    start = time.perf_counter()
    action()
    qapp.processEvents()
    return (time.perf_counter() - start) * 1000


def sampled(
    qapp: QApplication, actions: Sequence[Callable[[], object]], warm: bool = True
) -> Sampled:
    """Each of `actions` timed, after one pass of them all if `warm` (timed
    for the record, not judged), with the garbage collector held off.
    `warm=False` for a first time, judged as one."""
    collecting = gc.isenabled()
    gc.disable()
    try:
        warm_up = tuple(timed(qapp, action) for action in actions) if warm else ()
        return Sampled(tuple(timed(qapp, action) for action in actions), warm_up)
    finally:
        if collecting:
            gc.enable()


def longest_allowed(budget: Budget) -> float:
    """What any one run may take: the slot budget, or the budget itself
    where that's longer (a theme change, a start)."""
    return max(budget.ms, budgets.SLOT.ms)


GITHUB_MAC_TIMES = 2.0
"""On GitHub's own Mac runner a median is held to twice its budget
(decision 0195): that VM's noise is the size of a budget of a few ms (its
50 ms sleeps took 125-151 ms: polyglotic-hq 420), so it can't tell a slow
app from a slow VM. Twice still catches a doubling; every run is still held
to the slot budget, and a person's Mac and every other runner to the
budget itself."""


def on_githubs_mac() -> bool:
    return (
        sys.platform == "darwin"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    )


def median_allowed(budget: Budget) -> float:
    """What the median may take: the budget, or `GITHUB_MAC_TIMES` it on
    GitHub's Mac."""
    return budget.ms * (GITHUB_MAC_TIMES if on_githubs_mac() else 1.0)


def fits(budget: Budget, sample: Sampled) -> bool:
    return sample.median <= median_allowed(
        budget
    ) and sample.longest <= longest_allowed(budget)


def _load(sample: Sampled) -> float | None:
    """The PC's load for a try: read during its runs if it was, else now."""
    return sample.busy if sample.busy is not None else busy_pc.busy_share()


def _frame_budget_is_advisory(budget: Budget) -> bool:
    """The shared Linux PR runner has a slower frame median (HQ 711)."""
    return (
        budget == budgets.FRAME
        and sys.platform == "linux"
        and os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted"
        and os.environ.get("GITHUB_EVENT_NAME") == "pull_request"
    )


def within(
    budget: Budget,
    take: Callable[[], Sampled],
    busy_from: float = busy_pc.SATURATED,
) -> None:
    """`take`'s samples within `budget`: the median within it and no run
    over `longest_allowed`. If over, they're taken once more, and again
    while the PC measures busy - `busy_from` and up; saturated unless the
    test says - up to `busy_pc.MOST_TRIES` (decisions 0040, 0103); the test
    fails only if the last try is over too, and says what every try found
    and how busy the PC was: "over on a busy PC" if every reading said
    busy, else "over". On the shared Linux PR runner, a frame median miss
    within the slot limit is reported as a timing notice.
    """
    tries = [take()]
    busy: list[float | None] = []
    while not fits(budget, tries[-1]) and len(tries) < busy_pc.MOST_TRIES:
        if len(tries) >= 2:
            busy.append(_load(tries[-1]))
            if not busy_pc.saturated(busy[-1], busy_from):
                break
        tries.append(take())
    last = tries[-1]
    passed = fits(budget, last)
    if not passed and len(busy) < len(tries) - 1:
        busy.append(_load(last))  # the last try's: to say how busy
    test = os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0]
    as_main = "" if passed else beside_main(test, budget, last)
    notice = ""
    if (
        not passed
        and _frame_budget_is_advisory(budget)
        and last.longest <= longest_allowed(budget)
    ):
        notice = "frame median over budget on the shared Linux pull request runner"
    judged = Judged(
        test,
        budget,
        tuple(tries),
        passed or bool(as_main or notice),
        tuple(busy),
        busy_from,
        as_main,
        notice,
    )
    JUDGED.append(judged)
    if as_main or notice:
        title = "Timing notice" if notice else "Over its budget as main is"
        line = f"{test} {budget.name}: {last.describe()} - {judged.verdict()}"
        print(f"\n{title} - {line}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::warning title={title}::{line}")
        return
    assert passed, (
        (
            f"{OVER_ON_A_BUSY_PC.upper()} (every reading {busy_from:.0%} busy or more): "
            if judged.on_a_busy_pc
            else ""
        )
        + f"{budget.name} over its {median_allowed(budget):g} ms (any one run"
        f" {longest_allowed(budget):g} ms) in {_all(len(tries))}: "
        + "; ".join(f"try {n}: {t.describe()}" for n, t in enumerate(tries, 1))
        + f"; {busy_pc.describe(busy[-1])}"
    )


BESIDE_MAIN_ON = ("win32", "linux")
"""Where CI keeps main's record of the budget tests: the PC's Windows
runners, and its Linux runner - a container on the same PC, 2 CPUs, where
a look drag's step measured 7.4-10 ms against its 8 (polyglotic-hq 563:
it failed four pull requests on 2026-11-20 that hadn't touched it, and
main's own run passed it on a second try at 7.4)."""

RECORD_KIND = f"pytest-{sys.platform}"
"""Main's record of the budget tests on this system: Windows' and Linux's
are kept apart (the drag's step: 5.9 ms on Windows, 7.4-10 on Linux, the
same day)."""


NOT_BESIDE_MAIN = (budgets.START_FROM_SOURCE, budgets.START_PACKED)
"""The starts keep their own judging (decision 0103): at `SLOWER` than
main's, a start 200 ms slower (304's first wheel guard) would barely fail."""


def beside_main(test: str, budget: Budget, last: Sampled) -> str:
    """For a comparable test over budget on Windows or Linux:
    main's record of it, if the last try isn't `timing_record.SLOWER` - the
    words for the verdict - else "" (it fails)."""
    if (
        sys.platform not in BESIDE_MAIN_ON
        or start_record.on_main()
        or budget == budgets.FRAME
        or budget in NOT_BESIDE_MAIN
    ):
        return ""
    record = timing_record.load(RECORD_KIND)
    main = record.timings.get(test) if record else None
    if record is None or main is None:
        return ""
    if timing_record.Timing(last.median, last.longest).slower_than(main):
        return ""
    return (
        f"main's ({record.commit[:8]}) median {main.median_ms:.1f} ms,"
        f" longest {main.longest_ms:.1f}"
    )


def keep_mains_record() -> bool:
    """On CI's run of main, on Windows or Linux: every judgement's last try
    kept as main's record (decision 0136). False if not kept."""
    if sys.platform not in BESIDE_MAIN_ON or not start_record.on_main() or not JUDGED:
        return False
    new = {
        j.test: timing_record.Timing(j.tries[-1].median, j.tries[-1].longest)
        for j in JUDGED
        if j.budget not in NOT_BESIDE_MAIN
    }
    if not new:  # only the starts: nothing to keep (and nothing hidden)
        return False
    sha = os.environ.get("GITHUB_SHA", "")
    record = timing_record.load(RECORD_KIND)
    # added to what main's other sessions kept of this commit (the UI lab
    # job runs some budget tests by themselves)
    kept = dict(record.timings) if record and record.commit == sha else {}
    kept.update(new)
    return timing_record.save(RECORD_KIND, kept, sha)


def _ordered() -> list[Judged]:
    """Over first, then retried, then the rest as they ran."""
    return sorted(JUDGED, key=lambda j: (j.passed, len(j.tries) == 1))


def summary_lines() -> list[str]:
    """Every judgement, one line each, for pytest's summary."""
    lines = []
    for judged in _ordered():
        last, first = judged.tries[-1], judged.tries[0]
        warm = f"{max(first.warm_up):.1f}" if first.warm_up else "-"
        lines.append(
            f"{judged.test.rsplit('/', 1)[-1]}  {judged.budget.name}"
            f" {judged.budget.ms:g}: median {last.median:.1f}, longest"
            f" {last.longest:.1f}, warm-up longest {warm} - {judged.verdict()}"
        )
    return lines


def summary_markdown() -> str:
    """Every judgement as a table, for CI's run page."""
    lines = [
        "## Budget tests",
        "",
        (
            "Each timed action in the main suite (pytest), offscreen, in ms: the"
            " median of its runs is held to the budget and its longest run to"
            " 50 ms (or the budget, if longer). A try over either is taken once"
            " more - up to twice more again while the PC measures saturated"
            " (decision 0040) - and the first is shown with the last. A test"
            ' over in every try while every reading said busy is "over on a'
            ' busy PC" (decision 0103). On the shared Linux pull request runner,'
            " a frame median miss within the slot limit is a timing notice. The warm-up"
            " (a first pass of the same actions) is recorded, not judged."
        ),
        "",
        "| Test | Budget | Median | Longest | Warm-up longest | |",
        "|---|---|---|---|---|---|",
    ]
    for judged in _ordered():
        last, first = judged.tries[-1], judged.tries[0]
        warm = f"{max(first.warm_up):.1f}" if first.warm_up else ""
        verdict = judged.verdict()
        lines.append(
            f"| {judged.test.rsplit('/', 1)[-1]} | {judged.budget.name}"
            f" {judged.budget.ms:g} | {last.median:.1f} | {last.longest:.1f} |"
            f" {warm} | {verdict if judged.passed else f'**{verdict}**'} |"
        )
    return "\n".join(lines) + "\n"
