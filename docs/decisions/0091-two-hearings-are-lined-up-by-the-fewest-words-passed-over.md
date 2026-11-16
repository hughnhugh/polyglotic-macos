# 0091 Two hearings are lined up by the fewest words passed over

- **Status:** accepted (amends 0088's "Where the update carries on")
- **Date:** 2026-11-13
- **Decided by:** polyglotic-hq project 301 (its brief: "A caption may
  keep a slightly worse word; it must not lose words"); Claude reviews it
  with the pull request, and the user may overrule it.

## Situation

Settled text (0088) keeps the words a caption has shown for 3 s and takes
only what comes after them from an update. To know where "after them" is
in the update, the two hearings are lined up word by word. 0088 did that
with `difflib`, which takes the longest run of shared words first and
breaks a tie by the earliest place in the old hearing.

QA batch 7 (polyglotic-hq 300) found what that costs. When the update
loses - or hears differently - a word just before the settled point, and
a common word comes a little later, the settled word is lined up with the
later one:

- shown "...entered the yard", settled up to "the";
- heard again as "...entered yard and cornered the inmates";
- `difflib` lines "the" up with the later "the": the caption became
  "...entered the inmates". Three words the learner should have read are
  gone.

In 300's 360 made-up seams of this kind per language, 16 English words
were lost in 5 cases, and 6 Mandarin characters. 300's own
candidate (leave out a lone shared word that puts the update two or more
words further on) cut that to 6 words: it still let `difflib` choose
"the" before "yard" whenever the later word was only one word out, or was
part of a run of two.

## Decision

`core/listening/settling.py:_shared` lines the hearings up itself, by
cost:

- **The update is the old speech again, and then goes on.** Every old
  word is either found in the update or passed over; so is every word of
  the update up to the last one found. A word passed over costs 4
  (`_SKIP`); a word found is worth 3 (`_SAME`). The update's words after
  the last one found are the speech going on, and cost nothing.
- **The cheapest lining up is taken.** Passing "the" over costs one
  word; reaching the later "the" costs three and leaves "yard" without
  its match. So a lone word at the old hearing's end is found in the
  update only if at most one word was gained before it; two words
  together, three; three, five.
- **A word cut short is the word** ("refresh" and "refreshing", three
  letters or more: `_ALIKE`, `_STEM`), and the old hearing's last word,
  which a live caption may have half said, is any word that starts with
  it.
- **Of two equally cheap, the earlier place in the update**: no word of
  the update is left out.
- **Quick for long captions:** what the hearings share from the start is
  taken as it is, and after that the same word is looked for at most 24
  words out (`_APART`).
- Between and after the words found, places are reckoned as before
  (0088: in proportion, then word for word, or by `grew`).
- Enforced by `tests/test_settling.py`: 300's cases as written examples,
  and `test_no_word_is_lost_or_doubled_at_any_seam` - every place four
  made-up passages can be settled to, with the update losing, gaining or
  mishearing a word one to three words back (about 20,000 seams).

## Why

- The rule the user's promise needs is "never lose a word the learner
  hasn't had", and the old lining up broke it in the commonest way two
  hearings differ: one small word, near the end.
- **Measured on made-up seams:** 300's cases lose no English word now
  (16 before); on every seam of eight made-up English and five Mandarin
  passages, 162 of 74,391 and 46 of 72,336 results were short of words
  with `difflib`, and none are now.
- **Measured on the real models** (296's six five-minute recordings of
  FLEURS, made again on 2026-11-13, each replayed through the caption
  history with `difflib`'s lining up and with this one): no word shown
  3 s or more was rewritten in either, bar the one Mandarin character
  0088 explains. The captions were the same in five recordings. In the
  sixth - English, Live updates as before pieces, where the rule acts
  most - one caption of 172 updates differed: `difflib` had doubled a
  word ("...and supporting a a transport system..."), and this lining
  up didn't. That recording's error rate went from 5.85% (41 of 701
  words) to 5.71% (40); the others' didn't move. One sample of read
  speech in each language, not a claim.
- **What it costs.** When the update *gains* two or more words right
  before the shown caption's very last word, and that last word is
  already settled (a finished caption re-heard by a join), the last word
  is no longer found in the update: the caption shows it, then the
  update from one of the gained words on, so that word comes twice
  ("We met at the store", then "We met at the big blue store and went
  home" gives "We met at the store blue store and went home"). `difflib` got this one right and lost the two
  gained words instead. One gained word is handled either way (tested).
  We chose the side that keeps words.
- **Time:** 5 ms for 300 words with every seventh different (1.7 ms
  before), and about 1 ms for 60 (0.2 ms before); the usual update,
  which only adds words to a caption of 20 to 60, about 0.2 ms (0.1 to
  0.2 ms before).
- Not taken: 300's candidate on top of `difflib` (above: it doesn't end
  the loss).
- Not taken: the most shared words first, then the fewest passed over.
  In Chinese a two-character word said twice ("公园玩，公园里") then wins
  over the place the words really are.
- Not taken: trusting any run of two or more words wherever it is. It
  fixes the gained-words case and brings the loss back for repeated
  phrases.

## What would make us reverse it

Doubled words at a seam seen in testers' captions more often than lost
ones were; or the lining up showing in the interface thread's stalls.

## How we'd reverse it

`_shared` is one function behind `_LinedUp`; putting `difflib`'s
matching blocks back is a few lines, and the tests above say what would
then break.
