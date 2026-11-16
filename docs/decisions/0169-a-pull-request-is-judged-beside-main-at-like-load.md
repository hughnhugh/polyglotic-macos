# 0169 A pull request's timings are judged beside main's at like load

- **Status:** accepted (reversible; adds to decision 0136, which it keeps)
- **Date:** 2026-11-16
- **Decided by:** polyglotic-hq project 381 (brief: "a PR's timing judged against main's record scaled by the run's own measured load ... a busy run of unchanged code passes; a real 2x regression on a calm or busy run still fails"). Claude reviews it with the pull request. No budget changes: the numbers stay the user's (decision 0031).

## Situation

Decision 0136 compares a pull request's action over its budget with main's
last record on this PC, and fails it if it is more than 1.5x main's
(`SLOWER`). Main's record is whatever load main's run had; the pull request
is whatever load it has. The PC is shared by two CI runners and every
agent's tests, and its load moves from about 25 % to over 80 % busy within
an hour.

- 367 (2026-11-15/16) found Settings' section switch at 8-10 ms on busy
  pull requests against main's calm 5.3-6.7 ms: #694's run was 9.9 against
  5.33, 1.86x, with nothing changed.
- Train #711 failed its UI lab at 2026-11-16 00:46 on
  `w4_settings_timing: section_switch` at the Largest text size: 12.2 ms
  after four tries, the PC 80 % busy.
- A section's first show was timed as a section switch (fixed beside this,
  381's other pull request: `section_first_show`), but any action near its
  budget meets the same thing on a busy PC.

## Decision

- **A reference step** (`tools/ui_lab/reference.py`): before each gated
  state, the lab times a fixed piece of interface work - one of two panels
  of 24 wrapped labels hidden, the other shown, laid out and painted, with
  what it queues - 12 times, and keeps the median as the state's
  `reference_ms`. Its code doesn't change with a pull request, so it slows
  only with the PC.
- **Main's record keeps each gated state's step** beside its actions
  (`state: reference_step`, in the same file and format).
- **On a pull request**, main's timing for an action is scaled by the load
  scale before 0136's comparison: the median step of the state and its 5
  neighbours either side, now, over the same states' median in main's
  record (`load_scales` in `tools/ui_lab/__main__.py`). Over 1.5x main's
  *at like load* fails; otherwise it is "over its budget as main is", as
  in 0136. Each line now says the scale ("the PC 1.30x as slow as for
  main's"), and an action that fails beside main's record says so
  ("slower than main's - ...").
- **No step in main's record** (a record kept before this, or a state new
  to it): scale 1, 0136 as it was.
- The scale works both ways: a pull request on a calmer PC than main's run
  is compared with less than main's record.
- Unchanged: the budgets, the retries (0040), main's runs held to the
  budget alone, the starts (0103), the pytest budget tests (0136's
  `beside_main` still compares unscaled).

## Why

- **It asks 0136's question at like load:** did this change make the
  action slower, on this PC as busy as it is now? 381's bench (main's code,
  2026-11-16, Settings' seven states at two text sizes, a run at 42-49 %
  busy as main's record against runs at 64-76 % busy with four
  below-normal busy loops added): of the runs over a budget, 0136 failed
  88 pairs of Settings' first shows and 56 of the old section switch; at
  like load, 17 and 9.
  (Each bench group was 7 states, so the 11-state window was the whole
  group.) The whole gate, main's code with 381's split, a record kept as
  main's then a pull request's run with four busy loops added (88-91 %
  busy at its retries): 8 actions over budget; 0136 would have failed 4,
  at like load 2.
- **What it doesn't fix:** at 88-91 % busy the step read 1.24-1.30x while
  single-sample actions ran 1.3-2.4x (Words at 10,000 met: first search
  50.5 ms against main's 20.9), and those still fail. A saturated PC is
  0040's retries' to deal with, or the runners'.
- **A 2x regression still fails:** of the same runs made twice as slow,
  0136 caught 500 of 504 first-show pairs and like load 488; on a calm run
  against a calm record, 402 and 404 of 420. Tested in
  `tests/tools/test_ui_lab_like_load.py`: unchanged code on a PC 1.7x as
  slow passes; twice main's on that PC, or on a calm PC, fails.
- **The neighbours' median, not the state's own step:** one step varies by
  about a fifth on one load (coefficient of variation 0.18-0.21). Scaled by
  its own step alone, the bench caught 456 of 504 doubled first-show pairs
  instead of 488, and passed fewer busy runs. Eleven states are about
  10-20 seconds of a run, short beside a busy spell of other jobs.
- **Why a step of interface work, though 0040 turned one down:** 0040's
  calibration step (pure Python, against its quickest in the process)
  scaled a *budget*, so on a calm PC it loosened the budget whenever the
  CPU's clock moved. Here the budget is untouched, and the step scales
  main's timing against main's own step: a clock change that slows the
  step slows the action too, and only the comparison with main moves.
- **Alternatives not taken:**
  - **The CPU's busy share as the scale:** it doesn't say how much slower
    the interface thread runs. 381 measured the old section switch only
    1.03-1.06x slower at 64-65 % busy than at 47-49 %, where 367 saw
    1.5-1.9x on CI's runs at 35-80 %; the step measures the slowdown itself.
  - **Main's record from a calm run only:** the PC is rarely calm while CI
    works, and a pull request on a busy PC would still meet a calm record.
  - **Main's code re-run in the same job:** the lab's timed run is 3-5
    minutes; doing it twice on the one Windows runner doubles every train.
  - **A looser `SLOWER`:** lets a real regression through on a calm PC.

## What would make us reverse it

- A regression under 2x merging because a pull request's step read slow
  while its actions weren't: the run's page names the scale each time, so
  look for scales over about 1.5 on a calm-looking run.
- The step and the actions parting ways under some load (the step slowing
  much more or much less than Settings or Words): then time a real state's
  warm action as the step instead.

## How we'd reverse it

Drop `load_scales` and the `scaled` call in `tools/ui_lab/__main__.py`'s
`judged_beside_main` (the gate is 0136's again), and `reference.py` with its
call in `lab._run_state` and its lines in `gated_timings`. Records with
`reference_step` entries can stay: nothing else reads them.
