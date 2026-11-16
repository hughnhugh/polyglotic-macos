# 0150 A caption window selects by places, and never takes the keyboard to copy

- **Status:** accepted; amended by [0177](0177-a-caption-drag-selects-character-by-character.md) (a drag selects character by character, no snap to words; a double-click selects a word)
- **Date:** 2026-11-15
- **Decided by:** the user, 2026-11-15 (DECISIONS.md #158/#159: "I want
  drag and select and ctrl c / right click to copy. Should be able to
  freely copy all texts across all caption interface / dictionary pop
  ups"; "yes go with that" to drag-select anywhere, right-click copies
  without taking the keyboard, Ctrl+C once the window is clicked into);
  the gesture is 340's design (decision 0132, `docs/caption-model.md`,
  "Selection"), built in polyglotic-hq 358.

## Situation

A caption window's text could be copied only a caption at a time (a
right-click, decision 0126) or all at once. A drag from a word selected a
phrase within its row and pinned its lookup; a drag from no word moved the
window. The window never takes the keyboard (`WindowDoesNotAcceptFocus`):
a full-screen game can minimise when it loses it. The layouts differ
(today's clause a row, the Lab's New layout with captions running on and
parts lined up), and captions arrive and the window is resized while the
learner reads.

## Decision

- **A selection is two places** in the captions
  (`core.listening.selection`: a caption's key, a clause, a character, a
  side), never lines or pixels. What it holds is asked of the captions as
  they are now, so it is the same words after a resize, in another layout,
  and as captions arrive; a caption gone from the window drops out. Both
  ends on one side: that side's words between them. One on each side:
  both sides of every clause between, whole.
- **The gesture, told apart by where the drag goes, not by a key:** a
  press and release on a word looks it up; a drag within the word's own
  clause and side is a phrase, pinned as before - and held as a selection
  too; a drag out of it (another clause, the translation, another caption)
  is a selection, snapped to whole words at both ends, with no lookup; a
  drag from no word moves the window.
- **Kept** until a click elsewhere (in this app through an event filter;
  on another app by reading Windows' mouse state while it's held) or Esc
  (likewise: the key event in this app, Windows' key state over a game -
  read, not taken, as the lookup card reads it).
- **Copied** by a right-click on it (`copying.copy_quietly`: no menu,
  "Copied" by the mouse) or by Ctrl+C while one of this app's windows has
  the keyboard (not into a text field, not over words selected there; the
  pinned card's Ctrl+C is the card's, decision 0126/333). A right-click
  elsewhere still copies that caption (0126).
- **The caption window still never takes the keyboard.** "Clicked into"
  is read as: one of the app's windows has the keyboard because the
  learner clicked into it. Over a game or a browser, Ctrl+C is that app's;
  the right-click copies.
- **Text:** a caption a line, two when both sides are held, its clauses
  joined as the transcript joins them; no times or names (the transcript's
  Copy has those). Only the clipboard: nothing selected or copied is
  logged, sent or kept. Enforced by `tests/test_caption_selection.py`,
  `tests/ui_next/test_select_captions.py` and review.

## Why

- Places are the caption model's one way of pointing at text (0132), so
  the selection needs no code per layout and survives what a window does.
- The drag's destination tells a phrase from a selection without a
  modifier key, which over a game may be the game's.
- Taking the keyboard on a click would make Ctrl+C work everywhere, but a
  full-screen game loses focus (and can minimise) on any press on the
  window - and a drag is a press. Not taken: activating the window on a
  click; reading Ctrl+C from Windows' key state while a selection is held
  (it would work over a game, but the game gets Ctrl+C too, and it reads a
  letter key on another app's keyboard: the user's call, below).

## What would make us reverse it

- Learners pressing Ctrl+C over a video and getting nothing: read Ctrl+C
  from Windows' key state while a selection is held and the mouse is over
  the window (the user decides: it widens what the app reads of the
  keyboard).
- Learners losing a phrase highlight they didn't want kept after a pin:
  stop holding the phrase (copy it by the card's Copy instead).
- Learners wanting character-exact ends: drop the snap to whole words.

## How we'd reverse it

`ui_next.caption_selection.HeldSelection` holds the keeping and the
copying (its poll and event filter); `CaptionWindow._select_to`,
`_select_across` and `_pin_selected` hold the gesture. Each choice above
is a few lines there, with its test in `test_select_captions.py`.
