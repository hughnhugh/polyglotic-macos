# 0260 Steady's captions are dealt onto cards that never change shape

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** the user, on preview 0.1.10-preview.1 (2026-11-20:
  "I just want a smooth mode in steady that feels responsive, there is no
  text jumping around up and back, lines being formed to and fro,
  translations popping in mid way pushing everything around, lines getting
  pushed too much whilst I'm reading it. It might need to function more
  like a 3d wheel stack, like flicking through sticky notes or book pages
  ... One mode that feels smooth. One mode that is reliable."), then "go
  ahead and execute a preview for this" (polyglotic-hq DECISIONS #244,
  project 552). How it is built is Claude's, reversibly. Takes the place
  of [0251](0251-steadys-layout-is-two-zones.md) as Steady's default.

## Situation

Steady's two zones (0251) laid the same text out twice - line by line in
the live zone, then again as a caption in the transcript - and both
layouts were composed again whenever a caption's text or translation
came. On real recorded speech, a minute of preview 1 held (polyglotic-hq
552's replay, every character's place in every frame):

- 16-30 jumps (a character moving over 360 px/s, the fastest 248-263 px
  in one 60 Hz frame);
- 10-17 times a shown word changed place or line;
- 10 of 12 and 14 of 20 translations moved what was said when they
  arrived, by up to 146 px.

## Decision

In a paced mode, unless the learner's `steady_cards` is off, a caption
window deals its captions onto **cards** (`ui_next.views.cards.Deck`):

- **A card is one line** of what was said and the room under it for its
  translation. A word placed on a card keeps its card and its place.
  Words are added at the end of the front card; one that doesn't fit - or
  whose translation wouldn't, as far as the server's unseen text says -
  starts the next card.
- **A shown word the server changes** is changed where it is if it fits
  its room. Otherwise the change waits until its caption is finished, and
  the card is then set again within itself, once. A word never changes
  card.
- **A translation goes into the room kept for it** (`CaptionWindow.
  card_height`: a card's height is kept from when it is first drawn). It
  is cut between cards where the fewest word links cross; what is wider
  than its card runs on into the next card's room, and at the last is cut
  short with an ellipsis. It never takes a second line.
- **The next card is made a word ahead:** the server's text runs ahead of
  what the playout shows, so the deck knows when the next word won't fit.
  The stack moves while the last word of a line is read
  (`CaptionWindow.card_room`), and the word arrives on a card in place.
- **One motion** (`views.cards.Glide`): the stack is drawn below its
  place by an amount that follows a critically damped spring to rest. A
  push while it moves adds to how far it has to go and keeps its speed;
  it never passes its place, so nothing comes back down.
- **Older cards turn away on a drum** (`views.cards.drum`): flat in the
  foot of the window, then closer together, flatter and fainter, gone
  before the top edge. Left edges stay in line; no edge cuts a card.
- **The deck sits between the playout and the window's view, and gives
  caption updates again**: each card is a small caption (`CaptionId`
  "card:N") whose clauses fit one line, with its share of each
  translation and the word links inside it. The view, the one layout
  (0132), word links, marks, lookups, selection, Say it and copying see
  captions, as they always did. Nothing downstream knows a deck exists.
- **A card's room is what it holds** (`CaptionWindow.card_height`): its
  label too, and until its translation is there, the room one takes -
  what the last one took, else about a row. No card keeps more than it
  uses, so the gaps between cards are even.
- **The stack is never drawn more than a card and a half below its
  place** (`GLIDE_MOST`): a burst is caught up with at once, not followed
  from under the window.
- **Scrolled back, the cards are a flat list**, each one whole and
  readable to the oldest; live text waits. The wheel and a scroll bar
  (`caption_window.scrollbar`, in cards, in the window's right padding)
  turn it; Back to live stands under the cards, never over one
  (`pill_room`), and a question at the top never covers one.
- **Subtitles are parameters, not another display:** `set_card_limit(n)`
  draws only the newest n cards, `set_cards_centred(True)` stands each
  card in the middle of the width, and the text size is the window's own
  (`set_text_size`). 556's Video preset sets them.
- A window's width, text size or faces changing deals the cards again
  from each caption's latest update (`_deal_again`), at rest.
- Two zones (0251) and the one list stay, for `steady_cards` off.

## Why

Every complaint was a layout composed again after it was shown. A card is
laid out from text that only grows at its end, so the engine never has a
reason to move a word; the translation's room is part of the card from
the start; and the only motion left is the stack's, which one spring
makes continuous. Being caption updates again keeps every per-caption
feature working with no second copy of the window's state (the reason
0251 gave for one view).

Not taken: a widget of its own drawing cards from cached pictures (552's
first prototype: every feature keyed by caption line would need routing,
and its text was not the engine's); smoothing the two zones (the text is
still laid out twice, and the handoff changes its shape); a fixed
ease-in-out per push (restarting it on each push stutters in bursts).

## What it costs

- A lookup's context line and "copy line" are a card's text, not the
  whole caption's; Copy all gives a line per card.
- A change to a shown word that doesn't fit waits for the caption's
  finish (a second or two with the earlier word on screen).
- A translation much longer than its line ends in an ellipsis (the
  transcript window has all of it).
- The caption window's Transcript length and its 150 lines count cards.

## What would make us reverse it

The user preferring the zones or the list after the preview; learners
missing whole-sentence lookups; the ellipsis being common on a language
pair (then: a smaller translation, or two rows of room).

## How we'd reverse it

`steady_cards`' default to False (one line in `ui.settings`): the window
then deals nothing and shows captions as before. Deleting the mode is
`views/cards.py`, the `deck` branches in `caption_window.py` and this
record.

## Changed since

[0261](0261-the-card-stack-waits-for-a-line-to-be-read-and-scrolls-by-the-card.md):
the stack waits for a line to be read before it makes room, scrolls by the
card, and a caption's translation is one text cut at words' edges.
