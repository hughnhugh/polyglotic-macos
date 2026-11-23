# 0266 Captures and the listening session recover by themselves, and say so

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, on polyglotic-hq project 557's brief (from 529's
  architecture review, its top fix); a reversible technical choice

## Situation

The user, 2026-11-20, on a preview: "it stops working randomly sometimes
again. Not sure why it gets hung." polyglotic-hq 529 (findings B1 and B2)
found two ways captions stopped for good, by reading the code:

- **A capture** (one app's, everything else, the whole system's, the mic)
  whose thread hit an error nobody foresaw - in the speech detection, the
  timing or the encoding its callback runs - ended for good. It kept the
  error's type in `error`, which nothing but a CI tool read, and logged
  nothing; the "no captions?" check then said the app was quiet. An app
  whose capture failed to open was never tried again: its target is
  always its name.
- **The listening session** reconnected after network errors, but any
  other exception - in the protocol handling, the learning-data exchange,
  reading the device's credentials - logged "the session failed" and
  stopped it until the learner changed sources or restarted. One stored
  outbox row this version can't read would do it at every session open.

## Decision

Whatever carries captions recovers by itself, with a capped backoff, and
the log says when it opens, fails and stops - by kind and the error's
type, never names or text:

- **Captures** (`platform/capture_restarts.py`, both Windows' and the
  Mac's): an error nobody foresaw restarts the capture's thread, and a
  failed open is tried again (a device as well as an app), after 1 s,
  doubling, at most 30 s; a run of 60 s starts the waits again. While it
  waits, `error` says why, and the speech pipeline marks the source
  `stopped`: the check's sound link is broken with `CAPTURE_STOPPED`,
  named at once and even beside another source that is heard.
- **The listening session** (`connection/session.py`): an exception
  nobody foresaw in a session, or in reading the credentials, is logged
  and the session tries again (`Reconnects.after_failure`: half to all of
  1 s doubling, at most 60 s; back to the first after a session that ran
  60 s), waiting meanwhile, not stopped. An outbox row this version can't
  read is dropped and counted (`connection.exchange`), so it can't fail
  every session.
- **Counted in the session's summary** (polyglotic-hq 566): the
  listening session's `listening_session_ended` carries
  `capture_restarts` (each capture's `AudioCapture.restarts`, taken by
  the speech pipeline), `session_failures` and `unreadable_dropped`
  (since the last summary), so the reversal trigger below can be read
  from testers' usage statistics, not only from logs they send.

Enforced by fault-injection tests: an exception in a capture's callback,
a capture that fails to open, an exception in the session's loop, in
`credentials.load()`, and an unreadable outbox row - each ends with audio
or captions flowing again.

## Why

- A learner can't tell "nothing is playing" from "Polyglotic stopped
  listening"; the only fix was to restart the app, and nobody knew to.
- A capped backoff keeps a fault that repeats from spinning the CPU or
  calling the server several times a second, while a fault that passes
  (a device busy, a model slow to load, an app still starting) clears
  within half a minute.
- Alternatives not taken: stopping after N failures (the learner is left
  where they were, just later); restarting the whole listening run from
  `main` (more state to rebuild, and it would hide which part failed).

## What would make us reverse it

- Logs from testers, or their summaries' counts (a session with tens of
  `capture_restarts` or `session_failures`), showing a capture or session
  restarting in a loop - every 30 or 60 seconds for minutes - without
  recovering: then the
  restart hides a deterministic bug, and the check should say "report a
  problem" sooner, or the app should stop and say so.
- A restarted capture leaving a caption half-finished in a way learners
  notice.

## How we'd reverse it

Small: each capture's `_run` and `_deliver` and the session's
`_keep_open` hold the loops; taking the retry out puts back the old
stop. The check's `CAPTURE_STOPPED` and the pipeline's `stopped` can stay
either way.
