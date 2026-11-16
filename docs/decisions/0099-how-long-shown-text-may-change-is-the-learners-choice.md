# 0099 How long shown text may still change is the learner's choice, 0 to 3 seconds

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user (polyglotic-hq project 309, 2026-11-14: "I
  feel like changing lines up to 3 seconds in live updates is a bit too
  long anyway, make this a configurable setting. After 0s - 3seconds");
  Claude reviews it with the pull request. Amends
  [0088](0088-shown-text-settles.md), which fixed the time at 3 s.

## Situation

Decision 0088 settles a caption's words once they have stood unchanged
for 3 s: a later hearing of the same speech (the next live update, the
finished caption, a join) no longer rewrites them. The user finds 3 s of
possible rewriting too long to read under, and asked to choose.

A shorter time has a price. The later hearing has heard more speech, so
it is the better one; settling a word sooner throws away more of its
corrections.

## Decision

- **One setting, `text_settles_after`, 0 to 3 seconds, default 3**
  (`core.listening.settling.SETTLE_RANGE`): Settings > Captions > Timing,
  "Text can still change for", offering 0, 1, 2 and 3 s. It applies in
  every timing.
- **Each caption history holds the time** (`CaptionHistory.set_settle_after`)
  and uses it where it used the constant. Every place captions are kept
  follows the setting: each caption window, each transcript and the
  app's own feed (`main.follow_settings`, `Transcripts.follow`).
- **Everything else in 0088 stands:** clauses above a caption's last two
  are settled whatever the time; settled rows keep their translation;
  a word is never cut in half.
- **At 0 a word stays as first shown, with one exception:** the last
  word of a live caption, which may be half said ("th" for "this"), is
  still the update's. Freezing it would keep half-words on screen.
- A change applies from the next update on; nothing shown is rewritten
  by choosing.
- Enforced by `tests/test_caption_history.py` (the time chosen; 0; the
  range), `tests/ui/test_caption_modes.py` (stored and read leniently),
  `tests/ui/test_everything_else.py` (every history follows) and
  `tests/ui_next/test_panels.py` (the control).

## What each time costs (measured 2026-11-14)

Recordings of public read speech (FLEURS, five minutes each language)
made through the app's own speech detection and timing on the real
models by polyglotic-hq 301 and 307, replayed through `CaptionHistory`
at each time (`polyglotic-hq/projects/309-.../work/analyse309.py`).
"Left wrong": words wrong in the final text that the updates as sent
would have corrected, per 100 words spoken (701 English words, 811
Mandarin characters). "Changed on screen": words rewritten after being
shown, in the five minutes.

| Recording | 3 s | 2 s | 1 s | 0 s |
|---|---|---|---|---|
| Live updates every 1.5 s, English (301) - left wrong | 0.0 | 0.0 | 0.7 | 0.7 |
| ... changed on screen (8 as sent) | 8 | 8 | 4 | 4 |
| Live updates every 1.5 s, English (307) - left wrong | 0.4 | 0.6 | 1.4 | 1.4 |
| ... changed on screen (15 as sent) | 11 | 9 | 4 | 4 |
| Live updates every 1.5 s, Mandarin (301) - left wrong | 0.0 | 0.0 | 0.4 | 0.5 |
| ... changed on screen (9 as sent) | 9 | 8 | 3 | 3 |
| Live updates every 1.5 s, Mandarin (307) - left wrong | -0.1 | 0.0 | 0.7 | 0.7 |
| ... changed on screen (13 as sent) | 12 | 11 | 3 | 3 |
| Live updates every 0.75 s, English (307) - left wrong | 0.7 | 1.6 | 2.6 | 7.3 |
| ... changed on screen (92 as sent) | 87 | 80 | 70 | 27 |
| Live updates every 0.75 s, Mandarin (307) - left wrong | -0.1 | 0.0 | 0.5 | 3.2 |
| ... changed on screen (51 as sent) | 51 | 47 | 40 | 15 |
| Steady, English (301) - left wrong | 0.1 | 0.1 | 0.1 | 0.1 |
| Steady, Mandarin (301) - left wrong | -0.1 | -0.1 | 0.0 | 0.1 |

Read plainly:

- **2 s costs little** at the default interval (0 to 0.6 words in 100)
  and removes little: most rewriting is of words under 2 s old.
- **1 s** leaves 0.4 to 1.4 more words in 100 wrong at the default
  interval and there halves or better what changes on screen (with
  updates every 0.75 s: 0.5 to 2.6 more wrong, a fifth less changing).
- **0 s** is much the same as 1 s when live updates come every 1.5 s
  (a word has nearly always stood a second by the next update), but
  with updates
  every 0.75 s it leaves 3 to 7 more words in 100 wrong: the first
  hearing of each word, on under a second of speech, is kept.
- **Steady** is barely touched at any time: it shows finished captions.
- What still changes at 0 s is the last word of a live caption.

One five-minute sample of read speech per language and interval, not a
claim: conversation and film speech weren't measured, and the real
models weren't run again for this (the recordings were replayed).

The setting's own line says the cost in words, with no figure: "Shorter:
fewer words change while you read, and more mistakes stay as first
heard - most of all when Live updates come faster than every second."
(polyglotic-hq 330, 2026-11-14. It first said "1 to 3 more wrong words
in 100 at 1s, and up to 7 at 0s when Live updates come faster than every
second"; 329's QA found that an accuracy figure no claims check has
cleared - RELEASE-NOTES.md's rule - so the figures stay here, with where
they came from, and not in the app.)

The row shows in every timing, Steady too: Steady's dim line at the
longest wait for text, and a short caption joined to the next, are heard
again and rewritten, and the setting decides how much of them stays. The
replays above barely moved there (0.0 to 0.2 words in 100 between 3 s and
0 s, on read speech), yet hiding the row would leave a choice made in
Live updates acting unseen in Steady.

## Why

- The user asked for it, and the right time is a matter of taste the
  alpha can settle: reading comfort against accuracy.
- The default stays 3 s: nothing changes for anyone who doesn't choose.
- Offered as whole seconds: each is measured above; a value set by hand
  in the settings file (0.5, 2.5) is followed and shown as itself.
- Not taken: a per-window time (one more thing to keep in step; nobody
  asked). Not taken: a Lab control - the user asked for a setting, and
  it changes what is kept, not how it looks.
- Not taken: 0 freezing the half-said last word too (above).

## What would make us reverse it

The alpha's testers settling on one value: then it becomes the fixed
time again (0088's constant) and the control goes. Or learners at 0 s
reporting wrong words more than they valued the stillness.

## How we'd reverse it

Remove the row from `TimingPanel`, the `settle_after` field from
`Timing`, and `text_settles_after` from `AppSettings` (a stored value is
then ignored); set `SETTLE_AFTER_SEC` to the value chosen. A few lines
and their tests.
