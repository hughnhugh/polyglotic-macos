# 0162 A pack's ranks are refused when their top 1,000 carries junk

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** polyglotic-hq project 374's brief ("a test or check in
  `tools/dictionaries` that refuses a rank list with the junk 325 found");
  the user's #176 (ranks are the only "known" line in every language);
  Claude reviews before merge.

## Situation

Ranks are now what "I know about N words" means in every language
(polyglotic-hq DECISIONS #176), and they gate each language's pack (#175).
polyglotic-hq 325 found junk in a built pack's top 1,000: affixes taking
their stem's frequency (79 in Russian's), names spelled like common words
(28), hyphenated junk, a capitalised abbreviation lending "northwest" the
frequency of "no". 325 fixed each cause in `packs.frequencies`, but nothing
stopped a new language, a new list or a builder change from bringing it
back unseen. 374 found one more kind in a French pack built on 341's branch:
seven numbers ("311", "9-3", "4x4") in the top 1,000.

## Decision

- **`tools.dictionaries.rank_check.problems`** reads a built pack's records
  and lists what is wrong in its top 1,000 words: any affix; any word with a
  digit; more than 30 names (every entry of the word a name); more than 10
  Latin-alphabet words in a language not written in it; in a language that
  writes a word's syllables apart (Vietnamese), fewer than 5 % of the top
  words with a space (the list ranks syllables).
- **`packs.build`** runs it and says "ranks pass the junk check"; `packs`
  exits 1 when a pack fails it, as it does under the coverage floor, so the
  packs workflow fails.
- **A word with a digit takes no frequency** (`packs.frequency_of`), the
  cause of the French numbers.
- Tests: `tests/tools/test_rank_check.py` (each rule), and
  `test_packs.py`'s build test (a failing pack says so).

## Why

- A check on the built records sees what a learner gets, whatever list or
  rule produced it; checking each list instead would miss what the builder
  does to it (the affixes came from the builder, not from wordfreq).
- Limits are counts in the top 1,000, not shares, so a small pack is held to
  the same line. They sit above what good packs carry on 2026-11-16:
  Spanish 10 names, Russian 9, French 15, Japanese and Vietnamese 0;
  Vietnamese 32.9 % of its top words with a space.
- Alternatives: a warning only (junk would ship unread); filtering junk
  silently in the check (hides a builder bug behind the check).

## What would make us reverse it

A language whose real top 1,000 needs more names or Latin words (a
language written in two scripts, a pack with many loanwords), or a rule
that refuses a pack a native reader finds right.

## How we'd reverse it

Change a limit in `rank_check` (one constant each), or drop a rule; the
build keeps reporting the rest. Removing the check is deleting the module
and its two lines in `packs.build` and `packs.main`.
