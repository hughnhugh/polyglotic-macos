# 0132 One model of a caption, laid out by one layout: every way of filling the window is an option of it

- **Status:** accepted - being built in the steps of
  [docs/caption-model.md](../caption-model.md). On `main` so far: the
  model (step 1). The one layout is on the prototype branch
  `340-caption-model` (pull request #637, a reference, not for merge)
  until step 4.
- **Date:** 2026-11-15
- **Decided by:** the user, 2026-11-15 ~07:52 ("yes go ahead";
  polyglotic-hq DECISIONS.md #161, option A), on polyglotic-hq project
  340's design - asked for after using 0.1.5: "Word links seem to break
  on many features, new lab modes, captions filling width, between
  clauses doesn't seem to work well ... We might need to first principles
  design this, I ideally want it to be dynamic ... processed data and
  word linkages should be catered to the caption window and caption
  window is dynamic".
- **Will replace:** 0100 (a poured caption keeps a layout per row), in
  part: its rule that every row keeps a layout of its own stays; the pour
  goes - at step 5, when 0100 is marked replaced.

## Situation

A caption reaches the app as clauses, each with what was said, its
translations and word links as character spans (`core.listening.captions`).
On 0.1.5 that data is read again by each feature, its own way:

| What | Where it is decided today |
|---|---|
| A caption's lines | Qt's wrap of a clause row (`caption_layout._lay_out`); the pour's own word cutter and first-fit (`views.pour._flow`); line by line's pairs (`pour_paired`), which falls back to the wrap; `_rest`, for text the pour and Qt counted differently |
| What a "word" is | the server's link spans; the pour's `tokens`; the dictionary's word split (marks, the word under the mouse); the settling's own cutter |
| A link's number, so its colour | `display.numbered_links`, from 0 in **each clause** |
| Which links show | `numbered_links` (key words, the cap); `views.links.hidden_links` (words past what I know); `caption_marks` (none in the learning load) |
| Where a link's ends are joined | `caption_layout._ends` / `_arrows` (facing clause rows only: off when poured); `caption_window.linked_with` (hover); `display.counterpart` (the card) |
| Where both sides can be cut | `views.captions._cuts` -> `pour.matching_cuts`, from the raw links again |

Measured and pictured in 340 (its `pictures/today`, `work/`):

1. **Two clauses on one poured line share a link colour.** Links are
   numbered per clause, the line holds several clauses.
2. **Arrows go when captions fill the width**, and **word links go in the
   learning load** - each feature turned the other off rather than be
   drawn with it.
3. **"Fill the width" fills little.** The pour is per caption, so short
   captions - most of a conversation or a game - each still take a line
   pair; and line by line cuts a clause only where no link crosses, which
   Chinese and English seldom allow, so it wraps as a clause row.
4. **A word already shown moves down a line** in 1.5-3 % of a poured
   caption's growths: the join's ellipsis is given room only once a
   clause follows.
5. **Settled text loses every link of its row** when the finished caption
   heard one word differently (0 of 3 kept in 340's case).

One cause runs through 1-4: there is no one description of a caption that
layouts lay out. Each layout has its own rows, its own words and its own
idea of where a link is. 5 is separate: links are spans of the server's
text, and settled text is not always the server's.

## Decision

1. **One model of a caption** (`core.listening.caption_model`, no Qt),
   built once per caption version from the caption history's `Caption`:
   - **places** (`Words`): characters of one clause's text on one side.
     Everything that points at caption text - a link's end, a mark, the
     word under the mouse, a run of a line, an end of a selection - is a
     place. No layout has rows of its own to index;
   - **units**: what a line never breaks inside, cut once per clause;
   - **links**, numbered across the whole caption in reading order; a
     later clause renumbers none before it; every link the server sent,
     key or minor - which are drawn is asked of the model
     (`shown_links`), not baked into it;
   - **where both sides can be cut**, and which clauses are settled;
   - a clause that did not change keeps its very `ClauseModel` through
     the caption's updates, so what a layout measured for it is kept.
   - **Not in it:** a word's learning state. Known, in the load, saved are
     the learning context's (contexts do not import each other); the
     interface lays them over the same places (`caption_marks` today, a
     Qt-free `views.word_marks` in the migration).
2. **One layout** (`ui_next.views.flow`, no Qt): the models, a width and
   the fonts' measuring in; lines of runs out. First-fit, in order, and
   nothing looks ahead - so **text already shown never moves when more
   comes**. Each clause's unit widths are measured once per text size; a
   resize step is arithmetic.
   Every way of filling the window is its options:

   | In the app | Options |
   |---|---|
   | A clause a row (the default) | `cut=CLAUSE` |
   | Translation below | `cut=CAPTION` |
   | Line by line | `cut=CLAUSE, share, split` |
   | Line by line, lined up (new) | `... aligned` |
   | Captions run on (new) | `... run_on` |
   | Originals hidden, captions only | `show_original`, or no translation in the model |
   | Your own speech on the right | `right` |
   | A joined window's columns | the same layout at each column's width |

   Line by line no longer needs a cut no link crosses: a clause that
   does not fit what is left of a line pair is cut on both sides where
   the **fewest** links cross - none where there is such a place, the
   fullest cut kept in step otherwise. It has no fallback shape.
3. **Word links are drawn from the model's numbers and places**, the same
   in every option: colours never shared within a caption; Arrows between
   any word and its counterpart on the line under it; and in the learning
   load the stage is the word's colour and the line just under it, the
   link's bar below that.
4. **A selection is a range of places** (`Selection`): the same words
   after a resize, in another option, and after its captions grow.
5. **Links go through settled text**: a row of settled words keeps the
   update's links for the words both have (`settling._shown_with_links`).

The engine keeps decision 0100's good half: each clause side has one
`QTextLayout` of its own text, its lines placed where the layout put its
runs - so marks, the hover and the lookup still go by row and character.

## Why

- The breakage is where features meet (fill x links, load x links, fill
  x arrows). With n layouts and m things drawn on text, each pair needs
  code; with one layout and places, none does. The prototype's proof: the
  interface's whole test suite ran with the switch on and three tests
  differed - two that assert today's limits (no arrows when poured, the
  style's new field) and one timing, since fixed.
- **Not** a rich text document (`QTextDocument`) per window: 108's audit
  and decision 0031 found direct painting of per-row layouts is what
  keeps a new caption under 4 ms; a document relays more than it must.
- **Not** best-fit line breaking (Knuth-Plass): better-looking lines, but
  a new clause can change every line above it. Captions are read as they
  arrive; text that moves is worse than a ragged edge.
- **Not** learning state inside the listening model: it would make
  `core.listening` import `core.learning`, or copy its data on every
  Learning change.

## What would make us reverse it

- The one layout cannot hold a budget the separate paths held (measured
  in 340: a resize step 1.0-1.3 ms against today's 1.0-1.6 ms; a live
  update 1.2-1.5 ms against 1.0-1.4 ms; budgets 8 and 4 ms).
- A way of filling the window the user wants that first-fit cannot do -
  balanced lines, say - and that matters more than text holding still.

## How we'd reverse it

Until step 5 of 340's migration both paths exist behind the choice in
`CaptionStyle.flow`: turning it off is one line. After it, the pour and
the clause-row wrap are gone and going back means restoring
`views/pour.py` and `CaptionLayout._lay_out`'s two branches from git -
about a day, plus the tests that went with them. The model costs nothing
to keep either way.
