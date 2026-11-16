# 0174 A word a pack hasn't got is looked up by its parts

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude, for polyglotic-hq project 390 (380's report: on
  real German captions, Blog-Erfahrung, T-Rex and Internetmaterialien
  were word links with no word under them). Reversible.

## Situation

A spaced language's word split keeps a hyphenated word whole, and German
writes compounds closed up, often with a linking letter (Arbeitsplatz:
Arbeit + s + Platz). No dictionary lists every compound. A word a basic
pack hasn't got was "Not in the dictionary": its link showed, with no
word found under it, and the card had nothing to give.

## Decision

- **Where:** `core.lexicon.compounds` finds a word's parts; a basic
  dictionary asks for them only when nothing else finds the word
  (`BasicDictionary.parts`). A word the pack has whole is never cut.
- **How:** a hyphenated word is cut at its hyphens, in any language. A
  piece the pack hasn't got is shown as not in it, and German cuts that
  piece again. A German closed compound is cut only where every part is
  a word the pack has, and no part is a name. A part has three letters
  at least, and the cut has four parts at most. A part is no name and no
  small word (an article, pronoun, determiner or conjunction: not
  schreien + den). A part cut short has four letters at least as written
  (Schul for Schule, not Bod for Boden). A present participle whose
  infinitive the pack has (schreienden) isn't cut at all. The linking letters
  (`LINKS`) belong to the part before. The fewest parts win, then the
  commonest by mean log rank (Koehn and Knight, 2003). A part in lower
  case is looked up as a noun first.
- **The card:** it says the word isn't in the dictionary as a whole and
  gives the parts' first meanings joined ("Internet + material"). It
  reuses the Chinese card's strings, so there are no new ones to
  translate. Pinned, it lists each part, which a click looks up.
- **Links:** a caption's words (`words_in`) are the parts, each over its
  own letters. So a link over a compound is known only when every part
  is known, and hearing it counts as hearing its parts.

## Why

- A learner who knows Internet and Material can read Internetmaterialien.
  The card says honestly that the whole isn't there, and doesn't pass a
  part off as the word.
- In core, the rule is plain Python over the pack's lookups (the
  `compounds.Find` callable), testable without Qt or a file.

## What would make us reverse it, and how

- **Wrong cuts** that mislead, found by a native reader or on captions.
  Raise `MIN_PART`, require ranked parts, or drop closed compounds and
  keep hyphens. Each is a constant or one function in `compounds`.
- **Counting a compound's parts as heard** might skew what the learner
  is shown as known. If so, `words_in` can drop the parts (keep the card).
- **A pack with its own compound table** (a full German dictionary)
  would make this a fallback only, as it already is.
