# 0101 One copy per user and data folder: a named mutex holds it, a local socket asks it to show

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user asked for it (polyglotic-hq 310, 2026-11-14:
  "you should only be able to open 1"); the mechanism is Claude's
  reversible choice, recorded here

## Situation

Nothing stopped a second copy of the app. Two copies of one install share
one settings file, one outbox, one learning file and the log; each takes
the hotkeys and the tray, and each opens its own sessions with the server.
Saved settings could be overwritten by the other copy's older ones.

A second start also ran Velopack's start-up before anything else, and
with a downloaded update waiting, Velopack applies it there: its `apply`
force-stops every process running from the install folder
(`force_stop_package` in Velopack's `apply_windows_impl.rs`, read
2026-11-14) - the copy the learner was using ended without saving.

## Decision

- **One copy per Windows user and data folder.** The copy that runs holds
  a `CopyLock` (`ports/one_copy.py`): on Windows a named mutex,
  `Local\Polyglotic-<hash>` (`platform/windows/one_copy.py`), the hash
  of the user's name and the data folder's full path. A copy with a data
  folder of its own - a test's, a copy from source beside the installed
  one, QA's on private desktops - has its own name and runs beside it.
- **A second start** (`main.this_copy`, first thing after asking whose copy
  this is) doesn't take the lock: it asks the copy that holds it, on Qt's
  local socket of the same name (`ui/one_copy.py`), to bring its main
  window forward, as the tray's Open does, and exits with 0. It first lets
  that process come to the front (`AllowSetForegroundWindow`, the
  `LetToFront` port), since Windows lets only the program the learner is
  using bring a window forward.
- **Before Velopack and before anything opens:** the settings, the outbox,
  the log, the update check, a window. The installer's hooks
  (`--veloapp-*` arguments) and `--check-install` don't take part: they
  run as before.
- **The cases:** a copy still starting answers once its interface thread
  runs (a start waits up to 8 s, trying the lock again between asks); a
  copy quitting stops answering at `aboutToQuit`, so a start waits for it
  to end and then runs (an update's restart, a Quit a moment ago); a copy
  that crashed left nothing - Windows deletes the mutex with its last
  handle; a copy that doesn't answer in 8 s: the start says so in a box
  (in the learner's interface language, the settings read and never
  written) and exits with 1; started in the tray (`--in-tray`, as Windows
  starts it) while a copy runs: it exits with 0 and shows nothing.
- **Packed:** `PySide6.QtNetwork` and `Qt6Network.dll` are in the build
  again (about 2.8 MB; project 005 had left them out as unused). Its TLS
  and network-information plugins stay out.

Tested: `tests/ui/test_one_copy.py`, `tests/test_windows_one_copy.py`,
`tests/ui/test_main_one_copy.py` (the app itself, twice, in two
processes), and a real-window test on a private desktop
(`tests/test_private_desktop.py`).

## Why

- **A lock that can't go stale.** A lock file outlives a crash, or needs a
  process ID that Windows may give to another program later. The mutex is
  the OS's: it goes with the process however that ends.
- **The socket alone isn't a lock:** on Windows two Qt local servers can
  listen under one name (tried 2026-11-14; Qt's documentation says so), so
  two copies starting together could both run.
- **Qt's local socket for the asking** works the same on macOS and Linux
  later, and its timeouts give the "doesn't answer" case. The Win32
  alternative - a hidden message window found with `FindWindowEx` and
  `SendMessageTimeout` - needs no extra DLL but is Windows-only and runs
  Python inside a window procedure; it stays the way back if QtNetwork
  causes trouble.
- **The user's name in the hash:** the mutex is per session already, but a
  local socket's name is machine-wide; two people using one data folder
  (out of scope) would otherwise ask each other's copies.

## What would make us reverse it

- Testers who need two copies on one data folder (none known).
- QtNetwork in the build causing trouble: a size or start-time budget
  broken by it, or an antivirus flagging the named pipe.
- An elevated copy (run as administrator) that a normal start can't reach:
  it gets the "isn't responding" box today.

## How we'd reverse it

- Without the guard: drop `this_copy` and `SecondStarts` from `main` (a
  few lines); the modules can stay.
- Another way of asking: a new `ui/one_copy.py` (or a Windows adapter
  behind a new port) - `main` and the lock don't change.
