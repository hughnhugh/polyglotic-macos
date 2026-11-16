# 0115 Word links follow what the learner knows, per language, at paint time

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 323 (the user, 2026-11-14: "didn't
  want basic words to be linked ... estimate 3000 words known = linkage
  only occurs on 3000+ or 2000+ ... probably make it configurable again").

## Situation

The server links every word of a clause to its translation, in every
language. A tester watching Vietnamese (2026-11-14): "the colour lines are
too much ... I don't need it highlight words I already know well". The
only control was the Look's "Key words / Most words", the same for every
language and blind to the learner.

## Decision

- Each language learned has a choice (`core.learning.levels.LinkChoice`,
  in the settings' `language_choices`): **every word** (as before, and
  until chosen), **words past what I know**, or **off**; and, with the
  second, where links start if not at the known line (`links_from`).
- "Past what I know" hides a link when every word under it on that
  language's row is one the learner set known or ignored, or is up to the
  line (`Vocabulary.needs_no_link`). A word the dictionary doesn't have,
  and a name, is linked: nothing says the learner knows it.
- **A language with no full dictionary** has no ranks, so "past what I
  know" shows its key links only: the server's own mark for content words
  (`WordLink.key`, now carried on `LinkedWords`). It is fewer links, and
  what can honestly be offered until the language has a frequency list.
- A link shows if either row's language keeps it; a row in a language not
  learned has no say (as before).
- **Where:** `ui_next/views/links.py` (the rule, Qt-free) and
  `CaptionMarks`, which already works a line's marks out at paint time and
  forgets them on a Learning change. Core's `caption_rows` still makes
  every link: Listening doesn't learn about Learning, and links "On hover"
  stay whole - the learner pointed at the word.

## Why

- Not in `core.listening.display`: it would need Learning's verdicts
  passed into Listening, and the rows rebuilt (all 150 kept lines) on
  every Learning change; the marks are already lazy, per shown line, and
  invalidated per entry.
- Not on the server: it doesn't know the line (decision 0048: the level
  stays on the PC).
- Not by word length for languages without a dictionary: length says
  little in Vietnamese (muốn, "want", is four letters and in the first
  hundred words) or Chinese.

## What would make us reverse it

Marks at paint time costing the new-caption budget (measured: no change,
0.7 ms median in `test_caption_marks.py`); or the server sending each
word's frequency, which would give every language "past what I know".

## How we'd reverse it

`hidden_links` takes each row's say: a server frequency would fill
`RowLinks.known` for languages with no dictionary, nothing else changing.
