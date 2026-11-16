# 0033 The interface's text follows Windows' text size

- **Status:** accepted
- **Date:** 2026-11-07
- **Decided by:** the user agreed 135's proposal A (polyglotic-hq
  DECISIONS.md #61, 2026-11-07); built in polyglotic-hq project 138.

## Situation

Every size the interface gave its text was fixed in pixels: 13 px in
`ui_next.style`'s stylesheet, 11-26 px painted in the lookup card, Words'
table and the transcript. Windows' Settings > Accessibility > Text size
(100-225 %) changed nothing, so a low-vision learner could enlarge the
captions (A- / A+) but not Home, Words, the lookup card or the panels
(135, finding 5).

## Decision

- **One factor** for the whole interface, `style.text_scale()`: Windows'
  text size, read once at start by `main` from the system font as Qt reads
  it (`style.text_scale_of(QApplication.font())` - Qt 6 takes it from
  Windows' message font, Segoe UI 9 pt at 100 %), kept to 1.0-2.25.
- **Every size given to text, or to room that holds text, goes through
  `style.px(n)`** (n in px at 100 %): the stylesheet's font sizes, the
  painted fonts, the lookup card's width, Words' rows and columns, the
  transcript's rail and minimum, Home's column, the sidebar, the main
  window's minimum (760 x 520 times the factor, kept to the screen).
  Paddings, borders and gaps stay as they are, as Windows' own do.
- **Caption windows keep their own text size** (A- / A+, the window's
  setting); so do a transcript's lines. Their chrome follows the factor:
  the hover band and its buttons, the notice, Back to live, the settings
  popover - and a caption window's minimum width, which holds the band.
- **While running:** the main window re-reads the factor when Qt reports a
  font or theme change, restyles itself and says so (`text_size_changed`);
  `main` restyles the transcripts.
- **Checked:** the UI lab runs at a simulated text size
  (`--text-size 200`: the application's font set as Windows would give
  it) and CI runs its checks and budgets at 200 % as well as 100 %; the
  goldens are at 100 %.

## Why

- One factor, read in one place, can't drift between widgets; `px()` is
  greppable, and a fixed size without it stands out in review.
- The system font is what Qt already reads; Windows' own
  `UISettings.TextScaleFactor` (WinRT) or the undocumented
  `TextScaleFactor` registry value would be a second source of truth.
- Not taken: Qt's own scaling (`QT_SCALE_FACTOR`, a font DPI), which
  would scale everything - the caption windows over a game included, which
  have their own size - and blur the bitmaps.

## What would make us reverse it

- Qt stops taking its font from Windows' message font, or Windows' text
  size stops changing it (the user's walk at 125-150 % is the first real
  test).
- Learners want the interface's size set in the app, not in Windows.

## How we'd reverse it

- A setting in the app: `main` would call `style.use_text_scale` with the
  learner's choice instead of (or times) the system's - nothing else
  changes.
- Dropping it: `use_text_scale` is never called, the factor stays 1.0 and
  every `px(n)` is `n`.
