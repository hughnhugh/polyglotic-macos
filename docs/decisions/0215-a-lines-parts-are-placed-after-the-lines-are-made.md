# 0215 A line's parts are placed after the lines are made

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** Claude (polyglotic-hq project 458), on the user's request
  of 2026-11-17 ("placing characters in such a way to reducing distance
  between all arrow length sums ... a 3rd alternate lab mode could be clean
  even space everything"); behind the Lab, Packed by default; the user
  tries it in the 0.1.8 preview and chooses the default

## Situation

With "Fill the width" or "Line up the parts" on, the one layout
(`views.flow`, decision 0132) packs each line's parts to the left: a short
piece of Chinese sits at the start of the room its long translation takes,
far from the words it is linked to, and the right of the line is empty.
The user asked for parts placed where their word links are shortest, and
for a third way: everything spaced evenly.

The layout's rules stand: a line holds what it holds today, a part never
leaves its line, a caption's text doesn't jump as words arrive, and a
caption that runs on starts where the one before ended.

## Decision

- **Placing is a pass over a finished line pair, not part of filling it.**
  `Flow.compose` decides what each line holds exactly as before, with the
  packed places; when a pair closes, `FlowOptions.placing` moves its pieces
  sideways only (`_near`, `_even`). So the three placings always have the
  same characters on the same lines, and Packed is today's code path.
- **Nearest their links** (`Placing.NEAREST`):
  - *Lined up:* a part's two pieces share a slot as wide as the wider one;
    the narrower piece moves inside the slot to the median of where its
    links want it (between them, when two). A part's links never leave the
    part (`matching_cuts`), so each slot is settled by itself and the slots
    stay where they are.
  - *Not lined up:* the fuller line of the pair stays as text from the left
    edge; the other line's pieces move as a row, in order, to the places
    with the least total link length - isotonic regression in the L1 norm
    by pooling adjacent violators (`views.placing.nearest`).
- **Evenly** (`Placing.EVENLY`): a full pair's pieces - one closed because
  what came next didn't fit - are spread over the width, each line by
  itself, the same room between every two. A pair a caption ends in is
  left as it is, like the last line of justified text.
- **Only finished captions are placed.** A composition with a live caption
  in it is packed: it has no links yet, and its text must not move as
  words come. A caption settles once, when it finishes (when its links and
  parts arrive, which already lays it out again).
- **A pair left open for the caption after** keeps that caption's start:
  lined up, the last piece stops short of its slot's end by a join's room;
  not lined up, the line that moves ends no further right than the fuller
  line. Evenly leaves an open pair alone.
- A Lab row ("Parts placed": Packed / Nearest their links / Evenly),
  saved with the Lab's values; choosing one turns New layout on
  (`CaptionLab.choose`). Enforced by `tests/ui_next/test_parts_placed.py`.

## Why

- Measured on real captions (polyglotic-hq 458: FLEURS Chinese to English
  twice and English to Chinese, at 640, 1,000 and 1,400 px): Nearest
  shortens the links drawn by 29 % with both one-click layouts on, 65 %
  with Fill the width alone and 29 % with Line up the parts alone. Evenly
  shortens them 25 % with Fill the width alone, changes nothing with Line
  up the parts alone, and makes them 4 % longer with both: it is for the
  look, not the links. On the user's own case (their screenshot, both
  layouts, 640 px) a link is 70 px across on average packed and 39 px
  placed nearest. Composing a caption takes about 0.05 ms longer.
- Sideways-only keeps every promise the layout already makes; a placing
  that changed what fits would have to lay earlier captions out again.
- One line fixed, the other moved: moving both gained about 1 % on the
  user's case and nothing on the recorded sets, and left the fuller line's
  text starting away from the edge.
- The L1 norm (the links' total length, what the user asked for) rather
  than squares: a part sits right over one of its words instead of between
  all of them; ties go to the mean, so two links are shared fairly.
- Crossings can't be a goal: parts keep their order on both lines, so two
  links cross or not whatever the placing.
- Not taken: moving single words inside a part (text would stop reading as
  text); letting a narrower piece leave its slot (the lined-up look goes,
  for a few pixels).

## What would make us reverse it

- The one known cost shows in use: not lined up, with captions running on,
  a caption whose own-language text is much longer than its translation
  can start one line pair later than it would packed (1 of 12 measured
  cases, one extra pair in 30 lines). If that reads as a jump, open pairs
  stay packed when not lined up (one condition in `_near`).
- The user picks a default: then the Lab row goes, or stays as the way
  back.

## How we'd reverse it

Remove `Placing`, `views/placing.py`, the `_near` / `_even` pass and the
Lab row: the composer's filling is untouched, so nothing else changes. A
saved "placing" value is ignored by `CaptionLab.from_stored`.
