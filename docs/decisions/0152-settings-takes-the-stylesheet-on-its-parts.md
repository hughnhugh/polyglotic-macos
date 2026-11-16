# 0152 Settings takes the main window's stylesheet on its parts, and a section when it's shown

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** Claude, within polyglotic-hq project 360's brief (a theme
  change with Settings open near 25 ms, the way 0148 and 0149 did for
  pages); a reversible technical choice (polyglotic-hq CLAUDE.md, "Rhythm")
- **Amends:** 0148 (for one page)

## Situation

Decision 0148 put the main window's stylesheet on its parts: the sidebar,
the page on show and the dialogs. Qt restyles every widget under a changed
stylesheet, shown or not, so a theme change with Settings on show still
restyled all of Settings: 489 widgets, of which one section in six shows
at a time (Look is 107, Lab 132). The change took 52.5 ms there against
Home's 15 (polyglotic-hq 355's bench, `settings_case.py`).

## Decision

- A page can take the stylesheet on its parts instead of on itself: it
  has `use_sheet(sheet)` (`main_window.InParts`), which `MainWindow` calls
  where it would set the page's stylesheet (`_give`).
- Settings gives it to its head (the title, the sections' switch and the
  language lines, grouped in one widget, `settings.top`, so the sheet is
  parsed once there), to its scroll bars, and to the section on show.
  Each other section gets it when `show_section` shows it, before it's
  shown.
- The page, its scroll area's viewport and its column then have no
  stylesheet and paint nothing: the window's own background (0148) shows
  beneath them, as it does beside a column. The page's notices dialog is
  given the stylesheet (it was a child of the page's).
- The page itself gets no StyleChange from Qt now, and that event is what
  sized its column to the text size (`Page`) and its scroll range to its
  content (Qt's scroll area). `use_sheet` posts one: posted, not sent, so
  it comes once the page is shown, at its width. Without it the content
  kept its old height and nothing scrolled; sent at once, the first frame
  laid Look out at the hidden page's size.
- Held by `tests/ui_next/test_main_window_theme.py`: a theme change with
  Settings on show restyles the section on show and the head, no hidden
  section; a section shown later is restyled then; each section looks,
  pixel for pixel, as in a window built in the theme; and the page first
  shown is laid out in one pass. The UI lab's goldens of every Settings
  state are unchanged.

## Why

- The theme change with Settings on show: 52.5 ms on main, 25.0 and
  29.0 ms with this in two runs (355's bench, median of the last 10 of 12
  changes, offscreen, the user's PC, 2026-11-15); the UI lab's
  `theme_on_settings` 48.3 ms on main, 24.8 and 27.7 ms with this. A section's first show after a theme change now
  restyles it: the cost moves to that click, as 0148 moved a page's.
- Each widget given a stylesheet of its own parses it (about 1.4 ms for
  this one): the head's eight widgets each with it took the change to
  34 ms, grouped under one widget 29 ms.
- **Not taken:** taking hidden sections out of the page while hidden
  (reparenting): Qt moves a reparented widget's controls to the end of
  the window's Tab order, after Quit; fewer widgets (other projects'
  work, and the cost would come back with the next setting).

## What would make us reverse it

- A part of Settings outside the head, the scroll bars and the sections
  showing the app's default look (it would get no stylesheet): the
  goldens catch it for the states the lab has.
- A section's first show over the UI lab's `section_switch` budget.

How: remove `use_sheet` from `SettingsPage`; `MainWindow` then sets the
page's stylesheet as for any page.
