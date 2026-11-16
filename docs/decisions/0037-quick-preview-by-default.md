# 0037 Quick preview is the default, and the app keeps only a mode the learner chose

- **Status:** accepted; replaces the default in [0024](0024-caption-modes.md); its default replaced by [0055](0055-steady-is-the-default-again.md) (2026-11-09: Steady again)
- **Date:** 2026-11-08
- **Decided by:** the user made Quick preview Plus's default
  (polyglotic-hq DECISIONS.md #4, 2026-11-07 ~23:36: "Yes make quick
  preview plus's default"); polyglotic-hq project 176 built it; Claude
  reviews

## Situation

0024 made Steady the default and kept the mode followed in
`caption_timing`. Every save writes every setting, so a file holding
`steady` can't say whether the learner chose Steady or never chose.
The default now moves to Quick preview, Free stays on Steady once Free
exists (S1b/D1), and project 183 may recommend a smarter preview (a
preview only when talk starts after silence, then Steady). Each of those
changes the default again; none should move a learner who chose.

## Decision

- `core.listening.timing.default_caption_mode()` is the one place the
  default is decided: Quick preview.
- The settings keep the mode the learner **chose**,
  `caption_mode_chosen` - None until they choose one in a Timing panel
  or a caption window. `AppSettings.caption_mode` is the choice, or the
  default. A change of default moves everyone who hasn't chosen, and no
  one who has.
- Settings saved before this version: `caption_timing` of Quick preview
  or Live updates was a choice and stays; Steady (the old default) and
  anything not valid follow today's default. Settings from before there
  were modes keep 0024's reading of their interval, except that "Off"
  (finished captions only) is now a choice of Steady, the nearest mode.
- Every save also writes `caption_timing`, the mode followed, so an older
  version run afterwards follows the same mode (polyglotic-hq
  RELEASING.md section 5).

## Why

- A choice and a default are different facts; keeping only the mode
  followed made the next default change impossible to apply fairly.
- A new key is the version mark: a file with `caption_mode_chosen` was
  written by this version, so its `steady` is a choice; one without it
  wasn't. Not taken: a `caption_timing_chosen` flag beside the old key
  (two fields that must agree), or a settings version number (a general
  mechanism with one use).
- A learner who chose Steady in an earlier version can't be told apart
  from one who never chose; they move to Quick preview. Before the alpha
  that's only the user's own installs.

## What would make us reverse it

The alpha's `caption_mode` statistics or 183's numbers show Quick
preview's GPU cost (1.5-1.7x Steady's, project 021) isn't paid for by
learners keeping it; or the timing moves to the server (protocol v2).

## How we'd reverse it

Change `default_caption_mode()`: everyone who hasn't chosen follows at
their next start. A smarter preview is a new `CaptionMode` (or a
schedule in `_MODE_RULES`) returned there. Moving timing to the server
sends `caption_mode` (chosen or default) in the session's settings.
