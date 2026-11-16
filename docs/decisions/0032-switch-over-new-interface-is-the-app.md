# 0032 The switch-over: the new interface is the app; today's main window and overlays go

- **Status:** accepted
- **Date:** 2026-11-07
- **Decided by:** Claude, on polyglotic-hq project 132's brief (109's
  build order, step 9: "the developer switch becomes the default, the old
  `ui/` removed"), under the user's go-ahead for the rebuild (DECISIONS.md
  #53, 2026-11-07). Replaces the last part of decision 0031's point 2 ("one
  change deletes `ui/`, renames `ui_next/` to `ui/` and removes the
  switch"); the rest of 0031 stands.

## Situation

Steps 1-8 of the rebuild are built and merged behind the developer switch
`--next-interface`, and two UI judge passes reviewed them. Under the
switch, today's main window was still built (hidden) because `DesktopApp`
kept the app's state on it, and today's overlays' lock and hide were the
commands everything used. Decision 0031 planned one change that deletes
`ui/`, renames `ui_next/` to `ui/` and removes the switch. But the UI
judge's second pass (polyglotic-hq project 131) is changing `ui_next/`
files at the same time, one pull request per concern, and a rename of
every file would collide with each of them.

## Decision

1. **The new interface is what `main` starts.** `--next-interface` is
   accepted and ignored (hidden from `--help`) until the first release
   after this change, so a developer's old command line still starts the
   app; it is then removed. No way back to the old interface is kept: it
   would mean keeping today's main window and overlays alive.
2. **Today's main window, overlays, lookup popup and pages are deleted**
   (`ui/main_window.py`, `ui/overlay.py`, `ui/lookup.py`, the old pages,
   the developer's `tryout` that showed them, and the lab's states of
   today's interface). `DesktopApp` keeps the app's state itself - the
   session's state, the tray, the commands (pause, lock and hide every
   caption window, caption my own speech, the feedback forms, quit) - and
   the new main window (`main.Hub`) and the tray follow it.
3. **`ui/` keeps, for now, the pieces the new interface uses** and that
   don't belong to one window: `DesktopApp` (the tray, the commands, the
   caption feed, "Looks wrong?"), the settings file's shape and its
   migrations, the window theme's palettes and fonts, the tray and logo
   icons, Learning's tools, the apps-with-sound list, and today's dialogs
   (first-run language, level picker, consent, sign in and out, delete
   learning data, feedback, the comparison card). `ui/` and `ui_next/`
   still don't import each other; `main` wires them.
4. **The rename is a later, mechanical change:** once the UI judge's fixes
   have landed, `ui/`'s remaining pieces move into `ui_next/` and
   `ui_next/` is renamed `ui/` - imports only, no behaviour.

## Why

- The alpha gets the rebuilt interface on `main` now; the old one was
  already unused under the switch, and keeping it costs every change a
  second place to keep working.
- Moving the state off today's window is what lets it be deleted rather
  than built and hidden at every start.
- Deferring the rename keeps this change reviewable (deletions and a
  slimmer `DesktopApp`) and keeps the UI judge's pull requests mergeable.
  Not taken: renaming now (every one of 131's pull requests would
  conflict); moving `ui/`'s pieces into `ui_next/` now (the same, for
  fewer files, and no reader is helped by it until the rename).

## What would make us reverse it

- A feature found missing from the new interface that the old one had
  (polyglotic-hq project 109's feature map, checked in project 132) and
  can't be added quickly - the old one would be brought back from git
  history behind the switch, not kept alive here.
- The rename still not done a few weeks after the judge's last pass: a
  sign that the two packages are settling in as permanent.

## How we'd reverse it

- **The old interface back:** revert this change's pull requests; nothing
  else depends on its absence (the settings file still holds every key
  today's interface read - polyglotic-hq RELEASING.md section 5 - so an
  older build reads it).
- **The rename:** `git mv` and import updates, about an hour, with the
  import-linter contracts' module names.
