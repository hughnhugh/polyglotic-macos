# 0097 Live updates wait their turn under the server's speech ceiling

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, on polyglotic-hq project 307's brief (the user, 2026-11-14: "get it to work on all the other outstanding tasks"); a reversible technical choice, reviewed with the pull request

## Situation

The server takes at most 600 seconds of audio a minute from an account,
live updates and finished speech together (its protocol.md, Limits; its
decisions 0036 and 0061). Over that it refuses live updates; finished
speech is never refused to make room for them.

A live update sends its piece's speech so far again, so Live updates sends
far more audio than is spoken. Measured with the app's own speech detection
and timing rules on FLEURS read speech (English, 74% speech) and on speech
without a pause, seconds of audio a minute (polyglotic-hq 307):

| Apps talking | Every | Read speech | Without a pause |
|---|---|---|---|
| 1 | 0.75 s | 231 | 336 |
| 2 | 0.75 s | 459 | 672 wanted, 601 taken |
| 3 | 0.75 s | 693 wanted, 595 taken | 1,008 wanted, 619 taken |
| 3 | 1.5 s | 390 | 509 |

Three apps at 0.75 s - the founder's own setup - want more than the
ceiling. The server's window is the last 60 seconds, so its refusals come
in a block: once the minute is full every live update is refused until
enough of it has aged out, and only finished captions arrive meanwhile.
QA batch 7 (polyglotic-hq 300) saw 75 of 409 live updates refused; this
measurement, 129 of 796 on read speech (the longest stretch with every
one refused: 10.6 s) and 567 of 1,186 without a pause (28.9 s). The
learner was told nothing and the app logged a WARNING for each.

Sending less audio doesn't close the gap on its own: project 307 built a
rule that sends only a caption's tail and measured it on the real models
(its report). Where it was safe for accuracy it saved 11 to 17% of live
updates' audio; three apps talking without a pause need 40% less.

## Decision

**The app keeps to the ceiling itself, evenly** (`CaptionTiming`):
- A budget of audio on the app's clock, filled at the rate that keeps any
  minute under 90% of the ceiling (`LIVE_BUDGET_SHARE`), holding at most
  10% of it (`LIVE_BURST_SHARE`: three apps' live updates at 0.75 s for
  about 8 s before anything is spread). Everything sent is taken from it.
- **Only live updates wait for it.** A live update that is due while the
  budget is spent waits - it isn't dropped: it goes as soon as there's
  budget again, carrying the speech up to then. Finished speech never
  waits.
- **Each source gets its turn:** of the sources with a live update
  waiting, the one whose last live update was longest ago goes first. A
  source that stops talking gives up its turn.
- 90%, not 100%: the server counts a frame by the larger of its seconds
  and its bytes (2,600 a second), which came to as much as 3% over the
  app's count in Mandarin (polyglotic-hq 307), and the two windows don't
  start together.
- The ceiling is `SPEECH_SECONDS_PER_MINUTE` (600, the protocol's);
  `CaptionTiming.speech_ceiling` is there to set from `welcome`'s
  `limits.speech_seconds_per_minute` when a server first sends another
  number - nothing sets it today.

**The learner is told, once, calmly** (`core/listening/held_back.py`): a
live update that waited is marked (`TranscriptionRequest.held`, never
sent to the server); the session counts those and the server's own
refusals, and when 8 are held back within 20 seconds it gives the app the
notice `live_updates_held_back` - "Lots of speech at once - live updates
slowed; captions continue", where the server's notices show - and not
again for 10 minutes.

**The log says it once a minute:** how many waited and how many the
server refused since the last line (a WARNING only if the server refused
any), not a WARNING per refusal. The caption log keeps its line per
refused frame.

What the learner gets, three apps at 0.75 s (the same measurement): read
speech, a live update about every 1.1 s at the median (0.77 s asked) and
none refused; without a pause, every 2.2 s (at most 4.2 s), and none
refused. One app, or two in read speech, is never held.

## Why

- **Evenly, not in blocks.** The same number of live updates fit under
  the ceiling either way; refused by the server they stop for a third of
  each minute, spread by the app they slow.
- **In the timing rules, not at the connection.** A live update dropped
  as it's sent is lost, and the next waits a whole interval; one that
  waits in the timing rules goes the moment there's budget and carries
  the newest speech. The rules already know every request's length, on
  one clock for all sources.
- **Not the server's pace hint.** `pace` slows everyone when the fleet is
  busy; this is one account's own speech, and the server can't spread an
  account's live updates between its sources - only the app knows which
  is waiting.
- **Not a higher ceiling.** It's what keeps one account's work near four
  listeners' (the server's decision 0061); the app's fastest setting on
  four sources wants 2.5 times it.
- **Not fewer apps or a slower setting forced on the learner.** They
  chose three apps and 0.75 s; all three rarely talk at once for long, and
  when they do the app slows by itself and says so.

## What would make us reverse it

- The server timing live updates itself (protocol version 2): the budget
  moves there with the rules.
- A ceiling counted another way (by the server's time, not audio), or
  told apart per source: the app's count would no longer match.
- Learners with one app held back - the budget is wrong if that happens.

## How we'd reverse it

Set `speech_ceiling` to None in `CaptionTiming` (the rule is off, as in
the proof of concept) and delete `_refill`, `_live_budget`, `held` and
`held_back.py`; the notice's text and its translations go with them. An
hour's work; nothing is stored and the server is told nothing.
