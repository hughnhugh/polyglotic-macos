# 0188 The packed Mac app tries its capture on GitHub's Mac, never on Windows

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, within the user's "the Mac now" (2026-11-16,
  polyglotic-hq topic #10) and project 412's brief. The job's first run
  waits for the user's decision on macOS minutes (polyglotic-hq
  DECISIONS #190).

## Situation

Mac capture (0187) loads two native libraries from beside its packages'
code: catap's `libcatap_coreaudio.dylib` and sounddevice's PortAudio. No
PyInstaller hook collected catap's, so the packed `Polyglotic.app` would
have started, passed `--check-install` (which captures nothing) and then
heard nothing. 411's ten checks also needed a Mac, and nothing ran them.

## Decision

- **The bundle carries both libraries:** the spec collects catap's
  (`collect_dynamic_libs("catap")`), sounddevice's hook collects
  PortAudio's, and the spec drops the Windows PortAudio DLLs that come in
  the same macOS wheel. `build.MACOS.parts` lists both, so a build without
  them fails with "missing: ...". PortAudio's licence text, which the
  wheel doesn't carry, ships in `licenses/PortAudio/LICENSE.txt`.
- **A hidden `--check-capture REPORT`:** the app captures what the Mac
  plays and the default mic for 5 s each, and writes for each how many
  pieces arrived, how many seconds, the loudest sample, the capture's
  name and its error. It never writes the audio. The macOS job runs it on
  the packed app while it plays the app's own FLEURS sample into
  BlackHole. **It refuses on Windows**, because there it would hear the PC
  it runs on, and the self-hosted runners are the user's own PC.
- **411's checks run as the job's `capture` part**
  (`tools/macos_capture_checks.py`), after `pack` and `measure`. Each check
  ends as pass, fail or unknown. Only a fail fails the job; unknown means
  the machine didn't let the check see.

## Why

- Only a capture inside the bundle shows that the libraries load from
  where PyInstaller put them, with the bundle's signature and paths.
  `--check-install` promises to capture nothing, and it runs on the
  user's PC in the Windows release build, so the capture is a separate
  mode.
- A refusal inside the app itself is a stronger guard than relying on
  nobody running the mode on the user's PC.

## What would make us reverse it

- A Mac of our own, or a tester's, where the packed app is tried by hand.
- Velopack's macOS package bringing an install check of its own that
  captures.

## How we'd reverse it

Delete `check_capture`, its `_Heard`, the flag and the `packed` step of
`tools/macos_capture_checks.py`. The libraries stay in `MACOS.parts`.
