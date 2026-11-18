# 0211 An English word's meanings are in English unless the app is in Chinese

- **Status:** accepted (the delivery, in the installer, is Claude's
  reversible choice; the user may prefer a download - polyglotic-hq 447's
  report)
- **Date:** 2026-11-17
- **Decided by:** the user asked for it (2026-11-17: "implement english
  dictionary in english? only display the chinese if the app main
  language is set to chinese"); the design is polyglotic-hq 447's

## Situation

The English learner's dictionary is ECDICT (decision 0009): its meanings
are Chinese, written for Chinese speakers. Polyglotic's interface has 21
languages, and a Spanish, Vietnamese or English-speaking learner of
English can't read them. The packs already pick their meanings language
by the interface's (`main.pack_meanings`: Chinese for a Chinese
interface, else English).

Saved words, statuses, exposures, Anki notes and the server's copy all
name ECDICT's entry IDs (`ecdict:...`, decision 0007), so English
meanings can't come from a different dictionary with entries of its own.

## Decision

- **A second file, `ecdict-en.sqlite`,** built with `ecdict.sqlite`
  (`tools.dictionaries.build`): the same entries, IDs, readings,
  inflections and ranks, its meanings in English
  (`tools.dictionaries.english_meanings`), from the first of:
  1. **our own** short definitions (`english_core.txt`, 170 words)
     for the words WordNet has nothing for (the, of, you, because) or a
     wrong first sense (can: a tin; he: helium; like: no preposition);
  2. **Open English WordNet** (the 2025 "plus" edition, CC BY 4.0): its
     senses, the part of speech English uses the word as most first -
     counted in UD English-EWT (counts only) - each part of speech's
     senses in WordNet's order, a second common part of speech's first
     sense among the card's three; definitions cut at their first "; ";
     the first sense with a short WordNet example that uses the word;
  3. for an inflected form's own entry, what it is a form of ("past
     tense of be").
  Each meaning starts with its part of speech, as the packs' do.
- **The app** (`main.learner_dictionary_file`) opens `ecdict-en.sqlite`
  for an English learner unless the interface's meanings language is
  Chinese, and `ecdict.sqlite` then - or when the English file isn't
  there (an older build). The interface's language is read at the start,
  as it already is for the packs; a change takes effect at the next start.
- **It ships in the installer** beside the other two (5.2 MB gzipped,
  11.9 MB on disk), like `ecdict.sqlite`. No download, no pack list entry,
  nothing new leaves the PC.

## Why

- The same IDs keep everything a learner has: a word saved with Chinese
  meanings is the same word with English ones, and switching the
  interface's language switches the meanings, nothing else.
- Open English WordNet is CC BY 4.0, so its definitions can be shipped in
  a paid app with credit. Wiktionary's English definitions are better
  written but CC BY-SA 4.0; this file is CC BY-SA 4.0 anyway (wordfreq's
  ranks are), and share-alike reaches the data file, not the app that
  reads it (as for every pack), so Wiktionary stays an option for later.
- In the installer: every English learner not on a Chinese interface needs
  it at their first card; a download would show Chinese until it arrived,
  and needs a new rider kind on the built-in dictionary (decision 0197's
  `built_in` entry carries recordings only). 5 MB is about 3 % of the
  installer.
- Not taken: one file with both languages' meanings (a format change for
  a file every build reads); translating ECDICT's Chinese into English (a
  translation of a translation).

## What would make us reverse it

- The installer's size matters more than a first card in English: then
  `ecdict-en.sqlite` becomes a download (a `meanings` rider on decision
  0197's `built_in` entry for `ecdict`); `learner_dictionary_file` already
  falls back to Chinese until it is there.
- Learners find WordNet's definitions too hard: then Wiktionary's English
  definitions (CC BY-SA, ordered the same way), or more of our own.

## How we'd reverse it

Drop `ecdict-en.sqlite` from `tools/package/build.py`'s
`DICTIONARY_FILES` and `learner_dictionary_file` falls back to the Chinese
meanings: a line each. Its build is separate from `ecdict.sqlite`'s
(`build.english_records`), so it can be dropped or replaced alone.
