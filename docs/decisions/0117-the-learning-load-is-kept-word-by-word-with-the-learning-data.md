# 0117 The learning load is kept word by word with the learning data, and stays on the PC

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, for polyglotic-hq project 324 (the user,
  2026-11-14: "an alternate viewing mode [with] a configurable learning
  capacity/load (e.g. 500 words) ... will shift through the colour
  spectrum as you see the word more ... if user passes then the word is
  removed from the list ... the next x words after 500 get added"). A Lab
  mode, off by default. The rules themselves (the stages, what a meeting
  is, the check) are the user's and are in `core/learning/load.py`; this
  record is about how they are kept. Reversible.

## Situation

Every word status before this was estimated from the known line, never
stored (decision 0114): moving the line moves every estimate at once. The
load can't be: a word's stage depends on what the learner heard since it
entered, a colour can be full, and the learner adds words and sets them
aside by hand. And the load needs something Learning never had: the
dictionary's words in frequency order, not only the facts of words
already met.

## Decision

- **The load is rows, one a word it keeps** (`ports.learning`'s
  `StoredLoadWord`; the store's `load_words` table, schema version 6):
  whether the word is in the load, waiting, set aside or graduated; its
  stage; the meetings in that stage; whether the learner added it; its
  place; when it entered, last counted and graduated. A word that is in the
  load is a row from the moment it enters, so what is in the load never
  depends on recomputing it.
- **Meetings are the load's own count**, not the exposure counts'. A word's
  meetings start when it enters; "every time heard" counts each time in a
  caption (exposures count a caption once); "once a day" needs the day it
  last counted. `load.MeetingCounter` follows joins and withdrawals the way
  `exposures.ExposureCounter` does.
- **The rules (size, meetings a stage, what counts, the most in a colour)
  are not in the store.** They are the learner's settings, handed to
  `Vocabulary.set_load_rules`; None is the mode off, when the rows are
  kept and nothing is counted. Adding words by hand raises the size, which
  the load reports (`load.rules`) for the settings to keep.
- **The words enter in the order of their places** (`levels.place`: a
  word's frequency rank, or its syllabus level's size where that is
  smaller), the order Learning's window of words being learned has, so
  the load is that window's first words: 游戏, the 2,847th word in written
  text and an HSK 3 word, is at 1,000. The `DictionaryFile` port gives
  the words through two more calls - `headwords_ranked(after, limit)` and
  `headwords_at_levels(scheme)`, each by a headword's own first entry, the
  one a caption counts the word for; Lexicon merges them
  (`words_past`; the syllabus's words are read once a scheme and kept),
  and `main` hands that to `Vocabulary` as a function, as it does `facts`
  (decision 0002: Learning doesn't import Lexicon). A dictionary without
  ranks answers nothing: that language has no load.
- **It stays on this PC.** Nothing of the load is sent: no protocol or
  server change. A graduation is the status "known" set by the learner,
  which syncs as every status does, so a word graduated on one PC is known
  on the other (and graduates there if it is in that PC's load). Stages
  and meetings on two PCs are separate, and the Lab says so.
- **It is learning data:** deleted with it (`delete_learning_data`), on
  every path that deletes it, and an entry merged by a dictionary update
  takes its row along.

## Why

- Rows make the load something the learner can see and change (the list
  of its words, what waits, what graduated), which the user asked for.
- A separate count keeps exposures' meaning ("captions heard in", shared
  only as daily counts with consent) untouched by a Lab mode.
- No sync while it is in the Lab: the stage is a view of what was heard
  on this PC, a merge rule for two PCs' counts would be a guess before
  anyone has used the mode, and the protocol should not grow for an
  experiment. What matters across PCs, the graduation, already syncs.
- Alternatives not taken: deriving the stage from the exposure counts (no
  count since entering, no full colours, no "not yet"); keeping the load
  in the settings file (500 rows rewritten with every caption); a file of
  its own (deleting the learning data would have to know it).

## What would make us reverse it

- The mode leaves the Lab and learners use two PCs: then stages and
  meetings sync (a `load` message beside `learning`; server decision 0070
  and migration 0031 are reserved for it).
- A real quiz replaces the one click: `LearningLoad.check` is the seam;
  the rows gain what a quiz needs (when it was last asked, how often).
- The mode is dropped: the table stays empty (the store only adds), the
  port's two calls and `core/learning/load.py` go.

## How we'd reverse it

Syncing adds an event per change and a merge rule in `LearningLoad`; the
rows already carry the times a latest-wins rule needs. Dropping it removes
`load.py`, the calls in `Vocabulary`, the port's two methods and
`headwords_ranked`; version 6's table is left in place.

## Known limits

- Schema version 6: an app from before this refuses a learning data file
  this version has opened (as with every version before; RELEASING.md's
  "republish the last good one as a newer version" means a build that
  knows version 6).
- `headwords_ranked` reads the whole entries table (no index on the rank
  in the packs): 20-55 ms on the two learner dictionaries, measured
  2026-11-14. The load reads ahead in batches of 200 or more and keeps
  what it read, so it asks when the mode is turned on, when the size or
  the line changes, and about once every 200 graduations - never for a
  caption.
- The syllabus's words (about 10,900 for HSK 3.0) are read once a scheme,
  the first time the load asks: 37-48 ms more, that once, and kept (a
  few hundred kilobytes). The first reading of 1,000 words for Chinese
  took 89-98 ms in all, later ones 49-60 ms (2026-11-14).
- Those reads are kept off the interface thread by the interface, not by
  the load: `ui.learning.PlacedAhead` keeps the words once read, and
  `LearningTools.set_load_rules` reads a load's words and 400 past them
  on a thread of its own before the rules are set. A load that outruns
  that (the known line moved, more than 400 words added at once) reads
  the rest where it asks.
- A word's place is kept as it was when the word entered; a dictionary
  update that moves it doesn't reorder the load.