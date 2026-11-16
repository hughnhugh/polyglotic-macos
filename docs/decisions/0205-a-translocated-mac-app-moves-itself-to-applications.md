# 0205 A Mac app run from macOS's temporary copy offers to move itself to Applications

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** Claude, a reversible technical choice inside the user's
  "the Mac updates itself" request (polyglotic-hq 430's top next, 433's
  brief).

## Situation

Since decision 0202 the Mac updates itself through Velopack. But macOS
runs a downloaded (quarantined) app that's opened anywhere other than where
Finder moved it - typically straight from Downloads, after Safari unzipped
it - from a read-only copy at a random path,
`/private/var/folders/.../AppTranslocation/<UUID>/d/Polyglotic.app` (App
Translocation, macOS 10.12 and later). Velopack 1.2.161 doesn't look for
it: its apply step would try to replace that copy, and the tester would
silently never update. The site's steps say "Move Polyglotic to
Applications, then open it there", but nothing in the app checked.

## Decision

- At its start (after the interface language, before the first run's
  screens), the packed Mac app asks `ports.system.Translocation` whether it
  runs translocated: its path, or Security's `SecTranslocateIsTranslocatedURL`
  (`platform/macos/translocation.py`).
- If so, it asks once - whatever the answer (`applications_offered` in
  settings) - **Move Polyglotic to Applications?**, with how to do it by
  hand in the same box (`ui/move_to_applications.py`).
- **Move to Applications** moves the real app (found with
  `SecTranslocateCreateOriginalPathForURL`, never the copy) into
  `/Applications`, or `~/Applications` when the learner can't write there.
  A Polyglotic already there goes to the Bin, not deleted. Then the
  `com.apple.quarantine` attribute comes off the moved app, and a small
  shell waits for this process to end and `open`s the app from its new
  place. If the move fails, a second box says plainly how to do it by hand.
- Windows has no such thing: `OsAdapters.translocation` is None there.

## Why

- **The quarantine attribute comes off** because otherwise macOS would
  translocate the app again, even in Applications: only a move in Finder
  clears translocation. The learner already chose Open Anyway for this
  copy, and the bundle's signature is unchanged; an update Velopack
  installs carries no quarantine either (0202). The well-known LetsMove
  library, used by many Mac apps outside the App Store, does the same.
- **Asked once**, as "Start Polyglotic with Windows?" is (polyglotic-hq 176):
  a learner who says Not now still has the steps in the box and the help
  page, and isn't nagged at every start.
- **Before the first run**, because moving restarts the app: better before
  the learner answers anything.
- **Not taken:** quitting with only an explanation (leaves the work to the
  learner, the failure the brief names); moving silently (moves a file the
  learner didn't ask us to move); a `.dmg` with an Applications shortcut
  (still translocated if opened from the mounted image, and needs its own
  build work - a possible later addition).

## What would make us reverse it

- Velopack detecting translocation itself and moving the app (then this
  is redundant).
- A Developer ID and notarised, stapled releases where macOS no longer
  translocates opened-in-place apps for us, or a `.pkg` installer that puts
  the app in Applications.
- Testers reporting that the move or the restart fails on their Macs.

## How we'd reverse it

Delete `platform/macos/translocation.py`, `ui/move_to_applications.py`,
the `Translocation` port, `OsAdapters.translocation`,
`main.moved_to_applications` and its call, and the `applications_offered`
setting (an unknown key in a settings file is kept and ignored), with
their tests and the seven strings.
