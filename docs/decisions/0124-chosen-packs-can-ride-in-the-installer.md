# 0124 Chosen dictionary packs can ride in the installer, by a build switch, off by default

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user (polyglotic-hq DECISIONS.md #125, 2026-11-14:
  "Yes go with A, 330mb is not outrageous too can be a fallback option" -
  B, every pack in the installer, as the fallback). The switch's shape is
  Claude's, for polyglotic-hq project 327; reversible.

## Situation

Packs are downloaded when a language is learned (decision 0122). A tester
who can't download one - a network that blocks the storage, a PC offline
- would have no lookups in that language. The user kept "packs in the
installer" as the fallback.

## Decision

- **A build switch:** `python -m tools.package.build vX.Y.Z --packs ru`
  copies the named languages' packs (both meanings files, and their
  credits) into `dictionaries/packs/` beside `Polyglotic.exe`, each
  stamped with the build's version (`tools.package.build.bundle_packs`).
  Without the switch nothing goes in: the build now leaves out any
  `packs` folder it finds beside the dictionaries, so a pack built on
  the release machine can't ride along by accident.
- **The app reads them first:** an installed copy reads
  `dictionaries/packs` in its own folder (`main.installer_packs`) beside
  the downloaded ones (`main.packs_folder`), never writing it; the newest
  version of each wins, and a pack there is "on this PC" - no download is
  offered, offline too. A newer version in the list still downloads, into
  the data folder, as an update. Learning's list and Remove show only
  what was downloaded: the installer's own can't be removed (the next
  update would put it back).
- **Measured with Russian** (327's local build, 2026-11-14): see the pull
  request - the installer grows by Russian's two files, compressed.

## Why

- A switch, not a second release channel: one build recipe, and the
  alpha's installer stays small unless a release is made for an offline
  tester.
- Reading the installer's folder as one more pack folder reuses
  everything decision 0122 built (versions, the newest wins, updates).

## What would make us reverse it

- Downloads failing for many testers (the storage blocked somewhere): make
  a languages' installer the default for that channel, or mirror the
  storage.

## How we'd reverse it

Drop `--packs` and `installer_packs`; the build already ignores a stray
`packs` folder.
