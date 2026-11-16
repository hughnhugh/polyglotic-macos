# 0173 Thai words are found by the pack's own words, and ranked by counting them in Common Voice

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, for polyglotic-hq project 389 (the user,
  2026-11-16: "feel free to parallelise more dictionary work"). A
  technical choice, reversible. Which frequency source may ship rests on
  389's licence reading (its report; the user decides). The pack reaches
  testers only once it is published in the signed list (decision 0122).

## Situation

Thai writes a sentence's words without spaces ("ฉันกินข้าว", I eat rice);
a space ends a phrase or a sentence. Before any lookup, rank or link, a
caption must be cut into words, and the installed app may not gain a
library for it (decision 0123: no simplemma, and none of PyThaiNLP's
models). Qt has no Thai line breaker on Windows (polyglotic-hq 294).

wordfreq has no Thai. polyglotic-hq 374 measured two licensed lists: the
Thai National Corpus's word counts as PyThaiNLP ships them (`tnc_freq.txt`,
which PyThaiNLP releases as CC0) and Common Voice's Thai sentences (CC0).
389 read TNC's own position: Chulalongkorn University built the corpus
from texts whose copyright holders each signed a permission form for it,
it is offered only through a web concordance, and the university's own
frequency lists are "all rights reserved". PyThaiNLP's CC0 covers what
PyThaiNLP made; it can't give rights it doesn't hold in TNC's counts.

## Decision

- **The word split** (`core.lexicon.thai`): each run of Thai letters is
  cut into the pack's written forms at the least cost. A word costs
  `WORD` (4) plus log2 of its rank; each cluster no word covers costs
  `LEFT_OVER` (20), more than any ranked word, so the pack's words cover
  what they can. A tie goes to the longer first word. A cut never falls
  inside a Thai character cluster (before a mark or a following vowel,
  after a leading vowel, before a consonant silenced by ์), and the
  pieces no word covers are joined into one (a name stays whole). ๆ is a
  word of its own, not a content word. Words in another script are
  words as English's are. A word is matched with its marks in Unicode's
  order and with ำ written either way (the speech model sometimes writes
  it as ํ + า, as in "ประจํา"), and looked up as the pack writes it. The
  pack's forms are read once, at the first split (about 70 ms for 18,957
  forms). It is plain Python with no library, so every app with this code has it: the list names the pack's
  split `thai` (`tools.package.publish_packs`), and an app from before it,
  which would take a phrase for one word, is never offered the pack.
- **The pack** (`tools.dictionaries.packs`, `wiktth`): Wiktionary's Thai
  words with English meanings and Paiboon romanization (what learners
  read; polyglotic-hq 370), in one English file. Not Wiktionary's letters'
  own entries, symbols or affixes; no one-letter written form but ณ
  ("at") - the others are archaic, an ordinal or texting's spellings, and
  they let the split take any lone consonant for a word. A Thai entry's
  classifier and abstract noun (ตัว for หมา, ความดี for ดี) are other
  words, not its forms; other spellings are forms of their own, so the
  split finds them (`tools.dictionaries.thai`). Every entry is kept,
  ranked or not (`Draft.keep_unranked`): the split needs the words, or one
  the pack lacks is cut into shorter ones it has - กาแล็กซี (galaxy),
  never said in Common Voice, had been read as กา (crow) + แล็ก + ซี on
  the loop's captions.
- **The ranks:** the words of Common Voice's Thai Sentence Collector
  file (62,875 sentences, CC0), each line cut by the same split over the
  pack's forms, counted twice - the second count cut with the first's
  ranks, as the app's split is (`tools.dictionaries.thai.counted_words`).
  Only words the pack has are counted. Only the ranks reach the pack.
  TNC's counts are not used.

## Why

389 measured each choice (its report has the detail):

- **The split**, against UD Thai's hand-segmented sentences (UD_Thai-PUD,
  CC BY-SA 3.0; UD_Thai-TUD, CC BY-SA 4.0): word F1 74.2 % on PUD and
  77.6 % on TUD's test, where PyThaiNLP's newmm gets 67.0 % and 69.0 %.
  Most of the rest is UD's own convention: it cuts compounds Wiktionary
  lists whole (ได้รับ, พวกเขา, หลังจาก), which a learner looks up whole.
  The costs barely matter on UD (77.8-78.9 % across the settings tried
  on TUD's dev set); the one chosen keeps compounds and never leaves a
  ranked word's cluster over. It takes about 0.13 ms for a 125-character
  line, and 0.9 ms with every word's lookup.
- **The ranks:** a learner who knows the pack's top 1,000 words knows
  72.9 % of FLEURS's running Thai words and 81.0 % of Tatoeba's (top
  3,000: 87.2 % and 93.7 %). Ranked by TNC + Common Voice instead, as
  374 proposed, the same pack gives 72.9 / 79.8 % (87.5 / 93.0 %); by TNC
  alone 73.6 / 77.4 % (85.9 / 87.5 %). Common Voice alone costs nothing a
  learner would notice; 1,538 fewer words have a rank (13,485 against
  15,023), and they are rare ones.
- **The pack:** 19,698 entries (13,485 ranked), 3.7 MB. It finds 91.3 %
  of UD Thai-PUD's gold Thai words and 95.4 % of TUD's test (whatever
  ranks it has), and its words cover 97.9 % of the Thai letters of
  FLEURS's test sentences. The coverage probe says 96.3 %, but with its
  own split it can't miss a word the split made: the UD figures are the
  independent ones. Keeping the unranked entries added 1.2 MB, 0.6 points
  of word F1 on PUD and 0.8 points of PUD's gold words found.

## What would make us reverse it

- Chulalongkorn University (or TNC's maintainers) grants the use of TNC's
  counts and a learner measure shows them better (389 found none).
- A native reader finds the split wrong often on real captions: a
  dictionary-led split is only as good as the pack's words, and names it
  hasn't got can be cut into short words it has.

## How we'd reverse it

- The ranks' source is one line of the pack's config (`frequency`) and
  one source pin.
- The split is one choice in `main.open_pack` and `coverage.split_for`;
  a different split for packs already published would be a new split
  name in the list (`publish_packs.SPLITS`), so apps without it keep the
  pack they read.
- Entry IDs don't depend on either (decision 0007).
