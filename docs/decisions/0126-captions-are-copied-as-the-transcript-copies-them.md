# 0126 Captions are copied as the transcript copies them, to the clipboard only

- **Status:** accepted; Copy the newest caption taken out of "How it's
  reached" (polyglotic-hq 339; the user, 2026-11-15: "I dont want copy
  last line caption setting"), the rest unchanged
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq 333's brief, from the user's feedback 11
  (2026-11-13: "Copy to clipboard on all translation/captions"); the user,
  2026-11-14, put it in the current release. Right-click to copy is 333's
  proposal, for the user's review.

## Situation

The transcript window could copy a line (its right-click menu) and every
line (Copy all); a caption window, where the learner reads captions over
a game or video, could copy nothing. A caption window never takes the
focus (a full-screen game can minimise when it loses it), so it has no
keyboard, and its settings popover opens no menu or window of its own.

## Decision

- **What a caption window copies:** finished captions only - a caption
  still being heard is rewritten under the learner - written as the
  transcript's Copy writes them (`core.listening.transcript.as_text`):
  each caption's time on this PC, "You" on the learner's own, what was
  said, and the translation the window shows (and the second language's,
  for a line already in its language); none for Original only.
- **How it's reached:** a row in the window's settings popover (and in
  a joined window's column's), Copy all captions - all the captions the window holds to scroll back through,
  up to `CAPTION_WINDOW_LINES`; and a right-click on a caption copies that
  one, at once, without a menu (a menu would take the keyboard from the
  game). (Until 2026-11-15 a second row, Copy the newest caption, copied
  the newest finished one; 339 took it out.) The notice line says "Copied N captions", or "Nothing to copy
  yet". No key: the window never has the keyboard.
- **Where it goes:** the clipboard, nowhere else - never logged, sent or
  kept. Enforced by `tests/ui_next/test_copy_captions.py`
  (`test_nothing_copied_is_logged`) and review.

## Why

- One format everywhere: what a learner pastes from a caption window reads
  as what they'd paste from the transcript, and one function writes both.
- Right-click is the one gesture left free on a caption (a left click
  looks a word up, a drag selects a phrase or moves the window), and it
  works without the focus.
- Not taken: a copy button drawn on each caption (it changes how captions
  are drawn, which this release avoids); a right-click menu (a Qt menu
  takes the keyboard); copying a live caption (its words still change).

## What would make us reverse it

- Learners right-clicking by accident and losing what was on their
  clipboard: make the right-click open a small popover of choices, as the
  settings popover does, instead of copying at once.
- Learners wanting what was said or the translation alone, without the
  time: add those choices (the transcript's line menu may get them first).

## How we'd reverse it

`CaptionWindow.copy_text` and `_copy` hold the format and the clipboard;
the right-click is three lines of `mousePressEvent`, and the row is a
name in `settings_popover.ROWS` and `COLUMN_ROWS`. Any change is an hour
or two, plus the strings' translations.
