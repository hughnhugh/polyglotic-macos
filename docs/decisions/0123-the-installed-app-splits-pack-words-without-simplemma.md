# 0123 The installed app splits a pack's words without simplemma; Sudachi stays out

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, for polyglotic-hq project 327 (item 4: "the
  word-splitting libraries each pack needs are in the packaged app").
  Reversible; the licence reading of simplemma's data is Claude's, the
  user's only if it is ever shipped.

## Situation

The basic packs (decision 0035) were looked up through a word split per
language: letters plus simplemma's lemma for Spanish and Russian, Sudachi
for Japanese. Both libraries are in the `languages` dependency group,
which the release build leaves out (298). Measured 2026-11-14 on this PC:

| Library | On disk | Its data | Licences |
|---|---|---|---|
| simplemma 2.0.0 | 19 MB (54 languages) | Spanish 0.35 MB, Russian 0.68 MB; the seven basic spaced languages 3.5 MB | the code MIT; its lemma lists from Měchura's lists (ODbL), Wiktionary via Kaikki (CC BY-SA), FreeLing's data (per FreeLing's COPYING, section 2b), spaCy's lookups (MIT), UniMorph and Wikinflection (CC BY 4.0) |
| SudachiPy + sudachidict_small | about 110 MB (298) | the dictionary itself | Apache-2.0 |

What simplemma adds, measured on the real Russian pack (2026-11-14):
96.6 % of running words found with it, **96.4 % without** (wordfreq's
671,605 forms, weighed by frequency); the FLEURS probe sentences 95.7 %
either way. The pack's own inflection table (862,472 forms, from
Wiktionary) does the work; simplemma's guess is the fallback for a form
the table hasn't got (the misses it adds back are abbreviations: млн,
тыс, руб).

## Decision

- **simplemma stays out of the installed app.** The spaced split
  (`adapters/spaced_split.py`) works without it: words by letters, looked
  up through the pack's table; simplemma's guesses only where it is
  installed (from source, CI). So "spaced" packs are readable by every
  app with this code (`main.pack_reader`), and nothing is added to the
  installer or to the start.
- **Sudachi stays out** (about 110 MB): Japanese's pack needs the
  `japanese` split, which an installed app doesn't have, so the list's
  Japanese pack is never offered to it (`core.lexicon.packs.Reader`);
  Learning says a newer Polyglotic reads it. No small lawful Japanese
  splitter was found in this project's time: none was looked for beyond
  Sudachi's own small dictionary (already the smallest it ships).
- **Chinese and English** stay in the installer as they are (decision
  0009): their dictionaries open at the start and every learner has one.
  As packs they would save about 34 MB on disk (CC-CEDICT 24.9 MB,
  ECDICT 8.9 MB, as 0.1.4 installs them) and about 17 MB of the download
  (12.5 + 4.5 MB deflated; 0.1.4's full package is 84.2 MB), measured
  2026-11-14, at the cost of a first run that can't look anything up
  until a download ends - not worth it now.

## Why

- 0.2 points of Russian's running words isn't worth 1-19 MB, a second
  licence reading (FreeLing's data components are under several licences,
  some copyleft) and a credits page per language.
- The capability check (`Reader.splits`) already keeps an app from a pack
  it can't split: shipping a split later is a release, not a list change.

## What would make us reverse it

- A pack whose language needs lemmas the table can't give (a Spanish
  pack's misses, measured the same way, well above Russian's 0.2 points).
- Japanese for testers: ship Sudachi (or a smaller lawful splitter) and add
  `japanese` to the installed app's splits.

## How we'd reverse it

Move `simplemma` from the `languages` group to the app's dependencies (the
release build then collects it; keep only the basic languages' data files
with a `DROP` pattern in `polyglotic.spec`), add its licence texts to
`THIRD_PARTY_NOTICES.md`; nothing in the split changes.
