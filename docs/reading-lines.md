# Reading lines: pinyin, and the other scripts

Designed in polyglotic-hq project 364 (2026-11-15), agreed by the user the
same day (polyglotic-hq DECISIONS.md #174, #175) and built in project 369.
The decision is [0155](decisions/0155-a-reading-is-drawn-above-its-characters.md).

## What it is

A **reading line** is a small line of text that says how the text under it
is pronounced: pinyin above Chinese, furigana above Japanese kanji,
Jyutping above Cantonese. It belongs to a *language's text*, not to "the
caption" or "the translation": a learner hearing Chinese gets it on the
caption, one translating into Chinese gets it on the translation, and the
same switch covers both.

## The design

1. **Above each character, as ruby** (pictures A). Each syllable sits
   centred over its own character, in half the text's size, in the row's
   colour. A character whose syllable is wider than it gets room on both
   sides - less where its neighbour's reading is narrower than that one's
   character, so characters keep their spacing where they can; a small
   gap separates words, so the words are seen without joining their
   syllables.
2. **One switch per language** ("Pinyin above Chinese"), in Settings >
   Look (its own group, "Pinyin"). Off by default, with a size (Small
   or Medium) and, once, a hint on the caption window's notice line for a
   learner with Chinese's dictionary.
3. **A second choice: every word, or only the words past what I know**
   (pictures D). The same line the word links already use (decision 0130):
   a learner at 1,000 words sees pinyin only over the rarer ones.
4. **A language's lines keep one height** whether a given line has a
   reading or not, so text never moves down when a live caption's first
   reading arrives.
5. **The reading isn't part of the text**: selecting, copying, lookups,
   word links, the transcript and Anki cards are unchanged.
6. **Readings come from the dictionary already on the PC** (CC-CEDICT),
   by the word each character is in. Nothing new is sent to the server and
   nothing new is downloaded.

## What was considered and not proposed

- **A line under the row** (picture E, drawn only): pinyin written as a
  sentence between the caption and its translation. It reads well as
  pinyin, but the eye has to match syllables to characters by counting,
  it adds a full line to every caption, and it wraps at different places
  from the characters.
- **Above each word, syllables joined** (picture C): proper pinyin
  spelling (shídài), but a learner reading a character can't see which
  syllable is its own, and a wrong word split shows.
- **Tone colours** (picture B): kept in the prototype as an option. Not
  proposed as the default: five more colours in a window whose colours
  already mean something (who spoke, what is learnt).

## What it costs

- **Width:** Chinese with pinyin is 15.7 % wider on 100 FLEURS sentences
  (369; 364's spacing, each reading keeping to its own half, made it
  18.7 %).
- **Height:** 13 px more on a 28 px line at the default size.
- **Time** (369, offscreen): a row with pinyin takes about 0.2 ms more to
  lay out and 0.1 ms more to draw on Windows. A live update in a caption
  window with pinyin costs the same as without it in the same window, on
  Windows and on CI's Linux image alike (Linux 2.0 to 2.8 ms median in the
  new layout, inside the 4 ms budget); tests hold both. 364's 4.3 to 5.4 ms
  on Linux was a loaded runner against a different window (English text,
  no learner): 364's own test on a quiet copy of the runner's image took
  1.9 to 3.0 ms.
- **Accuracy:** on 12,294 characters of FLEURS Chinese, 8 wrong with the
  final rules (99.93 %; the rules were tuned on part of this text). On
  text unseen when measured: 26 wrong of 8,699 (99.70 %). pypinyin on the
  same text: 99.32 %; g2pM: 99.17 %.

## Other languages

| Language | The reading | Where it would come from | State |
|---|---|---|---|
| Chinese (Mandarin) | pinyin (later: zhuyin as a style) | CC-CEDICT, on the PC | built (369) |
| Japanese | furigana over kanji | Sudachi's reading, already in the app | next; needs its own accuracy check |
| Cantonese | Jyutping | rime-cantonese (CC BY 4.0) or ToJyutping (BSD-2) | needs a pack and a check |
| Korean, Thai, Russian, Arabic, Hindi | a romanisation | per-language tools | not proposed now: these scripts spell their sound; a learner past week two reads them |
| Vietnamese | chữ Nôm / Hán tự | no open source that covers running text | not proposed: see the report |

## How it's built

- `core/lexicon/readings.py`: `Reading` and `Readings`, a source's shape.
- `core/lexicon/chinese.py`: `ChineseDictionary.readings` - the word
  split, each word's everyday reading (the file's order, `everyday_first`),
  rules for a lone 为, 地, 只, 长, 得 and 重 by the words around it.
- `ui_next/reading_lines.py`: measuring and spacing (`ruby`), where each
  reading is drawn (`placed`), drawing (`draw`), and the caption windows'
  source (`source_of`, the learner's Chinese dictionary once it is read).
- `ui_next/views/flow.py` and `ui_next/caption_layout.py`: room above a
  line, in today's clause rows and the one layout (rows, Translation
  below, Line by line, run-on, lined-up).
- The setting: `CaptionLook.reading_lines` and `.reading_size`, saved as
  `reading_lines` and `reading_size` (`ui/settings.py`); Settings >
  Look's `ReadingLinesPanel`.

Not built: today's poured fills without the New layout (the Lab's), tone
colours, furigana.
