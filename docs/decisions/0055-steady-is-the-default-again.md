# 0055 Steady is the default again, for everyone who hasn't chosen

- **Status:** default replaced by [0242](0242-quick-preview-is-the-default-again.md) (2026-11-18); replaced the default in [0037](0037-quick-preview-by-default.md) (its "a choice stays" rule is kept)
- **Date:** 2026-11-09
- **Decided by:** the user, after using the app on the real models
  (polyglotic-hq DECISIONS.md #107, 2026-11-09 ~01:58: "Okay go ahead");
  polyglotic-hq project 260 built it; Claude reviews

## Situation

0037 made Quick preview the default (DECISIONS.md #4, 2026-11-07). On
2026-11-09 the user used the app on the real models and said "why does it
feel slow" (F32), liked "the mode where there is a loading bar whilst
there is speech being recorded / processed" (F33: Steady's listening
mark) and saw Quick preview "not do anything for an extended period of
time and then suddenly update all of the speech at once" (F34: its one
glimpse, then nothing until a pause or a breath cut).

## Decision

- `core.listening.timing.default_caption_mode()` returns Steady. It is
  still the one place the default is decided.
- 0037's rule stands: the settings keep only the mode the learner
  **chose** (`caption_mode_chosen`). A learner who chose Quick preview or
  Live updates keeps it; one who never chose - including every install
  that followed Quick preview as the default since 0037 - is on Steady
  from their next start.
- Help says when captions appear in each mode, the default first; Home's
  Timing panel lists Steady first (as before).

## Why

- Steady shows each sentence once, finished and translated, with the
  listening mark while it's on its way: the wait reads as "coming", and
  nothing on screen is rewritten. It is also the least GPU work (Quick
  preview is about 1.4-1.7x, polyglotic-hq projects 021 and 033).
- Not taken: Steady for new installs only. Learners who never chose
  didn't pick Quick preview; moving them keeps one rule ("the default
  moves everyone who hasn't chosen"), and before the alpha they are the
  user's own installs.

## What would make us reverse it

The alpha's `caption_mode` statistics show most learners switching to
Quick preview, or the user finds Steady's first words (about 4.5-5.5 s
after the speaker starts, project 145) too late once the listening mark
shows in every mode (project 260) and 243's phase 2 has tuned the breath
cut.

## How we'd reverse it

Return another mode from `default_caption_mode()`: everyone who hasn't
chosen follows at their next start, as here. The Help topic "When do
captions appear?" names the default first and changes with it.
