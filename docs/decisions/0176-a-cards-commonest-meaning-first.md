# 0176 A card shows a word's commonest meaning first: rare senses last, entries by treebank counts

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, for polyglotic-hq project 393. Reversible.

## Situation

Every Wiktionary pack (`tools.dictionaries.kaikki.read_language`, behind the
generic reader of decision 0168 and the Spanish, Russian and Vietnamese
readers) kept Wiktionary's order, and Wiktionary lists a word's entries by
etymology and its senses as editors added them. So a card's first meaning
was often not the one a learner meets:

- Thai's กับ showed "trap" before "with", มัน "fat" before "it", คุณ
  "attribute" before "you"; Arabic's قد "to cut into strips" before the
  particle, بعد "to be distant" before "after";
- Spanish's reader keeps a two-letter letter's name: "de", "te", "ese"
  showed "the name of the Latin script letter D" first;
- a sense Wiktionary marks archaic or obsolete could come first (ออก "to
  pay" before "to go out").

A word's frequency rank can't tell its senses apart: they share one word.

## Decision

The reader orders, and only orders - every key, so every entry ID
(decisions 0007, 0089), stays as it was:

- **An entry's senses:** those tagged archaic, obsolete, dated,
  historical, dialectal, uncommon, poetic, nonstandard or proscribed
  (`kaikki.RARE`) after its others. Not "rare": kaikki gives a sense its
  construction's notes, so German's denken "to think" was "rare" for its
  rare transitive use.
- **A word's entries** (`kaikki.in_order`), within the places they had:
  a word's own entries, then those of only rare senses, then names (in
  a script with capitals; in Arabic or Thai a name keeps its place:
  مصر is Egypt), then letters and affixes; then the entry of the part of speech that
  Universal Dependencies treebanks use the word as clearly most often -
  at least 1.5 times as often as Wiktionary's first's (`LEAD`), and in a
  quarter of its uses (`MIN_SHARE`), over at least 5 uses - comes first.
  Otherwise Wiktionary's order stands.
- **A form whose page starts as another word's form** (`kaikki.lemma_first`,
  `packs.lemma_table`): its lemma comes before its own entries, where the
  form is no word of its own - not a verb's form (their own rule), not a
  derived word (a verbal or agent noun, a gerund, a "female equivalent"),
  at most one everyday meaning of its own, and not used by the treebanks
  more as its own entries' part of speech. Spanish's "su" had shown "about,
  approximately" before suyo's "his, her"; "una" "one (a pronoun)"; "mi"
  the note mi. The lemma is the one the page names (una: uno, not un).
- **The treebanks** (`tools.dictionaries.treebanks`) are polyglotic-hq
  359's, CC BY-SA (Spanish's AnCora CC BY), each pinned at its release
  2.17 commit and listed in the pack's sources and credits. Only counts
  are used: a word counts under its lemma and its form. Ukrainian's only
  large treebank is non-commercial, so Ukrainian has none.

## Why

On the 300 commonest words with more than one meaning in Thai, Spanish,
German, Russian and Arabic (polyglotic-hq 393's report), measured against
which meaning human translations of real sentences use, and by hand: of
the 176 first meanings the entry order moved, 92 got better, 7 worse; a
random 200 had 26 wrong first meanings before and 13 after. Other signals were measured and left out: senses with examples first made
it worse in every language; the English frequency of a gloss's words
helped Thai and Arabic slightly and hurt Spanish and German.

## What this changes for learners

A caption's word counts for its headword's first entry, and an inflected
form for its lemma's (decision 0089, 366's #698). Where either changes, a
status set by hand on the old entry no longer applies to that word; nothing
is deleted. polyglotic-hq 393's report counts the words per pack.

## What would make us reverse it

- Treebank genres mislead (news: Spanish's sí is "himself" more than
  "yes" there, so the margin keeps Wiktionary's "yes"): raise `LEAD`, or
  drop a language's treebanks (`treebanks.FILES`).
- A better signal for the senses within one part of speech (which
  meaning translations of real captions pick): it would replace or follow
  this ordering in `in_order`.

## How we'd reverse it

Remove the `uses` argument (Wiktionary's order of entries comes back),
empty `RARE` (its order of senses) or `Draft.lemma_first` (a form's own
entries first again), and rebuild the packs. IDs don't move either way.
