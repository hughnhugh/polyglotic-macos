# 0151 The Chinese word split takes two common words over an unranked phrase of them

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 359's brief ("where an unranked
  dictionary entry competes with a split into ranked words (中的 vs 中 +
  的), prefer the ranked split, in both the desktop's split and the
  server's; keep real unranked words (names, idioms that are words)");
  Claude reviews before merge. The server's half is polyglotic-server's
  `links.phrases_of_common_words`, rule for rule.

## Situation

The word split (`ChineseDictionary.split`) cuts a run of Chinese into as
few dictionary words as it can, then the most even, then the commonest
(project 039). CC-CEDICT has many entries jieba never ranks because they
are two words side by side more often than a word: 中的 (zhòng dì, "to hit
the target"), 有了 ("to be pregnant"), 到了, 吃的, 不是吗, 有可能. As one
word each beats its two words on the first rule, so 生活中的 read "to hit
the target", 有了申根 "to be pregnant", and the hover card and the word
link both showed the phrase. Having no rank, each one also had no place
against what a learner knows, so under "past what you know" it was always
linked (polyglotic-hq 338: 32 such links on 100 FLEURS sentences).

## Decision

A dictionary form **without a frequency rank** that is **two words each
among the 3,000 commonest** (`COMMON_PARTS`; 中 + 的) isn't a word to the
split: the split takes its words. It stays one word if it is:
- **a name** (capitalised pinyin: 马里, Mali);
- **an idiom** ("(idiom)" in a meaning: 自由自在);
- **a word a syllabus lists** (an entry with an HSK level: 有的, "some",
  HSK 1; 一下儿, 不一定, 那时候).

It is still a dictionary word: looked up as itself, and found inside a
longer word (`parts`). Whether a form qualifies is asked of the file the
first time the split meets it, and remembered.

The server's split for word links leaves out exactly the same forms
(`phrases_of_common_words`, with the same hsk30 file the build pins), so a
link's underline still matches the hover highlight. Enforced by
`tests/lexicon/test_chinese.py` here and the server's word-link tests.

## Why

Measured on the real CC-CEDICT, jieba ranks and HSK lists (polyglotic-hq
359, 2026-11-15):
- **338's 100 FLEURS sentences:** 19 sentences split differently, every
  change examined: 中的 → 中 + 的 (4 times), 有的 kept, 研究人员 → 研究 +
  人员, 国家公园 → 国家 + 公园, 尤其是 → 尤其 + 是, 不是吗 → 不是 + 吗, 心目
  中的 → 心目中 + 的, 有了, 到了, 吃的, 并不, 有可能, 有意义, 上一个, 听不到,
  吃人, 和平条约. None reads worse. Unplaced links went from 32 to 12, links
  at 1,000 known words from 915 to 898 (of 2,064 and 2,076 words), with
  none inside the line.
- **CC-CEDICT:** 6,878 of its 53,819 unranked forms are left to their
  words (none of its 129,987 ranked forms split differently); 803 names,
  1 idiom and 62 HSK words that are two common words stay whole. The
  desktop and the server leave out the same 6,878, and split the 100
  sentences identically.

**Why 3,000:** at 5,000, 10,357 forms change, and 微表情 ("micro-
expression"; 微 is the 3,799th word) split into 微 + 表情 on FLEURS. Up to
3,000 the two words are ones a learner past the first levels knows, and
every FLEURS change was right. Rarer parts usually mean a coined term
(沧龙 "mosasaur": 沧 is the 21,810th), which stays whole.

**What it costs:** some real compounds whose parts are both common are
split (陈皮 "dried tangerine peel", 松塔 "pine cone", 元数据 "metadata";
polyglotic-hq 359's report lists 40 samples). A caption naming one is less likely than one where the two words
sit side by side, and both words still show their meanings.

Not taken: dropping the fewest-words rule for unranked words (a new split
for everything, and names would break); a list of bad phrases by hand
(thousands of them, never finished).

## What would make us reverse it

- Learners' lookups show a compound split that should be whole, often
  enough to matter: raise the bar (fewer, commoner parts) or keep that kind.
- A frequency source that ranks phrases as phrases replaces jieba's.

## How we'd reverse it

`_is_phrase` returning False (and the server's `phrases_of_common_words`
returning nothing) puts the split back as it was; `COMMON_PARTS` moves the
bar. No stored data depends on it: saved words keep their entry IDs.
