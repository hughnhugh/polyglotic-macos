"""The Mac's adapters (decision 0038; polyglotic-hq 408, 409), picked by
`main.os_adapters` for `darwin` - `platform/windows/`'s counterpart.

- `system.py` - macOS's name and version, the data folder (decision
  0185), the launch clock, the menu bar's light or dark, the error box;
- `keychain.py` - the device token in the Keychain;
- `one_copy.py` - one copy per user and data folder (a file lock);
- `hotkeys.py` - ⌃⌘L, P and H wherever the learner is (Carbon's
  `RegisterEventHotKey`; polyglotic-hq 428);
- `voices.py` - the word card's voice: macOS's voices (AVFoundation), each
  word played on the default output;
- `startup.py` - starting at sign-in, as a login item (`SMAppService`);
- `not_yet.py` - what the Mac build doesn't have yet, each saying so
  through its port (the sample played aloud);
- `on_top.py` - the caption windows over full-screen apps and on every
  Space: panels at the screen-saver level, in an app that is an accessory
  (no Dock icon) for its whole run (polyglotic-hq 429, decision 0201);
- `hold_key.py`, `text_input.py` - dictation's key (Carbon's hotkeys, or
  the modifiers' state) and its words typed into the front app as
  Unicode key events, with the Accessibility permission (429);
- `keys.py` - Esc, Backspace and clicks elsewhere, read for dictation, the
  settings popovers and the pinned card: AppKit's global monitor, only
  while asked about (polyglotic-hq 438);
- `window_list.py` - the windows on screen, front to back: numbers,
  levels and owners only;
- `capture.py` - one app, everything else, the whole system (Core Audio
  taps, through catap) and the mic (PortAudio), each to 16kHz mono; a
  permission not given said as `NOT_ALLOWED` (polyglotic-hq 411);
- `apps.py` - the apps with sound, an app's helper processes with it;
- `devices.py` - the outputs and mics, by Core Audio UID;
- `categories.py` - the known apps, by bundle ID;
- `cf.py` - Core Foundation and Security through ctypes;
- `objc.py` - Objective-C's runtime through ctypes (messages, blocks).

Every module imports on any OS (the frameworks load on first use), so the
logic is tested on Windows and Linux with fakes; what touches macOS itself
is marked `macos_only`.
"""
