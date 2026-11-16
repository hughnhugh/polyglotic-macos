# 0114 The level is a known line in words, with a learning window past it

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 323 (the user, 2026-11-14: "word
  frequency should be universal standard"; "known words (x thousand
  words), learning words (x to x+1 thousand words) ... rarer words which
  are outside of learning scope"). Replaces the level curve of project 019
  (MVP.md, "Known words", 2026-11-04).

## Situation

The learner's level was a curve on a level scheme's scale: an HSK level
or an English frequency band, a midpoint half a level above the level
picked, a slope, and a chance from which a word counted as known. With
whole levels the curve only ever cut at the level picked: it was a line
with three constants nobody could tune. A tester (2026-11-14) asked for
marks only on rarer words, and the user for three kinds of word, known,
learning and rarer, said the same way in every language.

Frequency rank alone can't be that scale for Chinese. The pack's ranks
come from written text (jieba's counts): of HSK 1's 300 words, one in ten
is ranked past 10,000 (谢谢 is 6,361st, 你好 8,621st, 再见 14,387th), and 20
of the 300 most frequent words are not in the syllabus at all (湖北, 石首,
天安门). Measured on the pack of 2026-09-27 (polyglotic-hq 323's report).

## Decision

- **A known line** (`core.learning.levels.KnownLine`): "I know about the
  X most common words". A word is estimated known up to the line.
- **A learning window** (`LearningWindow`): the next N words past the line
  (100, 500, 1,000 or 2,000; 1,000 until chosen). New words in it are the
  ones a caption points out. Past it a word is rarer: never pointed out,
  whatever "Word introductions" says; still looked up on hover or a click.
- **A word's place** on the scale is the smaller of its frequency rank
  and the size of its level's vocabulary in the language's syllabus
  (`EntryFacts.level_words`, from Lexicon: 1,000 for an HSK 3 word). So a
  learner at 1,000 words knows 谢谢 though the frequency list puts it at
  6,361, and "HSK 3" and "about 1,000 words" are the same line said two
  ways. A language with no syllabus is placed by rank alone.
- **A status set by hand always wins** (unchanged): the line only
  estimates.
- **Levels kept before this read as they did.** A stored level scheme and
  midpoint is a line kept as a level (`KnownLine.by_level`): known at or
  below the level, the window the level above, words outside the scheme
  rarer, and "Every new word" still every new word. A test checks it gives
  each word what the curve gave, for every level of every scheme. The line
  becomes one in words when the learner next says how many words they
  know.
- **Kept where the level was** (decision 0048): the learning store's one
  `level` row and the file beside it, as the scale `words` and the number.
  No new table or column, so a version before this still opens the file;
  it reads a scheme it doesn't know and marks no words until the level is
  picked again there. The window's size is a setting, per language.
- **Bulk "mark the top X known" is moving the line**, not thousands of
  stored statuses: it can be moved back, and nothing is sent to the
  server.

The curve's constants (`SLOPE`, `KNOWN_AT`, `NEXT_BAND`) are deleted.
`docs/rule-cases/levels.json` and `highlights.json` say the new rule.

## Why

- One scale every language with a frequency list can use; the syllabus
  only ever makes a word more common than its rank says, never rarer.
- The line and window are two numbers a learner can say and see, where
  the curve's were three they couldn't.
- Not rank alone for Chinese: it would mark 谢谢 for a learner of 3,000
  words. Not HSK alone: 5,543 of the syllabus's 10,860 words are in its
  last level, and a frequent word outside the syllabus was never known.
- Not a migration of what's stored: reading the old values as the same
  line changes nothing a learner sees, and needs no file change an older
  version would refuse.

The cost: in Chinese the words up to a line number more than the line
says, since both lists count (at 1,000: 1,604 headwords; at 3,000:
3,803). "About" is honest for it; the report gives the table.

## What would make us reverse it

A spoken-language frequency list for Chinese (subtitles) good enough that
the syllabus adds nothing; or learners finding the window's edges too
sharp (a word at 3,001 never marked, one at 2,999 always), which is what a
curve was for.

## How we'd reverse it

`place` is one function: a better list changes the pack, not the rule. A
soft edge is a change inside `KnownLine.knows` and `LearningWindow.reaches`;
what's stored (a scale and a number) would stay.
