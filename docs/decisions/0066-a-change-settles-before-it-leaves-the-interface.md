# 0066 A change settles before it leaves the interface

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** Claude, in polyglotic-hq project 273 (the user asked for every fix from the live test before friends connect, 2026-11-11); reversible, so Claude's call under polyglotic-hq CLAUDE.md's rhythm

## Situation

A control that moves continuously - today the look's "Panel: how solid" slider; soon the lab section's sliders (polyglotic-hq 270's batch C) - fires a change on every mouse move, 60 or more a second. Each change was saved with the settings, and everything that follows the settings ran: the caption windows, Home, Learning's page (which reads another language's level from its file), the sample lookup, and the listening session, which sent the server a `settings` message. In the user's log (2026-11-09) one drag held the interface 93-410 ms a time and the server answered `rate_limited` six times; its message bucket is shared with the speech frames, so a drag could cost speech.

## Decision

A change shows at once where the learner sees it, and goes anywhere further once it has settled - `main.SETTLE_MS` (300 ms) after the last change:
- the look: the caption windows and every panel show it at once; it's saved, and the rest of the app follows, once it settles (`main.Panels`), and at quit;
- the listening settings: handed to the session once a change settles, and only when they differ from what the session has (`main.SettingsHandoff`); the look isn't part of them, so a look drag sends the server nothing;
- whatever follows the settings does its work only when what it shows changed: Learning's page reads levels only when the languages learned or the word introductions change; Home looks for the sample once per language.

Held by `tests/ui/test_settings_handoff.py` and `tests/ui/test_look_drag.py`: counts of hand-overs, saves and file reads over a drag, and a drag step's time against `budgets.FRAME`.

## Why

- The learner sees every step of a drag, so the preview is never late; nothing else needs the steps in between.
- A trailing settle is simpler than a rate limit and sends the last value, which is the one that matters.
- 300 ms is under what reads as a delay after letting go, and well over the gap between mouse moves (16 ms), keyboard repeats (about 33 ms) or wheel notches.
- Not taken: saving on the slider's release only - a wheel, the keyboard or a click on the groove never "release"; a settle covers every way the value moves.

## What would make us reverse it

A setting the learner needs to reach the server or the disk within 300 ms of a change (none today: languages and timing are clicks, and a session starts with the settings as they are); or a crash within 300 ms of a drag losing the last look (quit saves it; a crash doesn't).

## How we'd reverse it

Set `SETTLE_MS` to 0 for a hand-over or save at the next pass of the event loop, or call `Panels.save_look` / `SettingsHandoff.hand_over` directly where the change is made. A few lines in `main`.
