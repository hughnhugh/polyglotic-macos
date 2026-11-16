# 0001 Ports and adapters on the desktop, checked by import-linter

- **Status:** accepted; where interfaces live replaced by
  [0008](0008-ports-and-adapters-packages.md) (they're in `ports/` now)
- **Date:** 2026-11-04
- **Decided by:** the user, 2026-11-04 (polyglotic-hq ENGINEERING.md,
  "Principles" and "Architecture"). Where the interfaces core needs live,
  and keeping `ui`, `connection` and `platform` independent of each other,
  were chosen by project 013 (2026-11-04) while encoding it; Claude reviews
  them with the pull request.

## Situation

The proof of concept mixed Qt, audio capture, networking and caption rules
in the same modules, which made every change risky. The app will gain
macOS and Linux capture, may change transport, and - likely in protocol
version 2 - hand its live-update timing rules to the server. Its structure
has to stay clean without anyone policing it by hand.

## Decision

The package is split into:
- `core` - what the app does (caption display state, timing rules, saved
  words, lookup rules), plain Python, no I/O, no Qt;
- `platform` - audio capture and speech detection, one package per OS
  (`windows/` now);
- `connection` - talks to the server (polyglotic-server's
  `docs/protocol.md`);
- `ui` - Qt;
- `main` - the one place that wires them together.

Checked by import-linter on every pull request (`pyproject.toml`,
`[tool.importlinter]`):
- **`layers`:** `main` → `ui` | `connection` | `platform` → `core`. Core
  imports none of the others; `ui`, `connection` and `platform` don't
  import each other - `main` connects them through core.
- **`core-no-infrastructure`:** core imports no Qt, audio or Windows API,
  network, storage or vendor library (the list is in `pyproject.toml`; add
  a library to it when it's first adopted).

**The interfaces core needs live in the context that needs them.** The
agreed desktop layout has no `ports/` package, so when a context needs
something from outside (the dictionary files, saved words on disk, sending
speech), it states it as a small `typing.Protocol` in its own package, and
`main` hands it an implementation from outside core.

## Why

- ENGINEERING.md principle 3: core knows nothing about Qt, the network or
  the platform, so a new OS means a new `platform/` package, a new
  transport means a new `connection`, and core's rules (such as the timing
  state machine) can move to the server unchanged.
- Checking it in CI means the structure can't quietly rot, whoever writes
  the code - agents included.
- **`ui`, `connection` and `platform` independent** (chosen while
  encoding): each is a plug, and plugs that import each other recreate the
  proof of concept's tangle. Strict now is easy to loosen later; the
  reverse isn't.
- **Interfaces inside the context** (chosen while encoding): the
  alternative was a top-level `ports/` package as in the server, which the
  agreed desktop layout doesn't have. Keeping them in the context is the
  classic domain-driven placement and needs no new package.

## What would make us reverse it

- Wiring everything through `main` and core gets contrived - for example
  the UI needs the list of capturable apps from `platform` and routing it
  through core adds nothing.
- Storage code (dictionary files, saved words, settings) or the updater
  has no natural home among `platform`, `connection` and `ui`. This is
  likely: see ARCHITECTURE.md, "Not placed yet".

## How we'd reverse it

- To let two of the plugs import each other: change `|` to `:` between
  them in the layers line (siblings that may import each other), with a
  new decision record. A one-line change.
- To add a home for storage and other adapters: add `ports/` and
  `adapters/` packages as in the server and a line in the layers contract,
  with a new record. Moving any interfaces out of the contexts is a rename.
