# 0240 Korean words open on what a caption most likely means, and its compounds show their parts

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** Claude, for polyglotic-hq project 516 (the Korean pack
  held under the floor by 510, draft #896). A technical choice,
  reversible. The pack reaches testers only once it is published in the
  signed list (decision 0122).

## Situation

510's Korean pack (Wiktionary's Korean words, ranked by wordfreq) found
87.8 % of the probe's words against the basic tier's 90 % and opened 78 %
of an audit's lookups on the right first meaning. Three things in the data
caused most of it:

- **wordfreq counts Korean by its parts**, as an analyser cuts it: a noun
  without its particles, a particle alone, a verb's or an adjective's stem
  (있 for 있다) and its past fused onto a vowel stem (갔 for 갔다). A
  predicate whose stem is also another word's spelling had no count: 가다
  (가 is the subject particle) was the 3,268th word, 먹다 (먹, ink)
  unranked, while a hanja syllable or a jamo's name took the stem's count
  (랑 the 133rd word, 크 the 222nd).
- **Wiktionary lists a word's entries by etymology**, so a form that is
  also a rarer word opened on that word: 대한 (대하다's "about") on "great
  khan", 마다 (the particle "every") on "to smash", 했다 on "newborn baby",
  있다 on "to stay", 안 (not) on "inside".
- **Korean closes compounds up** (국립공원, national park) and Wiktionary
  lists few; many Sino-Korean words have only their hanja's page (海上,
  "hanja form of 해상 (“maritime”)").

## Decision

- **Ranks** (`tools/dictionaries/korean.py`, `packs.read_korean`): a
  predicate is ranked by its fused past (갔 for 가다) and by its stem
  where the stem is no word of its own (있), only a hanja syllable's or a
  jamo's page (크), or a word whose count is mostly the predicate's, read
  by hand (`STEM_SHARED`: 먹, 알); never by the past, the honorific or an
  affix's count (셨, -째). An entry that is no word a learner meets (a
  hanja syllable's reading, a root, a jamo's name) takes no rank.
- **Which entry first:** hand-read tables over the commonest words, as
  Thai's first meanings are (decision 0173, polyglotic-hq 461): particles
  whose own entries are rarer words open on the dictionary's particle
  (`PARTICLE_FIRST`: 마다 on -마다); forms of a common predicate, or 것
  written short, open on it (`OPENS_ON`: 대한 on 대하다, 갈 on 가다, 게 on
  것); the commonest words' first meanings (`FIRST_SENSES`). A word with an
  adverb's, a determiner's or another small word's entry keeps it first
  (하지만, "but"), and a predicate's own dictionary form keeps its own
  (들리다, not 듣다). A sense that only says "See the entry at -는" is a
  form of -는. A word Wiktionary has only under its hanja gets an entry
  with those pages' meanings.
- **In the app** (`core.lexicon.korean_forms`, `compounds`, the split's
  `AFTER_A_BRACKET`): particles come off one another (월까지이다: 월), a
  particle alone is looked up as the dictionary lists it (라고: -라고) and,
  right after a bracket or a quote, is the word inside's ((성지)이: -이);
  an everyday noun of one syllable comes before a predicate (`COMMON_NOUNS`:
  일을 is 일, not 일다), an ending in 으 is never taken after ㄹ, and 해 and
  했 are 하다's before any other stem. A word the pack hasn't got, whole or without its particles,
  shows its noun's parts: words of two syllables or more, then a
  one-syllable suffix or word read by hand at its end (`COMPOUND_ENDS`:
  -성, 층) or a prefix at its start (`COMPOUND_STARTS`: 대-) - 국립공원은 is
  국립 + 공원. Its particles are no parts, as 학교에서's 에서 is no word of
  the caption's. Never single syllables alone: any of them is some word.
- Tested in `tests/tools/test_packs.py` (a pack built from a few
  Wiktionary lines and wordfreq's counts by parts), `tests/lexicon/
  test_korean.py` and `test_compounds.py`.

## Why

- No Korean treebank is among the pinned sources, and wordfreq can't tell
  대한 the noun from 대하다's form: the counts that decide other languages'
  order (decision 0176) aren't there. A table read by hand over the
  commonest words fixes what learners meet most, and a new extract that
  loses a listed meaning stops the build rather than undoing it quietly.
- Counting a stem for both its predicate and the word it spells (먹 for
  먹다 and ink) ranks the rarer one too high; leaving it out had cut the
  commonest verbs from the ranks, which is worse for a learner.
- A compound's parts on the card ("national + park") beat "no entry";
  the two-syllable rule and the affix lists keep names written in hangul
  (파티마, Fatima) from being cut into nonsense.

## What would make us reverse it

- A Korean treebank or parallel text pinned as a source, which could
  order the entries by counts instead of a table.
- Audits finding the tables' choices wrong for learners' captions (spoken
  Korean differs from FLEURS' read news), or compounds cut wrongly more
  often than rightly.

## How we'd reverse it

Empty the tables in `tools/dictionaries/korean.py` and rebuild the pack
(the IDs stay: only order and ranks change); drop the `"ko"` branch in
`compounds.parts`. Each is a small change; the app's guesses in
`core.lexicon.korean_forms` stand alone.
