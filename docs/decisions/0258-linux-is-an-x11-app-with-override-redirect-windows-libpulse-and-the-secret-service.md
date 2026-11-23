# 0258 Linux: an X11 app whose floating windows are override-redirect, its sound through libpulse, its token in the Secret Service

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude (polyglotic-hq 550), from the user's "Can you do
  the linux port now?" (2026-11-20 ~16:54, DECISIONS #243), 546's plan and
  547's spike on GitHub's runners; reversible adapter choices. The
  desktops supported and anything a learner sees differently on Linux are
  the user's (546's section 6).

## Situation

`main.os_adapters` raised `NoOsAdapters` on Linux. The first Linux build
(546's slice 1) needs every port of `OsAdapters` answered: capture of
everything the PC plays and the mic, the device token kept safely, the
caption windows over whatever the learner watches, the folders, one copy
- and everything Linux doesn't have yet saying so through its port, as the
first Mac build did.

Linux has four desktops worth supporting (546 section 2) and two display
systems. Native Wayland gives a normal app no always-on-top, no placing of
its own windows and no click-through on GNOME. 547's runs on GNOME 46 and
51 and KDE 6.8 (headless, GitHub's runners, 2026-11-20): Qt's always-on-top
flag alone was hidden by KWin under every focused full-screen window
(0/52), and lost by GNOME after a lock or unlock over one (21 times in 55),
`raise_()` never bringing it back; an override-redirect window stayed on
top every time (80/80 first shows, 103/103 locks and unlocks). GNOME also
ignored a live change to a mapped window's input shape (the click went to
nobody).

## Decision

- **The app runs as an X11 program everywhere** (XWayland on Wayland
  desktops): `OsAdapters.qt_platform` is `xcb` on Linux, and `main` sets
  it before Qt starts (`use_qt_platform`; offscreen and minimal left
  alone), so a Wayland session's own choice never applies.
  `platform/linux/` beside `windows/` and `macos/`, picked by
  `main.linux_adapters()`; only `main` imports it (import-linter's
  `os-in-one-place`, now naming it).
- **Every floating window is override-redirect on Linux:** the caption
  windows, the joined window, the settings popover, the lookup and
  sentence cards and the dictation sign carry `ui_next.above_all.ABOVE_ALL`
  (Qt's `X11BypassWindowManagerHint`; nothing on Windows and macOS).
  `platform/linux/on_top.LinuxOnTop` keeps their order by hand, as the
  Mac's `lifted` does: the windows given raised bottom first, then the
  app's other override-redirect windows showing above them.
- **Clicks passing through a window change only while it's hidden**
  (`above_all.set_click_through`): hidden, flag changed, shown again -
  never a live input-shape change. Tested
  (`tests/ui_next/test_locked_by_remapping.py`).
- **Sound through libpulse**, the system's own copy, by ctypes
  (`pulse.py`): everything the PC plays is the default output's monitor
  found by name, the mic the chosen or default input but never an
  output's monitor (no microphone then), streams never moved by the server
  (`PA_STREAM_DONT_MOVE`), the server's changes followed. One app at a
  time says no (`app_capture_support`) until slice 2.
- **The token in the Secret Service through jeepney** (a new Linux-only
  dependency, MIT, pure Python), on the plain session; where there's no
  keyring at all, a file only the user can read in `$XDG_STATE_HOME`; a
  keyring that won't open means not signed in, never a crash.
- **XDG folders:** data in `$XDG_DATA_HOME/Polyglotic`, the lock in
  `$XDG_RUNTIME_DIR`. `os` is `linux-<kernel major>` (protocol.md;
  the server already accepts it), channels `linux-x64-*`.
- **The distribution's own roots** are loaded for secure connections
  (`connection.tls.linux_roots`), as the Mac's are (decision 0236).

Proven on GitHub's Ubuntu runners through the public Linux copy
(`.github/workflows/linux.yml`, never run in this private repo).

## Why

- The ports already say what's needed; only the adapters and the windows'
  flags change, so the interface's logic is the same on every OS.
- Override-redirect was the only arrangement that never failed in 547; its
  price (no window manager focus or order for these windows) fits windows
  that never take focus and are dragged by the app's own handles.
- libpulse is a plain C library ctypes can call; PipeWire's own API is
  built from header macros. PortAudio isn't on Ubuntu, `pactl`/`parec`
  aren't either.
- jeepney rather than `secretstorage` (which brings `cryptography`) or
  QtDBus (which wants Qt's event loop on the calling thread).
- Not taken: native Wayland (a lesser product on each desktop: 546 1.2);
  keep-above with override-redirect only over full-screen windows (two
  states, and GNOME loses keep-above after a lock anyway: 547).

## What would make us reverse it

- GNOME ships a keep-above or zones protocol for Wayland clients, or
  XWayland is dropped by a desktop we support.
- Override-redirect windows misbehave on a real desktop (focus a popover
  needs, a compositor that hides them) in the live-USB check.
- The plain session refused by a keyring a supported desktop ships.

## How we'd reverse it

`ABOVE_ALL` is one constant; `LinuxOnTop` one class; `linux_adapters` in
`main.py` picks every piece. A native Wayland build would be new
adapters (layer-shell where there is one) behind the same ports. Another
D-Bus client would replace `SecretService`'s calls only.
