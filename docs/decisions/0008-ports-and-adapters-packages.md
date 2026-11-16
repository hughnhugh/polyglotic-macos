# 0008 Every interface core needs in `ports/`; storage in `adapters/`, as on the server

- **Status:** accepted; replaces the part of 0001 that put the interfaces
  core needs inside each context
- **Date:** 2026-11-04
- **Decided by:** adding `ports/` and `adapters/` with the first storage
  code: Claude's review of project 013, carried into D1 and D4
  (polyglotic-hq MVP.md, "Carried into the build projects from 013's
  review"; project 018's brief). The details below were chosen by project
  018 on 2026-11-04; Claude reviews them with the pull request. **One
  rule for every interface core needs** (moving D2's capture and mic-bleed
  interfaces into `ports/` too): Claude, 2026-11-04, following
  ENGINEERING.md's architecture.

## Situation

The first storage code has arrived: the app reads its dictionary files
(project 018, D4), and saved words, settings, the updater and crash
reports will follow. None of them fits `platform` (capture), `connection`
(the server) or `ui` (Qt) - ARCHITECTURE.md, "Not placed yet". Decision
0001 put the interfaces core needs inside each context, with `main`
handing core an implementation from somewhere outside it, and named this
as the likely reason to reverse it.

## Decision

As on the server (polyglotic-server decision 0001):
- **`ports/`** holds the interfaces core needs from outside - each a small
  `typing.Protocol` plus the plain value types that cross it, named for
  what core needs (`DictionaryFile`, `EntryRecord`), not for a technology.
- **`adapters/`** holds the infrastructure behind them that isn't capture,
  the server connection or Qt: the dictionary files (SQLite) first.
- **Layers:** `main` (and the developer `harness`) → `ui` | `connection`
  | `platform` | `adapters` → `core` → `ports`. Ports sit below core: core
  imports ports; ports import nothing from the package. The four plugs
  don't import each other.
- `core-no-infrastructure` now covers `ports` too: no Qt, storage, network
  or vendor library there either.
- **Every interface core needs goes in `ports/`, not inside a context**
  - whatever implements it (`platform`, `connection`, `ui` or `adapters`).
  D2's three, written meanwhile, moved here with this record, behaviour
  unchanged:
  - `AppList` and `AudioCapture` (with `PlayingApp` and `AudioCallback`),
    from `core/listening/capture.py` to `ports/capture.py`;
  - `MicBleedCheck`, from `core/listening/timing.py` to
    `ports/mic_bleed.py`;
  - `SourceCategory`, from `core/listening/sources.py` to
    `ports/capture.py`, because the app list reports it and ports can't
    import core. Listening's `Source` uses it from there.

Checked by import-linter (`pyproject.toml`); `tests/test_layout.py` expects
both packages.

## Why

- One rule in both repos: anyone who knows the server's layout knows the
  app's.
- The plain value types a port exchanges (an `EntryRecord`; a
  `SourceCategory`) need a home that core and the plugs can both import;
  below core is the only place that keeps the plugs out of core's
  internals.
- One place to look: every way core reaches outside is listed in one
  package, so a reviewer can see what a new OS, transport or storage
  format would have to provide.
- Core still gives the data its meaning: the dictionary file stores
  numbered pinyin and levels as pairs; `core.lexicon` turns a record into
  a `DictionaryEntry` with tone marks and a name flag. Swapping SQLite for
  another format is a new adapter; core doesn't change.
- **Alternative not taken:** keep the interfaces inside each context and
  add only `adapters/`. Then a port's value types live in a context, and
  any adapter importing them could reach the rest of that context.

## What would make us reverse it

- `ports/` fills with types that are really domain types, copied or
  converted back and forth for no gain.
- Adapters keep needing each other (for example settings needed by the
  updater) in ways that `main` can't wire simply.

## How we'd reverse it

- Interfaces back into contexts: move each port module into the context
  that uses it, drop the `ports` layer from the contract. A rename, about
  an hour.
- Adapters that need each other: change `|` to `:` between them in the
  layers line, with a new record.
