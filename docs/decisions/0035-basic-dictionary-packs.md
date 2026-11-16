# 0035 Basic dictionary packs: one pipeline, a config per language, not shipped yet

- **Status:** accepted
- **Date:** 2026-11-07
- **Decided by:** polyglotic-hq project 157 proposed the tiers and the
  sources; DECISIONS #65 leaves "basic dictionaries as a launch goal" to
  the user, with this groundwork as the default meanwhile. Project 164
  built it; Claude reviews it with the pull request.

## Situation

Captions come in about 24 languages; the app has dictionaries for two
(CC-CEDICT, ECDICT - decision 0009). Project 157 found open data good
enough for "basic" lookups in ten more, from one pipeline: Wiktionary as
kaikki.org extracts it (every language, English glosses, inflection
tables), JMdict for Japanese, wordfreq for frequency ranks.

## Decision

- **`python -m tools.dictionaries.packs [languages]`** builds one pack per
  language into `build/dictionaries/packs/`, separate from `build` (which
  still makes only what the installer ships). Each language is a `Pack`
  config: its sources (pinned by checksum, as in 0009), a reader that
  turns them into a draft (entries, written forms, inflections), its level
  schemes. Everything after the reader is shared: entry IDs, ranks, the
  cut, the file, the credits.
- **The same file format** as `cedict.sqlite` (`FORMAT` 1): the lookup
  reads a pack through `SqliteDictionary` like any other. Inflections go
  in the `lemmas` table; a written form's own entries in `forms`.
- **Entry IDs** follow 0007, with a registry per pack: `jmdict:` hashed
  from JMdict's own sequence number; `wiktes:` (Wiktionary, Spanish) from
  `word|part of speech|etymology number`, since kaikki has no IDs. A
  pack's name is lower-case letters and digits only - the server's
  `EntryId` pattern rejects a hyphen (157 had proposed `wikt-es:`).
- **Two files per pack, one per meanings language:** `<name>.sqlite`
  (English) and `<name>-zh.sqlite` (the Chinese edition of Wiktionary's
  glosses, English where it has none). The same entries and IDs.
- **The cut:** entries wordfreq ranks, or that have a level - the words a
  learner can meet in speech.
- **Nothing ships** until the user answers DECISIONS #65: no installer
  change, no download yet.

## Why

- One pipeline makes each further language a config and a reader, not a
  new build (157: about 15 agent-days for ten languages).
- Same format, same reader: core's lookups don't learn a new file.
- Two files rather than a second meanings column keep the format at 1 and
  each file's credits simple; the cost is the forms tables twice.
- Not shipped: the installer stays at Chinese and English until the scope
  decision.

## What would make us reverse it

- kaikki.org removes its per-language files (it says it will): the reader
  moves to the raw `raw-wiktextract-data.jsonl.gz` (2.9 GB) or our own
  copy (R2). The pins already fail loudly when the files change.
- Packs too big to download: trim the `lemmas` table to forms wordfreq
  ranks (Spanish: 762,000 inflected forms are most of its 29 MB).
- A meanings language per learner, not per file: a `meanings` table
  keyed by entry and language, and a format 2.

## How we'd reverse it

Remove `tools/dictionaries/packs.py`, `kaikki.py`, `jmdict.py` and the
pack sources; nothing in the app reads a pack unless the developer switch
asks for one.
