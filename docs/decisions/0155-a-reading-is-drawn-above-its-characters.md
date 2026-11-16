# 0155 A reading is drawn above its characters, and isn't part of the text

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** the user, 2026-11-15 ~23:40, on polyglotic-hq project
  364's wireframes ("The pinyin looks fine"; polyglotic-hq DECISIONS.md
  #174 and #175: above each character, with "only past what I know" as a
  choice); built by polyglotic-hq project 369

## Situation

A learner of Chinese can't say a character they don't know. The user asked
for pinyin, and for a design that also fits other scripts ("each
translation or caption line should have a pinyin/chunom/alternate written
line to toggle for the particular language", 2026-11-15). Captions are
laid out by several paths (rows, run-on, lined-up), each with its own
measuring, hit-testing, word links and arrows; a reading mustn't disturb
any of them.

## Decision

- A **reading** is a span of a text and what to draw above it
  (`core/lexicon/readings.py`). It comes from a `Readings` source given a
  text and its language; the Chinese one is the dictionary on the PC
  (`ChineseDictionary.readings`): each character read by the word it is
  in, in citation tones (no 一/不 sandhi, as dictionaries print them).
- A reading is **drawn above its own characters**, centred, in the row's
  colour, in a band of room above the line (`ui_next/reading_lines.py`).
  It is never inserted into the text: offsets, selection, copying,
  lookups, links, the transcript and exports don't know it exists.
- The layout learns of a reading only as **room**: extra width beside a
  character whose reading is wider, and a band above a line
  (`views/flow.py`'s `Above`). Every layout path takes the same room. A
  reading may reach over a neighbour's room where that one's reading is
  narrower, so characters keep their own spacing where they can.
- A language's lines **keep the band** whether a line has a reading or
  not, so text doesn't move when readings arrive.
- The switch is **per language**, for caption and translation alike
  ("Pinyin above Chinese" in Settings > Look, off by default), with a
  size (Small or Medium, a share of the text's) and, as a choice, readings
  only over the words past what the learner knows (decision 0130's line).
  A learner with Chinese's dictionary hears of it once, on the caption
  window's notice line.
- Not built: tone colours (kept as an idea: five more colours in a window
  whose colours already mean something), today's poured fills without the
  New layout (the Lab's), furigana and other languages' readings.

## Why

- Offsets staying true is what keeps lookups and links right; a line of
  pinyin *in* the text would need every consumer to learn to skip it.
- Above each character is what learners' books and the tools they know do
  (ruby), and it survives wrapping: a reading wraps with its character.
- Not taken: a separate line under the row (matching by counting, a line
  more per caption); joined per-word pinyin (a character's own syllable
  is lost); a server-made reading (a protocol change, and the dictionary
  on the PC measures 99.7 % on unseen FLEURS text, 364).

## What would make us reverse it

- Learners turning it off because captions get too tall or too wide.
- A language whose reading can't sit over single characters or words (a
  whole-sentence romanisation): that one would want the line under the
  row.
- Accuracy in real captions well below what FLEURS text showed.

## How we'd reverse it

The setting off is today's layout exactly (tests hold it), so turning the
feature off for everyone is the setting's default; removing it is
`reading_lines.py`, the `Above` room in `views/flow.py` and the style's
`reading_lines`, none of which the text, lookups or links depend on.
