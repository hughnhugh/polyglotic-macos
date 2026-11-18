# 0160 Cantonese is its own language, with its own dictionary pack and Jyutping

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** the user, 2026-11-17 (polyglotic-hq DECISIONS #179,
  items 1-2: "Yes cantonese is its own language with jyutping (this should
  also be a script assistance similar level to english phonology / zhu yin
  / pinyin)"), on polyglotic-hq 371's design; built by polyglotic-hq 450.
  The pack reaches testers only once it is published in the signed list
  (decision 0122).

## Situation

Captions come in Cantonese (`yue`) already: the speech model names it and
writes it as Cantonese is written (嘅, 係, 喺, 佢, 咗), the server puts it in
Hong Kong characters, and the window labels the line "Cantonese". Nothing
after that knew Cantonese:

- A Cantonese line's words went to the Chinese dictionary (CC-CEDICT) when
  Chinese is learned, and to none when it isn't (decision 0129). The card
  gave Mandarin: 係 was "xì: to connect", not "hai6: to be"; 佢 was "qú";
  佢哋 (they) and 而家 (now) had no entry. On HKCanCor's conversations
  (CC BY 4.0), CC-CEDICT has 84.6 % of the words said, and keeps 53 % of
  the words of two characters or more whole (371).
- Cantonese was "No dictionary yet" on Learning (`languages.tier_of`), so
  a card never offered to learn it, and word links past what you know were
  never judged by the Cantonese word (a learner of Chinese alone saw every
  link at every level: 258 of 258 in 371's run).
- A reading line (decision 0155) had pinyin only.

## Decision

1. **Cantonese is its own learned language** (`yue`, as
   `languages.learned_code` already has it), not a variety of Chinese: its
   own pack, its own readings, and its own learning data. A learner may
   learn both; neither's known words count for the other.
2. **A Cantonese pack**, in the basic tier (`languages.BASIC`), by the
   signed list (decision 0122): language `yue`, meanings `en`, dictionary
   `canto`, in the packs' own file format (`tools.dictionaries.packs`).
   - Entries: CC-Canto's (Cantonese words, Jyutping, English meanings),
     then CC-CEDICT's entries with their Cantonese reading (CC-Canto's
     readings file; where it gives several, the everyday one; where it
     gives none, rime-cantonese's). A CC-CEDICT entry CC-Canto has with
     the same reading is left to CC-Canto's, which adapted it.
   - Headwords in Hong Kong Traditional characters, as captions come; a
     Simplified form finds the same entries unless it is a Traditional
     headword of its own (系 "system" isn't 係's).
   - A form's entries: its everyday reading first (rime-cantonese's word
     list, else its characters' weightiest readings: 嘅 ge3 before koi3),
     then CC-Canto's before CC-CEDICT's, a "variant of" last - as
     decision 0155's order does for pinyin.
   - Jyutping is written in the pack with its tone number raised (hai⁶),
     so the card, saved words and the Anki deck show it as the reading
     line does.
   - Ranks (decision 0120): HKCanCor's words as spoken, averaged with
     wordfreq's written Chinese by each word's Simplified form. On 371's
     real captions (VOA news, a spoken Wikipedia article: 1,124 words)
     98.4 % of words have a rank; HKCanCor's alone ranked 61.7 %.
   - Licence CC BY-SA 4.0 (CC-Canto and its readings CC BY-SA 3.0,
     CC-CEDICT CC BY-SA 4.0, rime-cantonese CC BY 4.0, HKCanCor CC BY 4.0
     for counts only, wordfreq CC BY-SA 4.0); the credits name each.
   - Every entry is kept, ranked or not (147,880; 23.1 MB): the word split
     is by the pack's own words.
3. **A word split of its own, `han`** (`core.lexicon.han`; the
   `ports.word_split.WordSplit` port): the fewest of the pack's words over
   a run of Chinese characters, then the most evenly sized, then the
   commoner - Chinese's own rules, over the pack's forms. A phrase of two
   common words without a rank is left to them (decision 0151: 你嘅 is
   你 + 嘅). Plain Python, as Vietnamese's and Thai's are (decisions 0121
   and 0173). The pack list names it, so an app without it is never
   offered the pack (`packs.Reader`).
4. **A Cantonese line's words are looked up in the Cantonese pack** when
   it is here (the row's language holds: decision 0129, unchanged).
   Chinese's dictionary stays a fallback, and the card says so ("From the
   Chinese dictionary"). When Cantonese isn't learned, the card offers it
   ("Learn it too?"), as it does any basic language; learned, it keeps
   learning data as every pack language does (decision 0175).
5. **Jyutping over Cantonese** is a reading line at the same level as
   pinyin and zhuyin (decision 0155): its own switch in Settings, the
   same size and colour choices, on the caption and translation rows.
   Yale is a style of the same reading, later.
6. **The script stays Hong Kong Traditional** for Cantonese captions (the
   server's `scripts.cantonese`).

## Why

- A Cantonese learner's first need is the sound and the Cantonese meaning;
  a Mandarin reading on a Cantonese line is wrong information, not missing
  information.
- The pack path is the one every basic language takes: no new download
  route, no new consent, nothing sent anywhere. 371's prototype read a
  pack-format file through `BasicDictionary` and the card unchanged.
- CC-Canto with CC-CEDICT has 97.3 % of HKCanCor's words said (84.6 %
  without), and keeps 86.6 % of its longer words whole (53.0 % without;
  371).
- The pack's readings over its own split match HKCanCor's hand
  transcription for 94.6 % of characters outside sentence particles (450;
  371's prototype 96.0 %, ToJyutping 96.1 %). Most misses are the corpus's
  own spellings (哩 for 呢, 來 for 嚟: about 1,550 of 7,430) and colloquial
  readings rime-cantonese weighs below the literary ones (會 wui5, 返 faan1).

## What would make us reverse it, and how

- **CC-Canto proves too thin or too dated (its file is from 2017)**: swap
  or add a source in the pack build (words.hk under an agreement;
  Wiktionary's Cantonese senses). The app doesn't change: a new pack
  version.
- **Learners want Cantonese inside Chinese** (one set of known words): map
  `yue` to `zh` in `learned_code` for learning data only; the pack and the
  readings stay.
- **Jyutping from the pack reads too many words wrongly**: weigh a
  character's colloquial reading by HKCanCor's counts in the build, or
  ship ToJyutping (BSD-2) behind the same readings; the app reads what the
  pack says either way.
- **Mandarin-only written words rank too high** (的, 是 among the top 20,
  from wordfreq's half of the ranks): weigh speech above writing in the
  average, or add a Cantonese written list; a new pack version.
