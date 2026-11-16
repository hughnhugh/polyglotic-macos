# 0040 A timing over budget gets more tries only while the PC measures saturated

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq project 197 (brief item 4: "the smallest honest change ... never just widening the budgets"); Claude reviews it with the pull request. Adds to project 140's judging (a warm-up, the garbage collector held off, one retry; `tests/budget_judge.py`, `tools/ui_lab/lab.py`). No budget changes: the numbers stay the user's (decision 0031, polyglotic-hq DECISIONS.md #53).

## Situation

The budget tests and the UI lab time interface actions in wall time on
the user's PC, which the CI runners and every agent's test runs share.
Since 140 (2026-11-07), an action over budget is timed once more and
judged on the second try.

Measured for 197:
- **CI, 2026-11-07 10:22-18:27 UTC** (192 desktop CI runs, 368 Windows jobs,
  read from their logs):
  - **The UI lab:** 79 of 185 jobs needed a second run for at least one state, and every second run passed. Of the 39 retried actions whose numbers the logs showed:
    - 32 were one run over the 50 ms slot (51-309 ms) while the median stayed at 1-21 ms;
    - 7 were actions timed once (a cold page switch, a theme change), so their one run is their median.
  - **The pytest budget tests:** 1 retry in 180 jobs (4,680 judgements).
  - **Failures:** no budget failed a CI job.
- **This PC on 2026-11-08,** while the user played a game and agents ran, with the CPU 53-100 % busy (median 71 % of 16 threads): 260 judgements and 4 lab runs (316 state runs, two at 200 % text) needed no second try. The typical margins are wide: medians of 1-15 ms and longest runs of 2-19 ms, against budgets of 8-50 ms.
- **Project 179, 2026-11-07,** with many agents testing at once: the lab at 200 % text went over **in both runs** on some runs and not others:
  - the transcript (`w2_1000`'s rail, `w2_rail_popover`);
  - Home (`w4_picker_full`, `w4_everything_else`).

So a single slow moment is common and the retry absorbs it. Only a PC
loaded hard enough to slow two runs in a row fails, and nothing in the
verdict says the PC was the cause.

## Decision

When a try is over budget and its retry is over too, the judge reads
**how busy the PC is**: the share of all CPU time in use over 0.2 s, from
the system's own counters (Windows' `GetSystemTimes`, Linux's
`/proc/stat`; `tools/busy_pc.py`).

- At **50 % or more** (saturated), the action gets another try, up to **4 tries** in all. It was 90 % until 2026-11-11: with several agents working, the PC sat at 49-56 % busy, every physical core taken, and the start-time check failed five times in one evening on changes that added nothing at start (polyglotic-hq journal 2026-11-11). A real slowdown still fails every try.
- Otherwise it fails as before.
- The verdict always names the reading: "over in both tries (...; the PC 60% busy)", "ok on try 4 (...; the PC 97% busy)".
- Where the counters can't be read, no extra tries are given.

Both the pytest judge (`within`) and the lab's gate (`run`) do this. The
lab's JSON gains `tries` and `busy`. The budgets, the median and longest-run
rules, and the first retry are unchanged. Tests pin the load
(`busy_share` replaced), so no test depends on how busy the PC is.

## Why

- **It's measured, not assumed:** more tries are given only when the PC is shown to be saturated, at the moment of judging. A calm or merely busy PC gets exactly 140's rules. A real slowdown is over in every try, saturated or not, and still fails: the test "a real slowdown fails on a saturated PC too" checks it.
- **No budget moves.** The brief ruled out widening them, and so does decision 0031.
- **The failure says why.** A budget failure now names the PC's load, so "main is red" and "the PC was saturated" can be told apart without a rerun.
- **Alternatives not taken:**
  - **The median of 3 tries:** passing 2 of 3 is stricter than today's 1 of 2. With a chance p of one slow moment, it fails about 3p² against p², so it would fail more on a busy PC, not less.
  - **A budget scaled by a calibration step** (fixed pure-Python work timed against its quickest in the process): on this PC it read 1.6x "slower" at its median while nothing went over. CPU clock changes move it as much as load does, so it would have scaled budgets on a calm PC.
  - **Thread CPU time instead of wall time:** Windows updates it in 15.6 ms ticks, too coarse for 2-8 ms budgets, and it would miss an action's own waiting.
  - **Raising the test's priority:** it would take CPU from the user's foreground app (a game) on their PC.

## What would make us reverse it

- A real slowdown passing on a third or fourth try: an action slow often but not always, while the PC was saturated.
- CI often reaching 4 tries. That would mean the runners are saturated as a rule, and the answer is fewer jobs at once, not more tries.

## How we'd reverse it

Set `busy_pc.MOST_TRIES` to 2. The judging is then 140's again, and the
verdicts still name the load. Removing it entirely means deleting
`tools/busy_pc.py` and the loops in `within` and `run` (about 30 lines)
and the tests that pin the load.
