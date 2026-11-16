# 0038 The OS's adapters are picked in one place, at start, and nothing else imports them

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** Claude, for polyglotic-hq project 179 (the desktop's
  seams), from project 171's advice (`projects/171-mac-and-linux`,
  RESEARCH.md sections 4 and 7) and DECISIONS.md #71. Reversible - a
  technical choice. No behaviour change on Windows.

## Situation

The app runs on Windows only, but macOS and Linux are on the plan
(DECISIONS.md #71). Project 171's probe imported every module on Linux:
137 of 150 imported, and the 13 that failed were the Windows modules plus
`main` and `harness`, which imported them at the top. Because 41 test
files import `main`, none of those could even be collected off Windows.

Capture, the app list, the device token's store, updates, settings and
storage were already behind ports. The window-level and input pieces -
staying on top, hotkeys, key state, the taskbar's look - and the OS's
version and the data folder weren't: `main` (and `connection.app`, for the
version) called Windows directly. `OnTop` and `KeyState` were stated in
`ui_next`, not `ports/`.

## Decision

- **One function picks the OS:** `main.os_adapters()` returns the OS's
  adapters (`main.OsAdapters`) - capture, the app list, the device token's
  store, hotkeys, key state, staying on top, the foreground watch, the
  taskbar's look (and, since 245, the ID it knows the app by: decision
  0051), the OS's name and version, the data folder, the start
  failure box, the launch clock, and (since 176) the sample's sound
  (`platform.sample.SoundOut`) and starting at sign-in
  (`ports.startup.StartWithWindows`) - importing `platform.windows` (and
  `adapters.windows_credentials`) only when it's called. On an OS with no
  adapters it raises `NoOsAdapters`, naming what's missing. `main()` and
  `--check-install` call it; nothing else does.
- **The ports are in `ports/system.py`:** `OnTop`, `ForegroundWatch`,
  `Hotkeys`, `KeyState`, `LightTaskbar`, `OsVersion`, `DataFolder`,
  `ErrorBox`, `LaunchClock` (audio stays in `ports/capture.py`, the token
  in `ports/credentials.py`). The Windows adapters are unchanged; the OS's
  name and version (from `connection.app`) and the data folder (from
  `main`) moved, as they were, to `platform/windows/system.py`.
- **`AppInfo` carries the OS's version number** (`os_version`) beside its
  name, so a feedback report takes it from there; `AppInfo.this_app(os,
  os_version)` is given both by `main`.
- **Enforced:** import-linter's `os-in-one-place` contract (a `protected`
  contract): only `main` and `harness` import `platform.windows` or
  `adapters.windows_credentials`. The harness is a Windows-only developer
  tool (it plays audio with `winsound`) and stays so. A test
  (`tests/test_os_in_one_place.py`) loads `main` in a fresh interpreter
  and checks no Windows module came with it.
- **Type-checked as the other OSes see it:** `tools/mypy_platforms.py`
  runs `mypy --platform linux` and `--platform darwin` in CI; errors in
  the Windows-only modules are counted (34 on 2026-11-08, all Windows API
  names), any other fails. Tests that need Windows itself carry the
  `windows_only` marker and are skipped elsewhere.
- **Tested on Linux:** CI's `Checks (Linux)` job runs the import rule and
  every test but the `windows_only` ones on the self-hosted Linux runner,
  with Qt's system libraries unpacked into the job's folder
  (`tools/linux_qt_libs.sh`: the runner can't install packages).

## Why

- ENGINEERING.md already says `main` is the one place that wires
  everything; picking the OS there keeps that true for a second OS, and
  the import-linter contract keeps Windows code from leaking into shared
  modules (`platform`'s speech pipeline sits in the same package as
  `platform.windows`, so the layers contract alone couldn't stop it).
- Lazy imports in one function rather than a `platform/__init__` that
  picks: the device token's store is an adapter, and `platform` mustn't
  import `adapters`; `main` may import both.
- A dataclass of callables rather than a registry or plugin entry points:
  one OS today, two more planned, no need to find adapters at run time.
- Ports for the small pieces now, which ENGINEERING.md's "no abstraction
  without a second use" would otherwise delay: the second use (macOS and
  Linux) is planned, and 171 found these were what kept `main` from
  loading anywhere else.

## What would make us reverse it

- macOS or Linux dropped from the plan for good: the ports cost little,
  but `os_adapters` could go back to plain imports.
- A third kind of build (a web or mobile client sharing this code) that
  needs adapters picked by something other than `sys.platform`.

## How we'd reverse it

- Back to direct imports: `main` imports the Windows modules at the top
  again and the `os-in-one-place` contract goes - an hour.
- Picked another way: `os_adapters` is the one place to change.
