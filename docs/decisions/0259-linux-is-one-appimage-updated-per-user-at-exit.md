# 0259 Linux is one AppImage, built on Ubuntu 22.04, updated per user as it exits

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, in polyglotic-hq project 550 (Linux's slice 1),
  from 546's plan and 547's spike; the port itself is the user's
  (polyglotic-hq DECISIONS #243, 2026-11-20)

## Situation

The Linux app needs a package a learner can download and run on Ubuntu,
Fedora and KDE desktops, and that updates itself from the same signed feed
as Windows and the Mac (decisions 0017, 0019). Velopack, our installer,
packs Linux apps as an AppImage. 547's spike, on GitHub's Ubuntu runners,
found what that takes:
- a PyInstaller build runs only on the glibc it was built on or newer;
- Qt's X11 plugin needs libxcb-cursor0, which Ubuntu's, Fedora's and the
  other desktops' images don't install - without it the app exits at once,
  saying so only to a terminal;
- Ubuntu 22.04's fontconfig and FreeType, bundled, misread Fedora's font
  settings (45 complaints at each start);
- Velopack keeps downloaded packages in one folder for every user,
  `/var/tmp/velopack/<id>/packages`, which the first user's update makes
  theirs alone (mode 755): a second user of the PC can't update;
- Velopack's start-up (`App().run()`, which applies a downloaded update at
  the next start) can't be told about another packages folder.

## Decision

- **One file, `Polyglotic.AppImage`** - the same name at every version, so
  where the learner keeps it, and anything pointing at it, survives updates
  - on the `linux-x64-*` channels (`tools/package/pack.sh`).
- **Built in an `ubuntu:22.04` container** (glibc 2.35: Ubuntu 22.04+,
  Debian 12+, Fedora, Mint 21+), with uv's own Python and vpk at the pinned
  versions (`tools/package/linux_build.sh`).
- **libxcb-cursor0 and the xcb libraries bundled; fontconfig and FreeType
  left to the system** (the spec's `LINUX_SYSTEM`; `build.problems` fails a
  build that carries them). Qt's input-method plugins are kept (IBus).
- **Each user's downloads in their own cache**,
  `$XDG_CACHE_HOME/Polyglotic/packages`, given to Velopack as its locator
  (`adapters/velopack_updates.this_appimage`); the checked feed waits in
  `$XDG_CACHE_HOME/Polyglotic/verified-feed` (`main.verified_feed_folder`).
- **A downloaded update applies as the app exits**, not at the next start:
  the AppImage is replaced in place once the app has quit, and the next
  start is the new version. Restart now and "update required" work as on
  the other two.
- **A folder the learner can't change** (`/opt`, another user's) refuses the
  download before it starts (`DownloadFailed("NotWritable")`), and the log
  says to move the file into a folder of their own.

Proved by `.github/workflows/linux-package.yml` on the public copy:
linkage in clean Ubuntu 24.04, 26.04 and Fedora 45 containers, and the
update rehearsal (`linux_update_rehearsal.sh`) with no libfuse2, a second
user and a folder not theirs.

## Why

- An AppImage is what Velopack makes for Linux; it needs no install, no
  root and (Velopack 1.2's static runtime) no libfuse2. Flatpak's sandbox
  would change capture, and Flathub would own updates; Velopack has no
  `.deb` or `.rpm` (546, 1.7).
- Applying at exit rather than at start: the start can't see the per-user
  folder (Python's `App()` takes no locator), and replacing the file while
  nothing runs from it avoids a second restart at the start.

## What would make us reverse it

- Velopack's start-up gaining a locator (then the next start can apply, as
  on Windows and the Mac).
- A supported desktop older than glibc 2.35, or PySide6 needing a newer one
  than Ubuntu 22.04 has.
- Learners keeping the file where updates can't replace it, often enough
  that the app should offer to move it (as the Mac does out of
  translocation, decision 0205).

## How we'd reverse it

- Applying at start: drop `_apply_pending` and the `at_exit` hook in
  `velopack_updates.py`, and give `run_installer_hooks` the locator.
- Another build image: one line in `linux_build.sh` and the workflow.
