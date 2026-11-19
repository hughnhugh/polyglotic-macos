# 0243 The Mac is checked as a learner's Mac, on GitHub's Mac, every release

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude (polyglotic-hq 523), from the user's request of
  2026-11-18 ~22:10: "try to make more foolproof ways of testing mac to
  minimise human tester failure loop."

## Situation

Two Mac failures reached people on 2026-11-18 although every macOS job had
passed. Sign-in failed on every learner's Mac (polyglotic-hq 512): GitHub's
Mac has python.org's Python, whose own root list the packed app read, and a
learner's Mac doesn't. A caption window couldn't be resized and its settings
opened behind it (515): the job never moved a real mouse with another app in
front. The checks proved the app on a developer's machine, not on the Mac a
learner has. And 17 of the Mac's own tests failed for wording, so a red
suite told nothing.

There is no Mac here and no Mac tester to lean on before a release; GitHub's
macOS runners on the public copy are free (DECISIONS #190).

## Decision

The macOS job gets a `learner` part (`macos.yml`; off by default, turned on
with tests, pack, parity and updates by the mirror's `--parts learner`, and
by `publish-mac.sh`'s release build). Each check fails the job on a fail:

- **What's hidden:** python.org's Python, Homebrew, the developer tools and
  Xcode are moved aside while the packed app is checked
  (`tools/macos_learner_checks.py --hide`/`--show`; also around 512's
  `--check-tls` in pack). The build's own Python is pinned to uv's own
  build at an exact version (`UV_PYTHON`), so nothing the checks need is
  hidden.
- **What the app links:** every Mach-O in the bundle loads only from the
  bundle or macOS (`/System`, `/usr/lib`).
- **The download path:** the release's portable zip in `~/Downloads` with
  Safari's quarantine, unpacked by Archive Utility; it must verify with the
  built app's designated requirement; Gatekeeper's verdict is kept (a
  self-signed app is rejected until notarised; a broken seal fails). Opened
  as a double-click; Gatekeeper refuses it, it's marked approved as Open
  Anyway marks it, and it must start translocated, offer the move to
  Applications, move, lose its quarantine and open again from there.
- **A fresh account:** a new macOS user (`sysadminctl`) runs the installed
  app's `--check-install` and `--check-tls` (now also opening the session's
  WebSocket over `wss`).
- **The update learners get:** the published release (polyglotic.io's zip)
  installed; this build served from a feed in a folder as the next version;
  found, downloaded, applied, restarted; settings file, keychain item and
  designated requirement unchanged
  (`tools/package/macos_update_from_release.sh`).
- **As a user uses it:** 515's checks (real mouse, hover with another app in
  front, popovers over full screen, window levels) stay in `parity`; 515's
  settings sweep becomes standing (`tools/macos_settings_sweep.py`): every
  setting changed and put back, judged.
- **Sound out:** a recorded word and macOS's "Say it" played to BlackHole,
  heard back and judged for silence, clipping, level, length and pitch
  (`parity`'s `said_recorded`, `said_by_macos`).
- **The Mac's own suite** says each OS's words, so a red test is a real one.

## Why

- Every check runs where it's free and repeatable, with no person, and on
  the very build a release ships (`publish-mac.sh` runs it on the release
  run itself), so the release can't skip it.
- Hiding rather than a clean image: GitHub offers no bare macOS image, and
  a VM of our own costs money and upkeep. Moving the folders aside is what
  512 proved works, and it's undone at the end.
- A fresh user, not the runner's: the runner's account has years of
  developer state; a learner's has none. A GUI session for a second user
  isn't possible on the runner, so that user runs the windowless checks.
- Not checked by a machine, said plainly: a real trackpad and cursor,
  Retina rendering, real speakers and a person's ear, full-screen video
  apps (docs/macos.md, "What still needs a person"). Those stay a
  two-minute list in each preview's what-to-try.

## What would make us reverse it

- A learner's Mac failure that this part passed: then what it hides or how
  it opens the app is wrong, and the gap is added here.
- The part taking so long on releases that it's skipped (it adds about
  20-25 minutes), or GitHub charging for public-repo macOS minutes.
- Notarisation (Apple Developer Program): Gatekeeper's verdict would then
  be "accepted", and Open Anyway would no longer need emulating.

## How we'd reverse it

Turn the `learner` input off (one line in the mirror's `--parts` and in
`publish-mac.sh`); the tools stand alone and nothing in the app depends on
them. Undoing the pinned Python is removing two lines of `env:`.
