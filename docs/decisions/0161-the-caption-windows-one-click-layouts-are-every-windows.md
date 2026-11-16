# 0161 A caption window's one-click layouts are every window's, and the Lab's values

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude (polyglotic-hq project 372), on the user's request
  of 2026-11-15 (polyglotic-hq DECISIONS.md #175: "upgrade it as a one
  click setting ... from caption window"); the user tries it in a preview
  before release

## Situation

The user asked for one click on the caption window that turns on, together,
New layout, Line by line and Captions run on ("Fill the width"), and later
"Parts lined up" as a one click of its own. Those are the Lab's values
(`views.lab.CaptionLab`), kept in the look every caption window shares
(`CaptionLook.lab`) and saved as one setting. The brief asked whether the
click should be per window ("as a window's look") or for all windows, and
required one state, not two, with the Lab's rows.

## Decision

- The strip's layout buttons change the Lab's values, for every window,
  as the strip's Word links button changes Look's (249's F9). There is no
  per-window copy: the button shows `CaptionLab.filled`, a property of the
  values, so the button, every other window's and the Lab's rows can't
  disagree.
- Off puts back what the one click changed (`CaptionLab.with_filled`): the
  values before it, kept by `LookView` while the app runs; unknown (turned
  on in the Lab, or after a restart), the app's own without the Lab.
- Enforced by tests: `tests/ui_next/test_fill_in_one_click.py`.

## Why

- **One state.** A per-window override would be a second value beside the
  Lab's, and the Lab (in Settings, with no window of its own) could show
  only one of them. The brief's "one state, not two" rules it out unless
  the Lab's layout values move into each window's choices.
- **The precedent.** The strip already holds one every-window switch (Word
  links); the tooltip says "in every window" for both.
- **The layout's cost is per surface already.** A window measures and lays
  out its own captions; nothing about one shared value makes a window
  slower.
- Not taken: per window (`WindowChoices.fill`), kept for if the user asks
  for different layouts per app (a game's window filled, a call's in
  rows). It would also need a joined window's columns to agree.

## What would make us reverse it

The user, or testers, wanting one app's window filled and another's in
clause rows at the same time.

## How we'd reverse it

Move `flow`, `fill`, `run_on` and `aligned` from `CaptionLab` into
`WindowChoices` (saved per window, with the Lab's values as each new
window's default), make `caption_style` read them from the window, and
make the Lab set every window's. About a day, with the settings migration.
