# 0076 One app alone is tried on Windows 10 from version 2004, and given up on a PC where it fails

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** polyglotic-hq project 285 (the user, 2026-11-11 ~20:37:
  "Can you do per app captioning support for windows 10 too?"); Claude
  reviews it with the pull request. Amends [0006](0006-windows-capture-with-own-ctypes-wasapi.md),
  which captured one app only from Microsoft's documented build.

## Situation

Captioning one app alone uses Windows' process loopback (0006). Microsoft
documents it from build 20348 (`AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS`,
"Minimum supported client: Windows 10 Build 20348"; its sample's README
says the same). 20348 is Windows Server 2022's build: on a PC that means
Windows 11. So every Windows 10 (its last is 22H2, build 19045) captioned
only everything the PC plays: one caption window, no apps, no "everything
else".

Other apps ship it earlier. OBS registers its Application Audio Capture
from build 19041 (`plugins/win-wasapi/plugin-main.cpp`: "MS says 20348,
but process filtering seems to work earlier"), and its guide says Windows
10 version 2004 or later; win-capture-audio asks for "an updated version
of Windows 10 2004". Against that, a user of build 19042.662 (an early
20H2 update) reported that OBS heard nothing from his apps (OBS forum,
2022-10-08), and Microsoft never documented it there. Nobody on the team
has a Windows 10 PC.

## Decision

- **Three levels by Windows' build** (`platform/windows/capture.py`,
  `app_capture_support`): promised from 20348 (`YES`: as before), **tried
  from 19041** (`TRY`: Windows 10 2004 to 22H2), not before (`NO`:
  everything the PC plays, as before).
- **Tried means watched.** On a `TRY` build the captures of an app, and of
  everything else, tell a `Trial` what they find; the first outcome stands:
  - **it worked:** sound (any sample not zero) in an app's capture;
  - **refused:** Windows failed the activation or the stream's start -
    kept as its code (`refused 0x...`), or `no answer` if the activation
    never finished (5 s);
  - **silent:** for 10 s of checks (`SILENT_AFTER_SEC`), Windows' own meter
    of the app's audio sessions (`IAudioMeterInformation`, Windows 7+) heard
    it playing (peak 0.01 or more: `HEARD_PEAK`, -40 dBFS) while its capture
    got only zeros, or nothing at all. An app that's quiet - its meter
    under the line - is not a failure: silence is right then.
- **If it fails** (`main.AppsOneByOne`): everything the PC plays from then
  on, said once on Home and the caption windows in plain words, and
  remembered in the settings (`app_capture_fell_back`: the Windows build
  with its update, the app's version, and why). The next start doesn't try
  again on the same Windows update and app version; an update of either
  does, and so does Home's **Try apps again** beside the note that says why
  apps are off.
- **One content-free line in the log** (`app_capture_line`), also in a
  problem report's facts (`windows.apps_one_by_one`): "capturing apps one by
  one: Windows build 19045.5131, tried: it worked" - or "it failed (refused
  0x88890008)", "trying", "not tried: it failed here before (silent)",
  "promised", "not tried (Windows before version 2004)". The build, Windows'
  code and the words; never an app's name or anything it played.
- **Windows 11 is untouched:** no trial is made where it's promised, and
  without one an app's capture never reads a meter or tells anything (the
  tests show both). Only the words of Home's hover note change ("instead of
  apps"), since "the only choice on Windows 10" is no longer true.

## Why

- **A wrong guess costs nothing.** A Windows 10 where it fails ends where
  every Windows 10 is today - everything the PC plays - after one try, with
  a sentence saying why; one where it works gains apps one by one.
- **The first tester's PC answers the question for us.** Their log line
  (and a report's facts) carries the build with its update and the outcome,
  so the first Windows 10 report says from which update it works.
- **The update is part of the record,** not just the build: win-capture-
  audio's "an updated version of Windows 10 2004" and the 19042.662 report
  suggest it depends on the cumulative update. Remembering the failure per
  update means Windows Update tries it again by itself.
- **Silence is told from a refusal by Windows' own meter,** not by a guess
  from the session's state: many apps keep a stream open while silent, so
  "active" isn't "playing". The meter is a number, never audio.
- **Not taken:** a probe at every start (a capture of our own process):
  it can show a refusal but not silence, and it would run on Windows 11
  too. Waiting for Microsoft's documentation: Windows 10's support ended
  on 2025-10-14 (Microsoft's KB5066791, 22H2's last free update), so its
  documentation is unlikely to change.
- **Known edges, accepted:** the first outcome decides for the whole PC -
  an app Windows won't capture for its own reasons (a protected game, say)
  can make a working PC fall back; "Try apps again" undoes it. The meter
  can't tell an app muted in Windows' volume mixer; if the capture is
  silent then, it counts as a failure. A call app whose sound Windows
  files as communications can come through process loopback as silence
  even on Windows 11 (Microsoft's Windows-classic-samples issue #414:
  Teams, 2025-12-03; communications-category audio on build 26200,
  2026-10-28) - on Windows 10 that would count as a failure too. Everything
  else (leaving one app out) is judged only by refusals.

## What would make us reverse it

- Windows 10 testers' lines show it never works (every one `refused` or
  `silent`): go back to 20348 and drop the trial.
- They show it always works from some update: promise it from there
  (`YES`) and keep the trial below it.
- A crash in process loopback on Windows 10 (not a refusal) - the trial
  can't catch that; the crash reports would.

## How we'd reverse it

Change `APP_CAPTURE_TRY_BUILD` (or `APP_CAPTURE_MIN_BUILD`) in
`platform/windows/capture.py`; at 20348 the trial is never made and
everything else stays. Removing it entirely is `Trial`, the two hooks in
the capture loop, `AppsOneByOne` and the setting - about an hour. The
setting is ignored by older versions (unknown keys are kept, unread).
