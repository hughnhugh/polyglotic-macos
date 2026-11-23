# 0274 Re-speaking is sent and shown as the other person's, on dictation's key by default

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** the user asked for it (polyglotic-hq 567's brief, 2026-11-20 ~12:38: "Dictation for other user input ... arguably better than self-dictate", "a separate hotkey, or one hotkey for both by default, configurable"); Claude chose the design (567's report), for the user to try in the preview

## Situation

The learner hears someone - on a call, in a game's voice chat, in the room
- whose speech the app captions badly or not at all: too faint, music
over it, a bad line, or not captured. They can repeat it clearly into
their own mic. Captioned as "You", it would be in the wrong window, under
the wrong label, heard in the learner's own language and translated the
wrong way, and kept as the learner's speech. The server would also drop it
as mic bleed whenever it repeated the other person's caption within 8 s
(server `mic_bleed`) - which is what re-speaking does.

## Decision

- **Whose:** the source being captioned that spoke last (an app,
  everything the PC plays, the sample), never the mic or dictation
  (`core.listening.respeaking.respoken_for`). With nothing else captioned
  the press says "Nothing else is being captioned to re-speak for" and the
  mic stays closed (an in-person "Them" line is a proposed project).
- **Sent as theirs:** each hold is a finished caption of that source - its
  id and category - so the server hears it in that source's spoken
  language, translates it into that source's targets, keeps it in that
  source's context and doesn't treat it as mic bleed. **No protocol or
  server change**: caption ids are the app's own, and it marks the ones it
  re-spoke (`CaptionUpdate.respoken`, set by `QtListener` as they arrive)
  - "re-spoken" on the caption's label (with its source named even when
  labels are off) and the transcript's heading, "(re-spoken)" in Copy all
  and Save, a `respoken` column in the CSV.
- **One hold, one piece** as dictation's (cut at 30 s, 5-minute cap, Esc
  cancels, 10 s for an answer), with its own `DictationMic`; while held
  the mic's own "You" captions hear silence, as during dictation.
- **The key, by default dictation's** (`respeak_key` ""): a hold
  dictates, unchanged; a tap, then a hold within 0.4 s, re-speaks
  (`KeyGesture`). With dictation off, every hold re-speaks. Or a key of
  its own in Settings > Hotkeys ("Its own key"), held like dictation's.
- **On by default** (`respeaking`), as the user's "maximal function"
  defaults have it: with one key for both it takes no key of its own.
- **Enforced by:** `tests/test_respeaking.py`, `tests/ui/test_respeaking_app.py`.

## Why

- Sending under the other source's id makes everything that follows a
  source - language, translation targets, label, colour, side, window,
  transcript, Steady's pacing - right with no new path; a source of its own
  ("respoken") would need its own targets, labels, window routing and a
  server-side change to the mic-bleed check.
- Tap-then-hold over a modifier: it works with every key dictation can be
  (Right Ctrl, F9, Ctrl+Alt+D) and leaves dictation's hold exactly as it
  was; a modifier would need a second hand on Right Ctrl, and Shift with a
  held-alone key reads as a shortcut there. The cost: a stray tap no
  longer says "Hold the key while you speak" while re-speaking is on.

## What would make us reverse it

- The server's per-source state (Chinese memory, translation context)
  confused by the learner's voice under another source's id - captions of
  the source itself getting worse after re-speaking.
- Learners triggering re-speaking by accident (double taps).

## How we'd reverse it

- A source of its own: `Respeaking.cut` builds the request with another
  `Source`, `QtListener` maps its updates back to the target's id before
  the feed - a day, plus the server's mic-bleed check skipping it.
- The gesture: `KeyGesture` is the only place the tap is read; making
  "Its own key" the default is the setting's default.
