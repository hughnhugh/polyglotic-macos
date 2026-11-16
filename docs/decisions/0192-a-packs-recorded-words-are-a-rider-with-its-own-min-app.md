# 0192 A pack's recorded words are a rider with its own min app, added beside a pack already published

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude (polyglotic-hq 418), on the user's word of
  2026-11-16 16:59 (DECISIONS #191): Spanish, Italian and Portuguese audio
  publish once an app plays it, French by the user's ear later.
- **Updated** 2026-11-16 (polyglotic-hq 423), before it merged: the app
  that plays it is **0.1.7**, not 0.1.8 - the user, ~23:00: "Can't you
  deploy everything into 0.1.7?". The riders' `min_app` is 0.1.7. While
  DECISIONS #192 is open, the recordings come by themselves after their
  dictionary, and Learning's offer names both sizes before the download
  ("9.4 MB to download, then 29.0 MB of recorded words").

## Situation

Decision 0133 made a full dictionary a pack plus riders. 341 built the
riders (desktop #650-#653), named inside the pack's entry in the signed
list and stamped with the pack's version, published with the pack. By
2026-11-16 the packs were already out (version 2026.11.16, min app
0.1.7), and the recorded words for three languages were ready (405). An
app from before the player (0.1.6 and older) must keep its packs. Only an app that
plays the recordings should download them. The meanings riders (#650) are
still held (DECISIONS #171), so only the audio half goes to main.

## Decision

- A rider in the list carries its own `min_app`. An app takes a rider
  only if it reads that kind and format and is that version or newer
  (`core.lexicon.packs.riders_wanted`). The pack's own `min_app` is never
  raised to carry a rider.
- `tools.package.publish_packs --audio FOLDER --riders-only --version V`
  adds `<dictionary>-<V>.audio` to the entries the list already publishes
  at V. The pack files are left as they are: only the rider and the
  re-signed list go up. Without `--riders-only`, `--audio` puts the rider
  on packs published now.
- The app fetches a rider quietly after its pack. A pack already on the
  PC gets it at the daily check. A rider that fails never fails its pack.
  Before the download, Learning's offer names the dictionary's size and
  then the recordings' this app would take (`riders_wanted`), so the
  learner knows the whole download.
  Learning says the pack's words are recorded, and its tooltip names who
  said them and under what licence, from the file's own `info` (SIWIS's
  CC BY 4.0 for French).
- Only `audio` is a rider kind for now. A meanings rider would add its
  kind and an optional field, which this reader ignores until then.

## Why

- Riders inside the pack entry (0133) keep one signed list, and older
  apps ignore the field. Adding the riders to the published entries
  avoids re-stamping and re-uploading about 140 MB of packs.
- A `min_app` per rider says, in the list, which app may take it. The
  alternative, raising the pack's `min_app`, would hide the pack itself
  from the apps before the player.

## What would make us reverse it

- Riders that need to change more often than their pack, which would mean
  versioning them on their own.
- A second kind of rider whose choice depends on the learner (the meanings
  language), if that turns out to need more than a field on the rider.

## How we'd reverse it

Give the rider its own `version` in the list and its file name. The
reader's checks and the folder's `outdated_riders` key on the name, so
it's a change to `_riders`, `stamp_audio` and their tests, about a day's
work. Old lists stay readable, because a field the reader doesn't know is
ignored.
