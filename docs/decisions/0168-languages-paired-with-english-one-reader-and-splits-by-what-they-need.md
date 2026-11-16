# 0168 Languages paired with English: one Wiktionary reader, and word splits named by what they need

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, for polyglotic-hq project 380 (DECISIONS #175:
  "pair everything to english to start", then by popularity). Reversible.

## Situation

Each basic pack had its own reader (Spanish, Russian, Vietnamese, French in
#649). The first batch paired with English is seven more spaced languages
(German, Portuguese, Italian, Indonesian, Arabic, Hindi, Polish), with
more to come. Most read the same way; a few need rules where captions and
Wiktionary write a word differently:

- Hindi's vowel signs and Arabic's vowel marks are combining marks, which
  Python's `\w` hasn't got: the letter split cut "हिंदी" into ह, द.
- Arabic writes "and", "the", "with" and its pronouns onto a word
  (والكتاب); its inflection tables mark every vowel, captions none.
- Italian elides as French does (dell'anno).
- Indonesian and Hindi have regular endings and affixes that Wiktionary
  doesn't list as forms, and the installed app has no simplemma
  (decision 0123): Indonesian was 88.7 % of the probe's words without it.

## Decision

- **One reader** (`tools.dictionaries.packs.read_wiktionary`): a new
  spaced language is a `wiktionary_pack` config - its kaikki source, its
  title, and a `Spelling` where captions write forms differently (Arabic's
  forms without vowel marks; German's nouns' capitals are spelling, not a
  name's; a reading by romanization for Arabic and Hindi). English
  meanings only.
- **Ranks and entries** (`packs.frequencies`, `kaikki.read_language`;
  each was junk in a built pack's top words, or a common word missing):
  - a form of several words is shared by how common each is (Italian's
    "sono" had made suonare a top-25 word; Portuguese's "no", wrongly a
    comparative in two adjectives' tables, austro-húngaro the 12th);
  - a word that is only a name and also another word's form gives that
    word the frequency (Hindi's गया, Gaya and "went"; Arabic's الأرض);
  - German's nouns take their lower-case frequency where their own
    declension shows they are the word in use (wordfreq is in lower case:
    "menschen" says Mensch is, so it isn't the rare pronoun mensch; the
    noun Ich, the ego, has no forms in use, so ich stays I);
  - a hyphenated word wordfreq hasn't got whole is ten times rarer than
    the phrase of its parts (`JOINED`, wordfreq's own factor for words it
    joins): Portuguese's tem-tem had been its 69th word, Indonesian's
    ada-ada its 28th;
  - a form-of sense whose target is a phrase is a meaning (Italian's
    "della", "contraction of di la").
  - a word is looked up in a list as the list folds it too: wordfreq
    folds ß to ss, so German's Straße, heißen and gleichermaßen had no
    rank and were cut.
  The name, phrase and hyphen rules hold for every Wiktionary pack, so
  Spanish's, Russian's and French's change at their next build (the
  hyphen rule not Russian's: its subtitles' list already gives a
  hyphenated word a floor); the share holds only
  for the reader's languages (French and the batch): Spanish's and
  Russian's keep the whole form to each lemma until their ranks are
  measured again.
- **A pack's name is what the pack says is one** (`core.lexicon.basic`):
  every meaning "(name) ...", not a capitalised headword as English's
  rule has it. German capitalises every noun: on real captions 41 of 74
  German links were counted as names, which are never pointed out as new
  nor counted as heard; 2 after.
- **A word keeps the marks its letters carry** (`core.lexicon.english.words`,
  used by every spaced split).
- **Clitics and regular endings are guesses** (`adapters.spaced_split.CLITICS`):
  tried only when the pack hasn't got the word, so a word the pack has
  whole is never cut (وزير is minister, not و + زير). The lookup takes
  **the first guess that finds anything** (`core.lexicon.basic`), so
  guesses are written likeliest first.
- **Splits are named by what an app must have** (`publish_packs.SPLITS`,
  `main.pack_reader`): `marks` (Hindi), `clitics` (Arabic, Indonesian;
  an app with it has `marks`), `elided` (French, Italian). German,
  Portuguese and Polish stay `spaced`: an app from before reads them
  right.

## Why

- A config per language keeps the next batch (Chinese- and
  Spanish-paired, then more) to data and rules, not modules.
- Guesses, not cuts: the caption still shows the word as written, and a
  wrong guess only costs a lookup that finds nothing.
- Named splits: an app from before would cut Hindi wrongly and miss most
  Arabic words; the list keeps those packs from it (decision 0122's
  `Reader.splits`).

## What would make us reverse it, and how

- A language whose reading can't be a config (a script without spaces, a
  morphology guesses can't reach - Turkish was 79.7 % without simplemma):
  it gets a reader or a split of its own, as Japanese and Vietnamese have.
- Guesses that find wrong entries often enough to mislead (a native
  reader's check would show it): drop that language's guesses, or ship a
  form table built at build time instead.
- simplemma (or another analyser) in the installed app: the guesses for
  Indonesian and Hindi could go; the split names stay.
