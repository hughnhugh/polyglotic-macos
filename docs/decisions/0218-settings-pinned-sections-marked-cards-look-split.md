# 0218 Settings: pinned sections, marked cards, Look split in three

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** the user (what: "More icons in settings for visibility
  ... make each setting category very obvious as you scroll the page",
  2026-11-17; 449's design 4A, DECISIONS #195 item 6, judged in the
  0.1.8 preview); Claude, for project 470 (how it is built, a reversible
  choice)

## Situation

Settings' Look section was 2,557 px tall with no landmark: its six tabs
and the card titles scrolled away, and a card's title was the size of a
row's (polyglotic-hq 449's findings 7 and 8). The "Pinyin" group, renamed
Readings with Jyutping (450), was a card inside Look. "App language" was
on Settings > App twice: the line under the title and App's Language card
(449's finding 9).

## Decision

- **Eight sections:** Look · Word links · Readings · Timing · Speech ·
  Dictation · App · Lab (`settings_page.SECTIONS`). Word links and
  Readings are sections of their own, out of Look; Look keeps the look and
  Reset. `show_section("learning")`, a way in from before 304, lands on
  Word links now.
- **Marks beside words:** each tab has its mark (`settings_page.MARKS`),
  each card's title its mark in a soft square and is 16 px, not 14
  (`settings_marks.mark_card`, `#CardTitle[heading="true"]`). The marks
  are `glyphs`' - drawn, in the theme's colours - and never stand alone.
- **Pinned:** the title and the tabs are a part of the page's own above
  the scroll area's viewport (`setViewportMargins`), lined up with the
  column; under them, over the viewport's top, the name of the card the
  learner is in shows once its own title has scrolled away
  (`settings_marks.PinnedCard`). The wheel over them scrolls the page
  (`wheel.page_of` takes a control pinned above a viewport as on the page).
- **A dropdown where the tabs don't fit on one line** (`section_picker`),
  at any width, text size or language: they never wrap. 449 said "below
  about 520 px"; measured, English's eight tabs need about 600 px at
  Normal and more at Largest, so a fixed width would have wrapped them.
- **App's Language card is gone;** the line under the title is the one
  place the app's language is set.

Enforced by tests (`tests/ui_next/test_settings_captions_page.py`,
`test_wheel_scrolls_the_page.py`) and the UI lab's states
`w4_settings_links`, `w4_settings_readings`, `w4_settings_app_scrolled`.

## Why

Microsoft's settings guidelines group settings under headers with an icon
and a short name; NN/g's "Icon Usability" says a label must sit beside an
icon. A pinned head keeps "where am I" on screen on a long page; the
alternative, a rail down the side (449's 4B), costs 150 px of a narrow
window. Tabs that wrap to two or four rows were the problem 449 found at
narrow widths, so the dropdown replaces them rather than a second row.

## What would make us reverse it

Learners in the 0.1.8 preview finding the pinned head takes too much of a
short window, or missing the tabs behind the dropdown; or a ninth section
that makes the tabs a dropdown at the window's usual size.

## How we'd reverse it

Each part is separate: the marks are `mark_card` calls and the tabs'
icons (`_ink_tabs`); the pinning is `_place_head` and `_place_pinned`
(without them the head goes back into the column); the split is the
`placed` table in `_captions` and `SECTIONS`. No setting's stored value
changed, so nothing migrates either way.
