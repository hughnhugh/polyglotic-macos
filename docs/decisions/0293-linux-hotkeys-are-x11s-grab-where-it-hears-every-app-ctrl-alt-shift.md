# 0293 Linux's hotkeys are X11's key grab where it hears every app, with Ctrl+Alt+Shift

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude (polyglotic-hq 570, 546's slice 3), from runs on
  GitHub's runners; Ctrl+Alt+Shift agreed by Claude (the coordinator) on
  2026-11-20. Reversible inside `platform/linux/hotkeys.py` and
  `core.listening.hotkeys.OWN_MODIFIERS`.

## Situation

The app is an X11 program on every Linux desktop (decision 0258). Lock,
pause and hide must work while a game, a video or a call has the keyboard,
as Ctrl+Alt+L, P and H do on Windows. Each desktop treats an X11 app's
keys differently, and some already use Ctrl+Alt+L.

570's runs (pressing keys through each compositor's own input, with a
full-screen Wayland window focused):

| | X11's grab hears it over the Wayland window |
|---|---|
| A bare X server (an Xorg session) | yes |
| KDE Plasma 6.8 (KWin, Wayland) | yes: `XwaylandEavesdrops` defaults to `Combinations` in Plasma 6 (5.27: `None`) |
| GNOME 46 (Ubuntu 24.04) and GNOME 51 (Fedora 45), Wayland | no |

A combination another client already holds is reported taken on all of
them. The distributions' own default shortcuts (their packages, read on the
runners): Ctrl+Alt+L locks the screen on Cinnamon (Mint), MATE and Xfce; not
on GNOME 46-51 or KDE 5.27/6.8 (kscreenlocker: Meta+L). Ctrl+Alt+P and H,
and Ctrl+Alt+Shift with L, P or H, are taken by none of them. GNOME 48+
and KDE have the GlobalShortcuts portal; GNOME 46 doesn't.

## Decision

- **X11's key grab** (`XGrabKey` through libxcb, by ctypes: a connection of
  the hotkeys' own, every Caps Lock and NumLock variant, the X server's
  repeats let go) wherever it hears every app: an Xorg session, and
  Plasma 6's Wayland session (`for_this_session`).
- **Elsewhere none** (GNOME's Wayland session): every key answers "not
  working here", so the interface says how else to unlock, and the
  learner can bind `polyglotic --lock`, `--pause` and `--hide` in the
  desktop's own keyboard settings (polyglotic-hq 570's second pull
  request). The GlobalShortcuts portal for GNOME 48+ is its own step
  (polyglotic-hq 570's report).
- **Linux's own keys are Ctrl+Alt+Shift with the letter** (L, P, H and
  567's Back to live, J): one set for every desktop, free on all seven
  checked (`core.listening.hotkeys.OWN_MODIFIERS[Platform.LINUX]`, told by
  `os_words.platform`). Help and the caption windows write them so
  (`hotkeys_here`); the learner can change each in Settings > Hotkeys
  (567, decision 0273).
- `X11Hotkeys` grabs the combinations as the settings keep them
  ("ctrl+alt+shift+l", "f9").

## Why

- The grab needs no permission, no dialog and no portal, and it's the one
  mechanism that worked on X11 and on KDE.
- Grabbing on GNOME's Wayland session anyway would work only while an
  X11 window has the keyboard: the app would promise a key that does
  nothing over Firefox.
- Ctrl+Alt+L on Linux Mint would lock the screen instead, and the grab
  wouldn't even fail there in a Wayland session. A different set per
  desktop would make Help's words depend on the desktop.

## What would make us reverse it

- Testers on GNOME asking for hotkeys more than for the custom shortcut:
  then the portal (GNOME 48+) comes first.
- KWin changing its default for X11 apps' keys.
- Learners finding Ctrl+Alt+Shift awkward where Ctrl+Alt is free (GNOME,
  KDE): 567's Settings > Hotkeys lets each change it.

## How we'd reverse it

`OWN_MODIFIERS[Platform.LINUX]` (and `hotkeys_here`'s Linux case) for
the keys; `grab_works_here` for where the grab is used; a
`portal.py` beside `hotkeys.py` for the portal. An hour or two each.
