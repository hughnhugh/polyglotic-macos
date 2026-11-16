"""The start with a big learner, held to its budget: `main()` from source,
offscreen, to the main window's first paint, with a made-up learner of
30,000 words met on the real CC-CEDICT (`tools/learner_start.py`) - within
`perf.budgets`' START_FROM_SOURCE (polyglotic-hq 229). `--check-install`
times the start with an empty learner, so a start that grew with the words
met went over unseen: 541-566 ms at 30,000 before #339 (220).

Why 30,000 and not 10,000 words met: with #339 undone, the start at 10,000
measured 406-565 ms on 2026-11-08 - often within the budget, so a gate
there wouldn't keep #339's gain; at 30,000 it was 638-906 ms, and 276-381
ms with it but for one start in 50 (`tools/learner_start.py`, one process
at a time; CI's runner included). A learner
within the budget at 30,000 is within it at 10,000: the start only grows
with the words met.

The PC the runners share with every agent's work and the user's own
(polyglotic-hq 312, 2026-11-14) slows the start by about 45 ms for each 10 %
of it in use: it goes over 400 ms from about 44 % busy, and was 353 ms at
26 %. So each try waits for a calm PC first (`busy_pc.wait_for_calm`, up to
a minute), each start reads how busy the rest of the PC was meanwhile, and
the PC counts as busy for the start from `busy_pc.CALM` (30 %), not from
saturated: a try over on a PC that busy is taken again, up to 4 tries, and
if every try was, the failure says "over on a busy PC" - still a failure,
told apart from a slower start (decision 0103).

In CI the test runs holding the PC's lock alone (`tools/ci_lock.py`,
decision 0105): the other runner's heavy steps, and any local run that
takes the lock shared, have ended and new ones wait. So its first try may
wait longer for a calm PC (`FIRST_CALM_WAIT_SECONDS`): what's still running
then ends, and nothing new of ours starts. A failure on a busy PC also says
what the parts say against main's record (`start_record.grew`, 314): no
part grew - the whole start slowed, as a busy PC does - or which part grew.
It still fails either way: a start slower all round looks the same as a
busy PC, so only a calm try can pass it.

It needs the real CC-CEDICT, built from its pinned sources: CI's UI lab
job builds it (`python -m tools.dictionaries.build --only cedict`) and
names its folder in POLYGLOTIC_REAL_DICTIONARIES. Without that, it's
skipped: the tests' sample has 30 entries. The learner and a timed
start are tested everywhere on made-up dictionaries
(`tests/tools/test_learner_start.py`)."""

import itertools
import os
import statistics
from pathlib import Path
from typing import Any

import pytest
from tests.budget_judge import NOTES, OVER_ON_A_BUSY_PC, Sampled, within
from tools.learner_start import made_up_learner, returning_learner, timed_start

from polyglotic_desktop.perf.budgets import START_FROM_SOURCE
from tools import busy_pc, start_record

WORDS = 30_000
STARTS = 5
"""Starts a try, each a process of its own. Their median is the try's one
sample, held to the budget by `budget_judge.within` and taken again if
over, as every budget test's is: the typical start, as the budget means.
Not every start: on the user's PC, shared with other agents' work, 1 of
50 starts at 30,000 words met took over 500 ms (511; the rest 276-381 ms,
2026-11-08, CI's runner included), so holding all 5 would fail about one
pull request in 100 for nothing. Undoing #339 puts every start over
(638-906 ms): the median catches it."""

REAL_DICTIONARIES = "POLYGLOTIC_REAL_DICTIONARIES"

FIRST_CALM_WAIT_SECONDS = 180.0
"""The first try's longest wait for a calm PC; the later ones wait
`busy_pc.CALM_WAIT_SECONDS`. On 2026-11-14 a pull request's start waited a
minute at 77-79 % busy and failed; under CI's lock nothing new of ours
starts while it waits, so the runs going on end. At most about 3 + 3 x 1
minutes of waiting, inside the UI lab job's limit."""


def what_the_parts_say(parts: dict[str, float]) -> str:
    """For a failure on a busy PC: the parts against main's record on this
    PC - none grew (the whole start slowed, as a busy PC does) or which."""
    record = start_record.load()
    if record is None:
        return "no record of main's start here to compare its parts with"
    grown = start_record.grew(parts, record.parts)
    if not grown:
        return (
            f"against main's record ({record.commit[:8]}) no part grew: the whole"
            " start slowed, as a busy PC does - re-run on a calmer PC"
        )
    return f"against main's record ({record.commit[:8]}) these grew: " + ", ".join(
        f"{name} +{ms:.0f} ms" for name, ms in grown.items()
    )


@pytest.mark.windows_only  # the app's own OS adapters; the budget is Windows'
def test_the_window_is_shown_within_its_budget_with_30000_words_met(
    tmp_path: Path,
) -> None:
    folder = os.environ.get(REAL_DICTIONARIES)
    if not folder:
        pytest.skip(f"the real CC-CEDICT isn't built here ({REAL_DICTIONARIES})")
    dictionaries = Path(folder)
    learning = tmp_path / "learning.sqlite"
    made_up_learner(dictionaries / "cedict.sqlite", WORDS, learning)
    tries = itertools.count(1)

    def take() -> Sampled:
        n = next(tries)
        calm = busy_pc.wait_for_calm(
            most_seconds=FIRST_CALM_WAIT_SECONDS
            if n == 1
            else busy_pc.CALM_WAIT_SECONDS
        )
        starts = [
            timed_start(
                returning_learner(tmp_path / f"try-{n}-start-{i}", learning),
                dictionaries,
            )
            for i in range(1, STARTS + 1)
        ]
        read = [start.busy for start in starts if start.busy is not None]
        busy = statistics.median(read) if read else None
        print(
            f"try {n}: "
            + ", ".join(f"{start.window_ms:.0f}" for start in starts)
            + f" ms; before it {busy_pc.describe(calm)}; during it"
            + (f" the rest of the PC {busy:.0%} busy" if busy is not None else "")
        )
        # where the time went, beside main's last record on this PC: a
        # start that grew says which part grew (polyglotic-hq 314)
        taken[:] = [
            statistics.median(start.window_ms for start in starts),
            start_record.typical([start.parts for start in starts]),
        ]
        return Sampled((taken[0],), busy=busy)

    taken: list[Any] = []  # the last try's median and parts
    try:
        within(START_FROM_SOURCE, take, busy_from=busy_pc.CALM)
    except AssertionError as over:
        if taken and str(over).startswith(OVER_ON_A_BUSY_PC.upper()):
            raise AssertionError(f"{over}; {what_the_parts_say(taken[1])}") from None
        raise
    finally:  # pass or fail: in pytest's summary and on the run's page
        if taken:
            NOTES.append(start_record.table(taken[1], start_record.load()))
    if start_record.on_main():  # within its budget, on main: main's record
        start_record.save(taken[1], taken[0], os.environ.get("GITHUB_SHA", ""))


def test_a_failure_on_a_busy_pc_says_what_the_parts_say(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Against main's record on this PC: a start slower all round says no
    part grew (a busy PC's look, and a re-run's cue); one part slower, which."""
    monkeypatch.setenv("POLYGLOTIC_START_RECORD", str(tmp_path))
    assert "no record of main's" in what_the_parts_say({"learner": 100.0})
    main = {"learner": 150.0, "page_home": 100.0, "first_paint": 50.0}
    assert start_record.save(main, 300.0, "abcdef1234")
    busier = {name: ms * 1.4 for name, ms in main.items()}  # all round
    assert "no part grew" in what_the_parts_say(busier)
    grown = dict(main, page_home=160.0)  # one part, 60 ms
    said = what_the_parts_say(grown)
    assert "these grew: page_home +" in said and "learner" not in said
