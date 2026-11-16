# 0197 A built-in dictionary's recorded words have a list entry of their own, fetched only by its learners

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude (polyglotic-hq 424), on the user's word of
  2026-11-16 ~23:10 after hearing 417's samples: "Chatterbox
  single-language pack is good."

## Situation

Chinese's commonest 10,000 words are recorded (Chatterbox's zh-cmn pack,
417 and 424). Decision 0192 sends recorded words as a **rider** inside a
pack's entry in the signed pack list. But Chinese's dictionary,
CC-CEDICT, isn't a pack: it is built into the app and ships in the
installer, so there is no pack entry for a rider to ride on.

Two ways to deliver it:

- **In the installer**, beside `cedict.sqlite`. About 30 MB more in every
  installer and every full update package (the app's installer is about
  160 MB), for every learner, though most don't learn Chinese.
- **Through the pack list**, as an entry of its own. Only a Chinese
  learner downloads it, quietly, after the app has started.

## Decision

- The signed pack list (still format 1) may have a top-level `built_in`
  list. Each entry names a built-in dictionary (`cedict`), the language
  it is learned for (`zh`), and its `riders`, read exactly as a pack's
  riders are (kind, format, their own `min_app`, file, sizes, SHA-256s).
  The file is `cedict-<version>.audio`, the version being the recording's
  own date.
- An app from before reads the list as it always did: `read_pack_list`
  ignores keys it doesn't know. `read_built_in` reads the new entries, and
  a malformed one is left out.
- The app (`main.BUILT_IN_RECORDED`) fetches the recordings of a built-in
  dictionary only while the learner learns its language: at the daily
  check (2 minutes after the start, then daily), and when the language is
  added on Learning. It fetches them quietly, as a pack's update, and never
  on a metered connection. They go in the packs' folder, and a newer one
  replaces the older one, as a pack's rider does.
- The app opens a built-in dictionary's recorded words from the packs'
  folder or from the installer's dictionaries folder. So shipping them in
  the installer later needs no change to the app's code.
- Learning's card for the language says "Its commonest words are recorded
  (30.8 MB)." Its tooltip names who said them and the licence, from the
  file's `info`.
- `tools.package.publish_packs --built-in cedict --audio FOLDER` publishes
  them. The packs are left as they are, and every later publish keeps the
  list's `built_in` entries.
- CC-CEDICT's words are recorded under their Simplified headwords. A
  Traditional form plays its Simplified one's recording (polyglotic-hq
  439): the card's first entry's headword, then the Traditional
  converter's form (`views.lookup.Card.simplified`). A Traditional form
  written for two words (乾: 干 "dry", 乾 "heaven") plays the one the card
  shows first. A word that is a Simplified headword itself (乾, 著) is
  read as written unless Traditional is shown. On the built file, all
  10,000 words play for a Traditional learner (4,713 before).

## Why

- Only Chinese learners pay the 30 MB (29.6 MB to download). Packs already work this way
  (decision 0122): a learner downloads what their language needs.
- It reuses 0192's rider code: the download, the checks, `min_app`, the
  metered rule and the folder. Only the entry is new.
- It is reversible both ways, because the app also reads a file the
  installer brings.

## What would make us reverse it

- Most learners turn out to learn Chinese, or a first lookup without the
  recordings (in the first two minutes) proves to matter. Then ship them
  in the installer.
- More than one or two built-in dictionaries need riders. Then a
  built-in dictionary could become an ordinary pack with a flag.

## How we'd reverse it

- **Installer:** put `cedict.audio` (with a `version` in its `info`)
  beside `cedict.sqlite` in the build, and stop publishing the list
  entry. The app already reads it there. That is an hour's work, plus the
  installer's size.
- **List entry:** stop writing it. Old lists stay readable either way.
