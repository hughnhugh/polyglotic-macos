# 0253 Follow, Acquisition, Both: what is read first is one setting

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude asked for it to be built on polyglotic-hq
  DECISIONS #230's recommendation (item 6: "Follow / Acquisition / Both as
  one setting, Both the default"), reversibly, before the user's formal
  answer (526's brief, Phase 2).

## Situation

A learner uses captions two ways: to follow what is going on (the
translation matters, now), and to acquire the language (what was said
matters first; the translation is the check). The window showed both
lines together for everyone. 526's `paths-*` videos showed the three as
one choice.

## Decision

One setting, in Settings > Timing, for the paced modes
(`core.listening.playout.ReadingPath`; `caption_path` in the settings):

- **Both** (the default): a clause's translation comes as the clause
  ends, as before.
- **Acquisition:** what was said first. A clause's translation and word
  links are held back `translation_after` seconds (2 s unless the learner
  chooses 1, 2, 3 or 5) after its last word is shown
  (`PlayoutRules.translation_after`; the playout gives the caption
  without them, then with). Nothing is translated live
  (`translate_live` off): each clause's translation is the finished
  caption's, so the translator does about a quarter of the work
  (526's `translating-time.md`).
- **Follow:** the translation leads. What was said is drawn smaller and
  fainter, the translation larger and in full ink
  (`CaptionWindow.path_style`, `follows`). Only where there is a
  translation and what was said is shown.

The other modes are unchanged.

## Why

In the playout, because that is where a paced mode already decides when a
clause's translation shows; the windows draw what they are given. One
setting, because the three are one question to the learner.

## Not done here (the next stack)

- **Acquisition's reveal:** linked words lighting in both lines as the
  translation arrives, then going back (the marks are drawn by the
  learner's Word links setting as before).
- **The banded glosses** (DECISIONS #230 item 8).
- **Follow's order:** the translation above what was said; the one
  layout has no such order yet, so Follow changes size and ink only.
- **The server's per-clause translation** (item 7), which Both and
  Follow would use.

## What would make us reverse it

The user, after the preview build, wanting the paths as separate
settings, or Acquisition's delay to be by line rather than by clause.

## How we'd reverse it

The Timing panel's two rows removed; `caption_path` read as "both".
