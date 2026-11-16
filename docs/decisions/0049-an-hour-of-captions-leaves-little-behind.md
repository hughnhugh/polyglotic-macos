# 0049 An hour of captions may leave at most 3 MB behind: a memory budget CI holds

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq project 239 (brief item 3: "add a memory-over-time check to `perf/budgets.py` that CI or the lab can run in minutes (a synthetic hour at high speed), so a new leak shows the day it lands"); Claude reviews it with the pull request. The number is new, beside the time budgets the user agreed (DECISIONS.md #53, decision 0031): it changes, like them, in `perf.budgets` with a reason, through the user.

## Situation

223's QA (2026-11-08) ran two apps captioned for an hour with both
transcripts open: the app's private memory grew 247 → 284 MB, about
0.5 MB a minute, and didn't level off. 239 found why: the caption layout
engine kept 2,500 lines' layouts per surface, each about 15 KB of Qt's
memory, so every line a caption window or transcript showed stayed laid
out all evening (fixed in its first pull request). Nothing caught it:
the time budgets judge single actions, and a leak shows only over hours.

## Decision

`perf.budgets.MEMORY_HOUR` (a `MemoryBudget`, in megabytes): an hour of
captions, once the windows and transcripts are full, may grow the app's
private memory by at most **3 MB**.
`tests/ui/test_memory_over_an_evening.py` holds it, in CI on Windows on
every pull request: the interface as `main` builds and wires it,
offscreen, two apps captioned and both transcripts open, the learner's
tools on the sample dictionary; captions with text of their own at 223's
rate (16 a minute, two live updates before each) and a lookup pinned
each minute, fed as fast as the interface takes them. 150 synthetic
minutes fill what is bounded (each transcript's 1,000 lines listed),
then the next 60 are judged. It takes about 9 seconds.

## Why

- **Measured, 2026-11-08, on the user's PC:** with the layouts bounded,
  the judged hour grew 1.0 MB in each of 6 runs (the session's own text,
  kept for Copy all and Save, and little else); with 2,500 layouts per
  surface, as main had it, 33.0 MB. 3 MB is three times today's and a
  tenth of that leak: a layout or a widget kept per caption (about 15 KB,
  14 MB an hour) fails it.
- **Private memory, not tracemalloc:** the leak was Qt's memory, which
  Python's tracer never sees. The process's private bytes see both.
- **Synthetic, not the real app's hour:** the real hour (recorded audio,
  the speech pipeline, a test copy of the server) takes an hour and a
  Docker copy; the synthetic one takes seconds and drives the same
  interface code with the same feed. What it doesn't drive barely grew
  in 239's runs of the real app (recorded audio, the test copy, an hour
  traced by tracemalloc): the speech pipeline, the audio buffers and the
  Opus encoders stayed level (about 0.6, 0.3-0.5 and 0.4 MB); the
  connection's captions are what the transcripts keep; the session's
  summary keeps about 120 bytes a caption until the session ends.
- **An hour after the full ones, not the first:** the first hours fill
  what is meant to fill (the dictionary's first reads, the fonts, 1,000
  lines listed per transcript). Judging them would need a budget wide
  enough to hide a leak.

Not taken: a budget on the evening's total from the start (it would
mostly measure the warm-up); the UI lab as the home (its states are
seconds each, and a memory check needs the minutes of captions in one
process).

## What would make us reverse it

The check failing on changes that keep nothing (noise on a busy runner),
or a real leak in what it doesn't drive - capture, the connection - found
some other way.

## How we'd reverse it

Change `MEMORY_HOUR.mb` with a reason; widen what the test drives (a
replayed capture and `tests/fake_server.py`, as `tests/test_end_to_end.py`
does) if a leak hides outside the interface; or delete the test and the
budget - nothing else depends on them.
