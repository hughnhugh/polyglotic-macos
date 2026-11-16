# 0028 An Anki deck file with Polyglotic's own note types

- **Status:** accepted
- **Date:** 2026-11-06
- **Decided by:** polyglotic-hq project 099 (DECISIONS.md #41, A1 from
  project 085); Claude reviews

## Situation

The CSV needs the learner to map columns to a note type and, for people
new to Anki, to know what a note type is. A deck file (`.apkg`) carries
the note types, templates, styling and deck, so one double-click sets
everything up; stable IDs let a second export update notes in place.

## Decision

- **genanki 0.13.1 (MIT)** writes the collection's tables. Its dependency
  list names frozendict (LGPL-3.0), which genanki never imports, so it is
  not in the installed app (THIRD_PARTY_NOTICES.md).
- **Where it lives:** `adapters/anki_package.py` implements the
  `AnkiDeckWriter` port (`ports/anki_deck.py`). Core builds `DeckNote`s
  from the same `AnkiNote`s as the CSV (`core/learning/anki.py`), so the
  two files hold the same words, escaped text, tags and GUIDs
  (`polyglotic:<entry ID>`). The UI gets the writer through
  `LearningTools`; with none, the button is disabled.
- **Own temporary file.** genanki's `write_to_file` leaves its temporary
  collection in the system temp folder, and it holds the learner's words;
  we call `Package.write_to_db` on a file in a folder of ours, zip it
  ourselves and delete the folder before returning the bytes.
- **Fixed numbers** (Anki identifies by number): note types
  1791606001 (Chinese) and 1791606002 (English); decks 1791606101 and
  1791606102. Changing them would make Anki treat the cards as new types:
  don't, without a record.
- **Note type:** Word, Reading, Meaning, Sentence (the word in `<b>`),
  Translation, WordAudio, SentenceAudio, Source, Traditional, Notes,
  Listen and Recall (the flags), EntryID (last, as 085 said). Cards:
  Recognise always; Listen and Recall only when the note's flag field is
  filled (its text, "Listen" or "Recall", is the card's label, which is
  also what lets genanki's required-field table see the card). Today the
  export never sets a flag: `build(listen=, recall=)` does, ready for the
  card choices in the first-deck-by-goal work (A2). Source and Notes, the
  clip fields (decision #44 waits) and the audio fields stay empty.
- **Audio:** Anki's `{{tts zh_CN:...}}` / `{{tts en_US:...}}` where the
  audio field is empty.
- **Style:** Margin (project 091, direction A): its day and night colours
  (Anki's `.nightMode`), a pink marker under the word, no JavaScript.
- **Decks:** "Polyglotic" with a sub-deck per language (Chinese, English).

## Consequences

- Importing the file again updates the notes it made, and a CSV import of
  the same words matches them by GUID. A learner who edits a note keeps
  Anki's own rule: "update if newer".
- The note-type IDs and template names are now a published interface.
- Not checked here: opening the file in Anki itself (not installed, by
  the brief). The tests read the file back as Anki's importer does.

## 2026-11-07 amendment (polyglotic-hq project 152)

- **Now checked in Anki's own engine:** `tests/test_anki_import.py` imports
  the deck file and the CSV, as the Words page writes them, into a
  throwaway collection with the `anki` package (a dev dependency; AGPL-3.0,
  never in the installed app), with the options Anki's import screen starts
  with. Not checked: Anki's desktop or phone apps drawing the cards.
- **Corrected:** the CSV's and the deck file's notes are not "the same
  notes". The GUIDs match, so neither file doubles a word, but the note
  types differ (Basic, ours), so Anki leaves a word as the kind of note the
  first file made it ("conflicting") and updates it only from that kind.
- **Found, not decided:** every note in a deck file carries the time of the
  export, so Anki's "update if newer" overwrites a learner's own edits and
  tags on words we haven't changed. Marked `xfail` in the test until
  decided.

## 2026-11-07 amendment (polyglotic-hq project 162)

- **Times, decided (152's option 1a):** each note in the file carries when
  its word last changed in the app (its text, its line, the line's
  translation), not the time of the export; each note type carries
  `NOTE_TYPES_CHANGED`, when its cards or style last changed. Anki
  updates what it has only from something newer (its import screen's
  default, "If newer"), so exporting again leaves the learner's own edits
  alone - a note's Notes field and tags (Anki's "leech" and "marked"
  too), and their changes to our note types - until that word, or our
  cards, change. A change replaces the whole note: the learner's edits to
  that note go.
- **How our card changes reach decks already imported:** with a new
  `NOTE_TYPES_CHANGED`, at the learner's next import of a deck file,
  except where the learner changed our note type after that time (they
  can pick "Update note types: Always" in Anki's import screen). The test
  fingerprint fails when the cards change without it.
- **The fields and card types are fixed for good:** Anki matches a note
  type by their names and number; on any change it makes a second note
  type and leaves every word already imported on the first
  ("conflicting"), so nothing would update again. Tested.
- **What 152 saw as "flaky":** Anki's Python side caches note types and an
  import doesn't clear that cache; the collection itself had the new
  style each time. The test reads note types afresh.
- **Notes exported before this change** carry their export's time, newer
  than their words' changes: they stay as they are until the word
  changes in the app, or the learner imports once with "Update notes:
  Always" (which also replaces their edits).
