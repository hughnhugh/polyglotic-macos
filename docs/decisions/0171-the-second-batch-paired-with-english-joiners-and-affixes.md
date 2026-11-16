# 0171 The second batch paired with English: Persian's joiners, the affixes guessed, and a pack's own sentences in its ranks

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, for polyglotic-hq project 387 (DECISIONS #175:
  every language paired with English first, then by popularity). It builds
  on decision 0168, which it doesn't replace. Reversible.

## Situation

The second batch is twelve spaced languages: Dutch, Ukrainian, Persian,
Swedish, Czech, Romanian, Greek, Hungarian, Danish, Finnish, Filipino and
Macedonian. Each was built through decision 0168's reader and probed in
the installed app (no simplemma, decision 0123). The probe's floor is 90 %.

- **Read as French's is:** Dutch, Swedish, Romanian and Macedonian passed
  as they were.
- **Ukrainian:** its inflection tables mark the stress (яка́) and captions
  don't, so it found 54.8 % of the probe's words.
- **Persian:**
  - It writes plurals and the present's prefix on with a zero-width
    non-joiner (داستان‌های, می‌کنم). The letter split cut words there, so
    "های" became a word of its own (36 of the probe's misses).
  - Its tables mark vowels, as Arabic's do.
  - Wiktionary gives the classical romanization first (kitāb). Captions
    are Iran's Persian (ketâb).
  - polyglotic-hq 374 measured that its ranks are better from wordfreq
    averaged with Common Voice's sentences than from wordfreq alone.
- **Filipino:**
  - Its linker is written onto the word (isang is isa + ng; noong is
    noon + g), and verbs take prefixes, infixes and a doubled syllable.
    It found 77.1 %.
  - The name Isang (a diminutive of Isabel) had taken isang's frequency
    and was the pack's 8th word.
  - The app calls it "tl", and wordfreq calls it "fil".
- **Czech and Greek:** 89.8 % each.
  - Czech's negative ne- and superlative nej- aren't in its tables.
  - Greek's present tense lives on separate pages, which kaikki doesn't
    read into the tables.
- **Danish, Hungarian and Finnish** stay below the floor, or can't be
  built, without work outside this decision. polyglotic-hq 387's report
  says what each needs.

## Decision

- **Spellings (`packs.Spelling`):**
  - `STRESSED`, for Ukrainian: forms are read without their stress marks,
    and the reading is the headword with its stress, as Russian's pack has
    it.
  - `PERSIAN`: forms are read without vowel marks, and the reading is
    Iran's romanization (the first one written with â).
  - `FILIPINO`: every word with the linker on it becomes a form of that
    word (`linked_forms`). This leaves alone a spelling that is already a
    word or a form of one ("kung").
- **A word keeps its zero-width non-joiner or joiner** between letters
  (`core.lexicon.english.words`), in every spaced language. Nothing else
  writes one inside a word.
- **More guesses** (`adapters.spaced_split.CLITICS`), tried only when the
  pack hasn't got the word itself, as in 0168:
  - **Persian:** Persian's yeh and kaf for Arabic's; the present's prefix;
    the plural, comparative, possessive and ezafe endings, each with or
    without the joiner.
  - **Filipino:** the linker; prefixes, the -in- and -um- infixes, a
    doubled first syllable, suffixes.
  - **Czech:** ne- and nej- (at least three letters must be left, so
    "není" isn't read as ní, "her").
  - **Greek:** the present's endings (διαθέτουν: διαθέτω) and a feminine's
    genitive in -ής or -ας. A genitive in -ου isn't guessed, because its
    accent moves.
- **New split names** (`publish_packs.SPLITS`, `main.pack_reader`):
  - `joiners` (Persian): an app from before would cut its words at the
    joiner.
  - `affixes` (Filipino, Czech, Greek): an app from before 387 finds their
    words only below the floor.
  - Dutch, Swedish, Ukrainian, Romanian and Macedonian stay `spaced`, so
    a 0.1.5 app is offered them.
- **A pack's own sentences can join its ranks** (`wiktionary_pack(...,
  sentences=)`): the reader counts each word as the app's split finds it
  (`frequency.sentences_counted`), and the count is averaged with
  wordfreq's. Persian's pack uses Common Voice's Sentence Collector file
  (CC0), pinned to one commit.
- **A language's wordfreq code** can differ from the app's
  (`wordfreq_ranks.CODES`: "tl" is "fil"). `rank_check` reads Filipino as
  written in Latin under either code.

## Why

- These stay configs and rules, not modules: 0168's aim.
- Guesses can't cut a word the pack has. A wrong guess costs a lookup
  that finds nothing, or a near word.
- A form at build time (Filipino's linker) does more than a guess. The
  word takes the form's frequency, and a name spelled the same gives way
  under 0168's rule.
- The split names follow 0168: a pack is offered only to an app that
  reads it right.

## What would make us reverse it, and how

- **A native reader finds that the guesses mislead** (Filipino's are the
  broadest): drop that language's entry in `CLITICS`. Its pack then needs
  a form table built at build time instead.
- **Common Voice's sentences turn out not to be CC0** (the README says
  "the majority" of `server/data`, while the Sentence Collector's file is
  all CC0): take `sentences=` off Persian's pack and rebuild.
- **An analyser ships in the app** (simplemma or another): the guesses
  could go. The split names stay, as 0168 says.
