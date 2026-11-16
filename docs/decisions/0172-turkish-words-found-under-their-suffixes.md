# 0172 Turkish words found under their suffixes, by rules in the app

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, for polyglotic-hq project 388 (DECISIONS #175:
  every language paired with English, by popularity). Reversible.

## Situation

Turkish builds a word from a stem and a row of suffixes (evlerimizde: ev +
ler + imiz + de, "in our houses"). Wiktionary's tables list about a hundred
forms of each noun and nine hundred of each verb, but no participles,
verbal nouns, passives or "can", and no case after them. The installed app
has no simplemma (decision 0123), so 380's Turkish pack found 79-80 % of
the probe's words there (92 % from source) and was held back. Two of
Wiktionary's habits made it worse: a causative or verbal noun with its own
meaning ("araştırmak: causative of araşmak: to research") was read as a
form of its base, so "araştırmalar" (research) showed "to call each
other"; and Python's lower case of İ is i with a combining dot, which no
frequency list writes, so İngiltere and İngilizce had no rank and were cut.

## Decision

- **The app guesses the suffixes off** (`core.lexicon.turkish.bases`):
  rules of its own - the suffixes in Turkish's order (copula, tense,
  negation and "can", voice, participles and verbal nouns, case,
  possessive, plural, derivations), the buffer letters (y, n, s after a
  vowel only), a stem's b/c/d/ğ written p/ç/t/k, a lost high vowel put
  back, and a stem tried with the â dictionaries write after k, g and l
  (imkanı: imkân). Stems come out the least cut off first; a verb's as its
  infinitive only. They are guesses (decision 0168): tried only when the
  pack hasn't got the word, the first the pack has is shown.
- **Names:** a word with an apostrophe is a name with its suffixes after
  it; a capitalised word inside a sentence is a name too. Either is cut
  only at a compound name's possessive or plural (Okyanusu, Devletler),
  never further (`name_bases`, `spaced_split.NAMES`).
- **Turkish lower case** (I is ı, İ is i) is a guess before the rest.
- **The reader** (`kaikki.read_language`'s `derived`, Turkish's
  `Spelling`): a causative, passive, reciprocal, reflexive, verbal noun
  or diminutive whose gloss says what it means is a word of its own.
  For every pack, a word's frequency is also looked up with İ's combining
  dot taken off (`packs.listed`).
- **Its own split, `turkish`** (`publish_packs.SPLITS`, `main.pack_reader`):
  an app from before would find a fifth of Turkish's words in no
  dictionary, so it is never offered the pack. An app with `turkish` has
  `clitics` and `marks`.

## Why

- Measured on the pinned sources (polyglotic-hq 388): the probe 93.4 %
  in the installed app (was 78.8 %), above the 90 % floor; on 229 FLEURS
  sentences the probe never saw, 3.4 % of the distinct words found by
  guesses were wrong and another 3.4 % found a related word (bağıntı,
  correlation, as bağ, a tie). simplemma's own Turkish lemmas err too
  (kaynatmak: kayna, bildirilen: bil).
- A form table generated at build time for every lemma would be millions
  of forms (the pack is already 37 MB with Wiktionary's 1.2 million).
  Choosing among guesses by frequency at build time was tried and was
  worse: it cut ilçe to il and bina to bin.
- Zemberek (Apache-2.0) is the full analyser, but it is Java with a large
  lexicon; these rules are a few hundred lines of Python and need nothing
  installed.

## What would make us reverse it

Learners or a native reader finding wrong lookups often; a Turkish
analyser that runs in the installed app at a reasonable size.

## How we'd reverse it

Drop "tr" from `spaced_split.CLITICS` and `NAMES` (and the pack's split
back to `spaced` for a pack without guesses), or put an analyser behind
the same `bases` call. The reader's `derived` is one argument; the İ rule
one line.
