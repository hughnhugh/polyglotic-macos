# 0027 Recent speech: one in-memory store of finished captions' audio

- **Status:** accepted
- **Date:** 2026-11-06
- **Decided by:** polyglotic-hq project 097 (094's C1; DECISIONS.md #42, #44); Claude reviews

## Situation

"Looks wrong?" (a re-run on the best model) and clips for cards both need
the audio of a caption that was already sent. Today the app keeps only a
30 s raw buffer per source and discards each request's encoded audio once
sent.

## Decision

`core/listening/recent_speech.py` holds each **finished** caption's Ogg Opus
exactly as sent, by caption id, with start, end (the app's clock) and the
source's category. `SpeechPipeline.take` adds it as it hands the request
over, so what is held is what left the PC.

- Memory only. Cleared when the app closes (`stop`), when a source is
  removed, and when learning data is deleted (`forget_recent`, called from
  the delete-learning flow).
- Held 2 minutes of speech per source (`HOLD_SECONDS`, #42), measured
  against each entry's end on the app's clock; the oldest drop first. A
  per-category override (`category_hold`) is the hook for #44 ("whole
  session for videos"), unused and not in the UI.
- A hard cap of 4 MB per source (`MAX_BYTES_PER_SOURCE`) bounds memory
  whatever the setting; the newest entry is always kept.
- A joined caption's audio covers the whole stretch; it replaces the
  captions it joined.
- The port, `RecentSpeechPort.get(caption_id) -> HeldSpeech | None`
  (None: not held any more). "Keep this one" for a card is not built; it
  arrives with #44.

## Why

One store for both features avoids two copies of the same audio. At about
2.6 KB per second of speech, 2 minutes is about 315 KB. Live updates are
not kept: they are superseded. The store lives in core as plain Python (an
injected clock, no I/O), so it needs no new import-linter rule.

## What would make us reverse it

If clips need to outlive the app, they go to disk as their own storage
(a clip store), not by making this one persistent. Windows may page memory
to disk; that was already true of the 30 s buffer.
