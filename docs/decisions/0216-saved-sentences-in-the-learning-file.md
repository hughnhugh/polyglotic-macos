# 0216 Saved sentences live in the spoken language's learning file, read when first wanted, searched by a scan

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** the user's design (polyglotic-hq journal 2026-11-14,
  00:07 and 00:26); the open points are Claude's reversible choices in
  polyglotic-hq 459's brief; built in 459.

## Situation

The learner wants to save sentences - one clause or many, across lines,
captions and speakers - with the translation and word links they had,
in categories shared with saved words, find them again by "most words
matched in the text. characters matched for chinese or words matched in
english" over both sides, in under 100 ms at 5,000 sentences, and take
them to Anki.

## Decision

- **Where:** a table of their own, `saved_sentences`, in the learning
  file of the language the sentence was spoken in (its first line's when
  a selection holds two): learning file version 9. A sentence's parts -
  each clause's text, links and speaker - are one JSON column; each
  side's joined text and the translation's language are columns of their
  own. Its category references `categories`, so deleting a category
  deletes its sentences, as it does its words. Deleting learning data
  deletes them; nothing about them is sent to the server.
- **Read when first wanted:** not in `LearningStore.load` (the start's
  read) but by `LearningStore.saved_sentences`, the first time Words'
  Sentences or a save needs them. 5,000 take about 40 ms to read; the
  start stays as it was.
- **Searched by a scan** (`core.learning.sentences.SentenceSearch`):
  each sentence's text normalised once (on the first search), then each
  query word looked for in it - a Chinese or Japanese character anywhere,
  a Thai run anywhere, any other word at the start of a word. A sentence
  with at least half the query's words is found; ranked by how many,
  then the query as typed, then newest.

## Why

- The spoken language's file: a sentence is what the learner heard in
  the language they're learning, and its saved words - which mark it -
  live there too. The translation's language is kept, for the day a
  learner reads one language into two.
- One JSON column for the parts: they're only ever read and written
  whole; a table of parts would add joins and nothing searched by.
- A scan, not SQLite's FTS5: measured (`tools/bench_sentences.py`,
  2026-11-17), a search at 5,000 takes about 7 ms (median; 14 ms at the
  95th percentile) and 2.3 MB of prepared text. FTS5's own ranking is by
  matched terms' frequency, not "most of the query's words", its default
  tokenizer doesn't split Chinese into characters, and a second index in
  the learning file would have to be kept in step and scrubbed (213). An
  inverted index in memory would be faster at 50,000 (the scan is 73 ms
  median, 189 ms at the 95th percentile there) for more memory and code:
  not needed at the user's 5,000.
- Not in the start's read: the start is held to a budget
  (`perf.budgets`); a learner who never opens Sentences never pays.

## What would make us reverse it

- Learners keeping far more than 5,000 sentences, or a search felt slow.
- Sentences synced to the server (a privacy change first: today they
  never leave the PC).
- A sentence wanted in two learning files (a language pair learned both
  ways).

## How we'd reverse it

- Faster search: an inverted index (word or character -> sentences)
  behind `SentenceSearch`'s same `search`; nothing else changes.
- Another home: a version 10 that moves the rows; the port's
  `saved_sentences` / `save_sentence` / `delete_sentence` stay.
