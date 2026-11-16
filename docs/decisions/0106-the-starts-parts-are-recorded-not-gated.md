# 0106 The start's parts are recorded beside main's, not gated

- **Status:** accepted (reversible; adds to decisions 0046 and 0103)
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 314 (brief: "a guard that records the start's parts ... so the next 15 ms added shows up as a named part growing"). Claude reviews it with the pull request. No budget changes: `START_FROM_SOURCE` stays 400 ms (the user's, decision 0031).

## Situation

The start gate (decision 0046) says one number: the time from `main()` to
the window. When it failed on 2026-11-13 nobody could say from the run
which part had grown, or whether any had: 312 needed 122 starts to show it
was the PC's load. 314 measured the parts by hand (the learner's tools
about 135 ms, the pages about 120, the first paint about 27) and found the
start had lost its margin a few milliseconds at a time.

## Decision

- **The app marks its own parts.** `perf.start_parts`: `main`, `new_interface` and `Hub` call `done("name")` where each part ends, so the parts add up to the whole start. Always on (about fifteen clock reads); names only, checked like a span's.
- **The timed start reports them** (`TimedStart.parts`), and the start test prints the median of each in pytest's summary and on the run's page, pass or fail.
- **Main's last record is kept on the runners' PC** (`tools/start_record.py`: `%PROGRAMDATA%\polyglotic-ci\start-parts-main-<account>.json`, written only by CI's run of a push to main). A pull request's run prints each part beside it.
- **Grew, at this load:** main's parts are scaled by how the whole start compares, and a part 8 ms or more over its scaled share is marked `GREW`. A busier PC marks nothing; 15 ms added to one part is marked as about 14.
- **Recorded, not gated.** The budget is the gate. A mark is for the reviewer to read.

## Why

- **Not a gate per part:** the parts are 1-130 ms and move by several milliseconds between runs on a shared PC; a gate on each would fail by chance or be set too loose to mean anything.
- **Not the trace file:** the spans are off unless asked for, and the start's parts must be there on every run.
- **A file on the PC, not in the repo or an artifact:** the record is this PC's timing and only means something beside another run on the same PC. Both runners' accounts can read that folder (as CI's lock).
- **Scaling by the whole start** hides a change that slows every part alike. The gate's own number and decision 0103's verdict cover that.

## What would make us reverse it

Marks that mislead - `GREW` on pull requests that didn't touch the part, or
none on one that did - or the runners moving off one PC.

## How we'd reverse it

Drop `tools/start_record.py` and the note in the start test (an hour); the
marks in `main` can stay or go with them. To gate instead: compare in the
test and fail - a few lines, once the numbers have proved steady.
