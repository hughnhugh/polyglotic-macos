# 0158 The pages not on show get the stylesheet a second after the start, one page per turn

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** Claude, within polyglotic-hq project 367's brief (the UI
  lab's timed steps back inside their budgets on main: make the code fast
  again, not the budget); a reversible technical choice (polyglotic-hq
  CLAUDE.md, "Rhythm")
- **Amends:** 0149 (which amends 0148)

## Situation

Decision 0149 gave a page the main window's stylesheet when it's first
shown, not when it's added, to keep the start inside its budget. Its
cost was each page's first show restyling the page, and its reversal
condition was "a page's first show over the UI lab's `page_switch_cold`
budget" (50 ms). Since it merged (#679, 2026-11-15), main's own UI lab
runs measure:
- Words' first show at 10,000 words met: 19-32 ms before, 34-43 ms after.
- Words with two languages: 12-22 ms before (once 30), 32-44 ms after.

Under CI's load, pull requests measured 50-56 ms, and 361's four pull
requests failed on it.

Restyling the Words page is 12-15 ms of it: Qt polishes each of its 169
widgets under the new stylesheet. The page is polished in Qt's own style
while it's built, so keeping it out of the window until its first show
saves nothing. Measured in polyglotic-hq 367: no change in the first show,
and a later reparent cost more.

## Decision

- `MainWindow.style_ahead()` gives each page not on show the stylesheet
  now, one page per turn of the event loop (`_styled`, 0148's path), so no
  turn holds the interface for them all.
- `main` calls it `PAGES_STYLED_AFTER_START_MS` (1 s) after the start's
  first paint, beside the timers for the voices (2 s) and the packs
  (1.5 s). A first show after that restyles nothing.
- The start itself is unchanged: the timer starts after the first paint,
  so the start's own `processEvents` doesn't run it.
- Theme and text size changes are as 0148 has them: the page on show at
  once, the others when next shown.
- The UI lab's `window_with` styles ahead as `main` does, once the window
  is up. It does this before the first show it times, because that is
  the first show a learner's click meets.
- Held by `tests/ui_next/test_main_window_theme.py`: one page per call
  and the next on the next turn, and a page's first show then restyles
  nothing and looks as it did.

## Why

Interleaved on this PC, 62-68 % busy, the median of six runs each,
2026-11-15:

| First show | Main | With this |
|---|---|---|
| Words, 10,000 met | 48 ms | 32 ms |
| Words, two languages | 44 ms | 22 ms |
| Words, full | 42 ms | 23 ms |
| Learning | 19 ms | 10 ms |
| Settings | 32 ms | 26 ms |

- A learner's first click on another page comes seconds after the start,
  not within one. The work is still done, but it's done before the click
  instead of on it.
- One page per turn keeps each turn to one page's restyle (Words: 12-15
  ms), well inside the 50 ms any one slot may take.

**Not taken:**
- Styling every page at the start: 0149's reason, about 30 ms of the
  start's 400.
- Building the pages after the first paint: 312 measured it. It moved the
  cost to one stall after the paint.
- Keeping a page out of the window until first shown: it's polished while
  it's built anyway.
- Restyling ahead after a theme change too: the lab times a theme change
  with what it queues, and the pages not on show would count. Left as 0148
  has it.

## What would make us reverse it

- A stall after the start that a learner notices, or one page's restyle
  taking a slot over 50 ms.
- A page's first show over `page_switch_cold` again: then the page itself
  has grown, and needs fewer widgets.

## How we'd reverse it

Remove `style_ahead`/`_style_next` from `ui_next/main_window.py`, its
call and `PAGES_STYLED_AFTER_START_MS` in `main.py`, and the call in the
UI lab's `window_with` (about 30 lines). That brings back 0149.
