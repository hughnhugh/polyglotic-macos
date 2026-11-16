# 0016 The app is packed by PyInstaller as one folder, built and checked by `tools/package/build.py`

- **Status:** accepted; when `package.yml` runs replaced by
  [0021](0021-installer-built-on-main-not-pull-requests.md) (2026-11-05)
- **Date:** 2026-11-05
- **Decided by:** the stack - Python and PySide6, PyInstaller one folder,
  Velopack - the user, 2026-11-04 (polyglotic-hq project 005; README).
  How the build is done: project 035 (D5) on 2026-11-05, to project 032's
  checklist for D5 (items 4 and 5). Claude reviews it with the pull
  request.

## Situation

Testers install the app with Velopack, which packs a folder. Project 005
measured a PyInstaller one-folder build of a spike (0.34s to first paint,
38-53MB to download, Defender clean). The real app adds the dictionaries
(decision 0009), libsndfile, pydantic and websockets, and must ship
without tests, environment files or tokens, with every licence it owes.

## Decision

- **PyInstaller one folder, no console**, from the locked environment
  (`uv sync --locked --no-default-groups --group package`: the app's own
  dependencies and PyInstaller, pinned in `uv.lock`; nothing from the dev
  group). One file is never used: it unpacks to a temporary folder on every
  start, and Velopack wants a folder anyway.
- **The recipe** is `tools/package/polyglotic.spec`: the app's code from
  `src/` (so `tests/` and `tools/` can't get in), the speech-detection
  model, the release stamp (decision 0015). It leaves out what the app
  never loads: Qt's software OpenGL, Qt's translations, network, TLS and
  image plugins, and libraries' build and test helpers. No UPX.
- **Beside `Polyglotic.exe`**, as separate files: `dictionaries/` (with
  `CREDITS.md`), `THIRD_PARTY_NOTICES.md`, `licenses/` (each bundled
  package's licence files, Python's, and the LGPL-3.0 and GPL-3.0 for Qt,
  which PySide6's wheels don't carry - committed in
  `tools/package/licenses/`).
- **Checked by the build:** what the app needs is there; no `.env` file,
  nothing shaped like a device token (`pgd_` and 43 characters) in any file,
  no `tests` or `tools` module in the code archive; then the packed app
  runs `--check-install` - Qt offscreen, both dictionaries, the main window
  and overlays, the model on a second of silence, the Opus encoder, and
  the stamped version - without showing, capturing or connecting. Any
  failure fails the build.
- **Installed, the app logs to a file** (`logs/polyglotic.log` in the data
  folder, rotated at 1MB, 3 kept): it has no console. Logs stay
  content-free, as everywhere.
- **On pull requests** (on `main` since decision
  [0021](0021-installer-built-on-main-not-pull-requests.md)) that could change the result (`src/`, the tools,
  `pyproject.toml`, `uv.lock`, the notices), `.github/workflows/package.yml`
  builds it the same way and keeps the folder three days as an artifact.

## Why

- **Proven and cheap:** project 005 measured it; the user and Claude Code
  already work in Python.
- **A build that checks itself:** the release is made by a workflow
  nobody watches; the checks and the self-check make a broken or leaky
  build fail there, not on a tester's PC.
- **Licences:** Qt under the LGPL-3.0 asks for its text, the GPL's, and
  that users can replace the Qt libraries - one folder keeps them as
  separate DLLs.
- **Alternatives not taken:** Nuitka (compiles to C: smaller, slower to
  build, antivirus results untested - project 005's "what's left");
  `pyside6-deploy` (Nuitka underneath); PyInstaller one file (above).

## What would make us reverse it

- Antivirus engines flagging the build (PyInstaller's bootloader is a
  known false-alarm source): sign it first (TOPICS.md #2), then consider
  Nuitka.
- The download growing past the budget (80MB with dictionaries, MVP.md):
  trim further, or compress the dictionaries.

## How we'd reverse it

The build is two files (`polyglotic.spec`, `build.py`) and the app knows
only `main.installed()` and `main.dictionaries_folder()`. Another packer
means a new recipe that produces the same folder layout; Velopack and the
release workflow don't change. About a day, plus measuring.
