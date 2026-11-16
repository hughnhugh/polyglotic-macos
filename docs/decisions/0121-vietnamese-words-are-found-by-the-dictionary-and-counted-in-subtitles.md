# 0121 Vietnamese words are found by the dictionary, and ranked by counting them in subtitles

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, for polyglotic-hq project 325 (the user,
  2026-11-14: "maybe start with vietnamese and russian additions"; a
  tester watching Vietnamese asked for marks on rarer words only). A
  technical choice, reversible. Which frequency source may ship was the
  user's call (polyglotic-hq DECISIONS #146): on 2026-11-14 the user
  took the risk of counting OPUS's subtitles ("Ill take the vietnamese
  risk", option A). The pack reaches testers only once it is published
  in the signed list (decision 0122).

## Situation

Vietnamese writes every syllable apart: "học sinh" (pupil) is two
syllables and one word. Before any lookup or rank, a caption must be
split into words. Two problems follow:

- The basic packs' splits (simplemma, Sudachi) don't apply. The
  candidates measured were pyvi (MIT, but it brings scikit-learn and
  SciPy), underthesea (Apache-2.0; a CRF model trained on VLSP's data),
  VnCoreNLP (GPL-3.0, Java), and a dictionary longest match like
  Chinese's.
- Every published frequency list counts syllables, not words. wordfreq's
  and OpenSubtitles' lists have "học" and "sinh" but never "học sinh".
  Estimating a word from its syllables put "là là" and "có là" among the
  top 30, and only 28 % of its top 1,000 matched what subtitles say.

## Decision

- **The word split** (`core.lexicon.vietnamese`): each run of syllables
  with only spaces between them (a comma, digit or line break ends one)
  is cut into the pack's written forms. The cut uses the fewest words,
  then the commoner words by rank, then the longer first word. It is
  Chinese's rule (`core.lexicon.chinese`), over syllables. A syllable
  the pack hasn't got is a word of its own. The pack's forms are read
  once, at the first split: 92 ms for about 34,000 forms, on the thread
  that warms a pack as it opens (`main.PackDelivery`). It is plain Python
  with no library, so every app with this code has it: the list names
  the pack's split `vietnamese` (`tools.package.publish_packs`), and an
  app from before it, which would cut "học sinh" in two, is never
  offered the pack (`core.lexicon.packs.Reader`; decision 0123). The
  build's own check splits a line of a small Vietnamese pack
  (`main.try_a_pack`).
- **The pack** (`tools.dictionaries.packs`, `wiktvi`): Wiktionary's
  Vietnamese words in the Latin script, of one or more syllables, with
  English meanings and IPA, in one file: no `-zh` copy. Meanings in
  other languages are to come as files of their own per dictionary and
  app language (polyglotic-hq 326, DECISIONS #143); until then the list
  has only its English file, which every app gets whatever meanings it
  asks for (`core.lexicon.packs.best_offer`), and a PC opens it so
  (`main.PackDelivery.start`). Hán Nôm characters are left out. Another spelling
  ("bất kỳ" for bất kì, "hoà" for hòa) is a written form of its word, so
  the split finds it.
- **The ranks:** words counted in OPUS's OpenSubtitles v2018 Vietnamese
  text (34 million syllables), each line cut by the same split over the
  pack's words (`tools.dictionaries.vietnamese.counted_words`), at build
  time. Only the ranks reach the pack. The subtitles' text never does.

## Why

325 measured each choice (its report has the detail):

- **The split:** on 60 hand-checked lines (the app's own captions of
  FLEURS, Tatoeba, subtitles), 97.9 % of words were right with the pack's
  ranks. pyvi got 96.1 % and underthesea 94.6 %. It takes 0.04 ms a line
  and 0.2 ms for a 138-syllable line with lookups. It adds no dependency.
  Its misses are words English Wiktionary lacks: xảy ra, tối nay, cứu hỏa.
- **The ranks:** for a learner who knows the top 1,000 words, ranks
  counted from subtitles know 79 % of Tatoeba's running words; the
  syllable estimate knows 60 %. Counting Tatoeba itself (CC BY) did as
  well for the top 2,000 but ranked only 8,546 words, and its export is
  rewritten in place (last on 2026-11-07), so a pin breaks whenever it
  changes - until we keep our own copy.
- **The pack:** it finds 95.1 % of the FLEURS probe's content words and
  95.8 % of running words in the app's FLEURS captions. It is 4.5 MB.

## What would make us reverse it

- The legal reading of counting OPUS's subtitles changes (325's report
  sets it out). The next choice is Tatoeba's counts, from a mirrored copy.
- A learner or native reader finds the split wrong often in real
  captions. pyvi or underthesea would go behind the same `WordSplit`
  port.

## How we'd reverse it

- The ranks' source is one line of the pack's config (`frequency`) and
  one source pin.
- The split is one adapter choice in `main.open_pack` and
  `coverage.split_for`. A different split for packs already published
  would be a new split name in the list (`publish_packs.SPLITS`), so apps
  without it keep the pack they read.
- Entry IDs don't depend on either (decision 0007).
