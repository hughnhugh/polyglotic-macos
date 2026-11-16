# 0147 The main window's pages reflow at its floor, never scroll sideways

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 354 (found by 350, finding 3), within
  the agreed plan: `main_window.FLOOR`'s promise that every page fits it
  without a horizontal scrollbar.

## Situation

The main window is kept to the screen, never under 760 x 520 (`FLOOR`):
a 1280 x 720 laptop at 150 %, or 1366 x 768 at 150 %, has no more. Its
pages were laid out in fixed rows - a title and its choices, four buttons
side by side, a switch whose whole sentence was one line, a table's
columns at their full widths - so at the floor 16 of 21 interface
languages scrolled sideways on Home, Words or Settings (8-153 px), English
did at the Larger and Largest text sizes (up to 216 px), and the sidebar
took 267 of the 760 px at Largest. German Home was cut at "Untertitel
pausie…".

## Decision

One set of shared parts in `ui_next.controls`, used by the pages:

- **`Flow`**, a row that wraps: its items left to right, and what doesn't
  fit on the next line. Its least width is its widest item's, not their
  sum. Stretches work as in a row on the line they fall on; `right=True`
  keeps a line's buttons at its right (`right_row`, which replaces each
  page's own `_right`). The rows that made pages too wide use it: Settings'
  title and sections, the app language's line, Home's state, app rows,
  window buttons and feedback line, Words' filters, categories, export and
  legend, Learning's "Learn another language" and a language card's
  buttons, Help's papers.
- **`WrapButton` and `WrapCheckBox`**: a button's words wrap onto more
  lines when it's narrower than them, its least width its longest word's
  (a character's, in Chinese or Japanese). `text()` stays as given; only
  the painting breaks it. `SwitchButton` is one, so every switch's
  sentence wraps; so are Help's topics, Look's Reset and Words' "Only
  words not exported yet".
- **`Segmented`** lays its choices out with a `Flow`: too narrow, they go
  onto a second line.
- **Labels** that held a page open - Home's state title, the heard card's
  section labels, a hotkey's name - wrap. Card titles don't: wrapping
  every one made a theme change about 10 % slower, and none is too wide
  up to `FLOOR_SCALE`.
- **Word tables** narrow their columns where the table is too narrow for
  them all (`word_table.fitted`): the word column, then the category's,
  then Add to deck's and Known's to their longest word, whose button then
  shows its words on two lines. The meaning keeps at least 56 px.
- **The sidebar**, narrower than `NARROW`, is 184 px times the text size -
  and in a window narrower than the usual first size (`SIZE`, 1,000 px), at
  a large text size, only as wide as its words need, at least 184. Not at
  1,000 px and over: there the wider page column would run its lines past
  80 characters (the design detector's `line_length`).
- Sliders' least width no longer grows with the text: their handle
  doesn't.

The UI lab's `w4_pages_at_floor` holds it: the window at the floor, every
page and Settings section, no sideways scroll, in every language and text
size the lab runs at up to `FLOOR_SCALE` (1.8: Windows' 150 % with the
app's Larger, 125 % with Largest).

## Why

- One fix in the shared parts reaches every language, text size and
  future page; a fix per language would be undone by the next string.
  Translations aren't shortened.
- Wrapping keeps every word of a control. Eliding was the alternative the
  brief allowed for labels; nothing needed it.
- A wrapping row (rather than a row that switches to a column) keeps a
  row's look wherever it fits, which is every size but the small screens.

## Limits

- Over `FLOOR_SCALE` - Windows' 200 % text, or 150 % with Largest - Words'
  tables (their action buttons), Look's caption preview, a long card title
  and Dictation's language list are still wider than the floor's page, and
  the sidebar is taller than 520 px.
- `Flow` is a layout written in Python, so Qt asks Python each time it
  lays out: it keeps its heights by width until it's invalidated. A
  theme change measured 61 ms on main and 69-73 ms here, a Settings
  section switch 4.6 and 5.7 ms (budgets 100 and 8; offscreen, 2026-11-15).
- `Flow.add_layout` puts the layout in a widget of its own: a layout
  held straight in it was deleted twice as its window closed.
- Thai at the Largest size: Qt here finds no word breaks inside a Thai
  phrase, so a long phrase between spaces can't wrap.

## What would make us reverse it

Learners finding the wrapped rows harder to scan than a scroll, or a
redesign of the main window for small screens (a collapsible sidebar, a
table that stacks its columns) that makes these parts unneeded. Reversing
is per row: put back the `QHBoxLayout`; `Flow`, `WrapButton` and
`fitted` can stay unused or be deleted with their tests.
