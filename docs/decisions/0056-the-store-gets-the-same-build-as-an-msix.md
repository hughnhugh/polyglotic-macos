# 0056 The Microsoft Store gets the same build, packed again as an MSIX; the Store updates that copy

- **Status:** accepted
- **Date:** 2026-11-09
- **Decided by:** polyglotic-hq project 264, for DECISIONS.md #102 (the
  user, 2026-11-09 ~02:35: the Store is the beta's main Install, the
  unsigned download second). Claude reviews it with the pull request.

## Situation

- Windows warns about our unsigned installer (SmartScreen), and Smart App
  Control blocks it. A package the Microsoft Store publishes is signed by
  Microsoft, so it meets neither (polyglotic-hq 252's SIGNING.md). The
  Store takes an MSIX, which it signs itself ("The Microsoft Store will
  automatically re-sign your MSIX/AppX packages", Microsoft Learn, "App
  package requirements for MSIX app", updated 2026-08-24).
- An MSIX is a different kind of install from Velopack's:
  - Windows installs it read-only and the Store updates it, so Velopack
    can't update it;
  - its process has a package identity, so Windows knows it on the taskbar
    by `<package family name>!<app ID>` and nothing else;
  - its writes to `HKEY_CURRENT_USER` are kept in a private copy for the
    package ("All writes under HKCU are copied on write to a private
    per-user, per-app location", "Understanding how packaged desktop apps
    run on Windows", updated 2026-10-12), so our Run value (176) wouldn't
    start it with Windows.
- Decision 0044: one build per tag, promoted by repacking, never rebuilt.

## Decision

- **One build, packed twice.** Wherever Velopack packs the app, the same
  folder is packed as an MSIX too (`tools/package/msix.py`), and checked to
  hold its files byte for byte (`msix compare`):
  - the shared build steps (`.github/actions/build-and-pack`), so Package
    on main packs it on every build;
  - a promotion, from the promoted files (release.yml).

  The Release records `Polyglotic-X.Y.Z-<channel>.msix` beside the
  channel's installer. It lives in `build/store/`, not `releases/`, which
  the update feed is made from. The user uploads it to Partner Center.
- **The package's version** is `(MAJOR+1).MINOR.PATCH.0`: the Store wants
  the first part above 0 and the last part 0 ("reserved for Store use").
  0.1.0 is 1.1.0.0. The app's own version (About, `hello`) is unchanged.
- **The identity** is Partner Center's three values (Package/Identity/
  Name, Publisher, PublisherDisplayName), constants in `msix.py` changed
  by a pull request once the name is reserved. Until then a placeholder
  the Store would refuse.
- **It declares** `runFullTrust` (a desktop app; restricted, so the
  submission says why) and the `microphone`. Capturing other apps' sound
  (loopback) has no capability to declare.
- **Its icons** are the .ico's masters (`ui.icons`) at Windows' scales and
  target sizes, unplated on the taskbar, found through a `resources.pri`.
- **The tools** (MakeAppx, MakePri, SignTool) are the Windows SDK's build
  tools from NuGet, pinned by version and SHA-256: no SDK install, which
  needs an administrator.
- **The Store's copy knows it is one** (the package identity,
  `platform/windows/package.py`), and then:
  - Velopack's start-up and updates are off: core's `Updates` looks for
    nothing, and "update required" tells the learner to update from the
    Store;
  - About says the Store installed it and keeps it up to date;
  - the taskbar ID is the package's, never `Polyglotic.Desktop`
    (decision 0051: the installer's stands);
  - "Start with Windows" isn't offered (its Run value would be the
    package's private copy).
- **A rehearsal** (`--rehearsal`) is another app for an install on a PC:
  its own identity, no Start menu entry, a command to start it with
  arguments, signed only with a test certificate.

## Why

- **The beta's testers get what the alpha tested,** whichever way they
  install: the Store's package holds the same bytes as Velopack's.
- **Packing beside Velopack, not later by hand,** means every build on
  main proves the MSIX still packs: MakeAppx checks the manifest against
  its schema.
- **`(MAJOR+1)`** is the one mapping that keeps every 0.x and later version
  rising in the Store's order with the first part above 0. Numbering the
  beta 1.0.0 would avoid it, but that's a release-naming choice for the
  user, and the mapping must be fixed before the first submission either
  way.
- **Not taken:**
  - the Store's EXE listing of our Velopack installer: the Store requires
    it, and every file in it, signed with our own certificate ("Microsoft
    does not re-sign your installer"), which we don't have (252);
  - a Store copy that updates itself with Velopack: it can't write to its
    install folder, and Store policy wants the Store to update it;
  - Velopack's own MSIX support: vpk 1.2.161 has none we could find;
  - the Windows App Certification Kit in CI: it comes only with the full
    SDK and needs an administrator.

## What would make us reverse it

- The Store refuses the package or the restricted capability, or a
  tester's PC treats the Store's copy worse than the download.
- Signing arrives (the company's Artifact Signing): the Store's EXE
  listing of the Velopack installer becomes possible, with one install
  kind instead of two.
- The Store's identity changes when the account moves to the company:
  a new identity is a new app to Windows, and testers reinstall once.

## How we'd reverse it

- Drop the Store: remove the MSIX step from the shared build steps and
  release.yml (a few lines each) and `tools/package/msix.py`; the app's
  Store branch then never runs. An hour.
- The version mapping can't change once a package is in the Store: a
  lower version never reaches the testers who have it.
