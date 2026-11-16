# 0127 A transcript lists as far back as the learner chooses

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, for polyglotic-hq project 334 (the user's
  feedback 16, 2026-11-13: "An option for how long the transcript saves
  (a 3-hour lecture; presave before exit), without making the caption
  window long and slow"); the choices in it are the user's to overrule

## Situation

Each app's transcript (`ui_next.views.transcript.Transcript`) keeps its
captions in a caption history of its own: it lists the newest 1,000
(`TRANSCRIPT_LINES`) - laid out, scrolled and searched in its window - and
keeps the rest of the session, up to 50,000, as text for Copy all and Save
(polyglotic-hq 137). A three-hour lecture is 3,000-4,000 captions, so its
first two hours could be saved but not read back or searched in the
window. The caption window has a third history, its own 150 lines.

## Decision

- **How far back every transcript's list goes is a setting**, Settings >
  App > Transcripts (`transcript_length`): the newest 1,000 lines (the
  default: as before), the last 3 hours, or the whole session
  (`TranscriptLength`). Copy all and Save have the whole session whichever
  is chosen, as before.
- **The limit is the caption history's** (`core.listening.history`):
  besides at most `max_captions`, `keep_for` keeps only captions that
  first appeared in that many seconds; `set_limits` changes both while
  captions arrive. A lowered limit sends the oldest lines to Copy all's
  text at once; a raised one brings them back to the list, as text (no
  word links: those were dropped with them).
- **Three hours and the whole session list at most 10,000 lines**
  (`TRANSCRIPT_MOST_LINES`, about eight hours of a lecture's constant
  speech); past it the oldest are in Copy all and Save only.
- **The caption window is untouched:** it keeps its own 150 lines,
  whatever the transcript keeps.
- **Nothing is written to disk unasked.** Saving stays the learner's
  act - Save transcript as..., to a file they pick. An automatic save
  would change what the privacy notice says stays on the PC; it is left
  for the user to decide (polyglotic-hq 334's report).
- **Quit asks once** (and Restart now, which quits): with three hours or
  the whole session chosen, each transcript of more than 300 lines with a
  line added since its last whole save is offered Save... (the default),
  Quit without saving or Cancel, with "Don't ask again"
  (`transcript_ask_at_quit`; Settings > App > Transcripts turns it back
  on). Closing a caption window asks nothing: its transcript stays for
  the session. Windows signing out or shutting down asks nothing either -
  a question there would hold up Windows.

## Why

- Each caption update costs a transcript about 0.15 ms per 1,000 lines
  it lists (measured 2026-11-14: 0.6 ms at 4,000, 1.5 ms at 10,000, 7.5 ms
  at 50,000), because the history and the line list are walked whole on
  each update. 10,000 keeps a new caption inside its 4 ms budget with
  room for a second app; 50,000 wouldn't. The window itself lays out only
  the lines in view (300 kept laid out), so opening, scrolling and
  resizing cost the same at 4,000 lines as at 1,000 (the budget tests).
- Memory: a listed line costs about 1.0 KB, one kept as text about
  0.5 KB (tracemalloc, made-up captions of a sentence each) - three hours
  listed is about 4 MB, 1.6 MB more than the default.
- "An hour" (in the brief) was left out: the default's 1,000 lines are
  already about an hour of a lecture.
- Bringing lines back on a raised limit means a learner who changes the
  setting mid-lecture sees the whole lecture at once, not only what comes
  after.
- The question at Quit only with a longer choice: the brief's rule was
  "longer than today's 300", which in its picture only a longer choice
  reached. Asking every learner with 300 lines would put a new question
  in front of everyone who quits after 15 minutes of a game - a change to
  the default the release wasn't to carry. Asking all is one condition
  removed from `Transcripts.may_quit`.

## What would make us reverse it

- Learners on long sessions finding the window slow, or a caption's
  budget failing with several transcripts at 10,000 lines.
- Learners wanting the list and Save to keep less (privacy), or wanting
  the transcript kept across a restart.

## How we'd reverse it

- To list more cheaply: make the history's and `CaptionLines`' update
  touch only the changed caption (an index by caption id, a list rebuilt
  only at its end) - then the 10,000 cap can rise. The setting stays.
- To drop the setting: `TranscriptLength.from_stored` returns NEWEST,
  and the card in Settings > App goes; stored values are then ignored.
