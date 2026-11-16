# 0164 Mandarin is shown in Traditional by converting each caption on the PC as it arrives, one character for one

- **Status:** accepted; translations into Chinese (its "Where") replaced by
  [0204](0204-translations-into-chinese-follow-the-mandarin-script.md) (2026-11-17)
- **Date:** 2026-11-16
- **Decided by:** polyglotic-hq project 375's brief (the user, 2026-11-16:
  "is traditional mandarin now a valid captioning display method? where is
  this setting? especially if you have detect mode on"; DECISIONS #176,
  and #129 before it); Claude reviews before merge.

## Situation

The speech model writes Mandarin mostly in Simplified characters, Detect
or not. "Chinese (Traditional)" was only a language to translate into. A
learner who reads Traditional - in Taiwan or Hong Kong, or learning there -
saw every Mandarin caption in a script they don't read every day, and the
words they looked up, saved and sent to Anki came from it.

The caption's text is used everywhere after it arrives: the caption
window draws it and finds the word under the mouse with the word split,
the server's word links mark spans of it (in code points, protocol.md),
the transcript keeps it, copy and Anki take it, and Learning counts its
words by dictionary entry.

## Decision

**Setting:** "Show Mandarin in: Simplified / Traditional"
(`mandarin_script`), beside Spoken language in Settings > Speech and in a
transcript's Languages (the same panel). Not in a caption window's own
settings: those are that window's, and this is every window's. Not chosen, it follows this PC: Traditional
when the app's language is Traditional Chinese, or else when the first
Chinese among Windows' display languages is Taiwan's, Hong Kong's or
Macau's (`interface_language.reads_traditional`).

**Where:** each caption update is converted once, on the session's thread,
before anything else sees it (`main.MandarinScript`, through
`core.listening.captions.mandarin_written`): every clause's original
except a Japanese or Cantonese caption's; translations stay in the
language the learner picked for them. Nothing new goes to the server.

**How:** `core.lexicon.traditional.TraditionalChinese`: OpenCC's
Simplified-to-Traditional data (STPhrases, STCharacters, then Taiwan's
forms, TWVariants: OpenCC's `s2tw`), longest phrase first, **one character
for one** - a table that would change a length is refused, so the
server's spans, selections and the word under the mouse all still line
up. The table is OpenCC ver.1.1.9's (Apache-2.0), made into one file by
`tools/traditional_table.py`, read on a thread of its own when
Traditional is chosen (at the start, or switched on; polyglotic-hq 442).

**Words:** once Traditional is shown, the Chinese dictionary also finds a
word by its Simplified form (`ChineseDictionary.read_traditional`): where
the Traditional form isn't one of CC-CEDICT's (佈滿 is its 布滿) the split
uses the Simplified form, and where it is only "variant of" (宣佈) a
lookup gives the Simplified word's entries. So a converted line splits as
the line it came from, and counts the words a learner knows. The
dictionary is told when Traditional is chosen, not with the first
converted caption, so a card opened from Words before any caption finds
Taiwan's forms too, and told none when it's switched off, so it reads as a
Simplified learner's again (`MandarinScript`; polyglotic-hq 442).

Enforced by `tests/lexicon/test_traditional.py`, `tests/test_mandarin_script.py`
and `tests/ui_next/test_mandarin_script_row.py`.

## Why

Measured by polyglotic-hq 375 (2026-11-16):
- **Accuracy:** FLORES-200's human-written Traditional (zho_Hant, dev and
  devtest, 2,009 sentences, Taiwan's usage), taken to Simplified with
  OpenCC's t2s and back: 99.68 % of 67,734 Chinese characters as written,
  1,819 sentences exactly. Most of the 217 differences are both correct
  in Taiwan (台/臺, 布/佈, 周/週, 岩/巖). CC-CEDICT's own pairs word by
  word through the app's split (the other way that needs no new data):
  99.18 %, 1,563 sentences, with real mistakes (于 left for 於 112 times,
  后 for 後 85).
- **Words:** FLEURS Mandarin's 349 transcripts: 348 split exactly as their
  Simplified lines (331 without `read_traditional`); 7,361 of 7,410 words
  count for the same entry, and nearly all of the other 49 for the better
  one (後 "back", not 后 "empress"; 於; 藥 "medicine", not 药 "iris leaf").
- **Cost:** 0.06 ms a caption at the median, 0.27 ms at most (43
  characters on average), on the session's thread; the split of a
  converted line 0.077 ms against 0.068; the table read once, about 80 ms.

Taiwan's forms rather than OpenCC's own (為 裡 著, not 爲 裏 着) because
they are CC-CEDICT's: a lookup finds the word, not a "variant of" entry,
and they are what Taiwan's learners read. Hong Kong's forms differ in a
few characters (OpenCC's s2hk); one choice keeps the setting simple.

Not taken:
- **Converting only for drawing** (the text stays Simplified): every
  place that shows or hands on text would convert on its own - the caption
  window, the transcript, copy, Anki's sentence, a saved word's line - and
  one missed shows the other script.
- **CC-CEDICT's pairs** (no new data): less accurate (above).
- **The `opencc` package:** a native library for a table lookup Python
  does in 60 lines.

## What would make us reverse it

- Learners in Hong Kong ask for Hong Kong's forms: a third choice (s2hk's
  table), the same code.
- The speech model writes Traditional itself when asked: then the server
  could, and this conversion goes.
- A mistake that matters, often enough (a wrong 發/髮): more phrases, or
  OpenCC's newer data.

## How we'd reverse it

Take out the setting, `MandarinScript` and `read_traditional`'s callers:
captions arrive as the server writes them again. The table and the
converter can stay or go; nothing else depends on them. A small change.
