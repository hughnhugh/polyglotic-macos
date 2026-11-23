# 0252 The quiet view marks the learner's words in the line that is in the language being learned

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude asked for it to be built on polyglotic-hq 526's
  DESIGN.md (section 5.3), with an option; the user's report, 2026-11-19:
  the quiet view's words were highlighted in the translation.

## Situation

The quiet view's blue words were drawn in every row whose language the
learner learns (`CaptionMarks._quiet`). With Mandarin and English both
learned, Mandarin speech translated into English had its English
translation marked too: two lines of marks for one clause, and blue in
the line the learner reads to check, not to learn.

## Decision

- In the quiet view, a clause's marks go in **one** line by default: what was said, when its
  language is one the learner learns; otherwise its translation, when
  that is (`views.caption_window.rows_marked`, `MarksIn.LEARNED`).
- **An option** (Look, "Mark my words in"; `marks_in` in the settings):
  the language I'm learning (default), both lines (as before), what was
  said only.
- The quiet view only. The usual view's saved-word colours stay in both
  lines, each in its own language's colour (the every-dictionary work's
  tested behaviour: not this brief's to change); word links join the
  two lines and are unchanged.

## Why

The mark says "this is a word for you to learn": it belongs where that
word is. Per clause, so mixed speech (a clause in English among Mandarin
ones) is still marked where the learned language is.

## What would make us reverse it

Learners of two languages wanting both lines marked by default.

## How we'd reverse it

`CaptionLook.marks_in`'s and `AppSettings.marks_in`'s default to "both".
