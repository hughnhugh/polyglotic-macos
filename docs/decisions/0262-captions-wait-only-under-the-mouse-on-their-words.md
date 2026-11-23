# 0262 Captions wait only while the mouse is on their words

- **Status:** replaced in part by [0282](0282-short-captions-share-a-line-video-recedes-in-depth-and-a-resize-keeps-the-cards.md) (2026-11-21): the mouse on the words holds the view, never the captions
- **Date:** 2026-11-20
- **Decided by:** Claude, on polyglotic-hq DECISIONS #242's
  recommendation (option C), for the user's preview 2 (polyglotic-hq 554's
  brief), reversibly, before the user's formal answer.

## Situation

"Nothing moves under the mouse" (109; polyglotic-hq 145, 158): while the
mouse moved anywhere over an unlocked caption window, new caption
updates waited, until it left or had been still for 4 s - so a click a
moment late still landed on the word that was under it.

polyglotic-hq 543's trace showed this rule is what freezes captions: on
the user's preview 0.1.10-preview.1 (2026-11-20), report 40f40850 ("5-10+
seconds til text") had the window's hold at p95 19.0 s, captions held by
the mouse 19 times, while capture, the network and the server were all
fast (server p95 236 ms); report b26df5af's hold was at p95 4.9 s. A
mouse crossing the window - on its way to a game, a video's controls,
another app - held everything for as long as it moved, then let it all
in at once.

## Decision

- New captions wait only while the mouse is **on a caption's text**
  (`CaptionWindow._over_words`: a character drawn there, as the lookup
  finds it), or while a phrase is being selected.
- The panel around the text, the hover band, the edges and a column's
  divider never hold them; moving off the words, or leaving the window
  (a column too), lets them in at once.
- Left still on the words, the mouse lets them in after `HOLD_SEC`, 1 s
  (4 s before).
- No caption waits longer than `HOLD_MOST_SEC`, 2 s, however the mouse
  goes on moving over the words; the moves after it hold the next ones.
  A selection being dragged is the one exception: its words stay put
  until it's let go.
- In a joined window each column holds its own captions alone.

Tests: `tests/ui_next/test_caption_window.py` (the 20 s pattern of report
40f40850, over the panel and over the words) and
`tests/ui_next/test_joined_window.py`.

## Why

- It keeps the reason for the rule (the word under a click doesn't move)
  and ends the freezes everywhere else (DECISIONS #242: A kept the
  freezes, B kept them for as long as the mouse moves, D is a change
  to the caption layout, which polyglotic-hq 552 is changing now).
- The 2 s ceiling is ours, beyond #242's C: a mouse moving over the words
  for a long time (reading along with it, sweeping across a game) would
  otherwise hold captions as long as it moved, as before. 2 s is longer
  than reaching for a word and clicking it, and shorter than the 4 s the
  rule used to wait after a mouse stopped.

## What would make us reverse it

- Testers' clicks landing on the wrong word again (a lookup of the word
  beside the one aimed at), or the trace's `window_hold` hangs staying
  over 2 s.
- The user choosing another option on DECISIONS #242.

## How we'd reverse it

Constants and one method in `ui_next/caption_window.py`: `HOLD_SEC`,
`HOLD_MOST_SEC`, and `_hold_on_words`, which decides on each mouse move
(holding on every move while hovered brings back 158's rule). Option D
would replace the hold with a layout that never moves the line under the
mouse - a larger change, in the caption layout.
