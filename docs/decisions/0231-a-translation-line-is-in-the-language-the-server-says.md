# 0231 A translation line is in the language the server says it is written in

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** polyglotic-hq project 497's brief (from 490's report, finding 5); polyglotic-server decision 0097; Claude reviews before merge

## Situation

A clause's translation is kept under its target, and a line already in
the target is translated into the target's second language and kept
under the target all the same (polyglotic-hq 427 and 432). The app worked
out which language such a line is written in from the caption's label
(`captions.written_in`): a caption said in the target has its lines in
the second language; any other, in the target.

Since polyglotic-server decision 0096 a clause's line follows the
clause's own language, not the caption's. In a window into English,
Chinese its second, a caption labelled Mandarin with an English clause
in it ("It's not what I expected in the beginning,") has that clause's
line in Chinese (这与我最初的预期不同。), under English. The app read it as
English: no pinyin over it, no Traditional for a learner who reads
Traditional, an English row's font and lookups (a Chinese word in it was
still found by its writing, polyglotic-hq 337), and the transcript saved
it in the English column (polyglotic-hq 490,
`pictures/e2e-2-after-pr329.png`).

## Decision

- **`Clause.written_in`** (`core.listening.captions`), by the same key as
  `translations`: the language each line is written in, from the
  server's `written_in` (protocol.md, server decision 0097).
- **`captions.line_language(clause, key, said_in, second)`** is the one
  answer to "what language is this line in": the server's word for it,
  else `written_in` from the caption's label as before (an older server).
- It decides everything that reads a line's language: the row's language
  (`display.translation_shown`, so the one layout, the font, the reading
  line - pinyin, Jyutping, furigana - and the lookups follow it), the
  learner's script for Mandarin (`mandarin_written`), and the transcript's
  columns (`transcript`). A kept translation keeps its language with it
  (`history.keep_translations`, `settling`).

## Why

- **Only the server knows.** Which way each clause went depends on its
  language runs, their thresholds and the target's second language - the
  server's rules (0096), which may change again. Copying them into the
  app would keep two copies in step; the server's word ends that.
- **The old guess stays as the fallback**, so the app works as before
  with a server that doesn't send it, and a line the server says nothing
  about is read as before.
- Not taken: guessing from the line's own script. A line's writing tells
  Chinese from English, but not Mandarin from Cantonese, Simplified from
  Traditional (`zh-hant`), nor Japanese's kanji from Chinese.

## What would make us reverse it

- A protocol version that keys each translation by the language it is
  written in: then the key says it and the field goes.

## How we'd reverse it

`line_language` back to `written_in` at its three callers, and the field
off `Clause` and the connection's parse - a small change; nothing is
stored with it.
