# 0270 Linux budget tests are judged beside main's record too

- **Status:** accepted (reversible; widens decision 0136 from Windows to Linux)
- **Date:** 2026-11-20
- **Decided by:** polyglotic-hq project 563, item 2 (brief: "judge it against a measured baseline, as the Windows budgets are, or skip it on the shared runner"); BACKLOG.md "Linux budget tests judged beside main's record, as Windows' are (386, 406)". Claude reviews it with the pull request. No budget changes: the numbers stay the user's (decision 0031).

## Situation

`tests/ui/test_look_drag.py::test_a_step_of_a_look_drag_within_a_frame`
(the `frame` budget, 8 ms) failed Checks (Linux) on four pull requests on
2026-11-20, at medians of 8.2-10 ms. None of them had touched it. Main's
own Linux run that day passed it only on a second try (7.4 ms, after 8.0).
On Windows the same day it measured 5.9 ms. The Linux runner is a container
on the user's PC with 2 CPUs, beside the live server and the Windows runners.
Each failure cost a re-run of the job on every train.

Decision 0136 already answers this on Windows: a test over its budget
fails a pull request only if it is more than 1.5x main's record. It was
Windows only, because the record was kept in `C:\ProgramData`, which the
Linux runner doesn't have. On Linux that path is a relative folder inside
the job's checkout, and the checkout is cleaned for each job.

## Decision

- **The pytest budget tests keep main's record on Linux as on Windows**
  (`tests/budget_judge.py`, `BESIDE_MAIN_ON`). Each system has its own
  record (`pytest-win32`, as before, and `pytest-linux`), so neither is
  judged against the other's timings.
- **On Linux the record is in the runner's home** (`~/.polyglotic-ci`,
  `tools/timing_record.OFF_WINDOWS`). It lasts from job to job, as the
  runner's registration does, until the container is made again.
- **The rest is 0136's, unchanged:** main's own runs are held to the
  budget alone; more than 1.5x main's, or with no record, fails; the
  starts keep 0103's judging. Not on a Mac: GitHub's Mac runner keeps
  nothing between jobs, and it has its own allowance (decision 0195).

## Why

- **It asks whether the change made it slower,** on the runner where the
  test is measured. A 2x slowdown still fails, in every try.
- **Skipping the budget tests on Linux** would have been simpler. But the
  Windows suite runs only on a train (decision 0167), so a pull request's
  only budget check before the train is Linux's.
- **A looser Linux budget** would change the user's numbers (0031).

## What would make us reverse it

- The Linux runner's container being made again often, so the record is
  missing and pull requests are held to the budget again. Then keep the
  record on a named volume.
- A regression under 1.5x reaching main through Linux alone. Main's own
  run still shows it.

## How we'd reverse it

Set `BESIDE_MAIN_ON` back to `("win32",)` in `tests/budget_judge.py`. The
record in the runner's home can be left there, because nothing else reads it.
