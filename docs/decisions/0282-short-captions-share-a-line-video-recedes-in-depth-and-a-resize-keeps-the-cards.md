# 0282 Short captions share a line, Video's subtitles recede in depth, and a resize keeps the cards

- **Status:** accepted
- **Date:** 2026-11-21
- **Decided by:** Claude, reversibly, on the user's preview-2 feedback the
  same morning (polyglotic-hq 583): "there's also this bug where
  consecutive lines get made for single words in a sentence"; "subtitles
  mode, instead of rolling up, I want it to go deeper into the screen, so
  they're still readable"; "resizing screens creates bugs now, resetting
  the entire window, or going back to start of transcript". The reading
  times are polyglotic-hq 585's provisional rules (not yet agreed by the
  user). Amends [0260](0260-steadys-captions-are-dealt-onto-cards-that-never-change-shape.md)
  and [0261](0261-the-card-stack-waits-for-a-line-to-be-read-and-scrolls-by-the-card.md);
  replaces [0262](0262-captions-wait-only-under-the-mouse-on-their-words.md)'s
  wait (item 6).

## Situation

- **A card a word.** On 583's recording of slow, paused Mandarin (FLEURS
  cut into pieces with pauses of 0.9-3.5 s), the server finished 32
  captions with a median of 6 characters. Every one ended in a full stop,
  mid-sentence too ("目前在。", "因为。"), and each was translated on its
  own. The pauses between them ran 1.6-7.3 s (median 2.7 s). The deck
  started a card for any caption shown 2.5 s after the last word (0261,
  "carries on ... within 2.5 s"), so preview 2 dealt 29 cards for those
  32 captions, each a few characters at the window's left edge.
- **Video rolled its older line up on the drum.** It turned and flattened
  there, and a card left at once as the next came.
- **A resize dealt every card again** (0260: "Only a new width or text
  size deals the cards again"), withdrew them all, and set the window
  back to live.

## Decision

1. **A caption carries on on the front card while it fits.** It starts a
   card only when it is said by another source, or in another language
   (each side said in one language: a card names one, and its
   translation goes one way), or after a pause in the speech of over
   `NEW_CARD_AFTER_SEC` (5 s). The pause is measured by the captions' own
   speech times; without them, it is the time since the last word was
   shown. A sentence's end is not a break: the server ends every finished
   fragment with a full stop. The translations join the line's
   translation as before.
2. **A centred card keeps its words still as more come.** It first stands
   where it will be in the middle once its caption is said (the server's
   text runs ahead of the playout: `Deck.expected`). As words come it
   keeps its left edge, and moves left only as far as it must to stay
   inside the width (`centre_rows(kept=...)`).
3. **Video's subtitles recede in depth** (`set_cards_recede`;
   `views.cards.Depth`). The newest card stands at the foot at full size.
   Each older card stands above the one in front of it, at
   `DEPTH_SCALES` (0.9, then 0.8) of the text size. Each is laid out
   again at that size and proportionally narrower, never scaled as a
   picture, so it keeps its rows. It is dimmer by `DEPTH_INK`: its colour
   is mixed towards its outline's (or a solid panel's), never under
   4.5:1. A new card fades in, rising a quarter of its height, while the
   others step back together in `DEPTH_SEC` (0.3 s), eased. Past the last
   step a card fades out from the back. Video shows a card at each step
   (`SUBTITLE_CARDS` = 3), and its window is sized for them
   (`SUBTITLE_ROWS` 7.3 rows, from 5.4). Scrolled back, the cards are the
   flat list, as before.
4. **A card stays readable until it is read** (`views.dwell`, every value
   named there). A card's need is 0.35 s plus its characters at a reading
   pace: what was said at 3.25 Chinese characters or 10 letters a second,
   its translation at 9 or 17. That is between 1 and 7 s, counted on the
   card's whole text. A card is read when:
   - what was said has stood its need from its first word, and 1 s after
     its last;
   - its translation has stood its need from when it landed;
   - or, with no translation yet, 2.5 s have passed since its last word.

   With the reading hold on (`set_reading_hold`; Video: `HOLD_VIDEO_SEC`,
   2 s), a new card waits while the card it would take out of reading
   isn't read, at most the hold. The window then runs behind the speech
   and catches up in the next pause. Elsewhere the hold is off, and a new
   card waits for the line before it as 0261 says. A window doesn't fade
   while a card drawn in it isn't read, and a translation landing starts
   its fade again.
5. **A resize lays the same cards out again** at the new width
   (`_lay_out_again`). None is dealt again or withdrawn, and new words are
   dealt at the new width. A card wider than the new width takes a
   second row. At live, the window stays live. Scrolled back, the first
   card read whole stays where it is on the screen. A change of text size
   or faces still deals the cards again.

6. **The mouse holds the view, never the captions** (the user,
   2026-11-21 ~10:35: "The mouse shouldn't hold up delivery, could hold
   up pushing text by introducing back to live / new messages alert
   right?"). This replaces
   [0262](0262-captions-wait-only-under-the-mouse-on-their-words.md)'s
   wait, which held updates up to 2 s.
   - Every update comes into the window at once: cards are dealt,
     translations land, the pacing goes on.
   - While the mouse is on the words, the view holds. With cards it stops
     at the newest card shown (`view_held`), and the cards after it wait
     past the view. Without cards the scroll holds where it stands.
   - Back to live counts what came. With cards it stands at the top, over
     no new card.
   - `VIEW_GRACE_SEC` (0.5 s) after the mouse comes off the words or
     leaves, the view goes live in one glide, unless the learner scrolled
     back meanwhile. Back to live goes at once.
   - Text that doesn't move (a word lighting, a translation into its kept
     room) still changes under the mouse.
   - The trace no longer marks any update held by the mouse.
7. **A card all but flat on the drum is drawn flat.** At rest Everyday's
   second card was squashed 0.986 and Video's older card 0.967, enough to
   soften the text. A card squashed less than `FLAT_ENOUGH` (0.95) is
   drawn flat. A card fading (on the drum, coming in, in depth, under the
   toolbar) fades through its colours' alpha, not the painter's opacity,
   so 584's outline stays solid under faint text.

**Video's depth is off for now (2026-11-21, 583's addendum).** Round 2
fixed the cause the first film showed: a card dealt again was held back
by the reading hold, so the stack lost its front card and got it back.
The step now comes from the drawn order, and each card's place is eased.
An offline replay shows 0 drops, but the FLEURS film couldn't run on the
PC's memory. `_place_subtitles` sets `set_cards_recede(False)` until a
film shows reversal, jump, pushed-while-reading and clipped at or below
preview 2's. Everything else above is on, Video's three cards and its
reading hold included, on the drum.

## Why

The server's fragments were each a card because the only break was the
time since the last word. In slow speech, pauses of 2-4 s fell inside
sentences, so the line is the unit and a pause only ends it when it is
long. Depth keeps every line drawn whole and at a readable size, so
there is no squash and no tilt. Laying out again at each size keeps the
text as sharp as the front's. A resize is the learner's action on the
window, not on the captions, so the captions they were reading stay.

## What it costs

- A line can join captions said up to 5 s apart, each with its own
  translation and full stop ("Currently at. Any actions taken by Iraq.").
  This is the server translating fragments; see polyglotic-hq 583's
  proposed project.
- Video's window is about a third taller over the film (7.3 rows from
  5.4).
- With the hold on, Video's words can run up to 2 s behind the speech.
- A narrower window shows wrapped cards (two rows) until new ones come.
- A centred card near the right edge moves left word by word as it fills.

## What would make us reverse it

- The user finds joined fragments harder to read than a card each.
- Video's three cards cover too much of the film.
- 585's agreed rules give other numbers (one edit in `views.dwell`).

## How we'd reverse it

- `NEW_CARD_AFTER_SEC` back to 2.5 with display time.
- `set_cards_recede(False)` in `caption_windows._place_subtitles`, with
  `SUBTITLE_CARDS` 2 and `SUBTITLE_ROWS` 5.4.
- `set_reading_hold(None)`.
- `_deal_again` dealing again on any width.
- The mouse hold: `receive` keeping updates in `waiting` while `_holding`,
  as 0262 had it.

## Checked by

- `tests/ui_next/test_cards.py`: a sentence said slowly is one line; a
  long pause or another language starts a card.
- `tests/ui_next/test_card_stack.py`:
  - a narrower window lays the same cards out again;
  - a resize at live stays live; scrolled back, it keeps the line read
    where it is;
  - subtitles recede, each card laid out at its size; one eased step;
  - a card in depth stays readable;
  - a new card waits for the card it takes out of reading;
  - a centred card keeps its words still;
  - the mouse on the cards holds the view, never the cards;
  - a card all but flat on the drum is drawn flat.
- `tests/ui_next/test_caption_window.py`, `test_joined_window.py`,
  `test_arrivals.py`, `test_arrival_gap.py` and `test_window_trace.py`:
  the mouse holds the view, and no update.
- `tests/ui_next/test_dwell.py`.
