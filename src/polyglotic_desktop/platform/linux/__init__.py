"""Linux's adapters (decision 0038; polyglotic-hq 546, 547, 550), picked by
`main.os_adapters` for `linux` - `platform/windows/`'s and
`platform/macos/`'s counterpart. The app runs as an X11 program (XWayland
on Wayland desktops).

- `system.py` - the kernel's major version (protocol.md's `os`), the
  distribution, desktop and session (feedback's version), the XDG
  folders, the launch clock, the desktop's own error box;
- `secret_service.py` - the device token in the desktop's keyring (the
  Secret Service, through jeepney); a file only the user can read where
  there's no keyring;
- `one_copy.py` - one copy per user and data folder (a file lock in
  `$XDG_RUNTIME_DIR`);
- `pulse.py` - the sound server through libpulse (ctypes, the system's
  own copy);
- `capture.py` - everything the PC plays (the default output's monitor,
  by name) and the mic (never an output's monitor), following the
  server's changes; one app at a time and everything else (each app
  stream's own monitor, fixed to it, summed: 561, decision 0268);
- `apps.py` - the apps playing, one entry per app (its streams grouped by
  executable), for the app picker; `categories.py` - the known apps by
  their Linux executables, and those listed before they play;
- `devices.py` - the outputs and mics, by the server's names;
- `hints.py` - light or dark (the settings portal) and a metered
  connection (NetworkManager), as the desktop says them over D-Bus (571);
- `menu_entry.py` - the app's own menu entry and icon, written by the
  AppImage at each start (Velopack installs none);
- `on_top.py` - the caption windows, popovers and card above everything
  as override-redirect windows, their order kept by hand;
- `not_yet.py` - what the first Linux build doesn't have yet, each saying
  so through its port: hotkeys, dictation, Esc and
  clicks elsewhere read, the sample played aloud. The word card's voice is
  None in `main.linux_adapters`: the card never offers it;
- `startup.py` - starting at sign-in: an XDG autostart entry for the
  AppImage, off until the learner turns it on (571).

Every module imports on any OS (libpulse and D-Bus load on first use), so
the logic is tested on Windows and macOS with fakes; what needs Linux
itself - a sound server, a session bus - is run on GitHub's Ubuntu runners
(`.github/workflows/linux.yml`).
"""
