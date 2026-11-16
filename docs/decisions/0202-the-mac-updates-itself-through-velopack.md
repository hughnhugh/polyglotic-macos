# 0202 The Mac updates itself through Velopack, with Windows' signed feed

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** the user, 2026-11-16 ~23:45 ("implement mac feature parity
  ... We'll try release this into current release"; polyglotic-hq 430).
  Replaces the part of 0196 that kept the release's zip
  (`build.release_zip`).

## Situation

Windows updates itself through Velopack from a feed we sign (decisions
0017-0020). The first Mac release (0196, polyglotic-hq 422) was one zip per
version, with no updates: a learner would have to download each version
by hand. The app's updater (`adapters/velopack_updates.py`) and the signed
feed's check (`adapters/signed_feed.py`) are Velopack's Python library and
plain Python, and Velopack has a Mac wheel and packs Mac apps - but only on
a Mac, and the Mac build runs on GitHub's Mac, where the feed's key must
never go.

## Decision

- **Packing:** `tools/package/pack.sh` packs a `macos-*` channel with
  `vpk pack` on the Mac job: the signed `Polyglotic.app` as it is, the full
  package, Velopack's portable zip and the channel's feed; no `.pkg`
  installer (`--noInst`: it would need Apple's installer certificate, and
  an unsigned one is worse for Gatekeeper than the zip).
- **Signing:** `vpk pack` adds `Contents/MacOS/UpdateMac` and `sq.version`
  to the bundle, which breaks its signature, so it signs again: only what
  it adds and the bundle (`--signDisableDeep`), with the build's identity
  (`POLYGLOTIC_CODESIGN_IDENTITY`; ad hoc without one). Velopack 1.2.161
  always asks for Apple's timestamp service and the hardened runtime with
  .NET's entitlements; `tools/package/macos_codesign.sh`, put first on
  vpk's `PATH` as `codesign`, drops both and signs as `build.sign` does
  (`--timestamp=none`). The designated requirement is unchanged, so a
  learner's permissions carry over (0196).
- **The first install is Velopack's portable zip**, uploaded under the
  fixed name the site links to (`Polyglotic-macos-arm64-alpha.zip`). A zip
  without UpdateMac (422's) can never update itself, so 422's zip is gone.
- **The feed is signed on the PC**, with Windows' key: the release run
  keeps the packages, the unsigned feed and `SHA256SUMS` one day; 430's
  `publish-mac.sh` downloads them, checks them, signs the feed with
  `tools.package.sign_feed` and uploads the package, the zip, the
  signature, then the feed - Windows' order.
- **Checked where made:** `tools/package/macos_release.py` checks the feed
  lists the version's full package as it is, and the portable zip's app
  has UpdateMac and its version, verifies, and has the built app's
  designated requirement.
- **Rehearsed:** with pack or release, the Mac job packs the build as 0.0.1
  and 0.0.2 into a feed in a folder, unzips 0.0.1 into `~/Applications`,
  and the installed copy finds, downloads and - at its next start -
  applies 0.0.2; the updated app must still verify with the built app's
  requirement (`tools/package/macos_update_rehearsal.sh`).
- **The app** keeps the signed feed's checked files in
  `~/Library/Caches/Polyglotic/verified-feed` on a Mac
  (`main.verified_feed_folder`): never inside the bundle, which its
  signature seals.

## Why

One updater, one feed format and one key for both OSes: the app's code is
unchanged but for where the checked feed waits. Alternatives not taken:
- Sparkle (the usual Mac updater): a second updater, a second feed and a
  second signing scheme (EdDSA), and Objective-C to call from Python.
- Signing the feed on the runner: the key would have to be a GitHub
  secret on the public repo.
- Re-signing after `vpk pack` by rewriting the package: the feed's sizes
  and SHA-256s would have to be rewritten too.
- Writing UpdateMac and sq.version into the bundle before the build signs
  it: copies Velopack's private layout, which a vpk update can change.

## What would make us reverse it

- Velopack's macOS updater failing for testers in ways it doesn't on
  Windows (permissions on `/Applications`, App Translocation).
- A Developer ID (0196's reversal): then vpk can sign and notarize itself,
  and the shim goes.
- A vpk upgrade that changes `codesign`'s arguments: the shim passes on
  what it doesn't know, and the rehearsal fails if the signature breaks.

## How we'd reverse it

Drop the `macos-*` branch of `pack.sh` and the shim, and go back to a
plain `ditto` zip (one download per version). Installed copies would stop
finding updates; the app's code doesn't change.
