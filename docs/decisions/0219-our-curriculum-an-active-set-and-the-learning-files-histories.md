# 0219 Our curriculum is an active set of words in the learning file, beside histories of statuses and the known line

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user (polyglotic-hq DECISIONS #201: the quiet view's
  words are a multiselect, "Our curriculum" the default; 473's option A);
  the store hooks are Claude's reversible call (DECISIONS #202, 474's
  findings 7); built in polyglotic-hq 477.

## Situation

The quiet view (477) shows a few chosen words in blue on grey captions.
"Our curriculum", its default, is to be a small set of words that stay
with the learner over several days and follow what they actually hear
(473). The written curriculum units (473's rider) don't exist yet, so
0.1.8's version is the rule alone: 473's option A. A later learning mode
(474) will want to know which words were chosen, how each word's status
moved and how the known line moved - none of which the learning file
kept.

## Decision

- **The active set** (`core.learning.curriculum.Curriculum`): `size`
  words, 50 until the learner says. Words past the known line (new or in
  the deck, not names): those heard in captions from what the PC played
  first, the most heard first, then the next by the learning load's
  order. New words enter only between sittings (a sitting ends after 30
  minutes with no finished caption, or when the app closes). A word met
  on 3 separate days (the learner's own, the PC's) retires and doesn't
  come back; a word that sat a whole sitting unmet gives up its place; a
  word set known or ignored leaves. Kept in `curriculum_words`, a word a
  row (in or retired), learning file version 10.
- **The histories:** `status_history` (entry, before, after, source,
  time) and `line_history` (scheme and midpoint, or none; how; time),
  appended in order and never changed. Statuses from the server are
  recorded with the source `server`.
- **Word sets:** `set_words` (set name, entry, sources, added), kept in
  step with the quiet view's chosen words as the set `quiet`, each word
  with where it came from (`curriculum`, `load`, `saved`); only what
  changed is written.
- All of it stays on the PC; "Delete learning data" deletes all four
  tables, and a merged entry's rows go with it (the histories keep the
  old ID: they record what happened).

## Why

- A set of its own, not a flag on the load: the load is the Lab's 500
  words moving through colours by meetings; the set is 50, filled
  heard-first and retired by days - different rules, and either can be
  chosen without the other.
- Heard-first: 473 measured it put a blue word in more captions where
  words are rare (Chinese at 1,000 known words: 28 % of captions with a
  set of 50, against 7 % for 20 words by frequency).
- Between sittings only: nothing new turns blue while the learner reads.
- Histories now, while they cost a row a change: what the learner did
  can't be rebuilt later (undoing a test, the map's growth, "what
  changed" all need it - 474).

## What would make us reverse it

- The written curriculum's units (473's rider) arrive: the set is filled
  from units ready for the learner, and the rule here becomes their
  fallback for languages without units.
- The histories grow too big to keep: a status change a row is about
  60 bytes; marking the first 5,000 words known writes 5,000 rows
  (300 KB). If that matters, a bulk change becomes one row.

## How we'd reverse it

- The set: drop `Curriculum` and the `curriculum_words` table's use; a
  later migration can leave the table empty (migrations only add).
- The histories and word sets: stop writing them; old rows stay until
  "Delete learning data".
