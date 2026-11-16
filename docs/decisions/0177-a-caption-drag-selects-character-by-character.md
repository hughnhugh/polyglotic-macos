# 0177 A drag in a caption window selects character by character

- **Status:** accepted; amends [0150](0150-a-caption-window-selects-by-places-and-never-takes-the-keyboard.md) (its gesture's snap to whole words)
- **Date:** 2026-11-16
- **Decided by:** the user, trying 0.1.7 preview 1 (2026-11-16, polyglotic-hq
  395): "in this situation gang gang can't highlight individual gang, then
  can't highlight na individually. I want each character to be selectable
  one by one for flexible copy paste, not clause by clause selection" -
  0150's own "what would make us reverse it" ("learners wanting
  character-exact ends: drop the snap to whole words").

## Situation

0150's drag snapped both ends to whole words of the word split: within a
clause a phrase grew a word at a time, and a selection across captions
started at the start of the pressed word and ended at the end of the word
the mouse was in. In Chinese, where the split joins characters into words
(刚刚, 游戏), a learner couldn't select one character of a word, and the
end jumped a word at a time instead of following the mouse.

## Decision

- **A drag selects exactly the characters the mouse passes**, in every
  script: within the clause, from the character pressed on to the one under
  the mouse (刚, then 刚刚, then 刚刚呢); across clauses, rows and captions,
  from the character pressed on to the place the mouse is (between two
  characters). No snap to words.
- **A drag starts once the mouse has gone the platform's drag distance**
  (`QApplication.startDragDistance`) from the press; till then it's a
  click, and a click looks up the word under it as before.
- **The copy is what's highlighted**, punctuation and all; the lookup of a
  phrase is still trimmed of spaces and punctuation at its ends.
- **A double-click on a word selects the word whole** and holds it to
  copy, as in any text, so the whole word is still one gesture away; its
  first click has already looked it up.
- The rest of 0150 stands: selections are places, both sides of a clause
  are held whole when the drag crosses from what was said into its
  translation, kept until a click elsewhere or Esc, copied by a
  right-click or Ctrl+C, the window never takes the keyboard. Enforced by
  `tests/ui_next/test_select_captions.py`.

## Why

- It's what the learner asked for, and what every text field does: the
  selection follows the mouse.
- The double-click keeps a quick whole-word copy, the one thing the snap
  gave, without making every drag jump.
- Not taken: a modifier key to switch between words and characters (over a
  game the key may be the game's, 0150's reason against keys).

## What would make us reverse it

- Learners finding it fiddly to select whole words with a drag in a
  language without spaces: snap only the end the mouse is at, after a
  pause, or offer the snap as a choice.

## How we'd reverse it

`CaptionWindow._select_to`, `_select_across` and `mouseDoubleClickEvent`
hold the gesture (0150's `_snapped` and `_snapped_place` went in this
change); each is a few lines, with its tests in `test_select_captions.py`.
