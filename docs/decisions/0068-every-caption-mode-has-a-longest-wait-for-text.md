# 0068 Every caption mode has a longest wait for text

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** the user, 2026-11-11 ~02:40 ("I just don't want these
  super long extended monologues causing the captioning to completely
  stop ... Probably max 3s or something before displaying current
  text"), built by Claude for polyglotic-hq project 277. How it's done is
  a reversible technical choice.

## Situation

Each caption mode had its own schedule, and nothing bounded how long
speech could run with nothing new on screen. Steady showed nothing until
a breath after 3 s or the cut at 6 s (its first words at a median 4.4 s
on stand-ins; up to 6.2 s without text in 268's simulation). Quick
preview's growing schedule left 3 s between its 3 s line and the cut,
whatever the learner wanted; Live updates waited as long as the interval
the learner chose (up to 20 s).

## Decision

- **One rule over every mode:** `CaptionTiming.max_wait` - speech never
  runs longer than this many seconds, since its caption started or its
  last live update, without a live update asked for. 3 s unless the
  learner chooses (`max_wait_for_text`, 2 to 6 s; saved, followed from
  the next frame, no restart).
- **It's a floor under each schedule, not a schedule of its own:** a
  live update is due when the mode's schedule says so *or* the wait has
  passed (`_live_update`). Steady has no schedule, so the wait's are its
  only live updates - nothing sooner than the wait, so it stays the
  calmest mode. Quick preview and Live updates keep their schedules and
  get an extra update only where a gap would pass the wait (Quick
  preview at a wait under 3 s; Live updates at an interval longer than
  the wait).
- **Steady's lines look like Quick preview's:** translated, dim and
  italic, replaced by the finished caption (`CaptionMode.provisional_lines`
  decides both `translate_live` and the look's `preview`).
- **The server's pace hint stretches it** (`paced_max_wait`), as it
  stretches every live update: a busy server is protected first.
  Finished captions never wait.
- The breath cut (3 s, 0.3 s pause, 6 s limit) and everything else in
  the modes' rules stay as they were.

## Why

- A floor keeps each mode's character - its schedule and its look -
  and changes nothing where the schedule already meets the wait. One
  number to explain, one place it's enforced, one test over every mode.
- Alternatives not taken: a shorter breath cut for Steady (more finished
  captions, each heard once - but cuts mid-sentence at 3 s and hurts
  accuracy, which 021's check at the 6 s cut hasn't settled); a new
  "growing" schedule for Steady (a second schedule to keep in step with
  the wait); clamping the Live updates interval to the wait in settings
  (the interval control is 273's to change, and the rule does the same).
- The cost is speech heard again: the simulation in polyglotic-hq 277's
  report gives it per mode.

## What would make us reverse it

- The real models or the friends' sessions show the extra lines in
  Steady cost more card than they're worth, or learners find the dim
  line in Steady distracting.
- The server takes over live-update timing (protocol version 2): the rule
  moves there with the rest of `timing.py`.

## How we'd reverse it

Construct `CaptionTiming` with `max_wait=None` (the proof of concept's
behaviour, and still the class's default) - one line in `main`. The
setting can stay stored and unread; `provisional_lines` back to Quick
preview only puts Steady's look and `translate_live` back.
