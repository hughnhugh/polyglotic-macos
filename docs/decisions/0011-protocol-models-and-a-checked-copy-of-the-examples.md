# 0011 Protocol messages as pydantic models, tested against a checked copy of the server's examples

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** project 022 (D3a, the thin connection), 2026-11-04 -
  the question project 013 left open (ARCHITECTURE.md, "Not placed yet")
  and D3a's brief asked to settle; Claude reviews it with the pull
  request.

## Situation

polyglotic-server owns protocol.md and an example of every message
(`docs/protocol-examples/v1/`). Versioning rule 5: "the server's tests
replay them; the app's tests check its own messages against them". The
server repo is private, so this repo's CI can't read it without a
credential. The app also needs its messages as typed values, and must
read the server's messages without a newer server breaking it (rule 1:
unknown fields and types are ignored).

## Decision

- **A copy of the examples in `tests/protocol_examples/`**, written only by
  `tools/protocol_examples.py copy <server checkout>`, which reads the
  server's `origin/main` through git and writes a manifest,
  `MANIFEST.txt`: the server's commit and each file's SHA-256, in
  `sha256sum`'s format (as JSON, `"v1/auth_failed.json": "<hash>"` looks
  like an API key to the secret scan).
- **Tests (`tests/test_protocol.py`):**
  - the copy matches its manifest, so nobody edits an example here to make
    a test pass;
  - every example is either checked or listed as "not used by the app
    yet", so a new message in a refreshed copy fails until someone decides
    what the app does with it;
  - each message the app sends, built from the app's own values (a
    `TranscriptionRequest`, `ListeningSettings`), equals its example
    exactly; each message the app reads parses from its example into the
    right values.
- **Keeping it current:** `tools/protocol_examples.py check <server
  checkout>` says whether the copy matches the server's `origin/main`.
  Run it, then `copy`, whenever protocol.md changes; the pull request
  that changes the server's examples names the desktop change that follows.
- **The models are pydantic** (2.14, as on the server - its decision
  0005) in `connection/protocol.py`: exact for what the app sends (the
  server's own `Literal`s, so the app never sends what it would refuse);
  lenient for what it reads (codes kept as strings, so a new `notice` or
  withdrawal reason is ignored rather than dropping the message).
  `ProtocolError` names fields, never values, and tokens, invite codes,
  caption text and spelling hints are kept out of every `repr`.

## Why

- **No credential to manage.** The other option, CI checking out the
  server repo, needs a fine-grained read-only token (or deploy key) stored
  as a secret, renewed when it expires, and also given to Dependabot's
  pull requests (they don't see Actions secrets). The user would have to
  create it. A copy works offline and in every CI run.
- **A stale copy costs little in version 1:** within a version the
  examples only grow (rule 1: additions only), and the app ignores what
  it doesn't know - which the tests also check. A change that would break
  an old app raises the version and gets a new `v2/` folder, which the
  tool copies alongside.
- **The manifest makes the copy honest:** a hand edit fails CI, so the
  copy is always some real commit of the server's examples.
- **pydantic** gives typed models, validation of the server's messages and
  JSON in one small dependency (pydantic-core is one compiled wheel, about
  2MB), and the same library as the server, so the two sides read alike.
  Not taken: plain dataclasses with hand-written parsing (more code to
  get wrong, for every message); msgspec (smaller and faster, but a second
  modelling library across the two repos for no measured need).

## What would make us reverse it

- The copy is found stale when it mattered - the app shipped with a
  message the server's examples had already changed.
- A second person joins and the cross-repo step gets forgotten; or a
  credential becomes cheap to keep (an organisation with a GitHub App
  that can read both repos).
- pydantic's size or start-up time shows up in D5's measurements.

## How we'd reverse it

- **CI reads the server's examples directly:** add a read-only token as a
  secret, check the server repo out in CI, and point
  `tools/protocol_examples.py check` at it as a CI step (and keep the
  copy as the offline fallback). An hour, plus the user creating the
  token.
- **Another modelling library:** `connection/protocol.py` is the only
  module that uses pydantic; the tests compare JSON, so they carry over.
  About half a day.
