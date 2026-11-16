# 0089 Dictionary packs are kept with the learner's data; a language's packs keep their entry IDs from basic to full

- **Status:** accepted
- **Date:** 2026-11-13
- **Decided by:** Claude, for polyglotic-hq project 298 (the user's
  feedback 17, 2026-11-13: "Make sure the full dictionary upgrade path
  works if a user already installed the basic dictionary"; DECISIONS #122
  B). Reversible - a technical choice; how packs reach a PC (a download,
  or the installer) is the user's, in 298's report.

## Situation

The full dictionaries (CC-CEDICT, ECDICT) ship inside the app, beside
`Polyglotic.exe` (decision 0009), and are replaced with it at every
update. The basic packs (decision 0035) are built but not delivered: the
developer switch `--basic-dictionaries` reads them from
`<dictionaries>/packs`, which for an installed copy is the install
folder, `%LOCALAPPDATA%\Polyglotic\current\dictionaries\packs`.
Velopack replaces that whole folder at each update and removes it at
uninstall (decision 0014), and the Microsoft Store's copy can't write
into its own folder at all (decision 0056). So a pack put there is gone
after the next update, and no download could ever put one in the
Store's. (Today no installed copy can use a pack anyway: the word splits,
simplemma and Sudachi, are in the `languages` dependency group, which the
release build leaves out.)

The upgrade the user asked about - a learner with a language's basic
dictionary getting its full one - rests on three things: where packs
live, what a new pack replacing an old one does to the learner's words,
and how the swap is made. The first two can be settled now; the third
waits for packs to be delivered at all.

## Decision

- **Where:** an installed copy keeps its packs in
  `<data folder>\dictionaries` (`main.packs_folder`): `%APPDATA%\Polyglotic\dictionaries`,
  beside the learner's settings and learning data, outside the install
  folder. Updates and reinstalls leave them; a rehearsal install
  (`--data`) has its own. From source, packs stay where
  `tools.dictionaries.packs` writes them (`build/dictionaries/packs`).
- **What carries:** a language's packs keep their entry IDs whatever
  else a pack keeps: an ID is its entry's key's hash (decision 0007), not
  a position, so the bigger pack of a full dictionary gives every entry
  the basic one had the ID it had. A saved word keeps its own text
  (headword, reading, meaning) in the learning data, so it - and its Anki
  note - outlives its entry even if a new dictionary drops it. Tests hold
  both (`tests/tools/test_packs.py`, `tests/learning/test_anki_export.py`).
- **How a pack is replaced** (for when packs are delivered; not built):
  downloaded beside the old one as `<name>.sqlite.part`, resumed if cut
  off, checked against the feed's size and SHA-256, opened as a
  dictionary of the right language and tier, and only then moved over
  the old one in one rename (`os.replace`). Free space is checked before
  the download (the pack's size twice: the new file and the old one side
  by side). Until the rename the old pack answers lookups; any failure -
  offline, the disk full, a bad checksum - leaves it and says why.

## Why

- Roaming app data is where decision 0014 put everything that must
  outlive the install folder; one folder for the learner to back up or
  delete. Local app data would be the usual place for big re-creatable
  files, but `%LOCALAPPDATA%\Polyglotic` *is* the install folder, and a
  new top-level folder would be one more thing an uninstall leaves behind
  unnamed.
- Keeping IDs by key, not by build, is what decision 0007 already does
  for CC-CEDICT's updates; the packs follow it, so an upgrade needs no
  migration of the learner's data at all.

## What would make us reverse it

- Roaming profiles on testers' PCs (a school's or company's domain) that
  sync tens of megabytes at every sign-in: move packs to a local folder
  outside `%LOCALAPPDATA%\Polyglotic`.
- A full dictionary built from a different source than its basic one
  (another dictionary, not Wiktionary): its keys differ, and the upgrade
  needs a registry mapping old IDs to new (decision 0007's `merged`).

## How we'd reverse it

`main.packs_folder` is the one place that says where; moving existing
packs is a rename at start, or a fresh download. Nothing in the learning
data refers to the folder.
