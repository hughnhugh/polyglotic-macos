# 0012 The server connection is `websockets` on asyncio, in a thread of its own

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** project 022 (D3a, the thin connection), 2026-11-04 -
  the choice its brief asked for ("`websockets` with asyncio in a thread,
  or Qt's `QWebSocket`, and record why; it must not block Qt or the
  capture threads"); Claude reviews it with the pull request.

## Situation

The app keeps one WebSocket open per listening session (protocol.md):
speech frames out whenever the timing rules decide, caption updates in at
any time, a `ping` every 25 seconds, a watch for 60 seconds of silence,
and reconnects with backoff. Capture runs on its own threads (decision
0006) and the interface on Qt's; neither may ever wait on the network.
The same code should also run headless - in CI, and as the benchmark's
load (project 023) - without a Qt application.

## Decision

- **`websockets` 17.4** (BSD-3), its asyncio client, in
  `connection/session.py`.
- **One thread per listening session runs its own asyncio loop**
  (`ListeningSession.start`). Other threads only hand it work - `stop`,
  `speech_ready` (from the speech pipeline's capture threads),
  `change_settings` - through `call_soon_threadsafe`; each returns at once.
- What it hears goes to a `SessionListener`, called on the session's
  thread; `main` passes what the interface needs over to the Qt thread
  (a Qt signal does that by itself).
- **Configured for the protocol:** the library's own pings off (the app
  sends `ping` messages, protocol.md); compression off (speech is Opus
  already); 1 MiB the largest message accepted. The library's frame-level
  DEBUG logging - which would print `hello`'s token and caption text - is
  sent to a logger capped at INFO.
- Redeeming an invite code is one HTTP request with the standard
  library's `urllib` (`connection/sign_in.py`), off the UI thread.

## Why

- **Headless and testable without Qt.** The tests drive real WebSockets
  against a stand-in server on 127.0.0.1 in seconds, with no Qt event
  loop; the benchmark (023) and a CI end-to-end run need the same.
  `QWebSocket` would tie the connection to a running `QCoreApplication`
  and put it on the Qt thread, competing with drawing captions.
- **Never blocks Qt or capture:** all waiting happens on the session's
  loop; the pipeline's lock is held only to take what's queued.
- **The same library the server runs on** (uvicorn uses `websockets`
  17.4), mature and typed, with close codes, timeouts and proxy support
  (it reads the system's proxy settings).
- **Not taken:**
  - *Qt's `QWebSocket`:* no extra thread or dependency once Qt is in, but
    see above; also PySide6 isn't a dependency yet (D1 adds it).
  - *`websocket-client`:* blocking, one thread per direction, and timers
    for ping and the dead-connection watch would be hand-rolled.
  - *`aiohttp`:* a bigger dependency for one WebSocket and one POST.

## What would make us reverse it

- Threading trouble between the session's thread and Qt that signals
  can't solve simply.
- The app needs more concurrent network work (sync sessions alongside
  listening, D3b) and one loop for all of it would be simpler - then one
  long-lived connection thread, not one per session.

## How we'd reverse it

- To Qt: a `QWebSocket` version of `ListeningSession` with the same
  public methods and listener; `reconnect.py`, `protocol.py` and
  `listening.py` are already free of any library and carry over. About a
  day, with the tests moved onto a Qt event loop.
- To one shared loop: move the thread out of `ListeningSession` into a
  small connection runner that `main` owns. A few hours.
