# 0234 A dictionary's meanings in the learner's language come as riders

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** Claude (polyglotic-hq 510), within DECISIONS #196 (A:
  finish the English pairs first, human-made meanings first) and the plan
  of polyglotic-hq 448; builds on decisions 0133, 0192, 0197 and 0211

## Situation

An English learner reads ECDICT's meanings in Chinese, or since 0.1.8 in
English (decision 0211) - never in their own language. A Spanish speaker
learning English should read Spanish. 341 designed meanings files (#650,
#652) on a stack that never reached `main`; 418 brought only its
recordings up.

## Decision

- A dictionary's meanings in one more language are a **meanings file**
  (`adapters/meanings_file.py`): entry ID -> meanings, plain SQLite, one
  language each, `<dictionary>-<language>-<version>.meanings`.
- It is a **rider** (decision 0133) of `meanings` kind, with the
  language in its list entry (`meanings`) and its own `min_app` (0.1.9,
  decision 0192): a pack's, or a built-in dictionary's in the list's
  `built_in` entry (decision 0197) - ECDICT's for English learners, from
  `--built-in ecdict --meanings FOLDER`.
- The app takes only the file in its **interface's language**
  (`main.meanings_wanted`: none for English or Chinese, the dictionaries'
  own), quietly, as recordings come; an app from before ignores the kind.
- A **shelf** (`MeaningsShelf`) holds the file open per dictionary; each
  dictionary reads through its view (`explain_in`), so a file that
  arrives is used from the next lookup, without a restart.
- The card's meanings are, in order: the file's where it has the entry,
  else the dictionary's own (`ecdict-en.sqlite`'s English, else - an
  older build, or a Chinese interface - ECDICT's Chinese). The entry, its
  ID and rank don't change, so statuses and saved words don't.
- **Only human-made rows are shown.** The format keeps 341's `machine`
  column, but this app treats a machine's row as absent: machine-made
  meanings wait for the GPU night and the user's yes (#171 Q2) and a
  card that labels them (#110).

## Why

The dictionary is built once, in the format older apps read; each
language is a small extra file (1-3 MB) a learner downloads only in their
own language. Riders already carry recordings with the same checks,
retries and clean-up; a built-in dictionary already has its own entry.
The alternatives - a separate English pack per meanings language (as the
`-zh` packs are), or every language inside the installer - cost every
learner the download of every language.

## What would make us reverse it

Learners asking for meanings in two languages at once (their own and
English side by side), or meanings files growing past a pack's size.

## How we'd reverse it

The card could take two files (a second shelf entry per dictionary).
Dropping the riders from the list drops them from every PC at the next
update; the dictionary files never changed.
