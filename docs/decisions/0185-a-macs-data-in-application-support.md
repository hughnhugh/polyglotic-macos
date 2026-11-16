# 0185 On a Mac, the user's data lives in `~/Library/Application Support/Polyglotic`

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** polyglotic-hq project 409 (the app starts on a Mac),
  from 408's plan and Apple's file-system guidelines; Claude reviews it
  with the pull request. The folder name follows the app ID,
  `Polyglotic`, as on Windows (decision 0014).

## Situation

The first Mac build (polyglotic-hq 408, 409) needs a data folder: settings,
`learning.sqlite`, `outbox.sqlite`, the logs and the one-copy lock files.
On Windows it's `%APPDATA%\Polyglotic`, outside the installer's folder, so
reinstalling or uninstalling never deletes what the learner built
(decision 0014). A Mac app is a bundle in `/Applications` that is replaced
whole by an update or a new zip, and dragged to the Bin to remove it -
nothing inside it may hold the learner's data.

## Decision

- `platform/macos/system.data_folder()` is
  `~/Library/Application Support/Polyglotic`.
- The one-copy lock files (decision 0101's `CopyLock` on a Mac) live in its
  `locks/` folder.
- The device token stays out of it, in the Keychain
  (`platform/macos/keychain.py`), as Windows keeps it in Credential Manager.
- `--data` still points the app at any other folder, as on Windows.
- Checked by `tests/test_macos_adapters.py`
  (`test_data_folder_is_application_support`).

## Why

- **Where macOS apps keep the user's own files:** Apple's File System
  Programming Guide puts "app-created support files" in
  `Library/Application Support/<bundle or app name>`, backed up by Time
  Machine and untouched when the app is removed (from memory, not
  re-checked on 2026-11-16).
- **The same name as Windows'** (the app ID), so what's documented for one
  reads for the other.
- **Alternatives not taken:**
  - `~/Library/Containers/...`: only for a sandboxed app (the Mac App
    Store's); the first builds aren't sandboxed. Moving there is the
    reversal below.
  - `~/Library/Caches`: macOS may empty it; the learner's words aren't a
    cache.
  - A dot-folder in the home folder (`~/.polyglotic`): what command-line
    tools do; hidden from the learner and not where Mac users look.

## What would make us reverse it

- A sandboxed build (the Mac App Store, or a hardened build that needs
  the sandbox): its data lives in its container.
- Bundle-ID-named folders becoming expected (`com.polyglotic.app`) once the
  app is signed with an identity.

## How we'd reverse it

A new record and one function, `data_folder`, plus a move at the first
start of the new build: if the old folder exists and the new one doesn't,
move it (the files are closed then; one copy runs). An hour's work and a
test; no tester has Mac data yet (2026-11-16).
