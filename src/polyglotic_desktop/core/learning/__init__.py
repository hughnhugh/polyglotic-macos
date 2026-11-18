"""Learning: lookups, saved words, word statuses and exposures - the pitch.

Owns lookups (hover or pinned) and lookup context, saved words with their
category and source sentence, word statuses (new, learning, known,
ignored) and the learner's level they're estimated from, which words of a
finished caption are highlighted, exposures and "words you keep hearing".
The server holds learning data as entry IDs and times; a saved word's
source sentence and the exposure counts stay on this PC (DOMAIN.md: Data
and privacy).

- `vocabulary`: `Vocabulary` - the rules together, kept through the
  `LearningStore` port (`ports.learning`); publishes learning events.
- `levels`: the level as a known line and its learning window; `statuses`: statuses and their source.
- `saved_words`: saved words, categories, finding them in a line.
- `sentences`: saved sentences - kept with their translation, links and
  speakers, on this PC only - and finding them again.
- `highlights`: unfamiliar words, as the learner's word introductions say.
- `load`: the learning load - a Lab viewing mode: a fixed number of words
  moving through four colours by their meetings, checked and replaced.
- `languages`: the languages being learned, and what each one's dictionary
  can do (full, basic or none yet).
- `exposures`: counting finished captions once each, joins included.
- `coverage`: the share of what was heard that the learner knew, per day.
- `listening_time`: listening with captions on, per day and source category.
- `bands`: the words met by frequency band or level, and where they stand.
- `lookups`: lookup context. `anki`: saved words as a CSV for Anki.

Learning doesn't import Lexicon (decision 0002): words reach it as
`core.shared.WordInLine`s, with the facts it needs about their entries.
"""
