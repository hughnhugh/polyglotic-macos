# 0204 Translations into Chinese are written in the script chosen for Mandarin, as a second language too

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** polyglotic-hq project 432's brief (Claude's call, reversible,
  recorded there: the user chose Traditional, and still saw Simplified
  translation lines in 427's pictures); Claude reviews before merge.
  Replaces the "Where" of [0164](0164-mandarin-in-traditional-is-converted-as-captions-arrive.md)
  ("translations stay in the language the learner picked for them").

## Situation

0164 converts what was said - each clause's original - into the script the
learner reads Mandarin in, and leaves translations as the server writes
them. The server writes Chinese ("zh") in Simplified. A learner who chose
Traditional (Settings > Speech, "Show Mandarin in") and translates into
Chinese, or has Chinese as a language's second language (English heard
in a window into English: the server keeps the Chinese line under
English, protocol.md's `second_languages`), saw Mandarin captions in
Traditional and every Chinese translation line beside them in
Simplified: 爱的道路, 发音, 们 in polyglotic-hq 427's pictures, with the
user's own settings. "Traditional" plainly means every Chinese line the
app shows.

## Decision

The same conversion as 0164 (`core.lexicon.traditional.TraditionalChinese`,
OpenCC's s2tw, one character for one), at the same place (`main.MandarinScript`,
on the session's thread, before anything else sees the caption), now also
takes each translation **written in Mandarin**
(`core.listening.captions.mandarin_written`):
- a translation kept under `zh`;
- a second-language line in Chinese: kept under a target `T`, for a
  caption said in `T`, where `T`'s second language is `zh`
  (`captions.written_in`, the rule `display.translation_shown` uses; the
  second languages from the settings, `MandarinScript.seconds`).

Not converted: a translation into `zh-hant` (written in Traditional
already), Japanese as a second language (kanji aren't Mandarin), and any
other language. A Japanese or Cantonese caption's own characters still
aren't converted; its translation into Chinese is.

Because the text itself is converted, everything after it follows with no
code of its own: the caption windows, readings (pinyin or Zhuyin, from the
dictionary's reading of the Traditional word: `read_traditional`), word
links (spans kept: one character for one), lookups (the card finds the
Traditional form by its Simplified one), learning marks, the transcript,
Copy, Save and Anki's sentence translation.

Enforced by `tests/test_mandarin_script.py`.

## Why

- One setting, one script: a Traditional reader shouldn't see two scripts
  side by side, one of them the one they said they don't read.
- The same reasons as 0164 for converting the text, not the drawing: one
  text for every place that shows or hands it on.
- **Not taken:** asking the server for `zh-hant` whenever Traditional is
  chosen. The server's Traditional is a different translation request
  (another language to the translator), would change what's sent, and
  would leave a second-language line's script to the server's own rules;
  the converter is already measured (0164: 99.68 % of characters as
  written) and costs well under a millisecond a caption.
- **Not taken:** a "Chinese (Traditional)" choice in the second-language
  picker only. The learner already said which script they read; a second
  place to say it would disagree with the first.

## What would make us reverse it

- Learners who read Traditional captions but want Simplified translations
  (a learner of both scripts): a setting of its own, "Translations into
  Chinese in: ...".
- The server writing Traditional itself when asked (0164's reversal too).

## How we'd reverse it

Drop the translations from `mandarin_written` (and `MandarinScript.seconds`):
translations arrive as the server writes them again. A few lines and their
tests.
