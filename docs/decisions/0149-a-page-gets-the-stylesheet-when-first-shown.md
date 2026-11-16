# 0149 A page gets the main window's stylesheet when it's first shown, not when it's added

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** Claude, within polyglotic-hq project 357's brief (win the
  start's time back under its 400 ms budget without changing it, decision
  0103); a reversible technical choice (polyglotic-hq CLAUDE.md, "Rhythm")
- **Amends:** 0148

## Situation

Decision 0148 put the main window's stylesheet on its parts: the sidebar,
each page as `add_page` takes it, and each dialog. The theme change got
fast, but every page now had a stylesheet of its own from the start, and
Qt polished each one's widgets under it while the pages were built and
when the window was first shown. A widget under a stylesheet of its own
page cost about twice what it did under the window's one stylesheet
(a bench of 6 pages of 80 widgets: 52 ms against 26 ms). With 2026-11-15's
work together (#679, 857 widgets), CI's start test went over its budget:
413 and 409 ms against 400.

## Decision

- `add_page` gives the stylesheet only to the first page added, the one
  the stack shows until `go_to`. Every other page gets it from `go_to`
  when it's first shown (`MainWindow._styled`, 0148's path for a page not
  on show during a theme change).
- Nothing else of 0148 changes: a theme or text size change restyles the
  sidebar, the page on show and the dialogs; the other pages when shown.
- Held by `tests/ui_next/test_main_window_theme.py`: at the start only the
  page on show has the stylesheet, and each other page, first shown
  later, looks pixel for pixel as it did with the stylesheet from the
  start; and by the UI lab's goldens of every page.

## Why

- The start with 30,000 words met (`tools/learner_start.py`, offscreen, 12
  starts each, alternating, the PC about 10 % busy, 2026-11-15): main
  323 ms, #679 401 ms, with this 280 ms. The pages' parts went from 135
  to 45 ms and the first paint from 35 to 10 ms.
- What it costs: each page's first show restyles it (the UI lab's
  `page_switch_cold`, held to its budget).
- **Not taken:** building the pages not on show after the first paint
  (312 measured it on 2026-11-14: it moves the cost to a stall after the
  paint, which grew more than the paint gained); one stylesheet on the
  window again (0148's theme change would be slow again).

## What would make us reverse it

- A page's first show over the UI lab's `page_switch_cold` budget.
- Code that reads a hidden page's size or fonts before it's shown and
  keeps what it read (without the stylesheet they're Qt's defaults).
