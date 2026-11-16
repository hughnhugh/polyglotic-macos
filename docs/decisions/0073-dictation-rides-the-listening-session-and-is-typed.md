# 0073 Dictation: a source of its own on the listening session, one piece per hold, typed into the program with the keyboard

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** polyglotic-hq project 283's brief and its design
  (`projects/283-dictation-hold-a-key-and-speak/DESIGN.md`), from the
  user's feedback of 2026-11-09 ("basically the same functionality as
  transcribe own voice ... pauses and capitalizations ... an option for
  Australian English ... multilingual"). Claude reviews it with the pull
  requests; the questions only the user can answer (plans, minutes, the
  default key, the notice's line) are in the design's section 8, with the
  defaults built meanwhile.

## Situation

The user wants dictation: hold a key, speak, let go, and the words are
typed where the cursor is, in any program. Their own prototype
(`workspace/dictate`) does it with Whisper on the PC, typing phrase by
phrase as they talk - which broke sentences at every pause ("like It's like
Oh, yeah"). The app already sends the learner's mic to the server
("Caption my own speech") and gets finished captions back.

## Decision

- **A source of its own on the listening session:** `DICTATION`
  (`core.listening.sources`), category `mic`, never translated (its own
  targets are none: `ListeningSettings.source_targets`), heard in the
  language chosen for dictation or detected
  (`source_spoken`). No protocol change: per-source targets and spoken
  languages are protocol v1 (the server's decisions 0033 and 0051).
  Dictation's "none" never makes the session "Original only" in its
  summary.
- **One hold, one piece of speech, sent when the key is let go**
  (`core.listening.dictation.Dictation`): the speech model hears the whole
  of it, so pauses inside a hold don't start sentences. A hold over 30 s
  is cut at its quietest moment in the last 4 s (`quietest_cut`); pieces
  are typed in order, whatever order their answers come in. A press under
  0.3 s sends nothing; Esc cancels whatever isn't typed yet; a piece
  unanswered in 10 s is given up.
- **What's typed** (`dictated_text`): the finished caption's clauses
  joined, English fillers on their own out, Australian spelling if chosen
  (`core.listening.australian`), a space after - none after Chinese or
  Japanese.
- **Typed, not pasted:** Unicode key events, into the window that had the
  keyboard when the piece was cut - nothing typed if another window has it
  when the text comes back. The clipboard is never touched. **One file
  may send input:** polyglotic-hq's guard refuses any code that sends
  input to the desktop, and allows it in
  `platform/windows/text_input.py` alone (the user, 2026-11-11,
  polyglotic-hq DECISIONS #116). `type_text` sends a piece's events in one
  call and reports it typed only if Windows took them all. No test types
  for real: they pass a stand-in for the call, and inside a test run
  `type_text` without one sends nothing.
- **Never kept, never a caption:** its answers are taken out of the
  caption feed before the caption history, so dictated text never shows
  in a caption window or transcript, never counts as heard words, and its
  audio isn't held for "Looks wrong?" or a problem report. The log says
  states and counts only.
- **The mic is open only while the key is held**, and 0.2 s after (the
  last word). With nothing chosen to caption, the key opens a listening
  session, which closes 60 s after the last dictation's answer.

## Why

- The listening session is already open while the learner captions, and
  already carries the mic: a second connection would hold another of the
  account's two session places, and the server already does everything
  dictation needs.
- Sending the whole hold is what fixes the prototype's capitals and
  pauses, and it's what Wispr Flow (the user's reference) does.
- Typing keeps the promise that dictated text isn't kept anywhere (a
  clipboard manager would keep a paste), and works in game chat boxes.

## What would make us reverse it

- Testers find the wait after letting go too long and want text as they
  speak (a preview, then typed): live updates for the dictation source.
- The server needs dictation apart from captions - its own minutes, no
  mic-bleed text check (a shadowed line is dropped as bleed today): a
  `dictation` source category, a protocol addition.
- Programs where typed text fails and pasting works turn out to matter
  (remote desktops without Unicode input).

## How we'd reverse it

- Text as you speak: send live updates for the dictation source from the
  platform's recorder, and show them in the sign; `Dictation` keeps typing
  finished text only.
- Its own category: the server adds it first; the app changes
  `DICTATION_SOURCE`'s category.
- Pasting: a second typing adapter behind the same port (`ports.system`),
  chosen per program.
