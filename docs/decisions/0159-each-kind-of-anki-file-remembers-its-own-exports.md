# 0159 Each kind of Anki file remembers its own exports

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** Claude, under polyglotic-hq project 368's brief (item 5:
  "decide the rule from what a learner expects"); QA 361's B5 found it

## Situation

Words' export writes an Anki deck file (.apkg) or a CSV, each with "Only
words not exported yet". Until now one record ("exported at", per word)
served both: an .apkg export marked its words, so a CSV of only new words
straight after came out empty ("No new words since the last export"), and
the other way round.

## Decision

Each kind of file keeps its own record. `core.learning.vocabulary.AnkiFormat`
names the kind (`deck`, `csv`); `Vocabulary.anki_words`, `export_anki` and
`mark_exported` take it; Words passes the kind its button writes. The
learning store's version 7 adds `anki_csv_exports` beside `anki_exports`
(from then on the deck file's), starting as a copy of it: which kind wrote
a word before is unknown, so both remember it, as the one record did.
`Vocabulary.is_exported` still means "in a file of either kind". Tested at
the domain (`test_each_kind_of_file_remembers_its_own_exports`), in the
store (`test_each_kind_of_anki_file_keeps_its_own_exports`, the version 6
migration) and on Words.

## Why

A learner who uses both formats is sending the words to two places - the
deck file into Anki, the CSV into a spreadsheet, another flashcard app or
a second Anki profile. "Only words not exported yet" means "not yet sent
there": each destination should get every word once. With one shared
record the second destination silently missed words; nothing on the page
said why, and nothing could get them there short of exporting everything.

Not taken:
- **Keep the shared record and say so** ("since the last export, in
  either format"): honest, but still leaves the second place without the
  words, which is the thing the learner wanted.
- **Remember each file (path) separately:** closer still, but a learner
  saves the next export under a new name as often as the same one, and
  the record would grow with every file name.

## What would make us reverse it

Learners exporting both formats into the same place (importing the CSV
into the same Anki collection as the deck file) and getting each word
twice. Anki's own duplicate check (the note's GUID, `anki.py`) makes that
an update, not a duplicate, so this is unlikely to bite.

## How we'd reverse it

Read both tables as one record again in `load` (the later time per word)
and write both on every export: a few lines in `Vocabulary` and the store;
the version 7 table can stay.
