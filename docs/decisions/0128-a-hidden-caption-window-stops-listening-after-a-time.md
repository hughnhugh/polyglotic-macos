# 0128 A hidden caption window stops listening after a time the learner sets

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user's feedback 18 (2026-11-13: "A caption window
  hidden in the background still runs and loads the server ... a maximum
  hide timer, 15 minutes maybe"), polyglotic-hq project 335; the default
  for bringing a window back is the user's to set (335's report).

## Situation

Hiding the caption windows (the tray's "Hide all caption windows", Home's
"Hide all", Ctrl+Alt+H) only stops drawing them: the apps they
caption are still captured and their speech still goes to the server.
The live server is one GPU on the user's PC that every tester shares, so
a window hidden and forgotten costs everyone, for as long as the app runs.

## Decision

Each caption window the learner hid has its own timer
(`core.listening.hidden.HiddenWindows`, plain Python on a clock the caller
reads). Past the learner's limit - 5, 15 (the default) or 60 minutes, or
Never, in Settings > Captions > Behaviour - its app's listening pauses:
`CaptionWindows.paused_sources` names the window's source (and the mic's,
once every window showing my speech is paused), and `main` hands it to the
speech pipeline, whose `CaptionTiming.paused_sources` sends nothing for
them, live or finished, exactly as the learner's own Pause does - their
speech is still followed on the PC, so showing a window mid-sentence picks
the speech up where it started. Showing the windows starts it again by
itself. Home's row for the app and the tray's tooltip say "paused after 15
minutes hidden"; while a hidden window still captions its app (a caption
in the last 30 s), they say "captioning while hidden". An opt-in, "Show a
hidden caption window when speech starts", shows the windows (never
activated) at a caption 30 s after the last one, and after the window was
hidden.

Hidden means the learner's Hide. Windows minimised by Windows are
restored at once (polyglotic-hq 272), so they never count; a window behind
other windows or on another virtual desktop isn't told apart. Tested at
the model level on a made-up clock and with real windows offscreen.

## Why

- Pausing the source, rather than taking it out of the capture plan,
  keeps the windows, their captions, transcripts, choices and the
  capture's usage statistics as they are, needs no server change, and
  reuses the rule Pause already follows - one place in the timing state
  machine decides "nothing is sent".
- The session stays open, as under Pause: closing it when every window is
  paused would free the account's place on the server too, but it brings
  reconnects, sync and Home's "Stopped" into a release that had to be
  small. Proposed as its own project.
- A timer per window, not one for all: a window opened while hidden counts
  from its own opening, and the model stays right if windows are ever
  hidden one by one.

## What would make us reverse it

Testers hiding windows on purpose to listen without seeing captions (a
"listening only" use) and finding them paused; or the open idle session
itself turning out to matter for the server's capacity.

## How we'd reverse it

Never is a choice already; making it the default is one constant
(`PAUSE_AFTER_MIN`). Removing the feature is deleting `core/listening/
hidden.py`, `CaptionTiming.paused_sources` and the wiring in
`caption_windows.py` and `main.py` - an afternoon. Closing the session
when every window is paused would build on `paused_sources` in
`main.follow_choice`.

## Added before the release (2026-11-14, polyglotic-hq 335's report)

- **An open transcript counts as reading the window:** while an app's transcript window is open (not minimised), its hidden caption window isn't paused, a paused one starts again, and the limit counts from when the transcript closes (`HiddenWindows.read`, `Transcripts.is_open`). Without it a learner who hid the captions to read the transcript lost them after 15 minutes.
- **The screen locked doesn't count as hidden yet** (#619 was taken back out): a lecture captioned while Windows locks the screen would have stopped after 15 minutes with nothing saying so after the unlock. It comes back once unlocking says what was missed.
