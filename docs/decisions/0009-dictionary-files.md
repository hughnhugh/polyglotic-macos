# 0009 Dictionary files: SQLite, built from pinned sources, not committed

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** the sources and their licences: the user, 2026-11-04
  (polyglotic-hq project 008: CC-CEDICT, ECDICT cut down without its
  `collins` and `oxford` columns, jieba, HSK levels; share-alike accepted,
  dictionary files shipped as separate, unlocked files with credits). The
  format, the pins and the build were chosen by project 018 (D4) on
  2026-11-04; Claude reviews them with the pull request.

## Situation

The app looks words up on the PC, instantly and for free. The proof of
concept downloaded CC-CEDICT's text (4MB gz) on first use and parsed it
into memory: 1.37s and about 108MB of Python objects on 2026-11-04's
machine, measured on the 2026-09-27 release. Known words (MVP.md) add per
entry an entry ID, a frequency rank, HSK levels and inflections. The files
must be reproducible from a clean checkout, and the repo's pre-commit check
stops any added file over 500KB.

## Decision

**Format:** one SQLite file per dictionary - `cedict.sqlite` (Chinese
learners) and `ecdict.sqlite` (English learners) - plus `CREDITS.md`. The
schema belongs to `adapters/sqlite_dictionary.py`, which both reads it (for
core, through the `DictionaryFile` port) and writes it (for the build); the
file carries a format number the app checks.

**Built, not committed.** `uv run python -m tools.dictionaries.build`
fetches each source, checks it, and writes the files to
`build/dictionaries/` (git-ignored). The release workflow (D5) runs it and
ships the files beside the app; until then it's run by hand. The same
sources give byte-identical files (a test builds twice and compares).

**Sources, each pinned by URL and SHA-256** (`tools/dictionaries/sources.py`):

| Source | Version | Licence | Gives |
|---|---|---|---|
| CC-CEDICT | 2026-09-27T12:50:23Z, 125,127 entries; the Wayback Machine's copy of MDBG's file (MDBG serves only the latest) | CC BY-SA 4.0 | Chinese entries |
| jieba `dict.txt` | commit 67fa2e3 (2020-02-15) | MIT | Chinese frequency ranks |
| hsk30 (PyPI wheel; its data files are read from the archive, its code never run) | 0.2.1 (2026-09-06) | MIT | HSK 3.0 levels: the 2025 exam syllabus (`hsk-2025`) and the 2021 standard (`hsk-2021`), kept apart |
| ECDICT `ecdict.csv` | commit 39cfb96 (2026-11-02) | MIT | English entries, IPA, inflections |
| wordfreq (PyPI wheel; only `large_en.msgpack.gz` is read) | 3.1.1 (2023-11-21) | data CC BY-SA 4.0 (credit SUBTLEX, Google Books Ngram, OpenSubtitles) | English frequency ranks |

**Rules in the build:**
- **ECDICT cut:** words ranked in either of its corpora (`frq`, about 42,000
  words; `bnc`, about 45,000) or on one of its exam lists, with Chinese
  meanings: 57,841 of 770,611 rows. Its `collins`, `oxford`, `definition`,
  `detail` and `audio` columns are never read.
- **Frequency ranks:** Chinese from jieba's counts (90,721 of 125,127
  entries ranked). English from wordfreq, as project 019 recommends (its
  sources are named; ECDICT's corpus isn't): each entry's frequency is its
  word's plus its inflected forms', since statuses are per entry (57,023
  ranked). `--english-frequency ecdict` uses ECDICT's own columns instead
  (56,992 ranked). The file records which was used
  (`info.frequency_source`); each source is one function, so another list
  is a new function.
  - Measured 2026-11-04: the two put 72% of entries in the same English
    band and 94% within one band; their top 1,000 share 785 words.
    wordfreq is closer to speech: "children" 384 (ECDICT 27,285, ranked
    under "child"), "awesome" 1,458 (7,041), "thereby" 6,567 (3,179).
  - **wordfreq's data is CC BY-SA 4.0, so `ecdict.sqlite` built with it
    is CC BY-SA 4.0 too** (ECDICT's MIT allows that). Both files are then
    share-alike - already accepted for CC-CEDICT (project 008).
- **HSK levels** attach to every entry of the listed simplified word that
  isn't a name or a "variant of" (the lists give no pinyin). 2 words of the
  2025 syllabus and 31 of the 2021 standard aren't in CC-CEDICT.
- **Inflections:** each ECDICT lemma's forms (`p:ran/i:running/...`), then
  each form's own `0:` lemma, which wins: 39,355 forms.

**Measured** (2026-11-04, this PC, Python 3.12, files from the pins above):

| | `cedict.sqlite` | `ecdict.sqlite` | Proof of concept (CC-CEDICT gz) |
|---|---|---|---|
| Size | 24.9MB (12.5MB zipped) | 8.9MB (4.5MB zipped) | 4.0MB gz |
| Ready to use | 75ms (open, then every headword for the word split) | under 1ms (open) | 1.37s (parse, sort, English index, jieba) |
| Python memory | 21MB | about 0 | 108MB |
| A lookup | about 0.03ms | about 0.03ms | in memory |
| Word split, 28-character line | 0.13ms | - | similar (same algorithm) |
| Reverse lookup | 8-20ms; "to" 205ms | - | in memory |
| Build | 4.3s | 3.3s | - |

## Why

- **Fast start, little memory:** nothing is parsed at startup; only the
  set of headwords is loaded, for the word split. 18 times faster to be
  ready and a fifth of the memory, for an app that sits beside a game or a
  call all day.
- **Plain and unlocked**, as CC BY-SA requires (project 008): anyone can
  open an SQLite file with free tools. One file per dictionary keeps each
  file's licence and credits simple.
- **Queries D1 will need come free:** entries by level for first-run
  statuses, by ID for the vocabulary list.
- **Not committed:** 34MB of generated files, rebuilt in seconds from pins;
  committing them would fail the 500KB check and bloat history with every
  update. What must persist between builds - the entry ID registry - is
  small and committed (decision 0007).
- **Bigger to download than the gz** (12.5MB zipped against 4MB). The
  installer compresses it; an app with Qt is far bigger anyway.
- **Alternatives not taken:**
  - *The proof of concept's way*, text parsed at startup: smallest
    download, but 1.37s and 108MB every start.
  - *JSON or MessagePack loaded whole:* still parses everything at start.
  - *pickle:* fast, but runs code when loaded and isn't an open format.
  - *Committing the files* (with the size check relaxed): history grows by
    tens of MB per dictionary update, for files a build makes in seconds.

## What would make us reverse it

- The download size starts to matter (for example many dictionaries for
  other learners' languages) - then compress the shipped files and unpack
  on install, or trim the reverse-lookup index.
- A pinned URL disappears: the Wayback Machine's copy of CC-CEDICT, or
  GitHub's raw files. Then keep our own copy of each pinned source (for
  example as a release asset or in our R2 bucket) and pin that.

## How we'd reverse it

- Another format: a new adapter implementing `DictionaryFile` and a new
  writer for the build; core doesn't change. About a day.
- Committing the files: relax the size check for `build/dictionaries/` and
  stop ignoring it - an hour, but see "Why".
