# 0120 A dictionary's frequency ranks say what they are, and come from lists its pack names

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, for polyglotic-hq project 325 (the user,
  2026-11-14: "word frequency should be universal standard"; "See if you
  can expand to get frequency rankings for more languages too"). A
  technical choice, reversible; which lists a language uses is measured
  and said in 325's report.

## Situation

Project 323 makes one scale, a word's frequency rank, decide which words
count as known, which are pointed out and which get a word link, in every
language a learner adds. Every dictionary file already has a
`frequency_rank` per entry, but:

- nothing in a file says what its ranks are, so a language whose
  dictionary has none can't say so, and a reader can't tell "never met"
  from "not ranked";
- every basic pack's ranks came from wordfreq alone. wordfreq has no
  hyphens and no capitals, so the pipeline gave Russian's prefix "в-" the
  frequency of "в" (it was the pack's commonest entry) and the river
  "Или" that of "или" ("or"): 79 of Russian's top 1,000 entries were
  affixes and 28 were names, among them every sentence-initial "Или";
- a pack ranked entries, not words: "в" (a preposition) and "в" (the
  letter's name) took ranks 1 and 2, so Russian's "top 1,000" was about
  700 words, while CC-CEDICT's entries of one word share its rank;
- wordfreq blends written text with speech, and captions are speech.

## Decision

- **What a file says** (`info`, `adapters.sqlite_dictionary.RANKS`):
  `ranks` = "1" means each entry's `frequency_rank` is its word's
  place, 1 the commonest, by the lists named in `frequency_source` - a
  headword's entries share one rank, so "the top 1,000" is a thousand
  words; an inflected form counts for its lemma's entry; an entry
  without one was never met by the lists (a name, a rare word);
  `ranked_entries` says how many entries have one. Every dictionary
  writes them: CC-CEDICT (jieba's counts), ECDICT and the packs. A file
  without `ranks` was built before this: its ranks are the same for
  CC-CEDICT and ECDICT, but a basic pack's counted entries.
- **Where a pack's ranks come from:** the lists its config names
  (`packs.Pack.frequency`): wordfreq's, or a list of counts in
  FrequencyWords' `word count` format (`tools.dictionaries.frequency`).
  Several lists are averaged: a word's frequency is the mean of its
  share in each list that could have it.
- **Rules every list goes through** (`packs.frequency_of`,
  `packs.frequencies`): an affix ("в-", "-ить") has no frequency; a
  capitalised entry whose word in lower case is another entry or an
  inflected form ("Или") takes none of that word's; a hyphenated word
  a list hasn't got is estimated from its parts (wordfreq splits at
  hyphens: премьер-министр), but no higher than the rarest word of a
  list that counts hyphenated words whole ("у-т" and "так-с", made of
  common parts, had been in Russian's top 100). Entries left
  without a rank are cut from a pack as before, so "Или" at the start of
  a sentence finds "or".

Tests hold each rule (`tests/tools/test_frequency.py`,
`tests/tools/test_packs.py`).

## Why

- A reader that knows what ranks mean can treat a language with ranks as
  a full participant in 323's scale and one without as one without,
  without guessing from the data.
- The rules and word ranks alone matter: 325 measured Russian's pack on
  held-out text - for a learner who knows the top 1,000 words, the share
  of running words known in 20,000 of Tatoeba's conversational sentences
  went from 70.2 % to 73.7 %, and in FLEURS captions of read news from
  54.1 % to 58.5 %.
- Averaging lists keeps what each is good at. Averaged with
  OpenSubtitles' counts, the same learner knows 76.9 % of Tatoeba's
  running words and 56.8 % of FLEURS'; subtitles alone did best on
  conversation and worst on news (about 49 %).
- Not taken: a single "spoken" list for every language (none covers them
  all, and news-like captions suffer); levels per language from
  examinations (few are open; frequency is the one scale every language
  can have).

## What would make us reverse it

- 323's learners, or testers, find the bands wrong for what they hear:
  measure again with their kind of captions.
- A list with better licensing or register for a language appears.

## How we'd reverse it

Change a pack's `frequency` (one line) and rebuild: entry IDs don't
depend on ranks (decision 0007), so learners' words carry over. Dropping
the `info` keys means 323's reader falls back to "ranks if any entry has
one".
