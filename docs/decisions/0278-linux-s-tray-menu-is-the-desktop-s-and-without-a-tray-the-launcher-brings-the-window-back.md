# 0278 Linux's tray menu is the desktop's to show; without a tray, the launcher brings the window back

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude (polyglotic-hq 571), from 546's plan (slice 4:
  "the tray, everything in its menu; Home from the launcher where there's
  none"); reversible inside `ui/app.py`, `ui_next/no_tray.py` and `main`.

## Situation

On Windows and the Mac the app opens the tray's menu itself
(`show_tray_menu`), placed above the taskbar, because Qt places it badly
there. Linux's trays work differently:

- KDE's tray and GNOME's AppIndicator extension (Ubuntu's default) are
  StatusNotifierItem hosts: they draw the item's menu themselves from what
  the app exports over D-Bus. Without a menu set on the tray, Qt exports
  none: KDE then asks the app to open one at a point the app (an X11
  program under XWayland) may not know, and GNOME's extension has nothing
  to show.
- An X11 tray (an older Xfce panel, others) embeds the icon; Qt opens the
  menu set on it at the click.
- GNOME without the extension - Fedora's GNOME by default - has no tray at
  all. Closing the main window there left the app running with nothing on
  screen saying so, and nowhere but the window's own sidebar to quit.

## Decision

- **On Linux the menu is the tray's** (`tray.setContextMenu`): every
  desktop's tray shows it its own way, and the app never opens a second
  one. Every item is a plain action, a separator or a submenu, so a tray
  drawing it from D-Bus loses nothing (a test keeps it so).
- **Where there's no tray**, closing the main window doesn't hide it at
  once: the first time, a box over it says the app keeps running - its
  caption windows stay up - that the window comes back by opening
  Polyglotic again from the desktop's apps (a second start shows it:
  decision 0101), and that Quit is at the foot of its sidebar; it offers
  Quit at once. After that, closing just hides the window. The box shares
  the tray note's "said once" setting (`tray_note_shown`).
- Windows and the Mac are unchanged.

Checked on GitHub's runners (`linux-manners.yml`): on Xfce's panel the
menu was read over D-Bus by another process, as a tray reads it - every
item there - and Pause captions clicked there paused the app; on GNOME's
own window manager (no tray) the box showed, the window hid, `gio launch`
of a desktop file brought it back in 0.4 s, and Quit at the sidebar's foot
ended the app.

## Why

- The desktop drawing its own menu is what each desktop's users expect
  (its fonts, its theme, its keyboard), and the only way a D-Bus tray
  shows one.
- Asking once on close is the no-tray counterpart of the tray's one-time
  note (polyglotic-hq 135: learners thought they had quit), and offers the
  quit a GNOME user may have meant by closing the window.
- Not quitting on close: the caption windows are the point, and a learner
  closes the main window to watch or play.

## What would make us reverse it

- Testers on GNOME without a tray expecting close to quit (they'd say so,
  or quit from the box every time): make closing quit there, saying so
  the first time.
- A desktop whose tray draws Qt's exported menu wrongly (a missing
  submenu, stale check marks): open our own there, as on Windows.

## How we'd reverse it

`DESKTOP_SHOWS_TRAY_MENU` in `ui/app.py` back to False puts Linux on
Windows' route; `main` setting `no_tray` False puts closing back as it was.
Minutes each.
