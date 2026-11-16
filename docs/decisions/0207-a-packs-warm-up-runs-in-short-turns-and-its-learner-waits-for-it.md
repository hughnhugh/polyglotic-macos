# 0207 A pack's warm-up runs in short turns, and its learner waits for it

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** Claude, for polyglotic-hq project 436 (a reversible technical
  choice; the brief asked for the fix before 0.1.7 ships)

## Situation

When a dictionary pack opens, its word split reads its data on a thread of
its own ("pack warm", decision 0122). For simplemma's Spanish that is about
0.4 s of pure Python. Since 0.1.7, a learned pack language also opens its
learning data, Words section and Learning card at that moment (decision
0175).

Python runs one thread at a time. A thread busy in Python keeps the
interpreter until the switch interval (5 ms) has passed, and the interface
thread asks for it again at every call from Qt into the app's code. So the
interface's work beside the warm-up waited up to 5 ms at each of those
calls, and a pack learner's start froze for 0.44-0.72 s on real windows
(polyglotic-hq 426).

436 pinned the cause:
- With the warm-up left out, the freeze went.
- No thread held the interpreter for more than 40 ms at a time.
- A cProfile showed simplemma's decoding (823,841 calls) as the only
  heavy Python running.

## Decision

- **Its learner waits for it.** A pack language's learning data opens once
  its pack's word split has read its data (`PackDelivery.ready`, said by
  `readied`), not as soon as the pack opens.
- **Opening and showing in separate turns.** What the opening shows (its
  read-ahead, Words section, Learning card and the windows' marks) comes
  in the event loop's next turn after the opening (`show_opened` in
  `main`).
- **The warm-up runs in short turns.** While a pack warms up, the
  interpreter's switch interval is a tenth of Python's own:
  `perf.turns.short_turns`, 0.5 ms. It goes back to what it was once the
  warm-up ends. This covers whatever the interface does in that time,
  such as Learning's rows as the packs open, or a caption.
- **One pack at a time.** The packs warm up one after another on one
  thread. Many reading at once would spend the short turns handing the
  interpreter round: 50 packs took a test from 12 s to 100 s.
- **Close stops the queue.** `PackDelivery.close` drops the reads not yet
  begun.
- **What holds it:**
  - `tests/ui/test_a_pack_learners_start.py`: in a pack learner's start
    from source (the median of 3), no stretch over 100 ms from the packs'
    opening until 2 s after its learning data opened.
  - `tests/conftest.py`: waits for a test's warm-up to end before the
    next test, so that test's timing isn't changed.

## Why

- The read was already off the interface thread. The cost came from
  sharing the interpreter.
- Waiting for the read keeps the heavy opening clear of it. Short turns
  cover the rest, which can't be scheduled around.
- Measured on real windows, with interleaved starts (3 each, Spanish),
  the worst stretch from the packs' opening on was:
  - before the fix: 294-506 ms;
  - with the waiting alone: 79-174 ms;
  - with short turns and one pack at a time too: under 50-66 ms.
  Japanese went from 120-400 ms to 65-93 ms.
- The cost: the pack language's learning data opens 0.44-0.65 s after its
  pack, not at once. Its words are counted from then. Its lookups work
  from the pack's opening, as before.
- Not taken:
  - Reading the pack's data in another process: much more code for half
    a second once per start.
  - Not warming at all: the first Spanish caption would then read it on
    whichever thread asked, the interface's included.
  - Starting the warm-up later instead of making its turns short: it
    still met whatever else the start was doing (78-496 ms, 5 starts).
  - A short interval for the whole run: more switching all the time, for
    a cost that lasts a second.

## What would make us reverse it

- Python without the GIL (free-threaded builds), or a word split whose
  read lets the interpreter go (a native one). Then the switch interval
  doesn't matter.
- The watchdog or other timing misreading during a warm-up on testers'
  PCs. The watchdog's own tests missed a slow slot when a test's warm-up
  ran into them, which is why `tests/conftest.py` now waits.

## How we'd reverse it

- Remove `short_turns` from `PackDelivery._warm_each` and delete
  `perf/turns.py`.
- Open pack languages on `packs.changed` again, with
  `packs_beside(languages, basic)` in `open_added`.

That is about an hour. The start test would then fail as it did before.
