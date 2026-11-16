# 0046 CI holds the start to its budget with a made-up learner of 30,000 words met

- **Status:** accepted (a default, reversible: polyglotic-hq project 229's report asks Claude whether 30,000 or 10,000 words met)
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq project 229, from 220's finding that the start grew with the words met and nothing noticed. Claude reviews it with the pull request.

## Situation

The start's budget (`perf.budgets.START_FROM_SOURCE`, 500 ms from `main()`
to the window's first paint, from source; DECISIONS.md #53) was held only by
`--check-install`, which starts with an empty learner. The start's work grows
with the learner's words met: at 30,000 it took 541-566 ms on 2026-11-08
until #339 (220), and nothing in CI noticed.

## Decision

CI's UI lab job builds the real CC-CEDICT from its pinned sources
(`python -m tools.dictionaries.build --only cedict`, the sources cached) and
runs `tests/ui/test_start_with_a_big_learner.py`: `main()` from source,
offscreen, on a made-up learner of 30,000 words met
(`tools/learner_start.py`), in a process of its own per start, timed to the
window's first paint. A try is 5 starts; their median is held to the 500 ms
budget, and a try over is taken again as every budget test's is
(`tests/budget_judge.py`, decision 0040). The learner is made up from the
dictionary, never a real learner's file. Without the real dictionary (the
main suite, a developer's PC) the gate is skipped.

## Why

- **30,000, not the 10,000 220 proposed:** with #339 undone, the start at
  10,000 words met measured 406-565 ms on 2026-11-08 - often within 500 ms,
  so a gate there wouldn't keep #339's gain. At 30,000 it was 638-906 ms,
  and 276-381 ms with #339 but for one start in 50: the gate fails the
  first and passes the second with room for a busy runner. The start only
  grows with the words met, so a start within the budget at 30,000 is
  within it at 10,000.
- **The real CC-CEDICT, not the tests' sample:** the sample has 30 entries;
  the work that grew is per word met, looked up in the real file.
- **In the UI lab job:** where the interface's budgets already gate, and
  the shorter of the two Windows jobs (about 1.5 minutes against 3.6).
- **The median of 5 starts, not every start:** the budget means a typical
  start. On the user's PC, shared with other agents, 1 of 50 starts at
  30,000 words met took over 500 ms (511; the rest 276-381 ms, CI's runner
  included), so holding every start would fail about one pull request in
  100 for nothing. Undoing #339 put every start over (638-906 ms): the
  median catches it.
- **The budget itself, unchanged:** the user's call (decision 0031).
- Not taken: a tighter threshold at 10,000 (a new budget, the user's call);
  holding the learner's added cost against an empty learner's start (also a
  new number).

## What would make us reverse it

- The gate failing on code that is fine - the runner's noise, not the start
  (its tries on the run page say how busy the PC was).
- Work at the start that is right to grow with the words met and is fine at
  realistic sizes but over at 30,000: then 30,000 is the wrong size.
- The job's time growing past what the runner can carry.

## How we'd reverse it

Change `WORDS` in the test (10,000 is a one-line change) or remove the three
steps from `ci.yml`'s UI lab job; `tools/learner_start.py` stays as the tool
for measuring a start by hand.
