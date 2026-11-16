# 0125 A word's counterpart in its line is shown on the card, not kept

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq DECISIONS #143 (326's design, stage 1) and
  #110 ("meanings in the interface's language"); the user, 2026-11-14:
  "solve this such that dictionaries are displayed in app language". The
  brief (polyglotic-hq 328) fixed "not kept" until the user decides 326's
  stage 2. Finished captions only is 328's proposal, for the user's review.

## Situation

Most cards' meanings are in the dictionary's language - English for
Chinese words, Chinese for English ones (326, table 1) - not the
learner's. But every caption line already holds a translation in the
language the learner reads and word links joining its words to the
original's (`Clause.links`, from the server). The card got the line and
its translation, not the linked words.

## Decision

- **What:** a looked-up word's counterpart - the words of the other row of
  its clause that the clause's word links join to it - is the card's first
  line under the word, "Here: ngân hàng", hovered or pinned, on every kind
  of card; the main content where the row's language has no dictionary.
  None, no line.
- **Where it's worked out:** a display rule in listening,
  `core.listening.display.counterpart` (rows and links are listening's),
  put on the lookup's `LookupContext` by the caption window and the
  transcript (`views.lookup.with_counterpart`) as plain text and its
  language. Learning's code carries it to the card and nowhere else.
- **Which links:** every one in the clause, key or minor, drawn or not -
  the Look's settings and which links the learner sees (323) change only
  what's drawn. The translation used is the one shown with the row in the
  window or transcript the word was in; a word in a translation row gets
  what was said.
- **When:** finished captions only. A live caption can be rewritten under
  an open card, which doesn't follow it (as Learning's marks).
- **Not kept:** not on a saved word, not in Anki, not in the learning
  events; nothing new is read from disk or sent. Enforced by
  `tests/ui_next/test_lookup_counterpart.py`
  (`test_nothing_new_is_kept_or_sent`) and the pick by
  `tests/test_word_counterpart.py`.

## Why

- It's free: the data is in memory already, it works for every pair the
  server translates, and it's a meaning in context - the sense in this
  line.
- A display rule, not learning's: it is about a caption's rows and links.
  Learning's `LookupContext` only carries the text, like the line it
  already carries.
- Not kept, for now: one line's counterpart is one sense, sometimes a
  paraphrase; a saved word's meaning should be stable. Whether a saved
  word keeps its line's counterpart is 326's stage 2, the user's call.
- Not taken: showing it on a live caption and updating the open card (more
  moving parts for a few seconds' gain); only drawn links (323's thinning
  would hide the counterpart of a word the learner knows - the very words
  they look up to check).

## What would make us reverse it

- The user deciding a saved word keeps its line's counterpart (326's
  stage 2): `Vocabulary.learn` and `save` then store it, with the privacy
  notice's line on what a saved word keeps.
- Learners finding the counterpart wrong often enough to mislead (the
  aligner's links are about 81 % right, 039): show it only above a link
  confidence, or say "probably".
- Learners missing it on live lines: show it there and update the card.

## How we'd reverse it

Keeping it: two fields on `StoredSavedWord` and the store's schema (an
added column), Anki's note fields, the privacy notice - a project. Hiding
or thresholding it: `display.counterpart` alone. Live lines: drop the
`caption.live` check and have the card re-ask on `CaptionFeed.changed` -
about a day.
