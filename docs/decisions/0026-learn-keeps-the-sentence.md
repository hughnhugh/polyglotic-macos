# 0026 "Learn" keeps the sentence in a deck word, apart from saved words

- **Status:** accepted
- **Date:** 2026-11-06
- **Decided by:** polyglotic-hq project 089 (DECISIONS.md #41, A0, from
  project 085); Claude reviews

## Situation

`Vocabulary.set_status(learning)` ("Learn", "Add to deck") kept no
sentence; only `save()` kept the line a word was in. The MVP's Anki CSV
therefore had saved words without the caption they were heard in, the most
useful part of a card made from captions, and had no deck words at all.

## Decision

A word going into the deck through `Vocabulary.learn` keeps a **deck
word** (`core/learning/deck_words.py`): the entry's text, the caption
sentence, its translation and the time, in the learning store on this PC
(`deck_words` table, schema version 2). Which words were written to an
Anki file is kept per entry in `anki_exports`.

- It is **not** a saved word. Saving puts a word in a category, colours it
  in captions and sends `WordSaved`; learning is a status (`WordStatusChanged`
  only). Reusing `save()` would have made every deck word a coloured,
  synced, categorised word and changed what "saved" means. A word can be
  both; the file then uses the deck sentence, else the saved one.
- Nothing new leaves the PC: `learn` publishes the same status event as
  before, with no sentence (a test checks this).
- A deck word goes when the word leaves the deck (any other status, here
  or from the server) and with "delete learning data". It follows a
  dictionary merge (decision 0007) like the other data.
- The Anki file (`core/learning/anki.py`) holds both kinds of words, with
  a GUID `polyglotic:<entry ID>` (so 行 háng and 行 xíng don't clash and
  re-importing updates), `#html:true`, the word marked with `<b>` in the
  sentence, and "only words not exported yet" from the remembered marks.

## Why

Alternatives: a nullable sentence on the status record (it would be
synced-shaped data in a record the server mirrors); making Learn save into
a hidden category (the semantics above). A separate record keeps privacy
and meaning clear at the cost of one small table.

## What would make us reverse it

If saved words and deck words become one thing in the product (one "my
words" list with a deck flag), merge the tables then.
