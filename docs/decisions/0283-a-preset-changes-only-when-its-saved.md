# 0283 A preset changes only when it's saved: Save, Save as new preset, Discard, and Undo

- **Status:** accepted; replaces [0264](0264-presets-hold-the-caption-settings-and-save-every-change.md)'s saving at once (the rest of 0264 stands)
- **Date:** 2026-11-21
- **Preview 3b:** [0290](0290-bar-choices-save-as-they-are-made.md) supersedes the bar rules and keeps explicit saving in Settings > Presets.
- **Decided by:** the user, 2026-11-21 ~10:58, on preview 2's Settings: "Make changing preset options an intentional save rather than an automatic save - something like save preset button here or wherever is most logical." Then: "Or save as new preset." (polyglotic-hq 587's brief; Claude's defaults for the details, for the user to change on the preview)

## Situation

0264 saved every change into the chosen preset at once. On the preview the
user found that wrong: a change made to try something rewrote the preset.
They want the preset to change only when they say so - into the same
preset, or as a new one.

## Decision

- **The settings are the windows'; a preset is what was saved in it.** A
  change applies at once, as before, and leaves the chosen preset
  **edited**: `use_presets.edits` lists the preset settings whose values
  differ from the preset as saved (`values_of`). Nothing is stored for
  "edited" - it's worked out - so it survives a restart with the settings
  file as it is.
- **The steps** (plain Python in `ui.use_presets`, so 585's quick set-up
  can call them): `saved_into` (Save to Learning), `added` (Save as new
  preset…: one of the learner's own from the windows as they are, chosen;
  the one before stays as saved), `discarded` (back to the preset as
  saved), `reset` (a built-in's saved changes out: "Restore Everyday's
  defaults"), `renamed`, `removed`. `chosen` no longer saves the preset
  being left.
- **Undo, not a confirmation:** `before` takes the presets, the chosen one
  and the windows' preset settings before a step that loses something
  (picking another preset with changes not saved, Discard, Restore, Delete);
  `restored` puts them back and leaves every other setting as it is now.
  `main`'s `Panels` keeps it for 8 s and drops it as soon as anything in the
  presets changes after the step.
- **Only a preset's own settings count** (`PRESET_SETTINGS`): the app's
  language, hotkeys, account and the rest are never changes not saved.
  Settings' preset line shows only on the sections that hold them
  (Presets, Look, Word links, Readings, Timing), in its own box under the
  app's language.
- **Naming happens in Settings.** A caption window and its dropdown never
  take the keyboard (a full-screen game minimises when it loses focus), so
  the dropdown's Save as new preset… and Rename… open Settings > Presets
  with the name field ready.
- **Reading a file:** every preset keeps what was saved in it - 556's,
  saved at once, too - and the flat values stay the windows'. A file from
  before an edit to the built-ins (`AppSettings.built_ins`, `BUILT_INS`)
  moves the chosen built-in's untouched values to their new ones
  (`BUILT_IN_BEFORE`): Video's timing, Steady to Instant (585's measure, the
  user's "instant mode is the only usable mode for videos preset").
- **Enforced by:** `tests/ui/test_use_presets.py` (edits don't change the
  preset until saved; save as; switch and Undo; a restart; app-wide
  settings never count; Video's move) and
  `tests/ui_next/test_presets_saved_on_purpose.py` (the chip, the
  dropdown, the line, the notice's Undo, `Panels`).

## Why

- **Working "edited" out rather than storing it** keeps one source of
  truth: the settings file already held the windows' values and each
  preset's saved changes. A stored flag could disagree with both.
- **Undo over a confirmation dialog**: a switch is usually wanted; asking
  every time would get in the way, and Undo costs one click when it wasn't.
- **The Settings line rather than a button on each card**: one place that
  says what isn't saved, beside the sections that change it.

## What would make us reverse it

- Learners lose work: they switch, miss the 8 s Undo, and ask where their
  changes went. Undo's window or a confirmation would change; the usage
  counts (when the server's plan has them) would show discards that
  weren't meant.
- Learners never save, and live in "edited" for weeks: the dot is noise.

## How we'd reverse it

- **Back to saving at once:** `Settings.change` calls
  `use_presets.saved_into` on every change again (one line), and the line,
  the dot and the dropdown's first steps go.
- **A confirmation instead of Undo:** `Panels._losing_step` asks first; the
  domain's steps stay.
- **The built-ins' version** stays: it's how any later change to a
  built-in reaches a learner who never touched it.
