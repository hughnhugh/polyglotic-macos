# 0013 What waits for the server is kept in an outbox on disk; sync sessions open on threads of their own

- **Status:** accepted; its "Where" replaced by [0014](0014-user-data-in-roaming-app-data.md) (2026-11-05)
- **Date:** 2026-11-04
- **Decided by:** project 028 (D3b, the connection complete), 2026-11-04 -
  its brief asks for the offline buffer "behind a port", consent "stored
  behind a port" and sync sessions; Claude reviews it with the pull
  request.

## Situation

protocol.md: the app keeps `learning`, `usage` and `exposures` messages
until `received`, and `consent` until `received`, sends them again after
a reconnect, and opens a short **sync session** (`hello.purpose = sync`)
when something waits and nobody is listening. Nothing the learner did may
be lost while the PC is offline, the server refuses a message, or the app
is closed; nothing optional may leave without its consent (DOMAIN.md,
"Data and privacy"). Decision 0012 put each listening session on a
thread of its own and named "sync sessions alongside listening" as the
thing that might make one long-lived connection loop simpler.

## Decision

- **An outbox on disk, behind ports:** `ports.outbox.Outbox` (items
  waiting, by kind, bounded per kind - the oldest dropped first, with a
  count - and a few notes such as the learning sync cursor) and
  `ports.consent.ConsentStore` (the user's choices, newest last). One
  adapter implements both: `adapters/sqlite_outbox.py`, one SQLite file
  beside the learning data (`%LOCALAPPDATA%\Polyglotic\outbox.sqlite` is
  the plan; `main` chooses - *now `%APPDATA%\Polyglotic`, decision 0014*), written at once, shared by threads under a
  lock. *In the app, written on a thread of its own, in order
  (`adapters/background_outbox.py`, as for the learning data): a read
  waits for the writes before it, so nothing reads it out of order, and
  what's queued is written before the app ends - polyglotic-hq project
  144, added 2026-11-07, after 136 found a commit took 60-84 ms on the
  interface thread while the disk was busy.* Kept apart from the learner's own data (decision 0010): this file
  holds only what may leave the PC - entry IDs, times, counts, the
  tracking plan's properties.
- **`connection.exchange.DataExchange`** decides what goes in (consent
  rules: usage only with "usage statistics", exposures only with their
  own yes; a "no" drops what waits of that kind) and what goes out on any
  session, in order: consent, a deletion, learning events, exposures,
  usage, then `learning_sync`; batches within `welcome.limits` (count and
  message size), a few awaiting an answer at a time.
- **`connection.client.Connection`** chooses the session: the listening
  session while the user listens (everything goes out on it), otherwise a
  sync session after a short delay, retried after a growing wait if it
  can't connect. A sync session is a `ListeningSession` with
  `purpose="sync"`: no speech, and it closes itself once everything is
  answered. One session uses the exchange at a time; each still runs on
  a thread of its own (0012 kept). A listening session stopped because
  listening moved to another device (close 4011) counts as nobody
  listening here: it stays until "Listen here", and sync sessions run
  beside it (polyglotic-hq project 117 Low 2, added 2026-11-07).

## Why

- **Survives everything short of a lost disk:** SQLite transactions, as
  for the learning data (0010); a JSON file would need
  write-to-temp-and-rename and a rewrite per lookup.
- **A separate file:** the learning store is used only from the Qt
  thread (0010) and holds the learner's private data (source sentences,
  exposure counts); the outbox is written from the Qt thread and read
  from a session's. Separate files keep "what may leave the PC" in one
  place and avoid sharing the learning store's connection across threads.
- **Consent in the same file:** the choices are small, read by the
  connection with every usage event, and their record is itself a
  message waiting to be sent. Not taken: `QSettings` (ties the connection
  to Qt; the harness and tests run without it).
- **A thread per session, not one long-lived loop:** a sync session is
  short and rare (start-up, after listening, a burst of lookups); reusing
  `ListeningSession` kept the handshake, keepalive and refusals in one
  place. Moving to one loop (0012's "how we'd reverse it") is still a few
  hours if threads start to hurt.

## What would make us reverse it

- Testers lose learning events or see them twice.
- Two sessions at once (a sync session still closing as listening starts)
  confuse what awaits an answer often enough to matter - then one
  connection loop.
- The outbox fills in normal use (the dropped count in logs).

## How we'd reverse it

- Another store is a new adapter for the two ports; the exchange doesn't
  change. An hour or two.
- One connection loop: move the threads out of `ListeningSession` into
  `Connection`, which already owns the choice of session. A few hours.
