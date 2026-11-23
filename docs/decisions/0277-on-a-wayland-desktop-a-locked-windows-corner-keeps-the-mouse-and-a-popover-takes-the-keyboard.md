# 0277 On a Wayland desktop a locked window's corner keeps the mouse, and a popover takes the keyboard

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude (polyglotic-hq 570, 546's slice 3), from runs on
  GitHub's runners. The corner is DECISIONS #243 item 6: Claude's yes, the
  user hasn't answered yet, so it's behind a setting, on by default.
  Reversible inside `ui_next/unlock_spot.py`, `ui_next/settings_popover.py`
  and `ui_next/above_all.py`.

## Situation

On Linux the app is an X11 program everywhere (decision 0258). On a
Wayland desktop, the X server knows nothing of the mouse or the keys while
they're over or in another app's window. 570's runs (GNOME 46 and 51, KDE
6.8, input sent through each compositor, a full-screen Wayland window
beneath) found:
- **Over a locked window** (it lets every click through), the app never
  sees the mouse. So resting on the lock to unlock (polyglotic-hq 398)
  can't work there.
- **A small window kept over the lock's corner** hears the mouse arrive.
  On GNOME it never hears it leave: Qt still had the mouse "on" the corner,
  at its last place, after it had moved over the window beneath. On KDE
  it hears both.
- **Esc and a click elsewhere** went to the app beneath, for today's
  popover (it never takes the keyboard) and for a real `Qt.Popup` (its X11
  grabs don't reach past XWayland). A popover that takes the keyboard when
  it opens got Esc, and lost the keyboard on a click elsewhere, on all
  three.

## Decision

- **The unlock corner** (Linux on a Wayland desktop: `OsAdapters.
  unlock_spot`; `AppSettings.unlock_spot`, on). A locked caption window's
  lock corner, at least 60 x 40 px, is a window of its own that takes the
  mouse; the rest of the window still lets every click through.
  - The mouse arriving on it, moving on it or clicking it shows Unlock.
  - Unlock goes 3 s after the corner or Unlock last heard the mouse,
    because the leaving can't be heard.
  - Unlock still needs a click.
- **A popover takes the keyboard** while it's open (Linux:
  `POPOVERS_TAKE_THE_KEYBOARD`): an ordinary window, given the keyboard as
  it opens, closed by Esc or when another window takes the keyboard (a
  click anywhere else). Windows and the Mac keep theirs, which never takes
  it.
- **The first lock** on Linux says at length how to unlock (the corner,
  the hotkey where it works, or Home), once (`AppSettings.unlock_told`).

## Why

- Without the corner, a learner who locks a window over Firefox on GNOME
  can unlock it only from Home, or from the tray where there is one; on
  Ubuntu 24.04 there's no hotkey either.
- Showing Unlock on arrival, for a few seconds, never leaves a pill stuck
  over a game, and still needs a click, so a mouse passing over can't
  unlock by accident.
- Taking the keyboard costs a full-screen game its focus while the popover
  is open. But the popover opens only on the learner's own click on the
  caption window, so they've already left the game. Nothing else closed
  it.

## What would make us reverse it

- The user answering no to DECISIONS #243 item 6: set
  `AppSettings.unlock_spot` off, then remove it.
- Testers' clicks going missing in a game's corner under a locked window.
- A game minimising when the popover opens.
- A Wayland protocol, or a portal, that tells an X11 app where the mouse
  is or what was pressed elsewhere.

## How we'd reverse it

- **The corner:** `UnlockSpot.catch` and `_Catcher`, `CaptionWindows.
  set_unlock_spot`, `main.follow_unlock_spot`, the setting and the
  adapters' field. About an hour.
- **The popover:** `POPOVERS_TAKE_THE_KEYBOARD` false, then delete its
  branch.
- **The first lock:** `main.tell_how_to_unlock` and its two strings.
