# 0148 The main window's theme is on its parts, and a page not on show is restyled when it's shown

- **Status:** accepted; amended by 0149 (a page gets the stylesheet when
  first shown, not when it's added)
- **Date:** 2026-11-15
- **Decided by:** Claude, within polyglotic-hq project 355's brief (win the
  theme change's time back without changing how anything looks); a
  reversible technical choice (polyglotic-hq CLAUDE.md, "Rhythm")

## Situation

Decision 0031 scoped the new interface's stylesheet to its own window, so
a theme change no longer restyled every widget in the app. The main
window's stylesheet was on the window itself. Qt restyles every widget
under a changed stylesheet, shown or not, at about 0.06-0.09 ms each on
the user's PC. Between 2026-11-07 and 2026-11-15 the window grew from 326
widgets to 857 (Settings' sections, Learning, the dictation and caption
settings), and the UI lab's theme change from 33 to 77 ms against its
100 ms budget, failing desktop pull requests' UI lab on a calm PC
(polyglotic-hq 344). Home, the page on show in the lab, is 128 of the
857.

## Decision

- The stylesheet goes on the window's parts, not on the window: the
  sidebar, each page as `add_page` takes it, and each dialog the window
  opens (given it when Qt polishes it; `MainWindow.childEvent`).
- A theme or text size change restyles the sidebar, the page on show and
  the dialogs open at once. Each other page gets the new stylesheet when
  `go_to` next shows it - a first show in that theme, held to the first
  show's budget (`page_switch_cold`) in the UI lab's `w4_theme_change`.
- The window paints its own background in the theme's `BG` (the margins
  beside a page's column), as the stylesheet's `QMainWindow` and
  `#Content` rules did.
- `MainWindow.sheet` is the stylesheet its parts have, or will have when
  shown.
- Held by `tests/ui_next/test_main_window_theme.py`: a theme change
  restyles nothing on a page not on show; a page restyled late looks,
  pixel for pixel, as in a window built in the theme; the margins are
  the theme's background; a dialog over the window has its stylesheet,
  and a change while it's open reaches it.

## Why

- The UI lab's theme change (Home on show) went from 68 to 15 ms, and
  with Settings on show from 73 to 50 ms (medians of 5 and 3 runs,
  2026-11-15). Everything looked the same: 42 photographs of every page,
  in four looks, changed from Home and from Settings, and of a dialog,
  were identical to main's.
- **Not taken:** fewer widgets (the pages are 354's and other projects'
  work, and the cost would come back with the next feature); a palette
  instead of a stylesheet (every control would look different); restyling
  the hidden pages on a timer after the change (the lab times what an
  action queues, and a page shown during it would wait).

## What would make us reverse it

- Something parented to the window that is neither a page, the sidebar
  nor a dialog showing the app's default look (it would get no
  stylesheet).
- A page shown other than through `go_to` showing the theme before.
- The first show of a big page after a theme change growing past its
  50 ms budget - Settings' is about 36 ms on the user's PC.

## How we'd reverse it

Put `self.setStyleSheet(self.sheet)` back on the window in
`MainWindow._restyle_shown` and drop the parts' sheets, `_styled`,
`childEvent` and `paintEvent`: one file, under an hour. The theme change
goes back to restyling every widget.
