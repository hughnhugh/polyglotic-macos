# 0129 A word is looked up in its own script's language, not only its row's

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 337's brief - "with any set of
  learned languages and any caption language, the card for a word comes
  from that word's language's dictionary, every time" - after the user,
  2026-11-15, on 0.1.5: "Chinese dictionary doesn't seem to work
  simultaneously with english dictionary or is extremely flaky". Extended
  by Claude, 2026-11-15 ~08:40, to every learned language whose script
  tells it apart, after the user asked about "both english and chinese /
  other installed dictionaries". It narrows decision 0095's routing (by the
  row's language); 0095 stands otherwise.

## Situation

Decision 0095 opened Chinese's and English's dictionaries together and
sent each caption row to its own language's (`LearningTools.of`). A row's
language is its caption's: the first language the speech model names
(polyglotic-server `adapters/qwen_asr.py`). A mixed line has one:
"这个iPhone真的很好" is Chinese with an English word, "We had 火锅" English
with a Chinese one, and a short line can be named wrongly altogether.
With both languages learned:
- an English word in a Chinese row got "Chinese for it", never its
  English entry;
- a Chinese word in an English row, or in a row whose language has no
  code, wasn't even found to hover: English's word split doesn't split
  Chinese characters.
So the same Chinese word worked on one line and not on the next.

## Decision

- **The rule** (`core.lexicon.scripts.written_in`): a word whose script
  isn't its row's language's is taken for that script's language:
  - Chinese characters: Chinese (a Japanese or Cantonese row keeps them);
  - kana: Japanese (with kanji too: 食べる); Hangul: Korean; Thai; Greek;
    Hebrew; Devanagari: Hindi;
  - Cyrillic: Russian (a Ukrainian, Bulgarian, Macedonian... row keeps it);
  - Arabic script: Arabic (a Persian or Urdu row keeps it);
  - Latin letters: English, in a row not written in them or of a language
    not known.
  Otherwise the row's language holds.
- **Latin-script languages** (Vietnamese, Spanish, French...) can't be
  told from English by script. A Latin word in a row of one of them stays
  that language's: a Latin word in a Vietnamese line is far more often
  Vietnamese than English, and its pack is what the row was going to use.
  In any other row a Latin word is English, as the speech model writes a
  foreign word.
- **Only where that language is learned and has its dictionary here**
  (`LearningTools.word_language`): a full one open (Chinese, English), or
  a basic pack opened for a language learned (the tools' choices name
  every language learned). A pack on the PC for a language no longer
  learned isn't used; with Chinese alone, an English word in a Chinese row
  is still "Chinese for it" (306).
- **Where it applies:** the hover's word split (`LearningTools.word_at`: a
  Chinese character in an English or Russian row is split by Chinese's, a
  Russian word in an English row by Russian's pack; a basic row keeps its
  own split for its own words and for Latin ones) and the card
  (`Lookup.show`): its dictionary, and for a full language the learning
  data a pin, save, Deck or Known goes to.
- **Fallbacks, tried in turn until one has the word** (the user,
  2026-11-15 ~08:40: "We can also use the various translate functions
  either target or translation language / secondary as fallbacks, these
  should always be fallback options"; `LearningTools.dictionaries_for`,
  `found_in`):
  1. the word's own script's language, where that's learned (above);
  2. the row's language - what was said, or the translation's language on
     a translation row;
  3. the window's translation target;
  4. its second translation language;
  5. every other learned language with a dictionary here whose writing
     fits the word (`lexicon.scripts.fits`).
  Each with a dictionary here, each once; Chinese's only for a word with
  Chinese characters (a Latin word on a Chinese row stays "Chinese for
  it" rather than a Latin headword of CC-CEDICT's). Every one is tried
  before the card says "not in the dictionary"; if none has it, the row's
  (or the script's) dictionary says so as before. This settles the
  Latin-script case: a Latin word on a Spanish row is Spanish's if the
  pack has it, else English's.
- **The card says which dictionary answered** when it isn't the row's
  language's: "From the English dictionary", a faint line under the
  word's counterpart.
- **Cost:** a query a dictionary, read ahead already: a word none has,
  through four dictionaries on the shipped files (CC-CEDICT, ECDICT, the
  Russian and Vietnamese packs), took 0.18 ms (median; 337's report).
- **Not here:** Learning's marks and counting on a mixed row (each row's
  word split is still its row's language's) - proposed as their own
  project by 337.

## Why

- Where a script belongs to one language the script settles it; where
  several share it, the row's language wins when it's one of them, and
  the commonest otherwise. No guess about meaning, and nothing is sent or
  kept.
- Inside the tools that already route by language, so every view - the
  caption windows, the transcript, Words - follows without a change.

## What would make us reverse it

- A word in Latin letters in a non-Latin row that isn't English often
  enough to matter (pinyin, a French name in a Chinese line): it would
  then get "not in the dictionary" from ECDICT where "Chinese for it"
  helped more.
- The server giving each word its own language (a per-word language from
  the speech model): use that instead of the script.

## How we'd reverse it

`LearningTools.word_language` returning its `language` unchanged puts
every word back on its row's dictionary; `core/lexicon/scripts.py` and its
tests then go.
