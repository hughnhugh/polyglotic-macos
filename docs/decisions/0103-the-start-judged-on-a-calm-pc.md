# 0103 The start is timed on a calm PC where it can be, and a failure on a busy PC is named as one

- **Status:** accepted (reversible; adds to decision 0040 for the start, and to every budget test's verdict)
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 312 (brief: "make the test judge fairly without hiding a real regression ... say why that isn't enough and what would be"); Claude asked for a named outcome for a failure on a busy PC (2026-11-14). Claude reviews it with the pull request. No budget changes: `START_FROM_SOURCE` stays 400 ms (the user's, decision 0031).

## Situation

From 2026-11-13 14:16 UTC the start gate (`tests/ui/test_start_with_a_big_learner.py`,
decision 0046) failed on main `b61fef4e` and on most pull requests at
419-565 ms against 400 ms. On green runs that morning it had been 341-400 ms.

312 measured why, on this PC (Ryzen 7 9850X3D, 8 cores, 16 threads):
- **Not the code since 0.1.4.** 9fb2c0c (0.1.4), c4644161, 7a3bb264 and b61fef4e were started in turn, in a shuffled order, 122 starts. Allowing for load, the four were within about 15 ms of each other.
- **The PC's load.** Each start read how busy the rest of the PC was meanwhile. The start took about 45 ms more for each 10 % of the PC in use, and went over 400 ms from about 44 % busy (the start's own CPU included). At 26 % it was 353 ms.
  - From about 14:00 UTC the PC was 35-87 % busy: five agents, two Windows runners, and once the user's own browser on 8.6 of its 16 threads.
- **The start spreads over seven threads,** about 1.3 cores at once. So it slows long before the PC is saturated, while a one-thread interface action barely notices.

Why decision 0040's extra tries weren't enough for the start:
1. **The 50 % threshold:** a PC 50 % busy earns more tries, but the start is already over at 44 %.
2. **One reading, after the try:** the load is read for 0.2 s after a try, not during its starts.
3. **Retries land in the same spell:** they come seconds apart, while other agents' test runs last minutes.

## Decision

- **For the start (the test passes `busy_from=busy_pc.CALM`):**
  - Before each try, the test waits for the PC to read under 30 % busy over a second (`busy_pc.wait_for_calm`), for at most a minute.
  - Each start reads how busy the rest of the PC was during it: the PC's CPU time in use minus the start's own (`busy_pc.OthersMeanwhile`, `tools/learner_start.py`). The try's reading is the median of its starts' readings (`Sampled.busy`).
  - From 30 % the PC counts as busy for the start, so a try over on a PC that busy is taken again, up to 4 tries (0040's limit).
- **Every budget test's verdict:** when a test fails and every reading of the PC's load said busy, the verdict is "over on a busy PC", and the assertion starts `OVER ON A BUSY PC`. Otherwise it stays "over", which points at the code. Either way the test fails.
- **Unchanged:** the budget, the median of 5 starts per try, the longest-run rule, and 4 tries at most. Every other test keeps 50 % (`SATURATED`) and reads the load after a try.

## Why

- **Fair on a calm PC, honest on a busy one.** A start within its budget passes when the PC is calm. A slower start is slow in calm moments too, so it fails every try as before, and "over" with a calm reading says it's the code. When the PC never calms, the test can't tell a regression from the load (304's first wheel guard, a real +200 ms, read 565 ms under load, the same as load alone gives). So it still fails, but under its own name, and a reviewer knows to look at the PC first.
- **The margin is the code's to restore.** The window build grew by about 85 ms between 2026-11-08 and 2026-11-12: the Settings page is built whole at start. The imports thread's GIL use during the build costs about 90 ms more. Both are proposed in polyglotic-hq 312, not done here. The judge only stops a busy PC passing for a slow start, and the reverse.
- **Alternatives not taken:**
  - **A load-scaled budget,** the start "in calm-PC milliseconds" from a fitted slope. On the busy hour 312 measured, the PC was under 30 % busy for 2 % of starts, so the slope can't be fitted where it matters. It would also move a number that is the user's.
  - **The fastest starts of a try:** this loosens the calm gate by 30-50 ms.
  - **"Not judged" (a skip) on a busy PC:** that is green while hiding a regression. Claude asked for a named failure instead.
  - **A raised priority for the timed start:** measured, no difference (372-376 ms against 381 ms). The slowdown is cores shared with other work, which priority doesn't win back.
  - **Serialising the two Windows runners:** that halves CI's throughput, and the load is mostly not CI's.

## What would make us reverse it

- "Over on a busy PC" turning out, on a calm re-run, to be a real slowdown more than rarely. Then the busy reading would be hiding a regression's name, and the 30 % level is too low.
- The minute's wait adding enough to the UI lab job that the queue suffers. Shorten `CALM_WAIT_SECONDS`.

## How we'd reverse it

Drop `busy_from=busy_pc.CALM` and the `wait_for_calm()` call from the start
test. It is then judged by decision 0040 alone, and still reads the load
during its starts. The named outcome is `Judged.on_a_busy_pc` and its two
uses (`verdict`, the assertion). Removing them restores 0040's wording.
