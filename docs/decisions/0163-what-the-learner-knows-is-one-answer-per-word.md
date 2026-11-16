# 0163 What the learner knows is one answer per word, with the line as a frequency rank

- **Status:** accepted (step 1 of 349's migration; later steps add to it)
- **Date:** 2026-11-16
- **Decided by:** the user, polyglotic-hq DECISIONS.md #170 and #176
  (2026-11-16 ~00:05: "go with your safe default", "we don't really need
  levels for any languages, can just use word frequency ranking"); built by
  polyglotic-hq 373 from 349's design (draft #667, not merged)

## Situation

About ten places decided whether a learner knows a word, and they
disagreed (349's report): the known line, the learner's own marks, a
pinned lookup, the load's check, "mark the first N", word links' own rule,
"Start links at", basic languages' rank rule in the interface code, the
server's key words and Lexicon's base words. For a learner with no line
set, 15 % of the words in formal Chinese speech were "new" to marks, the
load and coverage, and "known" to links. Every new feature (pinyin past
what you know, a quiz, Anki import) would have worked "known" out again.

## Decision

- One `Knowledge` per language learned, in `core/learning/knowledge.py`,
  and one question: `of(word, as_if_knowing=None)`. The answer (`Knows`)
  is the word's status (the glossary's four), a confidence (sure, likely,
  a guess) and the reason. Evidence, strongest first: what the learner
  said about the word; an import; a pinned lookup of an assumed-known
  word; a number in numerals; the line; the words an unplaced form is
  made of; nothing.
- **The line is a frequency rank**, "I know about N words"
  (`Knowledge.known_words`), one number per language so it can sync later.
  A line kept as a level from before (the level picker, the starting HSK
  3 or English's 3,000) is read as the number of words its level stands
  for; only a scheme that gives no number (HSK 3.0's 2021 standard) is
  still read by level.
- A basic dictionary's language (Russian, Vietnamese...) asks the same
  question of a line alone (`Knowledge.by_line`), until it keeps learning
  data of its own.
- **Readers so far:** word links, full and basic languages
  (`Vocabulary.needs_no_link`, `LearningTools.knowledge_of`). Marks, the
  learning load, coverage, bands and Words still read
  `Vocabulary.status`; moving them (349's step 3) changes what a learner
  with no line set sees, so it waits for the user's word (#176 (a)).
- Each feature keeps its own policy over the one answer (a link hides a
  known word; marks skip names) and never works the answer out again.
- Enforced by tests: `tests/learning/test_knowledge.py` holds the
  evidence order and checks that links answer exactly as before for every
  kind of word, line and "Start links at" (`links_before`, main's rule at
  ce9a8fb3).

## Why

- One place to fix a wrong answer and to add evidence (lookups kept,
  an Anki import, a quiz).
- The user asked for no levels in any language: a rank is one number every
  language with a frequency list has, levels are a Chinese-and-English
  special case.
- Three confidence grades, not a number: nothing measured yet tells 0.7
  from 0.8.
- Not taken: moving every reader at once (349's prototype moved links only
  for the same reason: the other readers' change is visible and needs the
  user); dropping the stored level outright (old files keep it, and 0.1.6
  reads it).

## What would make us reverse it

- A feature that needs an answer the evidence order can't give (a
  learner's word that the app should overrule) - the user ruled that out
  for now (#176 (d): a word marked known stays known).
- Learners who want levels back (an HSK level is shown as a label only).

## How we'd reverse it

Readers go back to their own rules: `needs_no_link` to its body at
ce9a8fb3 (kept in `test_knowledge.links_before`), caption marks' basic
branch to `placed_within`. `knowledge.py` and its tests go; nothing is
stored by it, so no data changes.
