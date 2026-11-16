"""The Mac's adapters (decision 0038; polyglotic-hq 408, 409), picked by
`main.os_adapters` for `darwin` - `platform/windows/`'s counterpart.

- `system.py` - macOS's name and version, the data folder (decision
  0185), the launch clock, the menu bar's light or dark, the error box;
- `keychain.py` - the device token in the Keychain;
- `one_copy.py` - one copy per user and data folder (a file lock);
- `not_yet.py` - what the first Mac build doesn't have yet, each saying so
  through its port (hotkeys, dictation's key and typing, staying above
  full-screen apps, the sample played aloud);
- `capture.py` - one app, everything else, the whole system (Core Audio
  taps, through catap) and the mic (PortAudio), each to 16kHz mono; a
  permission not given said as `NOT_ALLOWED` (polyglotic-hq 411);
- `apps.py` - the apps with sound, an app's helper processes with it;
- `devices.py` - the outputs and mics, by Core Audio UID;
- `categories.py` - the known apps, by bundle ID;
- `cf.py` - Core Foundation and Security through ctypes.

Every module imports on any OS (the frameworks load on first use), so the
logic is tested on Windows and Linux with fakes; what touches macOS itself
is marked `macos_only`.
"""
