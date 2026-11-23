# 0084 The app's own text size multiplies Windows', and never touches the captions

- **Status:** accepted; its steps (0.9, 1.0, 1.2, 1.45) and Normal's place replaced by [0244](0244-the-apps-text-is-larger-by-default.md) (2026-11-20)
- **Date:** 2026-11-12
- **Decided by:** the user asked for it ("yes make it a setting, just a
  general remark", 2026-11-11 ~23:20, after testers said they couldn't
  read the app's text and explanations); built in polyglotic-hq project
  292

## Situation

The new interface sizes all its text through one factor, `style.px()`,
read from Windows' Text size (135's proposal A, decision 0031's
per-window stylesheets). Testers found the app's own text - Settings'
notes, a word's card's meanings and example, Help - too small to read,
and most won't find or change Windows' Text size, which resizes every
program. Captions already have their own size on each caption window
(A- / A+).

## Decision

Settings > App > **Text size**: Smaller, Normal, Larger, Largest
(`style.APP_TEXT_SIZES`: 0.9, 1.0, 1.2, 1.45), saved as `app_text_size`
("normal" when missing or unknown, so older settings read as Normal).

- **One factor.** `style.text_scale()` is Windows' Text size times the
  app's own, at most 2.25 (Windows' own largest, the range the interface
  was laid out and tested for: at Windows' 200 % and Largest, 2.9, the UI
  lab found the App language picker's text and a caption window's
  notices cut off). Everything already sized by `px()` follows it, and
  Qt's own parts take the app's share of it. Windows' part is still read
  from the system font as before (`windows_text_scale()` is what a
  Windows change is compared with).
- **Never under 12 px.** At Smaller, `px()` shrinks nothing already under
  12 px and takes nothing under it - the UI lab's `small_text` floor.
- **Captions are not touched:** their size is the caption window's own,
  and a transcript's lines are the transcript's own (each has A- / A+).
  Their chrome (the band, notices, the settings popover, the transcript's
  bar) follows the app's size, as it follows Windows'. The setting's own
  words say so.
- **At once, no restart.** `main` applies the setting before the first
  window (the first run's screens included). A change in Settings goes
  through `MainWindow.set_app_text_size`, which restyles the main window
  and emits `text_size_changed` - the signal a Windows change already
  used - so the transcripts, the caption windows' chrome, the logo and
  Qt's own parts (`style.size_qt_parts`: the tray's menu and submenus,
  tooltips with no stylesheet over them) follow.
- **Qt's own parts** take Windows' fonts as Qt has them, sized each time
  from those, so a change is never applied twice. The application's font
  is never set: Windows' Text size is still read from it.

Enforced by tests (`tests/ui_next/test_app_text_size.py`) and the UI lab:
CI runs every state at Largest (`--app-text-size largest`) with the code
checks - clipped text above all - and `text_sizes`' states show the main
surfaces at Smaller (built at it) and at Largest (switched while open).

## Why

- Multiplying keeps both choices meaningful: someone with Windows at
  150 % who picks Larger gets more, not a reset to 120 %. Replacing
  Windows' factor would ignore an accessibility setting the learner (or
  their PC's owner) made on purpose.
- Steps, not a slider: four choices a learner can see at a glance; each
  is about 1.2 times the last, which reads as an even step. Largest is the
  biggest step at which the main window's minimum (960 x 680 x 1.45 =
  1392 x 986) still fits a 1080p screen's work area at 100 % without being
  kept to the screen.
- Not the application font: setting it would stop Qt updating it from
  Windows, so Windows' Text size could no longer be read the way it is
  now, and every widget in the app would be restyled on a change - what
  decision 0031 moved away from.
- Not a zoom per window, and not the font family: out of 292's scope.

## What would make us reverse it

- Learners want a size between the steps, or larger than Largest: a
  slider, or more steps.
- Learners expect the captions to follow it too: then the two sizes would
  have to be designed together (they are deliberately separate now).
- Qt starts scaling the interface itself in a way that fights `px()`.

## How we'd reverse it

The steps are one dict in `style`; more steps or a slider change it, the
settings check and the Settings row. Dropping the setting: remove
`app_text_size`, `use_app_text_size` and the row - `text_scale()` falls
back to Windows' alone, and stored values are kept for older versions by
`Settings`' unknown keys. About an hour either way.
