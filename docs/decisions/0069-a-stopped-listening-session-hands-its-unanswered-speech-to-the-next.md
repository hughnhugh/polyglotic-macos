# 0069 A stopped listening session hands its unanswered speech to the next

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** Claude, for polyglotic-hq project 277 (271's finding;
  the brief named this option). Reversible - a technical choice.

## Situation

When what's captured changes so that nothing is chosen for a moment (a
source removed before another is added), `main.follow_choice` stops the
listening session and opens a new one at once. The old one stops on a
thread of its own: it sends its last finished speech and waits up to
3 s for the answers (decision 0012's drain). But the server treats a
new session from the same install for the same purpose as replacing the
old one, and closes the old one with 1000 as the new one's `hello`
arrives (protocol.md, `too_many_sessions`). The wait ended then - 64 ms
in the user's log of 2026-11-10 - and the finished speech still
unanswered was lost: a caption the learner never saw.

## Decision

- Once a listening session has stopped (its thread over), what it sent
  as finished speech and never had answered is handed to the listening
  session open then, if any (`Connection._hand_on`,
  `ListeningSession.hand_over` / `take_on`,
  `UnansweredSpeech.hand_over` / `take_on`).
- The new session sends it again first, as it does after a reconnect,
  keeps it as its own unanswered speech (so a reconnect, the stall
  notice and 271's giving up treat it like the rest), and counts its
  wait from when it was first sent. More than `KEEP_SEC` (120 s) old,
  it isn't handed on.
- With no listening session open - the learner stopped captioning, or
  signed out (which never hands anything on) - nothing changes: it's
  dropped once the drain is over, as before.
- Tested against the stand-in server with the real server's replacing
  rule (`tests/fake_server.py`'s `replacing`).

## Why

- It's the app's side only, and it reuses what a reconnect already does:
  the protocol says speech in flight "is sent again as finished speech if
  it matters", whatever the session.
- Not taken: keeping the session open through a moment with nothing
  chosen (the cleaner fix in principle, but it touches Home's states and
  `main`'s session handling, which other projects were changing); waiting
  for the old session to finish before opening the new one (up to 3 s
  more before the new source's first caption, and the protocol's "the app
  opens one at a time" would still be broken while it drains).
- No caption is shown twice: an answer the old session got before the
  server closed it is answered there and not handed on, and the server
  can't answer on a session it has closed.

## What would make us reverse it

- The server starts carrying a replaced session's work on into the new
  one by itself (it already keeps the old one's state for `resume`):
  then the new session's `hello` would name the old one in `resume`, and
  the handover could go.
- `follow_choice` stops closing the session when nothing is chosen for a
  moment: the handover would then only matter for the rare real stop and
  start, and could stay or go.

## How we'd reverse it

Remove `Connection._hand_on`'s call in `_finish_listening`; the session
and `UnansweredSpeech` methods can stay unused or go with it.
