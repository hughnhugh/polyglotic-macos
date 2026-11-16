# 0142 The spoken-language question makes room for the captions and goes by itself

- **Status:** accepted; replaces decision 0109's "it stays until answered"
  and where it sits. 0109's when and what stand.
- **Date:** 2026-11-15
- **Decided by:** Claude, from polyglotic-hq 350's brief ("Place it where it
  doesn't cover captions, and let it go by itself after a while if not
  answered"). The minute is a guess, for the user's review.

## Situation

Claude's validation loop (polyglotic-hq 346) ran the real app on real
captions and found the question "This sounds like Mandarin. Always hear it
as Mandarin?" over the top caption in every window picture on every build,
still there 30 minutes into a lecture. 0109 kept it until answered, and it
sat over the captions' top rows, so a learner who ignored it lost the top
line for as long as they listened.

## Decision

- **Where:** still at the top of the window (under the band's reach and
  the notice line), but the captions start below it while it shows
  (`CaptionWindow.question_foot`, used by the canvas as the band's foot
  is): the oldest rows in view make room, whole, as they do under the
  hover band. Captions are drawn newest at the bottom, so it takes the
  oldest row, never the newest.
- **How long:** unanswered, it goes by itself after `SHOWN_MS` (60 s) of
  showing - counted only while it shows; a locked window's hidden question
  starts its minute again when unlocked, so it never goes unseen.
- **Asked again:** not for that window and language until the app starts
  again (`SteadyLanguage.unanswered`, kept in memory only). Then the next
  steady run of five finished captions asks once more. Not now still means
  never (stored, 0109); Yes still names the language.

Enforced by `tests/ui_next/test_spoken_nudge.py`.

## Why

- Room rather than an overlay: a learner reads the newest captions at the
  bottom; giving up the oldest row while a one-click question shows costs
  less than any covered text.
- Not in the hover band: a learner who never hovers would never see it.
- A minute is about four finished captions of talk: long enough to read
  and answer between lines, short enough not to sit over a lecture.
- Once per app run when ignored: asking again at the next steady run
  would nag through a monolingual stream whose run keeps breaking on a
  mixed line.

## What would make us reverse it

- Testers missing the question (it goes before they look): a longer
  `SHOWN_MS`, or a reminder in the window's settings.
- Testers finding the lost top row worse than the question: a smaller
  question, or one in the hover band.

## How we'd reverse it

`SHOWN_MS` is one constant; the room is `question_foot` in the canvas's
paint (return 0 to overlay again); `unanswered` is one set in
`SteadyLanguage`.
