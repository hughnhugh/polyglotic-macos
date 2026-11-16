# 0133 A full dictionary for every language pair is a pack plus riders: meanings in the learner's language, and words recorded ahead of time

- **Status:** proposed (the build is in polyglotic-hq project 341's pull requests; the user decides the order of languages, the privacy wording and every upload)
- **Date:** 2026-11-15
- **Decided by:** the user asked for it (2026-11-15: "full dictionaries with TTS for each of them"; then: no Google, nothing charged, nothing that needs a card; no extra VRAM on the live server while testers use it); the design is project 341's, in its report

## Situation

A learner of any language, reading in any language, should get a
dictionary entry with meanings they can read and hear the word said. Today
a pack (decision 0122) has meanings in English, some in Chinese by a
second copy of the whole pack; a word is said only if Windows has a voice
for its language, which most PCs lack for most languages.

Forty languages times forty interface languages is 1,600 pairs: no pair
can be a file built by hand, and a pack copied once per meanings language
(the `-zh` packs) grows the storage and every update by the number of
languages.

## Decision

**A pair is one pack plus riders.** The pack stays as it is (format 1,
meanings in English from the English Wiktionary's extract, kaikki.org).
Beside it, small files that go with it:

- **Meanings files** (`<dictionary>-<language>.meanings`,
  `adapters.meanings_file`): the pack's entries' meanings in one more
  language, by entry ID. Each entry's meanings are either **human-made**
  (taken from that language's own Wiktionary extract, where it has the
  word) or **machine-made** (the pack's English meanings translated by a
  translation model we run ourselves - today Hy-MT2, Apache-2.0), and the
  file says which. The card shows a machine-made meaning labelled
  "Machine translation of:" with the pack's own meaning beneath it, so a
  wrong one can be seen to be wrong. An entry the file lacks shows the
  pack's meaning, as before (326's order: the learner's language, else
  English).
- **Audio files** (`<dictionary>.audio`, `adapters.audio_file`): the
  pack's commonest words (10,000 to start), each said alone, generated
  ahead of time by an open speech model we run ourselves whose licence
  and whose voice's training data allow commercial use (today Kokoro-82M,
  Apache-2.0; `tools.dictionaries.audio.VOICES` names each), stored as Ogg
  Opus with the stream's shared header kept once. About 2 to 2.5 kB a
  word.

**No outside speech or translation service.** Nothing is sent to Google or
any service that charges or needs a card, at build time or from the app.
The live server is not asked to speak: no word leaves the PC to be said,
and the server's GPU holds nothing new.

**Who says a word, in order:** our recording of it; else a Windows voice
of the language (also when the learner asks for it slower: a recording
slowed drops in pitch); else nothing, and the card says so. A card opened
with nothing to say its word is counted by language - a language code and
a number, with the usage statistics and only with consent
(`cards_without_voice_counted`) - so the languages that need recordings
show up. The word itself stays on the PC.

**Delivery.** Riders are named inside their pack's entry in the signed
list (`riders`), which an app from before them doesn't read: 0.1.5 takes
the pack as it always did. An app fetches the riders it reads and wants -
the recordings, and the meanings in the interface's language - quietly
after the pack, checked against the list as the pack is; one that fails
never fails the pack and is tried again with the daily check. They are
deleted with their pack.

**"Full" means full content here**, not the app's full tier
(`core.learning.languages.FULL`: coverage, levels, the learning load).
Promoting a pack language to that tier is its own project.

## Why

- A rider per language is small (a meanings file is a few MB; an audio
  file about 25 MB for 10,000 words) and a learner downloads only theirs:
  the storage grows by languages added, not multiplied.
- Human-made meanings exist for the common pairs (kaikki.org publishes 20
  Wiktionary editions); machine-made ones fill the rest, labelled. A small
  trial showed real errors in Vietnamese (avocado given as eggplant), so
  the label and the English beneath are part of the design, not polish.
- Generated ahead of time costs nothing per lookup, works offline, and
  keeps the lookup private; generating on request on the server would
  send each looked-up word to it and take VRAM testers' captions need.
- Not taken: Google's speech (the user: no charges, no card); MMS-TTS
  (CC BY-NC); espeak-ng in the app (GPL-3.0; it runs only at build time,
  as Kokoro's text-to-phoneme step); one pack copy per meanings language
  (the `-zh` copies, to be retired into riders).

## What would make us reverse it

- Machine-made meanings measured against the human-made ones turn out
  wrong too often to show even labelled: then English only until a better
  translator, for the pairs with no human-made source.
- The recordings' quality fails the recogniser's listening check for a
  language (a word said and not recognised as itself): that language
  waits for a better open voice and falls back to Windows' voices.
- A speech model small enough to ship in the app, with licences as clean,
  would replace audio files for every word rather than the commonest.
