# 0245 A caption's words are played out at the pace they were said, a constant delay behind

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** the user, in parts, in polyglotic-hq DECISIONS #230 and
  #233 (2026-11-19: "B is going to be a noticeably superior mode", "I
  would love for the captioning display rhythm to match the pace of the
  spoken text too but with a delay"; 2026-11-20: "A is fine, can have them
  as options"); #230 has no formal answer yet, so Claude asked for it to
  be built on its recommendations, reversibly (polyglotic-hq 526's brief,
  Phase 2). Builds on [0228](0228-established-text-is-drawn-as-final.md)
  (established text, the quiet correction) and
  0247 (word times; pull request #924).

## Situation

Caption text reaches the app in bursts, one per live update. Shown as it
comes, two thirds of the words arrive in a clump and 7-23 % of shown words
later change; shown only when finished, words come 2.4-2.9 s after they
are said, a caption at a time (polyglotic-hq 526's corpus: six recorded
update streams, three kinds of speech).

## Decision

- **A playout in `core.listening.playout`**: a pure state machine, times
  passed in, between the caption updates the server sends and whoever
  shows them. Each word has the moment it was said - the server's word
  time where an update carries one (`Clause.words`), else an estimate from
  the update's speech times and the words' syllables, less the 0.3 s the
  estimate was measured to run late (polyglotic-hq 528). A word is shown
  at its moment plus a delay: 1.75 s by default, with a live update's
  newest word held back until the next update confirms it or the server
  calls it established.
- **Options, not modes:** 1.5 s with the newest word shown too; the words
  waiting for their moment given as well, for the display to draw faint
  (karaoke), with or without the newest.
- **What it gives are caption updates again**: a live update that stops at
  the last word shown, all of it established (so it is drawn as final and
  a rehearing is a quiet correction, 0228), and the server's own finished
  update with the caption's last word. Nothing downstream knows a playout
  exists.
- **A clause's translation and word links come with its last word**, once.
- **Only the caption windows are paced.** Caption history, the transcript
  and what Learning counts take every update as it comes.
- The syllable estimate and the word split it needs live in the playout;
  a dictionary's split of unspaced writing is handed in as a function
  (core.listening does not import the lexicon).

## Why

On 526's corpus this shows words a steady 1.5-1.75 s after they are said,
1-6 % in clumps (two thirds), 1.5-15 % later changed (7-23 %); the
simulator's numbers were reproduced with this module
(`projects/526-the-polyglotic-display-algorithm/work/core526.py`). With
true word times 80-94 % of words land on their moment (528).

Not taken: an even pace steered by how much is waiting (526's first
design: the same lateness, not the speaker's rhythm); established words
only (as late as whole captions); pacing inside the caption window (the
rule would live in Qt, untestable without a window).

## What would make us reverse it

Learners finding word-by-word text tiring (broadcast research found
scrolling text pulls the eyes), or a speech model whose live text rarely
changes (then `hold_back` 0 and a shorter delay, no structural change).

## How we'd reverse it

The playout is one module behind one call in the caption windows: make
another caption mode the default (`default_caption_mode`), or delete the
module and its call. `Clause.words` stays (0247).
