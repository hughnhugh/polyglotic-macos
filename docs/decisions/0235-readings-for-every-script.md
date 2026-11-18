# 0235 Readings for every script: where each line reads from

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** Claude (polyglotic-hq 511, on 370's measurements and
  DECISIONS #200); reversible, so Claude's to make (polyglotic-hq
  CLAUDE.md, Rhythm)

## Situation

Decision 0155 put a reading over its characters (pinyin), 0160 added
Jyutping. The user asked for "all the phonetic helpers for languages non
romanised scripts" (2026-11-18) and a respelling above English
(2026-11-17, #200). 370 measured each script's data. Each line needs its
readings from somewhere on the PC, and one of them - Russian's stress -
isn't a reading above the text at all but a mark on a letter.

## Decision

Each line reads from what the app already has, or from rules:

- **Japanese furigana:** the Japanese pack's word split (Sudachi small)
  says how it read each word, as a new optional field of the port,
  `SplitWord.kana`; `core.lexicon.furigana` aligns it to the kanji. The
  small dictionary's known misreadings are put right in its adapter, where
  Sudachi's quirks belong.
- **English respelling:** the English dictionaries' build writes 471's
  respellings as their **form readings** (the table and port Russian's
  stressed forms already use); `EnglishDictionary.readings` reads them.
  Its own setting, `respelling_past`, on at first (#200: "only over new
  words"); the scripts keep `reading_past`.
- **Russian stress:** the Russian pack's stressed forms and headwords, as
  they are - no rider. Drawn as **a mark on its letter** (`Reading.mark`),
  in the text's own font at its baseline, and a `MARKED` language's rows
  keep no band.
- **Korean (Revised Romanization) and Hindi:** rules alone
  (`core.lexicon.korean`, `.hindi`), no dictionary, so any learner who
  turns them on gets them.
- **Every line is off at first and has its own switch** in Settings >
  Readings; word links' one click still turns on only pinyin and Jyutping
  (`reading_lines.ONE_CLICK`).
- A reader is anything with `ready` and `readings(text)`
  (`reading_lines.Reader`).

## Why

- No new downloads: furigana and stress use packs learners already have;
  the respelling rides in the English dictionary that ships with the app,
  through a table and port that exist.
- Sudachi's own reading, not a second analyser: 370 found UniDic and the
  larger Sudachi dictionaries 0.6 points better at most, for 87-775 MB.
- A mark, not a reading, for stress: drawn as a half-size reading over a
  band, 511's first try put a dot far above its vowel on real captions.
- Rules for Korean and Hindi: there is no Korean pack yet, and the only
  library that does RR's sound changes is GPL (korean-romanizer); 370's
  rules agree with g2pk on 99.6 % of words.
- Not taken: a reading pack per script (more downloads for little); one
  "Readings over" for all (English learners' respelling over every word is
  noise, while the user wanted pinyin over every word, DECISIONS #206).

## What would make us reverse it

- Furigana or stress wrong too often on casual speech (370 and 511
  measured read news) - a contextual model would be wanted.
- A Korean pack arriving with Wiktionary's own romanizations (ㄴ insertion,
  북한 Bukhan) - the rules would become its fallback.
- Learners asking for one switch for all readings.

## How we'd reverse it

- Another reader for a language is one module behind `Reader` and one
  branch in `reading_lines.reader`.
- Respellings move out of the English dictionary by writing them
  elsewhere at build and reading them through a new port; the reading
  line doesn't change.
- Stress as a reading above the line: drop `Reading.mark` from
  `core.lexicon.stress` and `ru` from `MARKED`.
