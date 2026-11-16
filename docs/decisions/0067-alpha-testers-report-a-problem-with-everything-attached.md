# 0067 Alpha testers report a problem with everything attached, and their diagnostics are on

- **Status:** accepted; where the cohort comes from replaced by
  [0072](0072-the-cohort-is-known-at-sign-in.md) (2026-11-11)
- **Date:** 2026-11-11
- **Decided by:** the user with Claude, 2026-11-11 ~01:20 (polyglotic-hq
  project 270's FEEDBACK.md, "Admin tooling"; project 275's brief). The
  server's side is its decision 0055.

## Situation

The user, 2026-11-11: "for alpha testing we should do the opposite and try
to collect as much data as possible, especially related to their client
and client logs ... Give the testers a one click functionality to submit
issues including all data associated with their bug. We can retrace it
and fix it." Decided: content-free diagnostics always on for alpha
testers; audio and caption text only inside a report the tester sends,
shown and agreed each time; no always-on sampling. The testers are the
user's briefed friends.

## Decision

- **"Report a problem" opens a different window for the alpha cohort**
  (`ui/problem_report.py`): wherever it's offered - the tray, Home's
  feedback line, Account, Help's "Still stuck?", the crash offer and the
  caption window's bar - an alpha tester gets the problem report; anyone
  else keeps today's feedback form. The cohort comes with every session's
  `welcome` and is kept in the settings (`cohort`), so it's known before a
  session opens; signing out forgets it.
- **Everything ticked, each part shown:** the log, the settings, facts about
  the app, Windows and the audio devices, the captions of the last few
  minutes as the caption history shows them (`core.listening.problem_report`),
  and each source's held speech from the recent-speech store (2 minutes,
  decision 0027), exactly as sent for captioning. Each with its size and
  Look; a call app's or the mic's audio says "This includes other people's
  voices." and stays ticked. What's left ticked is what goes.
- **Never on the interface's thread:** the request is built (base64 of the
  audio), kept in `problem-reports` in the data folder and sent by
  `connection.problem_reports.ProblemReportSender` on its own thread - kept
  and sent later when the server can't be reached, as feedback is. Home
  says when it has arrived.
- **Diagnostics on for testers:** an alpha tester's usage statistics and
  crash reports are turned on when the cohort arrives
  (`main.diagnostics_on_for_testers`), and the consent screen shows them on
  and fixed. At the first run, which asks before the code, the screen says
  it as a fact for testers. Word counts stay the tester's choice.

## Why

- One click from wherever the tester is when something goes wrong, with
  nothing to find or attach: what was heard and shown is what retraces a
  wrong or late caption.
- The cohort, not a setting the tester picks: the server refuses captions
  and audio from anyone else (server decision 0055), so the app shows the
  window only to those it will take them from.
- A new window rather than more ticks on the feedback form: the form is
  for everyone and stays as it is; this one is for the alpha and goes with
  it.

## What would make us reverse it

The alpha ends, or reaches people the user hasn't briefed: then
`TESTER_COHORTS` empties and everyone gets the feedback form again.

## How we'd reverse it

Empty `main.TESTER_COHORTS`: "Report a problem" opens the feedback form
for everyone and diagnostics follow the consent screen's choices. Then
delete `ui/problem_report.py`, `connection/problem_reports.py`,
`adapters/problem_report_files.py`, `ports/problem_reports.py`,
`core/listening/problem_report.py` and the `cohort` setting.
