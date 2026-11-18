# 0233 The start holds the garbage collector off until the window paints

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** Claude, within polyglotic-hq project 509's job: train B
  (#898) put the start with 30,000 words met over its 400 ms budget, and
  the fix was to make what it added lazy, not to raise the budget. This is
  a reversible technical choice (polyglotic-hq CLAUDE.md, "Rhythm").

## Situation

The start's budget, from `main()` to the main window's first paint, is
400 ms on the main PC (`perf.budgets.START_FROM_SOURCE`). Train B measured
427.6 / 430.2 ms in CI's UI lab against main's 330.

Python's garbage collector runs a collection after enough new objects
have been made. Each run goes through the objects of its generation and
the younger ones. The start makes tens of thousands of objects (a learner
with 30,000 words met makes two each), so collections run during the
start. A full collection also goes through everything the imports made,
and train B's new code made that larger.

Measured on the second PC (Ryzen 5 5600X), 5 starts of each kind,
interleaved, 2026-11-18:

| Start | Collector on (today) | `gc.freeze()` first | Collector off |
|---|---|---|---|
| main | 498 ms | 484 | 472 |
| train B | 561 ms | 549 | 529 |

Of the 33 ms train B added to the learner's part of the start, 19 were
collections.

## Decision

- `main()` turns the collector off as it begins and back on once the
  window has painted (`_start_and_run` calls `shown()` right after
  `start_parts.end()`).
- It's on again whichever way the start ends: a second copy's exit, a
  check's `sys.exit`, an exception (`try`/`finally`).
- A collector already off when `main()` is called stays off. Whoever
  turned it off turns it back on.
- Enforced by `tests/test_start_without_collections.py`.

## Why

- Nothing in the start needs memory back before the window shows. What
  wasn't collected meanwhile is collected at the first collection after
  the paint: one pass, in the time that already holds the stall while the
  connection's libraries load.
- It's the largest single saving left in the start on a mid-range PC
  (26-32 ms) that doesn't move work past what the budget measures. The
  first answer to a click comes no later, because the collection after the
  paint is no longer than those it replaces.

**Not taken:**
- `gc.freeze()` at the start. It saves less (12-14 ms). Objects frozen
  are never collected, which in a test run would keep earlier tests'
  garbage alive.
- Raising the collector's thresholds for the whole run. That would trade
  pauses during captions for the start; the frame and caption budgets
  matter more there.

## What would make us reverse it

- The memory taken during the start growing enough to matter: the start
  with 30,000 words met holding hundreds of MB before its first paint.
- A pause from the first collection after the paint showing up as a
  stall the watchdog logs at most starts (over the 50 ms slot).

## How we'd reverse it

Make `main` call `_start_and_run` with a `shown` that does nothing, and
remove the two `gc` calls: one function.
