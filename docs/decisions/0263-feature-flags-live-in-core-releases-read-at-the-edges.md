# 0263 Feature flags live in core.releases, read at the edges

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, for polyglotic-hq project 555 (the user's
  preview-1 feedback, 2026-11-20: the Detect nudge and Fill the width
  "remove/feature flag off"). A reversible technical choice; it settles
  ARCHITECTURE.md's "Not placed yet: the `flags` module - decide with the
  first flag".

## Situation

polyglotic-hq ENGINEERING.md says a repo reads flags through one `flags`
module, each with an owner and an expiry date and a test that fails when
it expires. The app had none: `welcome.features` was parsed and never
read. The first two flags are switches for everyone - code the user wants
out of the app for now but kept (the Detect nudge; Fill the width until
the Smooth mode fills lines itself) - not rollouts. Core's contexts are
independent (decision 0002) and can't import `core.releases`, which
owns flags.

## Decision

- **`core.releases.flags`** declares every flag (`Flag`: name,
  description, owner, expiry, default) in `DECLARED`, and is the only way
  code reads one: `flags.on(FLAG)`.
- **Read at the edges:** `ui`, `ui_next` and `main` read flags. A context
  inside core that needs one is handed the value by `main` (a setting, an
  argument), and never imports `core.releases`.
- **The value is the default for now**, the same for everyone.
  `set_value` sets one for a run: tests and the UI lab, to show what's
  behind it. When a flag needs a rollout, `main` passes
  `welcome.features`' value through `set_value`; nothing that reads it
  changes.
- **`tests/releases/test_flags.py`** fails once a flag is past its expiry.

## Why

- One module and one call keep the swap ENGINEERING.md wants open: the
  server's table, or a flag service, behind `set_value`.
- A local default is all the first two flags need; wiring
  `welcome.features` now would add a server change and a protocol example
  for a value nobody varies (no speculative generality).
- Settings would have been the other place, but a flag isn't the
  learner's choice and doesn't belong in their file.

## What would make us reverse it

A flag that must differ between learners, or change without a release:
then its value comes from `welcome.features` - still through this module.

## How we'd reverse it

Read `welcome.features` in `main` after `welcome` and call `set_value` for
each declared flag it names (a few lines and a test); declare the flag on
the server too. Removing a flag: delete it from `DECLARED` and its `on`
calls (and the code behind it if that goes).
