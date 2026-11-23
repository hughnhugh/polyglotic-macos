# 0244 The app's text is larger by default: every text size step shifted up

- **Status:** accepted; replaces the steps in [0084](0084-the-apps-own-text-size-multiplies-windows.md) (the rest of it stands)
- **Date:** 2026-11-20
- **Decided by:** the user (polyglotic-hq 524's brief, 2026-11-19 ~05:00:
  "next release make larger or largest the default app text size. then
  shift the scale again. essentially normal should be between larger to
  largest"); polyglotic-hq 524 built it and chose the factors; Claude
  reviews

## Situation

0084 gave the app its own text size, on top of Windows' Text size:
Smaller, Normal, Larger, Largest (0.9, 1.0, 1.2, 1.45), Normal the
default and the interface as it had been. Testers still found the app's
text small at Normal. The user wants the default between Larger and
Largest, and the whole scale moved with it, so Smaller is still a step
down and Largest a step up.

## Decision

- **The steps** (`style.APP_TEXT_SIZES`), the base 13 px text on each:

  | Step | 0.1.9 | Now | Base text |
  |---|---|---|---|
  | Smaller | 0.9 (12 px) | **1.0** - 0.1.9's Normal | 13 px |
  | Normal (the default) | 1.0 (13 px) | **1.3** - between 0.1.9's Larger and Largest | 17 px |
  | Larger | 1.2 (16 px) | **1.45** - 0.1.9's Largest | 19 px |
  | Largest | 1.45 (19 px) | **1.75** - new | 23 px |

  The names, the Settings row and `style.text_scale()` (Windows' times the
  app's, at most 2.25) are as 0084 has them. Nothing goes under 1.0, so
  `SMALLEST_PX` only guards now: no step shrinks the interface's design
  sizes.
- **Largest fits a 1366 x 768 laptop at Windows' 150 %:** the main
  window at its floor (760 x 520, `main_window.FLOOR`), every page and
  Settings section without a sideways scroll - the UI lab's
  `w4_pages_at_floor`, which holds up to `FLOOR_SCALE` (1.8). 1.75 is the
  largest step about 1.2 times Larger under it.
- **A new key, `interface_text_size`.** 0.1.9 and before kept the size
  as `app_text_size` on their steps; the new version reads that key and
  never writes it, so the same name never means two sizes, and a learner
  who goes back to 0.1.9 finds the size they had there (unknown keys are
  kept on every save, 107).
- **Untouched sizes follow the default.** `interface_text_size` is in
  `FOLLOW_DEFAULT` (0220): not in the record of changes, it is the
  version running's Normal. A file whose `app_text_size` is Normal counts
  as untouched, with or without the record - every file held Normal,
  chosen or not, and one chosen and chosen back can't be told apart.
- **A chosen size keeps its size on screen**, as the nearest new step
  (`settings.OLD_TEXT_SIZES`), and counts as chosen: 0.1.9's Smaller (0.9)
  is Smaller (1.0), its Larger (1.2) is Normal (1.3), its Largest (1.45)
  is Larger (1.45). The two that aren't equal move by a pixel or two at the
  base size; four steps can't land on all three.
- **The UI lab runs at the new Normal** (`--app-text-size normal`): its
  goldens, budgets, design findings and 21 languages are at 1.3, and
  `approve` and `design` now set it rather than trust the process's.
  CI's Largest runs are at 1.75, and its Windows 200 % run reaches the
  2.25 ceiling (2.0 x 1.3). The design detector judges a transcript's
  own text (its lines and headings, A- / A+) on the scale at 1.0, as
  0084 leaves it; its spacing grid holds only at 1.0, so in the lab's run
  it judges the states built at Smaller.
- **What didn't fit at 1.3 now does, without fixed widths:** the first
  run's dialogs (`ui.widgets.TextDialog`: the first screen, the level
  picker, the sign-in) were 520, 580 and 440 px wide whatever their text,
  and the first screen scrolled on a 1920 x 1080 screen; their least
  widths now grow with their text (`set_least_width`, at most nine tenths
  of the screen). The first screen also grows wider, up to 680 px at 1.0
  (`consent.WIDEST`), before its explanation scrolls: in Linux's fonts,
  wider than Windows', it still scrolled on a 1040 px tall screen at 1.3.
  The level picker's choices scroll on a screen too short for it
  (Windows' 150 % text on a 150 % laptop, 1.95), with OK in view, as the
  first screen's do.
- **The main window's sidebar scrolls** in a window shorter than it - the
  floor (760 x 520) at Largest - rather than squash its pages' buttons
  (the train's UI lab cut their words top and bottom); taller, it fills
  the window as before.
- **A joined window's column is never narrower than its strip needs** -
  the last one's beside the window's controls - nor MIN_COLUMN, and Qt
  keeps every resize to it, up to the screen's width: at Windows' 200 %
  and Normal (2.25) the last column's buttons were squashed. At 100 % that
  is 351 px a column for three apps, where 320 squashed the last one's
  buttons too.
- **Unit tests begin at the design sizes** (a factor of 1.0: Windows'
  100 % and the app's Smaller; `tests/conftest.py`), where the sizes they
  name (13 px text, a 960 x 680 window) were chosen - as they were before
  this change, when Normal was 1.0. A test of the default sets Normal
  itself; the fit tests (the first run on a 150 % laptop, the first screen
  on a tall one) run at Smaller and Normal both.

Enforced by tests: `tests/ui/test_larger_text_by_default.py` (the steps,
the nearest-step table, every kind of file from before),
`tests/ui_next/test_app_text_size.py` (each step's pixels),
`tests/ui/test_consent_dialog.py` and `tests/ui/test_first_run_fit.py`
(the first run fits at Normal), and the UI lab at Normal.

## Why

- The user asked for the default between Larger and Largest. 1.3 is the
  step whose base text (17 px) sits between 0.1.9's Larger (16 px) and
  Largest (19 px); 1.35 rounds to 18 px, a pixel from Largest.
- Moving every step keeps the choice useful: Smaller is the interface as
  it was for whoever liked it, Larger is 0.1.9's Largest, exactly, for
  whoever chose it, and Largest is a real step above it.
- A new key rather than the old one re-read: a file can't say which
  version's steps `"larger"` meant, and a marker beside it would be one
  more key for the same thing. The same reason 0220 records changes.
- Normal from 0.1.9 follows the default: the brief says so, and it is
  the only reading a file allows - 0.1.9 saved Normal for every learner.
- Tests at the design sizes rather than each test's numbers rewritten for
  1.3: about 35 tests named 1.0's sizes, many in files other projects own
  (the caption window's, the transcript's); they test a mechanism at a
  size, and the lab and the fit tests judge the default.

## What would make us reverse it

- Learners find Normal too large - the main window opens at 1248 x 884,
  more than a 1080p laptop at 125 % has, so it opens kept to the screen
  and its pages scroll down - or testers keep picking Smaller.
- A step proves too close to the next (Normal 17 px, Larger 19 px).

## How we'd reverse it

- **Other factors:** one dict in `style`, `OLD_TEXT_SIZES` checked by
  its test against them, the goldens approved again. A learner who chose
  a step keeps the step's name, so its size moves with the dict.
- **Back to 0084's steps:** put the dict back and make Normal's default
  1.0; files keep `interface_text_size`. A version that wants the old
  scale again under the old key would map the new steps back the same
  way. About two hours, most of it the goldens.
