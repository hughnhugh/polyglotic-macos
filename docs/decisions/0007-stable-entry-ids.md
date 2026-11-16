# 0007 Stable entry IDs: a hash of the entry's first key, plus a registry of exceptions

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** that statuses go to the server by entry ID, and that IDs
  must survive dictionary updates: the user, 2026-11-04 (polyglotic-hq
  MVP.md, "Known words"; DOMAIN.md, open question "Stable IDs for
  dictionary entries"). This design was chosen by project 018 (D4) on
  2026-11-04; Claude reviews it with the pull request.

## Situation

Word statuses (new, learning, known, ignored), saved words and lookups go
to the server as entry IDs, never as text (DOMAIN.md, "Data and privacy").
The server keeps them for years; the dictionaries change under them.

- **CC-CEDICT has no IDs.** An entry is its head line: traditional,
  simplified, pinyin (`電腦 电脑 [dian4 nao3]`), and the pinyin gets
  corrected - tones, capitals for names, a traditional form. Between the
  releases of 2025-11-25 and 2026-09-27, 823 of 125,127 entries changed
  their head line this way and 8 were merged into another entry
  (measured with `update_ids`; see below).
- **ECDICT keys entries by the word**, which doesn't change; words come
  and go.
- The server should store an entry ID as an opaque string with a length
  limit (polyglotic-server, project 017), and never need the dictionary to
  store one.

## Decision

**Format:** `<dictionary>:<10 characters>` - the dictionary's name (`cedict`
or `ecdict`, lower-case letters and digits), a colon, and ten characters of
Crockford's base32 in lower case (`0-9`, `a-z` without `i`, `l`, `o`, `u`).
For example `cedict:y7p98nwvxq`. Always ASCII, 17 characters today; the
server's limit should be 64, to leave room for longer dictionary names.
Treat it as opaque: nothing should parse the part after the colon.

**Where IDs come from:** the first 50 bits of SHA-256 of the entry's key
when the entry was first seen. CC-CEDICT's key is the head line with its
pinyin spaced singly; ECDICT's is the word. Unchanged entries need no
record anywhere: the build recomputes the same ID. The hash is fixed
forever; a test pins two values.

**The registry** (`tools/dictionaries/registry/<dictionary>.tsv`,
committed) records only the exceptions:
- `id <key> <entry ID>` - this key's entry has an ID that isn't its own
  hash: its key was corrected and it kept the old ID, or its hash was
  taken (then the next salted hash, recorded so it never moves).
- `merged <old ID> <entry ID>` - that entry was merged into this one. The
  dictionary file carries these, resolved through any chain, so the app
  can show a status saved under the old ID on the entry it became.

**When a source's pinned version changes**, `python -m
tools.dictionaries.update_ids <dictionary> OLD NEW` compares the two
releases and updates the registry. The rules:
- **Same key:** same ID; nothing recorded.
- **Changed:** a key that left and a key that arrived, sharing a *match
  key* and with meanings alike enough, are the same entry: the new key
  keeps the old ID. CC-CEDICT's match keys, strongest first: the same
  characters and the same syllables ignoring tones, capitals and spacing;
  the same simplified form and pinyin (traditional corrected); the same
  traditional form and pinyin (simplified corrected); the same characters
  with meanings at least half alike. Each key matches once; the strongest
  match, then the most alike meanings, wins.
- **Split:** one entry became two - the likelier one keeps the ID, the
  other is new.
- **Merged:** a key that left without a match, whose meanings are at least
  half alike to an entry still there with a shared match key: recorded as
  merged into it.
- **Removed:** anything else that left. Nothing is recorded; if the same
  key returns, so does its ID. An `id` record for a removed key stays, so
  its ID is never given to another entry.
- **Added:** anything else that arrived gets its hash.

The script prints what changed, with examples to check by eye; the
registry is committed with the new pin, and reviewed like code.

## Why

- **Unchanged entries cost nothing, and a lost registry costs little.**
  IDs are recomputed from the source, so the registry holds only what
  changed: 106KB after ten months of CC-CEDICT changes (831 records),
  well under the repo's 500KB limit for a file. Without the registry,
  every unchanged entry would still get the same ID.
- **The build is reproducible from the repo alone:** pinned sources plus
  the registry give the same IDs on any machine, in any order.
- **Short and fixed-length** for the server. 50 bits for at most a few
  hundred thousand entries makes a collision about 1 in 50,000 per
  dictionary; the build checks and salts if one happens (none in the
  2026-09-27 release).
- **Alternatives not taken:**
  - *The head line itself as the ID* (`cedict:天氣|天气|tian1 qi4`, as in
    the server's illustrative example): changes whenever the pinyin is
    corrected, up to about 220 bytes, and confusing once the entry's
    pinyin no longer matches it.
  - *Sequential numbers with a registry of every entry:* shorter IDs
    (`cedict:48213`), but the registry (about 4MB) becomes the only source
    of every ID - too big for a committed file, and losing it loses
    everything. Two branches adding entries would also collide.
  - *Content hashes of the meanings:* change whenever a meaning is edited,
    which happens daily.

## Measured on real releases

From the Wayback Machine's copies of MDBG's file (2025-11-25, 2026-09-27)
and MDBG's file of 2026-11-04, carried in two steps (2026-11-04):

| Step | Unchanged | Carried (key corrected) | Merged | Removed | Added |
|---|---|---|---|---|---|
| 2025-11-25 to 2026-09-27 | 121,643 | 823 | 8 | 1,643 | 2,661 |
| 2026-09-27 to 2026-11-04 | 124,999 | 11 | 1 | 116 | 355 |

Checked by eye, about 50 of each kind. Carried: capitals for names
(`[bu4 lai2 mei2]` to `[Bu4 lai2 mei2]`), tones (`[gan1 di4]` to `[gan3
di4]`), traditional forms (`只言片語` to `隻言片語`). Merged: variant
traditional forms folded together (`表帶` into `錶帶`). Removed: entries
dropped from CC-CEDICT (`上衫` "blouse", Taiwanese townships). No wrong
carry was seen; it isn't proven there are none.

## What would make us reverse it

- Wrong carries or merges found in review often enough that the registry
  needs hand-editing on most updates.
- Moving to a source with its own stable IDs (for example Wiktionary-based
  data with page and sense IDs), where those IDs would serve better.

## How we'd reverse it

- A different scheme for new dictionaries is just a new prefix; existing
  IDs stay valid.
- Replacing the IDs of an existing dictionary means a mapping from old IDs
  to new ones, applied once on the server and in the app's local data -
  the `merged` table already does that job for single entries.
