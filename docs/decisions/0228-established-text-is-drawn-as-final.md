# 0228 Established text is drawn as final, and a change to it is a quiet correction

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user, 2026-11-18 ~07:08 (polyglotic-hq DECISIONS.md #211: "two agree" every 1.0 s, no ghost text); built by polyglotic-hq project 494; Claude reviews before merge
- **Builds on:** polyglotic-server decision 0095 (the `established` count); 0088 and 0099 (settled text)

## Situation

A live caption's words may all still change, so the app draws the whole
of it as text still being spoken (Live updates a little dim; Steady's and
Quick preview's provisional line dim and italic). From 2026-11-18 the
server says how much of a live caption's start two live updates in a row
agreed on (`established`): on live's speech model the finished caption
changes 2.6 % of that text, against 13-18 % of a live update's last word,
and it covers about half the words 2.4-2.6 s before the finished caption
(polyglotic-hq 487).

## Decision

- **Drawn as final** (`core.listening.established`, `display.caption_rows`,
  `CaptionLayout.paint`): a live caption's established part is drawn as a
  finished caption's text - full ink - and the rest as before. A clause
  established to its end has its translation drawn as final too. Done at
  paint time with a format range, so nothing is laid out again and every
  layout (clause rows, poured, the one layout) draws it the same. On
  Steady's and Quick preview's provisional line the established part is
  at full ink but stays italic: italics are laid out with the line.
- **A quiet correction:** when an update - the finished caption, or a live
  update that heard established words differently - changes words shown as
  established, the words that took their place are drawn in a warm colour
  (`CORRECTION`, #f0a070, made readable on the panel), held for half of
  `CORRECTION_SEC` (1.5 s) and eased back into the row's own colour. Once
  per change: the window notes when each caption's correction came, and a
  rebuilt line with the same correction doesn't show it again.
- **The newer hearing wins:** established text is not held against a
  later update. Settled text (0088) still keeps what has stood 3 s (or the
  learner's time), so those words never change and are never corrected.
- **Counting:** the protocol's - characters of the clauses' originals
  counted in order, nothing between them - carried over to the text as
  shown when settled words differ from the update's, never ending inside
  a word.
- **Word links** stay as they were: never on a live caption's last clause,
  established or not (a next step: polyglotic-hq 494's report).

## Why

- Holding established text against a later live update (the brief's "only
  grows") leaves more wrong words up as final, for as many corrections.
  On 487's conversation trace, 4.5 % of live updates every 1.0 s change
  established words, and the finished caption then sides with the later
  update 53 times in 64. Measured on real speech through this app's own
  Live updates path at 1.0 s (polyglotic-hq 494, the validation copy, 8
  minutes of ASCEND's Mandarin-English conversation): following the newer
  hearing, the finished caption changes 3.2 % of established words and 1
  in 4 lines with established text shows a correction (24.7 %, counted
  before settling, which keeps words that stood 3 s, takes some); holding,
  5.6 % and 23.6 %. Holding would also keep wrong words past the 3 s after
  which settling keeps them for good. On an English monologue both are
  small (0.1 % and 0.6 % changed; 4.8 % of lines).
- Every change of an established word is shown, at a live update too: a
  word drawn as final that changes silently is worse than a flash. Shown
  only at the finished caption, 1 in 10 lines would flash in the
  conversation (10.1 %), and established text would change unflagged in
  4.0 % of live updates.
- Paint-time colour, not a second layout: established text moves no
  words and costs no layout, and the UI lab's goldens (no established
  text in them) don't move.
- Not taken: 487's mock-up recoloured the whole rest of the line after a
  change; recolouring only the replacing words says less, more exactly.

## What would make us reverse it

- Learners finding the corrections busy: in a Mandarin-English
  conversation 1 line in 4 with established text shows one. The steps
  back, measured on the same real speech: corrections only at the
  finished caption (1 in 10 lines; `history.apply` sets `corrected` for
  finished updates only), or three live updates agreeing on the server
  (1 in 8 lines, 30 % of words early instead of 46 %, 2.3 % changed).
- Learners reading the full-ink part as "can't change" and losing trust
  when it does.
- Forced-prefix decoding on the server (established text that never
  changes): corrections would go, and established text could be settled
  at once.

## How we'd reverse it

Drop the format range in `CaptionLayout.paint` and the correction colour
in the caption window (a few lines each); `Caption.established` and
`CaptionRow.established` can stay, unused, or go with them. To hold
established text instead, make `history.apply` treat it as settled for
live updates (`settled = max(settled, ...)`), an hour's work.
