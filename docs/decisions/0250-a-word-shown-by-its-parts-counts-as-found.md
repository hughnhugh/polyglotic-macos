# 0250 A word shown by its parts counts as found

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** the user, polyglotic-hq DECISIONS #227 (2026-11-18
  ~19:05: "yes sure, i'll let you make decisions for this thread" - words
  shown by their parts count as found, in every language). Built by
  polyglotic-hq project 533.

## Situation

A basic pack must find 90 % of the content words in 100 FLEURS sentences
of its language (`tools.dictionaries.coverage`, polyglotic-hq 157's rule).
The probe counted a word as found only if the pack had it whole. But a
word the pack hasn't got whole can still be useful on the card: a
hyphenated word in any language, and a closed German or Korean compound,
is shown by its parts (`core.lexicon.compounds`; Arbeitsplatz is Arbeit +
Platz, 국립공원 is 국립 "national" + 공원 "park"). Thai's, Vietnamese's
and Cantonese's word splits already cut such a word into the pack's words
before the probe sees it, so each part counted as found there, and the
same word in German or Korean counted as missed.

The Korean pack (polyglotic-hq 510, 516) found 89.1 % by the strict count
and 90.7 % counting words shown by their parts; what it still misses is
mostly Latin letters, names and loanwords, which no lookup closes.

## Decision

- `coverage.measure` counts a word as found when the pack has it whole,
  or when the card shows it by its parts and every part is a word the
  pack has (`coverage.shown_by_parts`). A hyphenated word with a piece the
  pack hasn't got (T-Rex's "Rex") stays a miss.
- The same rule for every language; the probe says how many were found by
  their parts (`Coverage.by_parts`), so a pack's figure can be read both
  ways.
- Enforced by `tests/tools/test_coverage.py` and by the packs' build,
  which records the share in each pack's `info` and fails below the floor.

## Why

- It measures what a learner gets: the card for 국립공원 says "national"
  and "park", which is what the floor stands for.
- It treats the spaced languages as the languages with their own word
  splits were already treated.
- The alternative, keeping the strict count, held Korean back on words a
  dictionary lookup can't close (polyglotic-hq 516's misses).

## What would make us reverse it

- An audit of a pack (448's rubric) finding that cards shown by their
  parts mislead learners often - wrong cuts like 프로테스트 ("protest")
  as 프로 + 테스트 - so that a pack passing only by its parts teaches
  wrong meanings.

## How we'd reverse it

Drop the `shown_by_parts` branch in `coverage.measure` (a few lines and
its test); the packs' recorded shares fall back to the strict count at
their next build, and any pack that then misses the floor is held.
