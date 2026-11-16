# 0110 A planned maintenance window is kept, placed by the server's time, and said in the learner's

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user asked for it on 2026-11-14 ("Yes build planned-maintenance notice for next release", polyglotic-hq project 319); the server's side is server decision 0066. Claude reviews the pull request.

## Situation

Polyglotic's server now tells the app of a planned maintenance window -
`welcome.maintenance` with `welcome.server_time`, a `maintenance` message
when it is set, moved or cleared, `server_busy` with `reason`
`maintenance` and `until` during it, and `notice` `maintenance_started`
before close 1001 at its start (server decision 0066). Before, a
maintenance read "Polyglotic's server is restarting", then "down" (#383),
with nothing said ahead. During a deploy the server can't be asked
anything, and a PC whose clock is off would put the window at the wrong
time.

## Decision

- **Kept:** the session holds the window it was told; the connection
  hands it to each new session; `main` keeps it in the settings
  (`maintenance`: its times and how far the PC's clock was ahead of the
  server's), so after a restart of the app inside the window, with the
  server away, it's still said. A `welcome` without one (none planned, or
  a server from before) lets it go.
- **Placed by the server's time:** `welcome.server_time` gives how far
  this PC's clock is ahead (`pc_ahead`); every rule
  (`core.listening.maintenance`) corrects the PC's time by it. The times
  shown are the window's own, in the PC's time zone and the app's time
  format.
- **Said:** Home's banner from a day before ("today" or "tomorrow", the
  learner's real day); the caption windows once, five minutes before;
  during it, Home's title and so the tray's "Planned maintenance until
  15:30", and its line "not your internet - captions come back by
  themselves when it's over" (polyglotic-hq 330, 2026-11-14: it said
  "Polyglotic's server is down for planned maintenance", which 329's QA
  found against the "never down" this record promises) - no countdown
  to the next try. The banner says it during
  the window when the state line doesn't (paused, say). Taken down when
  the window is moved away or cleared.
- **A failed try** - Polyglotic's server refused, not answering, failing
  the session, restarting, or refusing for the window - from five minutes
  before the start to a minute after the end is the maintenance; the
  learner's side (offline, blocked, the clock) is said as it is. After
  that, today's words.
- **Waiting:** in the window, a try at most every 2 minutes (a window
  cleared early is noticed); at its end, plus a random 0-60 s, so the apps
  don't all come back in the same second. A refusal for the window waits
  the server's `retry_after` plus the same random share.
- **Nothing held through it:** while the session waits out a window, the
  speech pipeline keeps nothing to send later (what waits is dropped, and
  so is what comes, counted as dropped), and finished speech still
  unanswered from before it is given up. Today an outage keeps up to two
  minutes of speech and sends it on reconnecting; after a window every app
  would do that at once - 320 measured finished captions' p95 at 7.7 s and
  new captions' first text at 6.7 s at capacity - for speech minutes old.
  Nothing is reordered: captions start again, in order, with what's said
  once the server is back. An outage nobody planned keeps today's rule.

## Why

- **Kept in the settings, not only in memory:** the window exists for the
  times the server can't be asked; an app started during a deploy would
  otherwise say "down". The settings file already keeps what the server
  last said (`cohort`).
- **The difference, not the server's clock itself:** the app compares
  with its own clock all day, offline too; one number from the last
  `welcome` corrects it. A PC clock changed since that `welcome` is off by
  the change - rare, and the next `welcome` puts it right.
- **No countdown during it:** "trying again in 95 s" for half an hour is
  noise; "until 15:30" is what the learner needs.
- **A day ahead:** enough for someone to plan their evening; a banner for
  a week is noise.

## What would make us reverse it

- Testers missing a window announced a day ahead (a weekly schedule):
  show it from further ahead, or in the tray's notification.
- Outages nobody planned: a status file beside the update feed (251's
  option B) would feed the same words.

## How we'd reverse it

`core.listening.maintenance`, `ui_next.maintenance` and their wiring in
`main` come out; the `maintenance` setting is ignored by a version without
it. About an hour.
