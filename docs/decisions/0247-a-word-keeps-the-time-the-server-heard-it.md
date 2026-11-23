# 0247 A word keeps the time the server heard it said

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** polyglotic-hq project 528's brief (from 526's "spoken pace": the user, 2026-11-19 ~13:55, "Yes exact timing would be amazing for this"); Claude reviews before merge
- **Builds on:** polyglotic-server decision 0099 (the protocol's word times)

## Situation

polyglotic-hq 526 proposes showing each word at the moment it was said
plus a fixed delay ("spoken pace", karaoke as its option). The app can
only estimate that moment: the words new in a live update are spread by
their syllables over the speech since the update before. 528 timed every
update of 526's six recorded streams with a forced aligner and replayed
them through 526's simulator: the estimate is late by 0.27-0.42 s on
average and off by more than 0.2 s for 55-74 % of words, so at 526's
"1.5 s" the words really come 1.72-1.87 s after they were said, and the
gaps between them drift from the speaker's by 0.18-0.21 s (median). With
the aligner's times the drift is 0 (median), and in a monologue 88 % of
words land within 0.1 s of their moment at a 1.5 s delay (94 % at
1.75 s; at 1.0 s live updates).

The server can now say when each word was said: `words` on a clause
(protocol.md, server decision 0099), seconds on this app's own clock.

## Decision

- **The protocol model reads `words`** (`connection.protocol.WordTime`,
  `Clause.words`): optional, `None` from a server that doesn't send it.
  Nothing else reads it yet: core's caption update is unchanged.
- **For 526's playout (its Phase 2), the rule:** a word's moment is the
  server's `start` for it when the clause has `words` - a dictionary word
  takes its first piece's start - and the app's estimate when it hasn't
  (an older server, a language the aligner doesn't time, a busy server).
  Times are on the app's clock, so they compare with `SpeechTimes`
  directly.

## Why

- **Times on the app's clock** need no knowledge of which speech frame an
  update answers (the session pairs a live answer with the newest frame
  sent, which isn't always the one answered).
- **Spans, not text,** place the times on this app's own word split
  however the server's aligner cut the line (it times each Chinese
  character on its own).
- **Read now, used later:** the field costs nothing to accept, and lets
  the server send it once its aligner runs without waiting for a release
  of this app.

## What would make us reverse it

- 526's playout built and measured on real use without a gain from the
  server's times (528 measured on six recorded streams only).

## How we'd reverse it

Drop `WordTime` and `Clause.words` from `connection/protocol.py`; an
update that carries them still parses (unknown fields are ignored).
