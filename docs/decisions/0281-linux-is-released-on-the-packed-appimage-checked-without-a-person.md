# 0281 Linux is released on its packed AppImage, checked without a person on GitHub's runners

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, in polyglotic-hq project 574 (Linux's slice 7),
  from 546's plan, section 3; the port itself is the user's
  (polyglotic-hq DECISIONS #243, 2026-11-20)

## Situation

Slices 1-4 (polyglotic-hq 550, 561, 571) checked Linux on GitHub's own
Ubuntu runners through the public Linux copy, but every tour ran the app
from source: only `linux-package.yml` started the packed AppImage, and then
only for its own `--check-install` and the update. The package is what a
learner downloads - PyInstaller's loader, the libraries it bundles or
leaves to the system, the Qt plugins `polyglotic.spec` keeps, the
AppImage's runtime - and none of the tours had seen it caption, sign in,
draw its windows or read its tray. 546's section 3 asked for seven checks
"on the mirror, in the release script": linkage, starts, capture, windows,
keyring, update, Fedora.

There is no Linux desktop of our own to test on (this PC has no room for a
VM; 546's section 3), and only the user's live USB for what a person sees.

## Decision

- **`.github/workflows/linux-release.yml`** builds the AppImage as a release
  builds it (`tools/package/linux_build.sh` in `ubuntu:22.04`) and checks
  that file, on the public copy only (every job refuses a private repo):
  - **package:** linkage on clean Ubuntu 24.04 and 26.04 with the app's own
    `--check-install`; the update rehearsal (in place, as the app exits,
    no FUSE 2, a second user, a folder not theirs); linkage and the update
    on Fedora 45 with FUSE 3 (`tools/package/linux_update_fedora.sh`);
  - **capture:** the sound server's and the keyring's own tests in a
    desktop session (from source: they test the libraries' calls);
  - **desktops:** the packed AppImage's tour (`tools/linux_packed_tour.sh`,
    `tools/linux_packed_tour.py`) on Ubuntu 24.04's GNOME, Ubuntu's GNOME
    with its AppIndicator tray, Fedora 45's GNOME, KDE Plasma 6 and Xfce
    with no keyring at all. The tour is only the outside - a stand-in
    server over TLS with a root added to the system's store, the players,
    the token kept where the app looks, a returning learner's data folder -
    and checks the app as a person's desktop would see it: its `hello`, the
    sources the stand-in hears, the X server's windows, the desktop's own
    picture of its screen, the tray's menu over D-Bus, the portal's file
    chooser asked for on the session bus. Nothing of the tour runs inside
    the app;
  - **verdict:** the seven checks, and the desktops' manners, as one answer
    (`tools/linux_release_verdict.py`); a part that didn't arrive is red.
- **The release script starts it** (polyglotic-hq's `publish-alpha.sh
  VERSION linux-check`): a snapshot of the build's commit pushed to the
  public copy's `linux-release-VERSION` branch starts the run; the script
  waits, keeps the verdict and the pictures, deletes the run's artifacts
  and exits 1 on red. A Linux publish runs it first and stops there.
- **Nothing in it reaches the live server:** no invite, no token, no secret;
  the packed app's update feed is a folder of nothing, and the stand-in
  names Linux's channel.

## Why

- The source and the package differ in exactly the ways that broke the Mac
  (512: the packed app's OpenSSL and its roots) and Linux before
  (550: `libxcb-cursor`; 561: the loader's library path in a link's
  browser; 571: the dropped platform themes). A check of the source can't
  see any of them.
- Checking from outside needs nothing in the product: no test hooks in the
  app, no build of its own for the checks. The Mac's in-app checks
  (`--check-parity`, `--check-capture`) were the alternative; they test
  the app's own view of itself, not a desktop's view of the app.
- GitHub's runners are free for a public repository, and the copy is the
  same tree the public Mac copy already publishes (DECISIONS #190).

## What would make us reverse it

- The runners' desktops drifting from what learners run (a headless shell
  that no longer stands for a person's), or the live USB finding what the
  tours call green broken: the tour's checks are then the wrong ones.
- A Linux build published from somewhere else (Flathub, a distribution's
  package): its own checks there.
- The free runners going away for public repositories: the same jobs on a
  rented VM or gpubox.

## How we'd reverse it

- Back to source tours: drop the `desktops` job, the rest stands alone.
- Another runner: `runs-on` and the `if` on each job; the scripts only
  need `GITHUB_ACTIONS=true` and root.
- The release script's step is one `case` branch in `publish-alpha.sh`.
