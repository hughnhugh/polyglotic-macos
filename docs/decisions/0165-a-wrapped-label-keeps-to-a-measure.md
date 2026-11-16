# 0165 A wrapped label keeps to a measure, and answers its layout from what it has kept

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, within polyglotic-hq project 376's brief (UI
  judge pass 3: fix the design detector's high and medium findings); a
  reversible technical choice (polyglotic-hq CLAUDE.md, "Rhythm")

## Situation

The main window's column is 720 px wide (109's 10.5) and a note in it is
12 px: its lines ran to 90-120 characters, in Settings, Learning, Account,
Help and Home. The design detector's `line_length` rule (Impeccable's 65-75
characters; at most 80) found it on 129 state-and-label pairs, 91 of them
in the baseline. The notes are made in some forty places by
`controls.label(..., wrap=True)`.

## Decision

- `copying.Measured` (a `QLabel`; `copying.Text` is one) keeps a wrapped,
  left-aligned label in a layout to `MEASURE` (64) of its font's average
  characters: it prefers that width, is as tall as its words need within
  it, and its place in its parent's layout is aligned left, once, the
  first time the layout asks. A sentence a word or two over stays on one
  line (`ONE_LINE`, at most `ONE_LINE_CHARACTERS`, the detector's 80). A
  word longer than the measure (a path) widens it. A label drawn as a band
  (`BANDS`: Home's notice) or with a stylesheet of its own, one centred or
  at the right, one not in a layout, and one that doesn't wrap, are as
  they were.
- Nothing is set when a label is resized (a margin kept up to date there
  laid a page out twice on its first show).
- What a layout asks on every pass is answered from what the label has
  kept: whether it's measured, the width its words need, and its height at
  the widths asked about (`heightForWidth`; Qt lays the words out again
  for each question). They're dropped when the words, the font, the
  style, the wrapping, the side, the margins or the parent change. No
  `event()` in Python: the main window has hundreds of labels.
- Tests: `tests/ui_next/test_notes_measure.py`; the UI lab's `line_length`
  rule and its section-switch budget.

## Why

- One place instead of forty: a maximum width on each note would centre
  it in a wider row (Qt centres a widget narrower than its cell) and miss
  the next note someone writes.
- By the font, not in px: the measure holds at Windows' text sizes and the
  app's Smaller to Largest.
- The kept heights make a Settings section's switch cheaper than before
  (3.8-5.9 ms in the lab against 6.1-8.0, budget 8): without them the
  Python calls added about half a millisecond a switch.
- Not taken: narrowing the column (the cards hold controls and tables
  that use 720 px); a second column of notes beside the controls (a new
  layout for every card: the user's to decide).

## What would make us reverse it

A label whose height is wrong after something changed that isn't dropped
here (a clipped or over-tall note in the lab's pictures), or a layout that
needs a wrapped label to fill its row.

## How we'd reverse it

`controls.label` makes a plain `QLabel` again and `Text` inherits from it:
two lines, and the lab's goldens and design baseline re-approved.
