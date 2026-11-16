# 0086 Live updates every stays at 6 s at most while one longest wait serves every timing

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** polyglotic-hq project 295 (the user, 2026-11-11: "0.5-20s
  live updates"); Claude reviews it with the pull request, and the user
  may overrule it. Until D2, the design session on the caption timings,
  settles whether each timing gets its own longest wait (polyglotic-hq
  DECISIONS.md #117).

## Situation

Live updates every was planned as 0.5 to 20 s (polyglotic-hq 248's IA,
section 2.2), the settings accept 0.5 to 20 (`ui/settings.py`,
`LIVE_INTERVALS`), and the Timing panel's line said "from 0.5 to 20
seconds" - but it offered 0.5 to 6 s (`LIVE_CHOICES`). Since 277 one
longest wait for text, 2 to 6 s, applies in every timing:
`CaptionTiming` asks for a live update whenever speech has run that long
since the last one, whatever the interval. So Live updates' text updates
every `min(interval, longest wait)` - an interval longer than the longest
wait is never followed. With the default 3 s, "every 4s" and "every 6s"
already updated every 3 s, unsaid.

295 drove `CaptionTiming` with 25 s of unbroken speech at 8, 10, 15 and
20 s: with any longest wait from 2 to 6 s, every one updates at the
longest wait (every 3 s at the default). Without a longest wait, 8 s
updates at 8 and 16 s, 10 s once, 15 s once, and 20 s never: the
long-speech split (`FINAL_MAX_SEC`, 20 s) finishes the caption first. The
server takes any of them (polyglotic-server `docs/protocol.md`, Limits): a
longer interval sends less speech a minute, and a 20 s section is about
52 kB, under the 256 KiB frame.

## Decision

- Live updates every offers **0.5 to 6 s**, as before; 8 to 20 s are not
  offered while the longest wait (at most 6 s) would always come first.
- The Timing panel says when the longest wait comes first: "Text still
  updates every 3s: the longest wait for text, below, is shorter."
  (`Timing.live_every`), and says the longest wait is "the same in every
  timing".
- Enforced by `tests/ui_next/test_panel_views.py`: every interval offered
  at every longest wait offered updates as often as `live_every` says, in
  `CaptionTiming` itself, and no interval offered is beyond the longest
  wait's range.

## Why

An interval the app never follows is a setting that lies. The ways to
make 8-20 s true - Live updates without the longest wait, a longest wait
of up to 20 s, or a longest wait per timing - change how captions are
timed for every learner and what DECISIONS.md #117 settled until D2, so
they're proposed (polyglotic-hq 295's report), not built.

## What would make us reverse it

D2 deciding that Live updates has no longest wait of its own beyond its
interval, or that each timing has its own; or learners asking for slower
live updates than 6 s.

## How we'd reverse it

Add 8, 10, 15 (and 20, which with today's 20 s long-speech split means no
live updates in unbroken speech) to `LIVE_CHOICES`, and hand
`CaptionTiming` the longest wait D2 decides for Live updates (`main.py`
and `platform/speech_pipeline.py` pass `max_wait` today). The panel's note
and `live_every` follow whatever rule `CaptionTiming` keeps; the test
above says when they don't. Under an hour of code, and an hour of tests.
