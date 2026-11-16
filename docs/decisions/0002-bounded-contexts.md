# 0002 One package per bounded context; contexts meet in core.shared

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** the contexts and their rules: the user, 2026-11-04
  (polyglotic-hq DOMAIN.md). `core.shared` as their meeting point was
  chosen by project 013 (2026-11-04) while encoding the rules; Claude
  reviews it with the pull request. The server makes the same choice
  (polyglotic-server decision 0002).

## Situation

DOMAIN.md names seven bounded contexts and the rules between them: no
shared objects (a dictionary entry and a saved word are different things,
linked by an ID), and events where they can ("caption finished", "word
looked up").

Four run in the app: Listening (the PC captures and shows), Learning (the
PC shows learning data and may cache it), Lexicon (dictionary files on the
PC, for instant lookups) and Releases (version, channel, flags). The others
- Translation, Accounts, Usage and plans - run on the server only.

## Decision

- `core/` has one package per context the app runs: `listening`,
  `learning`, `lexicon`, `releases`.
- **Contexts don't import each other** - the import-linter contract
  `contexts-independent` (an independence contract; it also catches
  indirect imports through other modules).
- **They meet through `core.shared`:** the events contexts publish and the
  IDs they share, as small immutable types with no logic. Every context may
  import it; it imports no context (`shared-imports-no-context`).
- `tests/test_layout.py` fails if a package is added to `core/` without
  being added to both contracts.

## Why

- An independence contract forbids even importing another context's event
  class, so events need a home that both the publisher and the listeners
  can import. One small shared module is the simplest such home, and it
  makes the "published language" between contexts visible in one place.
- Alternative not taken: each context exposes an `events` module that
  others may import, using import-linter's `ignore_imports`. Ignored
  imports are removed before checking, so a context's internals could then
  leak through its `events` module unchecked.
- Example of the rule in practice: Learning highlights saved words in a
  line, and Lexicon splits the line into dictionary words. Learning doesn't
  call Lexicon; it works from words and entry IDs that `main` (or an event)
  brings to it.

## What would make us reverse it

- `core.shared` grows logic, or becomes a dumping ground for types that
  aren't events or IDs.
- Learning and Lexicon keep needing each other's internals - a sign the
  boundary between "a dictionary entry" and "a saved word" is drawn in the
  wrong place on the PC.

## How we'd reverse it

- Split `core.shared` into one published-events module per context, with
  `ignore_imports` rules plus a contract that each such module imports
  nothing else from its context. About an hour, plus moving the types.
- Merge or redraw contexts: change DOMAIN.md first, then move packages and
  update the contract lists; the layout test points to anything missed.
