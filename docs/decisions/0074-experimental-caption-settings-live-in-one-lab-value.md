# 0074 Experimental caption settings live in one Lab value

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** Claude, for polyglotic-hq project 284 (the user's batch
  C, agreed 2026-11-11 ~01:45: "one lab section in Settings > Captions,
  every control live"). A reversible technical choice.

## Situation

The user and the alpha's testers want to tune how captions look and
arrive by feel - how long new captions stay bright, how dim older ones
get, spacing, the loading sign - and then keep what works and drop what
doesn't ("If there are things that are obviously bad, we can remove them
later from the real app", 270's FEEDBACK.md). Each such control added as
a setting of its own would spread over `AppSettings`, `CaptionLook`,
`main`'s two mappings and the panels, and taking one out later would
touch all of them.

## Decision

- Every experimental caption setting is a field of one frozen value,
  `ui_next.views.lab.CaptionLab`, held in the shared look
  (`CaptionLook.lab`) - so every caption window and the previews follow
  it as they follow the look, at once, with no restart.
- It's saved as one setting, `caption_lab`: a map of only the fields
  moved from their defaults, each read leniently (missing, wrong type or
  out of its measured range: the default). An untouched lab stores `{}`,
  so a later default reaches everyone who didn't move it.
- Its controls are one card, `lab_panel.LabPanel`, last in Settings >
  Captions, titled as experimental, with its own preview and "Reset the
  lab". "Reset the look" leaves the lab alone, and the lab's reset
  leaves the look alone.
- Each slider's ends are measured, not guessed; `views.lab` says how.

## Why

- One field to add, one to remove: a control that graduates moves out
  into the look proper; one that's dropped is a field and its control.
- Storing only what was moved keeps an untouched install on whatever the
  defaults are, and an older app reading the file ignores the key
  (settings keep keys they don't know).
- Alternatives not taken: a setting per control (spreads, as above); a
  feature flag per control (flags are for rollouts, not for the learner
  to tune - ENGINEERING.md's flags); a separate "advanced" window (the
  user asked for the controls beside the caption settings).

## What would make us reverse it

- The lab grows past what one card can hold readably, or a control needs
  per-window values (the lab is the session's, like the look).
- The alpha settles what works: then the kept controls move into the
  look's own settings and the lab shrinks or goes.

## How we'd reverse it

Move a field from `CaptionLab` to `CaptionLook` (and its key into
`AppSettings`, reading the old `caption_lab` value once), or delete the
field and its control - `from_stored` ignores keys it doesn't know, so a
saved value for a removed control is simply dropped.
