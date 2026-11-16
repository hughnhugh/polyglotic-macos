# 0130 Word links "past what you know" are judged by how common a word is

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** Claude, after the user's report on 0.1.5 (polyglotic-hq
  338: "So many basic words continue to be linked"); a reversible choice
  within 323's agreed design, recorded for review.

## Situation

323 (2026-11-14) made word links follow what the learner knows: with
"Past what you know" - the default for every language added since - a
link shows unless every word under it is one the learner knows. Its tests
checked chosen words on made-up captions. Measured on real captions
(100 FLEURS sentences per language, `tools.links_measured`), basic words
were still linked, for reasons the made-up captions never met:

- **A line kept as a level** - and the one every learner is estimated at
  until they set their level (HSK 3, decision 0114), which every newly
  added language has - knew only the words its syllabus puts at or below
  the level. A word the syllabus puts higher or leaves out was "rarer",
  so linked, however common: 与 (the 27th commonest word, HSK 4), 而
  (33rd), 一个 (34th, no level of its own). 62 % of a Chinese caption's
  words were linked with no level set, against 46 % at 1,000 words.
- **Names** were always linked: 美国, 日本, America, English, North and
  Sunday are among the commonest words in both dictionaries.
- **Numbers** were linked: 1940, 100 and 5 aren't in any dictionary.

## Decision

With "Past what you know", a word needs no link when:
- the learner set it known or ignored (as before); else
- the line knows it (as before); else
- it is placed (its frequency rank, or its syllabus level's size where
  that's smaller: `place`) within the words the line stands for. A line
  in words stands for its own number; a line kept as a level, for its
  level's size in its scheme (HSK 3: about 1,000 words;
  `KnownLine.words_known`, the sizes handed in from Lexicon by `main`).

A name is placed like any other word: a common one isn't linked, one with
no place - most names - is. A link with no letters under it (a number)
isn't linked. "Every word" still links every word, numbers too.

A word the dictionary hasn't got, or can't place, stays linked: nothing
says the learner knows it, and on real captions those are mostly names,
foreign words and rare compounds, whose translation is what a learner
would look up.

Tested at the domain level (`tests/learning/test_vocabulary.py`) and in
the link rule (`tests/ui/test_links_by_what_is_known.py`).

### Whose choice: the captioned language decides

A link pairs a word with its translation, and each row's language may
have a say. 323 showed a link if any row with a say kept it. On real
captions (Claude's validation loop, 346) that kept known words linked for
a learner of Chinese and English: 目前 (known at 5,000 Chinese words) kept
by "currently", "is" kept by 身处 on English speech, and - with Chinese
at "Every word", as every language learned before 323 kept, and English
added since at "Past what you know" - every link of an English caption.

The user decided (2026-11-15 ~11:10): "it should be determined by
captioned language not by translated language". When the learner learns
the language heard, its row's say alone shows or hides a link
(`views.links.hidden_links`); a translation row's say counts only when
the language heard isn't learned (hearing Japanese while learning
Chinese: the Chinese words decide).

### A basic dictionary's language: by its pack's ranks

A language looked up in a basic dictionary keeps no learning data
(decision 0035), so no level. 323 showed only key links there, trusting
the server to mark function words minor; the server's lists are Chinese
and English only, so every Russian, Spanish or Japanese word came marked
key and every word was linked (99 % of a Russian caption's words). Its
pack ranks its words (decision 0120): with the pack on this PC, a word
needs no link when it is placed within the place the learner chose on
its card ("Start links at", now offered for it), or the 1,000 commonest
until they choose (`UNKNOWN_LEVEL_LINKS_FROM`: about the words a learner
is estimated to know until they set a level). Without its pack, key
links only, as before.

## Why

The learner reads "past what you know" as "not the words I know". How
common a word is answers that for every word; the syllabus answers it
only for the words it lists, and its levels put very common grammar words
(与, 而) high. Placing by rank only where the level doesn't already know
the word keeps every word a level knew known.

Not taken: changing how highlights read a level line (there "rarer" means
not pointed out, which is right for 与); moving every learner to a line in
words (the learner's level is theirs to set, decision 0114).

1,000 for a basic language: Russian at 1,000 links 42 % of a caption's
words (at 500, 51 %; at 2,000, 31 %) - the same share as Chinese at 1,000
words (44 %). The card offers 500 to 8,000.

The captioned language deciding is the user's rule, and the simplest:
one row decides, the one in the language heard. (338 first made only a
translation row's "every word" lose its say; the user's rule covers that
case and the known words kept by a "past what you know" translation.) A
first-principles design of word links is 340's.

## What would make us reverse it

Learners saying common words they don't know lost their links - for
example a name known in English but not in Chinese, or a grammar word
like 与 they want to see paired.

## How we'd reverse it

`Vocabulary.needs_no_link` and `views.links._all_known`: a few lines
each, and their tests. The measurement (`tools.links_measured`) shows
the effect of any change on real captions.
