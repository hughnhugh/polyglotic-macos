# 0010 The learner's own learning data on the PC: one SQLite file, behind a port

- **Status:** accepted; its "Where" replaced by [0014](0014-user-data-in-roaming-app-data.md) (2026-11-05)
- **Date:** 2026-11-04
- **Decided by:** that statuses, saves and lookups go to the server as
  entry IDs and times while a saved word's source sentence and the
  exposure counts stay on the PC: the user, 2026-11-04 (polyglotic-hq
  DOMAIN.md, "Data and privacy"; MVP.md, "Known words"). The storage was
  chosen by project 025 (D1b) on 2026-11-04; Claude reviews it with the
  pull request.

## Situation

Learning keeps, on the PC, the learner's level (a curve: scheme and
midpoint), explicit word statuses with their source, categories, saved
words with their source sentences, exposure counts per entry, and daily
counts per entry for those who opt in to sharing them. The proof of
concept kept saved words in a JSON file beside the app, rewritten whole on
every change (`vocab.py`).

Exposures change on every finished caption - every few seconds while
listening - and over months reach tens of thousands of entries and a row
per entry per day. A crash or a power cut mid-write must not lose the
learner's statuses or saved words. Decision 0008 puts storage behind a
port in `adapters/`.

## Decision

- **Port:** `ports.learning.LearningStore` - load everything once at
  start (`LearningSnapshot`), then one write per change (a status, a saved
  word, a category, the level, a caption's exposures). Plain values cross
  it; core's Learning gives them their meaning.
- **Adapter:** `adapters/sqlite_learning.py`, one SQLite file. Each write
  is its own transaction (autocommit; a caption's exposures in one
  transaction). WAL journal. The schema version is SQLite's
  `user_version`, with one migration per version; a file from a newer app
  is refused, not opened.
- **Where:** `main` chooses the path - the user's local app data
  (`%LOCALAPPDATA%\Polyglotic\learning.sqlite` is the plan; nothing wires
  it yet). Not in the install folder, which updates replace. *Replaced by
  decision 0014 (2026-11-05): `%APPDATA%\Polyglotic`, since the installer
  replaces or removes all of `%LOCALAPPDATA%\Polyglotic`.*
- Core holds the data in memory while running (thousands of rows, a few
  MB at most), so highlights and lists never wait on the disk.

## Why

- **Safe against crashes for free:** SQLite's transactions; the JSON way
  needs a write-to-temp-and-rename, and rewrites everything on every
  exposure.
- **Grows well:** a change writes a row, not the whole file. The daily
  counts for opt-in sharing (D3b) are a table D3b can read and prune.
- **Already in use:** the dictionary files are SQLite (decision 0009);
  `sqlite3` is in the standard library - no dependency.
- **Open:** the learner's own data in a format anyone can open with free
  tools, for export or for the "see and delete your data" promise.
- **Alternatives not taken:**
  - *JSON beside the app* (the proof of concept): simplest, but rewrites
    everything on every finished caption, and isn't safe mid-write.
  - *Qt's `QSettings` / the registry:* not meant for tens of thousands of
    rows, and ties storage to Qt.
  - *Only on the server:* exposure counts and source sentences must stay
    on the PC (DOMAIN.md); the app must work offline.

## What would make us reverse it

- Sync (D3b) needs a log of changes rather than current state - then add
  a table, or move to an append-only file.
- The file gets corrupted in testers' hands more than rarely.

## How we'd reverse it

- Another format is a new adapter implementing `LearningStore`, plus a
  one-time copy from the SQLite file at start; core doesn't change. About
  half a day.
