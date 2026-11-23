# 0255 Each caption update is timed from the sound to the screen

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, for polyglotic-hq project 543. The user, 2026-11-20:
  "Can we measure end to end from client to server and render? I want
  complete visibility, at least for our own machine but ideally for clients
  too so we understand the behaviour"; and later the same day: "I want you to
  automatically get all this data especially for my PC, if it's appropriate
  for users too".

## Situation

The user saw live captions "delay and then process it all at once" at 0.5 s
live updates. The caption log (polyglotic-hq 271) had the send, the answer
and the moment the caption feed applied an update. It didn't show:

- the capture's lag, speech detection, the encode, or the send loop's wait;
- the server's queue, which `processing_ms` leaves out;
- updates dropped on the server;
- the interface thread's queue;
- a caption window keeping updates waiting: the mouse over it (109's
  "nothing moves under the mouse"), or the Lab's gap between new captions;
- the paint.

It also timed a live update's answer from the caption's latest live send,
not from the frame it answered. One that waited behind a newer send looked
quicker than it was.

## Decision

- **`perf.trace`**: one record per speech frame the timing asks for.
  - It has the moment the update passed each stage, on the app's monotonic
    clock: captured, heard, delivered, detected, encoded, taken, sent,
    received, handed, applied, released, windowed, painted. *(Amended
    2026-11-20, polyglotic-hq 551: `released` - a paced mode's playout let
    it out, with the record's `pace`, its delay - so Steady's own wait is
    the `pace` segment, not a window's hold, and a hang counts only what's
    beyond the pace. Without it, every utterance's start in Steady was a
    2-2.8 s hang of the window's.)*
  - It has the server's numbers. The answer echoes the frame's `seq`, which
    the app numbers in the speech header (the server's decision 0104).
  - It says how the update ended: painted, applied, unanswered (with the
    server's reason), overtaken in the app, not sent, or lost.
  - It says whether a window held it, and why (`mouse`, `gap`).
- **The process's tracer** is reached as a logger is (`trace.tracer()`).
  Wiring it through `main` would mean threading it through the capture
  threads, the session, the caption feed and every caption window for one
  call each. `trace.use()` swaps it in tests.
- **What's kept, and where:**
  - **Always, in memory:** the last 5 minutes. "Report a problem" attaches
    them to the app's log, at most half of the log's room, as
    `perf.trace_summary.compact` rows.
  - **On a PC that asks:** every record goes to `logs/trace.jsonl`, 4 x 8 MB
    rotating. A PC asks with a `trace-detail` file in the data folder or
    `POLYGLOTIC_TRACE_DETAIL=1`. Nothing in the app makes that file, so a
    tester's install never writes the file; it's for the owner's PC.
  - **The usage statistics** get one summary per listening session
    (`caption_timeline_summarised`, only with the user's consent). Each
    update's timeline never leaves the PC except in a report the tester
    sends.
- **`perf.trace_summary`** reads records into segments, hangs and their
  causes, bursts and drops. A hang is nothing new shown for over 2 s while
  the speech went on. The app, `tools.trace` (the viewer) and HQ's daily
  summary all use it.
- **Content-free:** numbers, the caption's random id cut to 8 characters,
  kinds, source categories and fixed words. Tested in `tests/test_trace.py`.

## Why

- **The stages are spread across four threads and five modules**, so
  measuring them takes marks in each. A record keyed by the frame's number
  joins them.
- **Durations from the server, plus the app's own round trip**, split the
  network from the server with no clock sync.
- **In memory by default** keeps a tester's PC as it was: about 600 KB for
  5 minutes, and no file. The owner's PC gets the detail without anyone
  asking, because it's the same PC.
- **Alternatives we didn't take:**
  - More caption-log lines: they don't join across threads and would double
    the log.
  - OpenTelemetry: a dependency and an exporter for one process and one
    server we own.
  - Recording only on demand: the user wants the data collected without
    asking.

## What would make us reverse it

- The marks cost measurable time on the capture or interface threads.
  Today each mark is one dictionary update under a lock, about 2 microseconds.
- A tracing service replaces it: the records map onto spans one to one.

## How we'd reverse it

- Delete `perf/trace.py` and its marks: one or two lines each in
  `platform/speech_pipeline.py`, `connection/session.py`, `ui/captions.py`,
  `ui_next/views/captions.py` and `ui_next/caption_window.py`.
- Delete `start_trace` in `main` and the report's attachment.
- The protocol's `seq` stays harmless.
