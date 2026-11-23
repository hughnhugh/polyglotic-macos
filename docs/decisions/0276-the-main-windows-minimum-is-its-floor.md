# 0276 The main window's minimum is its floor, not the size it opens at

- **Status:** accepted
- **Date:** 2026-11-21
- **Decided by:** Claude, in polyglotic-hq project 586 (the user's preview-2
  feedback, 2026-11-21 ~09:03: "Desktop client UI can't be resized also,
  shows the arrows but doesn't let you"); a reversible technical choice,
  recorded here for the user to see.

## Situation

The main window's minimum was 960 x 680 times the text size (248's section
2.1: a Settings section fits without scrolling), kept to the screen, and it
opened at `max(1000 x 740, that minimum)`. Since decision 0244 made Normal,
the default, 1.3, the minimum (1248 x 884) is larger than 1000 x 740, so
the window opened at exactly its minimum: Windows showed resize arrows on
every edge (the frame is resizable) but its track size (`WM_GETMINMAXINFO`,
Qt's minimum plus the frame) stopped every inward drag. 586's probe on a
private desktop read 1264 x 923 for both the window and its least track
size on a 2560 x 1440 screen. At Largest (1.75) the minimum was 1680 x
1190, most of that screen; on a 1080p laptop at 150 % it was the whole work
area, so no edge moved at all.

## Decision

- **Its minimum** (`minimum_size`) is FLOOR, 760 x 520, at every text size
  up to `FLOOR_SCALE` (1.8): the UI lab's `w4_pages_at_floor` checks every
  page and Settings section fits it without a horizontal scrollbar there,
  in every language. Above 1.8 its width grows with the text; its height
  stays 520 - the pages and the sidebar scroll down (524). Kept to a small
  screen as before.
- **The size it opens at** doesn't change: 1000 x 740, at least 960 x 680
  times the text size (`roomy_size`), kept to the screen - or the size the
  learner left it at (`AppSettings.main_window_size`, saved when it's
  closed to the tray and at quit).
- `FLOOR_SCALE` moved from the UI lab to `main_window`: the guarantee is
  the window's, the lab checks it. The lab's states photographed at "the
  minimum" (`at_minimum`, `words_minimum`, `settings_minimum`) are taken
  at `roomy_size`, the same size as before, so their pictures don't move.
- Enforced by `tests/ui_next/test_main_window_resizes.py`: at every text
  size, on three screens, it opens larger than its minimum both ways.

## Why

- Every page already fits the floor (354, checked every lab run); the
  bigger minimum only promised "a Settings section without scrolling",
  which the size it opens at still gives. A learner who wants it smaller -
  beside a game, on half a screen - now can, and scrolls.
- Not taken: opening it larger than the old minimum. At Normal on a 1080p
  screen the old minimum already filled most of the work area, so there
  was no room to open larger; and it would still never shrink.
- Not taken: a minimum that shrinks with the screen only. The edges must
  move on any screen at any text size.

## What would make us reverse it

Pages cut off or squashed at the floor at some text size or language the
lab doesn't run, or learners shrinking it to where Settings sections
scroll and finding that worse than a window they can't shrink.

## How we'd reverse it

`minimum_size` returns `roomy_size` again (one function) and the tests in
`test_main_window_resizes.py` that say it opens above its minimum go. The
saved size (`main_window_size`) can stay: `fit_to` keeps it to the minimum.
