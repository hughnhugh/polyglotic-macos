# 0047 The UI lab judges Words' first show on the median of five fresh pages

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq project 234 (brief item 1: "If it's only noise, make the gate judge like the start gate: a median of several tries ... not one sample. Don't loosen the 50 ms budget itself"); Claude reviews it with the pull request. Adds to decision 0040 (more tries only while the PC is saturated) and follows decision 0046 (the start: the median of 5 starts).

## Situation

The UI lab's `ui_next.w4_words_met_10000` times Words' first show for a
made-up learner of 10,000 words met, once, against the cold page switch's
50 ms budget (`perf.budgets.PAGE_SWITCH_COLD`). On 2026-11-08 it went over
in desktop #350's second CI run, in Simplified Chinese: 51.0 ms, then 58.7
ms on the retry, with the PC read as 38 % busy - so no more tries
(decision 0040) and the job failed. The change under test didn't touch
Words.

Measured for 234:
- **CI, the 39 UI lab jobs on 2026-11-08** (read from their logs): the
  first show's median was 23.1 ms in English, 26.2 at 200 % text, 24.2 in
  Simplified and 23.7 in Traditional Chinese; longest 41.9, 40.1, 58.7 and
  46.2. The one failure was the only time any language went over. In that
  job's Simplified step every Words state was slow - the heavy learner's
  first show 1.52 times its median, 1,000 words met 1.55 times, 10,000
  words met 2.43 times - and English's and Traditional's steps of other
  jobs were as slow overall. A busy runner, not the language.
- **This PC, 20 runs of the lab's Words states per language** (other
  agents' tests running, the PC 20 % busy at the median): medians 21.7,
  22.6 and 23.1 ms (English, Simplified, Traditional), longest 29.3, 40.3
  and 31.1 ms.

A page's first show happens once in a page's life. The lab times it once,
so its one run is both its median and its longest: one slow moment of the
PC in each of two tries fails the job, where an action timed six times
would have passed on its median.

## Decision

`Lab.time_fresh` times an action that happens once in a widget's life on
five fresh widgets, the setup of each not timed, and records their median
as the action's one run, held to its budget as any run is. Each of the
five is recorded beside it (`page_switch_cold_each`), not judged. The
`w4_words_met_*` states use it for Words' first show: five Words pages
and windows over the same prepared learner, each shown for the first
time; the last one stays for the rest of the state and the picture. A
try over is taken again as before (decision 0040). Tested in
`tests/tools/test_ui_lab.py`.

## Why

- **The budget is unchanged** (the user's numbers, decision 0031): a first
  show still has to be within 50 ms, now on a typical one rather than a
  single moment.
- **A real slowdown still fails:** it makes most of the five slow, so the
  median is over in every try. The test holds both: one slow show in each
  try passes; three slow in each try fails.
- **Five, as the start's gate (decision 0046).** Three would forgive one
  slow show, five forgive two. The five cost about 0.2 s a state: the
  10,000-word state took 0.49-0.55 s instead of 0.31-0.32 s (three runs
  each on this PC, 2026-11-08).
- **After 20 runs per language on this PC** the judged first show (the
  median of five) had medians 22.5, 23.2 and 23.6 ms (English,
  Simplified, Traditional) and longest 30.7, 34.8 and 34.6 ms; the 100
  single shows behind them per language, 20.0-35.8, 21.2-38.2 and
  21.0-42.9 ms. Neither before nor after went over here: the PC was 20-62 %
  busy, not as busy as the runner was.
- **Only Words' big learners,** the gated first shows that went over. The
  other gated first shows had CI medians of 2-19 ms on 2026-11-08 (Words with
  a full list the longest: 14.3-19.0 ms, longest 43.3) and none went over
  in the 39 jobs; they can take `time_fresh` when they need it.
- Not taken:
  - **a smaller first show** - the time isn't the language's, and 212 and 220 have already cut it;
  - **more tries on a busy PC below saturation** - decision 0040 keeps them for a saturated PC on purpose;
  - **a longer budget** - not the lab's to change.

## What would make us reverse it

- A first show that is slow only the first time in a process, which the
  later four would hide: the lab's Words states before it show Words
  first, so their pictures and timings would show it.
- The gate still failing on runner noise. Its tries and the PC's load are
  on the run's page.

## How we'd reverse it

Time the first show with `lab.time` again in `tools/ui_lab/pages.py`
(`words_met`), one line; `Lab.time_fresh` can stay or go with its test.
