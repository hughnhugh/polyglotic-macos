# 0175 A pack language learned keeps its own learning data, in its own file

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** the user, polyglotic-hq DECISIONS.md #184 (2026-11-16
  ~03:32: "can we make save features for each dictionary too. I want them
  all to be full dictionaries"); the shape is Claude's, for polyglotic-hq
  project 391. Changes decision 0035's "lookups only" for a pack; 0035's
  pipeline, 0089's entry IDs and 0122's delivery stand.

## Situation

Chinese and English keep learning data: the words heard and saved,
statuses, categories, the line, an Anki deck. Every other language with a
dictionary - a pack (0035): Russian, Vietnamese, Spanish, Japanese, French
and each batch since - was lookups and word links only, with nothing kept.
The user wants every dictionary to do what Chinese's and English's do.

What forces the choice: fourteen pack languages today and more each week;
installed apps (0.1.6 and before) that must keep working on the same data
folder; packs that arrive, are replaced and are removed while the app
runs (0122); learning data whose loss a learner would not forgive.

## Decision

- **One learning data file per language**, as Chinese and English already
  have (0095): `learning.sqlite` (Chinese), `learning-en.sqlite`, and
  `learning-<code>.sqlite` for a pack language (`learning-ru.sqlite`),
  each with its level file beside it (0048). **The same schema, the same
  version (8): no migration.** A pack language's file is made the first
  time the language is open.
- **A pack language opens when it is learned and its pack is on this PC**
  (`core.learning.languages.packs_beside`): at the start once the packs
  are opened, when "Learn it too?" or Learning adds it, and when its pack
  arrives. Then it has a `LearningTools` and a `Vocabulary` of its own,
  beside the starting language's, exactly as a second full language has
  (`LearningTools.also`, `of`): the card's status, Known, deck and Save;
  its section on Words with its categories; its Anki export; marks,
  counts and links from its own `Knowledge` (0163). A pack's language
  that isn't learned stays a lookup with "Learn it too?", nothing kept.
- **The pack is that learner's dictionary**: `BasicDictionary` answers
  what Learning asks of one (`facts`, `words_past`, `words_in_ranks`,
  `merged_ids`). The tools read the pack the lookups hold *now*, so a
  pack replaced by a download answers at once; one removed leaves a
  dictionary that finds nothing (`lexicon.basic.absent`) while the
  learning data stays open - saved words still show, from their own text.
- **The line is a number of words**, never a level (0163, DECISIONS
  #176): a pack has frequency ranks only. Until the learner says, the
  first 1,000 are estimated known (`UNKNOWN_LEVEL_LINKS_FROM`: where the
  language's links started before it kept anything, so nothing moves on
  the day this ships). Bands are frequency cut-offs.
- **Entry IDs** are the pack's own (`wiktru:…`, `jmdict:…`), hashed from
  the entry's key (0007, 0089): a rebuilt or bigger pack gives the same
  entry the same ID, so nothing is migrated when a pack is replaced. An
  entry a rebuild drops keeps its status by ID, and a saved word its own
  text (headword, reading, meaning, sentence). Merged IDs (0007) are
  followed when the language opens.
- **Anki:** a note type and a sub-deck per language, as Chinese and
  English have (`Polyglotic::Russian`, note type "Polyglotic Russian"),
  with fixed IDs worked out from the language's code, the same fields,
  the language's own voice for Anki's text-to-speech; `Traditional` is
  empty; `Reading` is the pack's (kana, IPA, or the word with its stress
  marked) where it has one.
- **An older app** never names `learning-<code>.sqlite`, so it never
  opens, migrates or deletes it: it shows the language as lookups only,
  and the words are there again in an app with this. Nothing an older app
  reads has changed - not the settings' keys (a pack language was already
  kept in `also_learning`), not Chinese's or English's files, not the
  protocol.
- **What leaves the PC** is what Chinese's and English's already send
  (protocol.md's `learning`): statuses, saves and pinned lookups as entry
  IDs and times, and - only if the learner opted in - daily exposure
  counts per entry ID. The saved word's text and sentence stay on the PC.
  New: those IDs can now be a pack's. As for a second full language
  today, the server's sync brings back only the starting language's
  entries (`DataExchange` keeps one dictionary's cursor).
- Enforced by tests:
  `tests/ui/test_pack_languages_keep_learning_data.py`,
  `tests/lexicon/test_basic.py`, `tests/test_anki_package.py`,
  `tests/learning/test_anki_export.py`.

## Why

- **One file per language, not one for all:** the store, its damage
  handling (0048, set-aside files), its deletion and its version are per
  file already and tested that way; a second full language proved the
  shape (0095). One file for all languages would need a language column
  or a prefix scan in every table and a migration of every learner's
  file to version 9 - which an installed 0.1.6 would then refuse to open
  ("from a newer app"), locking testers out of their Chinese words after
  a downgrade. Per-language files cost nothing to old apps.
- A learner's languages fail separately: one file damaged or from a newer
  app leaves the others open.
- **No new tier and no new class of dictionary:** the tools already
  routed a line to its language's own data; a pack only had to answer
  the same questions as ECDICT.
- Not taken: saving pack words into the starting language's file (entry
  IDs would tell them apart, but categories, the line, coverage and the
  Anki deck would be one language's - a Russian word under "HSK 3"); a
  store per pack *file* (a pack's meanings language or version must not
  split a learner's words).

## What would make us reverse it

- Learners with many languages for whom a file each is a cost: a start
  that opens ten stores (each about 5 ms empty, 60 ms at 10,000 words
  met - 306's measure) or a backup of many files. Then one file, with
  the language in each table's key.
- Sync across PCs for every language (the server's sync per dictionary):
  that changes `DataExchange`, not this.
- A pack language as the *starting* language (today always Chinese or
  English, opened before the first paint; packs open after it): its
  tools would open first, from the same file - no data change.

## How we'd reverse it

`main.pack_learner_tools` and `packs_beside` are the one place a pack
language's data opens: remove them and each pack is lookups only again;
the `learning-<code>.sqlite` files stay on the PC, unread, until an app
that reads them. Moving to one file is a version-9 migration that reads
each language's file into it - about three days, mostly the old-app path.
