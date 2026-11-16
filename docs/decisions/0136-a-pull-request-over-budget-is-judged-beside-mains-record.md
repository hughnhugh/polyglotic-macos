# 0136 A pull request over a budget fails only if it's slower than main's record on this PC

- **Status:** accepted (reversible; adds to decision 0040; the starts keep 0103)
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 344 (brief: "a budget measured on a shared runner should fail only when the code got slower ... a real 2x slowdown must still fail"). Claude reviews it with the pull request. No budget changes: the numbers stay the user's (decision 0031).

## Situation

344 read every failed CI attempt that a re-run then passed, 2026-11-04 to
2026-11-14: 67 attempts. Most were fixed by 312 and 314 (the start: 30, none
after 2026-11-13 21:00 UTC). What still failed after that:
- **The UI lab's theme change** (`w4_theme_change`, budget 100 ms) failed 5
  times. Its median on main was 29 ms on 2026-11-07, then 44 ms on 11-08,
  50-65 ms on 11-10/11, and 62-76 ms on 11-14.
  - Each failure was one run in eight over 100 ms, or a median of 78-122 ms.
  - They came at every load: 13 % to 71 % busy.
- **The three-column resize step** (`frame`, 8 ms) failed at medians of
  8.2-9.1 ms, at 13 % and 35 % busy.

Both are actions whose typical time on main has reached their budget.
Their failures are the code, not the runner, and no pull request in
between had changed them. Each failure cost a re-run of about 10 minutes on
the one Windows runner. More tries on a busy PC (0040, 0103) can't help an
action that is at its budget on a calm PC.

## Decision

- **On a push to main** (CI's run of main, on this PC), the gates keep every
  gated timing as main's record. The record holds the median and the longest
  run for each action, in `C:\ProgramData\polyglotic-ci` beside CI's lock
  (`tools/timing_record.py`). There is one record per UI lab kind (text
  size, app text size, language) and one for the pytest budget tests
  (Windows only).
- **On a pull request,** an action still over its budget after its tries
  (0040's rules, unchanged) is compared with main's record:
  - **More than 1.5x main's** (`SLOWER`), at the median or the longest run, or with no record to compare: it **fails**, as before.
  - **Otherwise it is "over its budget as main is":** named on stderr, as a warning annotation and on the run's page, and not failed.
- **Main's own runs are held to the budget alone.** When main goes over,
  main's run shows it every time.
- **The starts** (`start_from_source`, `start_packed`) keep their own judging
  (decision 0103).

## Why

- **It asks the question the brief asks:** did this change make it slower?
  A pull request that makes an action 2x slower fails, because 2x is over
  1.5x in every try. Tested in `tests/tools/test_ui_lab.py` (a click at
  60 ms against main's 30) and `tests/test_budget_judge_beside_main.py`.
- **The budget still means something.** Main's own run is held to it, so
  main at its budget fails visibly on main, where the cause landed, instead
  of on whichever pull request comes next.
- **Why 1.5x:** main's own runs of one action vary by up to a third within a
  day (the theme change: 49.6-65.0 ms on 2026-11-10/11), and a busy PC's
  runs vary more. A margin at 2x or over would let a real doubling pass.
- **Alternatives not taken:**
  - **More tries from 30 % busy, with a wait for calm** (0103's rules for
    every gate): the two actions above fail at 13 % busy. That rule would
    give near-budget code more chances to pass, and fix nothing on a calm PC.
  - **A looser budget:** the numbers are the user's (0031).
  - **The longest run judged as the second-longest:** it would hide a real
    stall that comes once in eight runs.
  - **A reference workload timed in the same run:** 0040 measured it moving
    1.6x with nothing over, from CPU clock changes alone.

## What would make us reverse it

- A regression of under 1.5x merging and then sitting on main for long. The
  answer is to watch main's runs, or to tighten `SLOWER`.
- Main's record often coming from an unusually busy or unusually calm run,
  so that pull requests are judged too loosely or too strictly. Then keep
  the median of main's last few records instead of the last one.

## How we'd reverse it

Remove `judged_beside_main` from `tools/ui_lab/__main__.py`, and
`beside_main` and `keep_mains_record` from `tests/budget_judge.py` (about 80
lines with their tests). The gates are then 0040's again. The record files
on the PC can be left; nothing else reads them.
