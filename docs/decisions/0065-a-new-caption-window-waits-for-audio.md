# 0065 A new caption window waits for audio until its first captions

- **Status:** accepted; replaces, for a window with nothing to read, the
  few seconds polyglotic-hq DECISIONS.md #56 gave it (#56 still holds for
  a window put somewhere new by Reset position, joining or separating)
- **Date:** 2026-11-11
- **Decided by:** the user, from their live testing (polyglotic-hq 270's
  FEEDBACK.md: "Caption screen should open up once you connect an app /
  select from my PC displaying waiting for audio"); Claude briefed it
  (polyglotic-hq 272, item 5); project 272 built it; Claude reviews

## Situation

DECISIONS.md #56 (2026-11-06) had a new caption window show its panel
and "X's captions appear here" for the fade-after time (8 s with fading
off), then fade until its first caption: "nothing sits over the game
until there's something to read". On the real models the user found a
window that came and went before anything was heard. That was no help
in telling whether the app worked, and with fading off it read as the
window minimising (272's item 4).

## Decision

- `views.caption_window.shows` keeps a window with no captions shown,
  whatever the fade setting. It stays from the moment its app is chosen
  (connecting an app, or choosing everything the PC plays, makes the
  window) until its first captions. After that the usual fading applies.
- An empty window draws its whole panel. In the middle it says "Waiting
  for audio…", or "Listening…" once speech is heard (the listening mark
  shows too), and "X's captions appear here" under it, in the window's
  own colour made readable on its panel.
- The intro (`introduce`, `intro_seconds`) is kept for a window put
  somewhere new; the intro-only state of an empty window
  (`CaptionWindow.introducing`) is gone.

Tests: `test_a_new_window_waits_for_audio_until_its_first_captions`,
`test_an_empty_window_says_it_waits_and_whose_captions_appear_there`,
`test_a_window_with_nothing_to_read_shows_waiting_for_audio`.

## Why

- The learner sees at once that the app is ready and where the captions
  will be, and the window doesn't vanish before it has been any use.
- The alternative was to keep #56 and lengthen its time. Any fixed time
  either goes before a quiet app speaks, or sits as long as this does.

## What would make us reverse it

- Testers finding an empty window in the way over a game before anything
  is said.
- A game where nothing is said for long stretches.

## How we'd reverse it

`shows` returns False for an empty window again after its intro: one
line, plus the tests above. The waiting words can stay for the intro.
