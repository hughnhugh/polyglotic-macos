# 0062 The languages being learned are a list; one full dictionary's learning data runs at a time

- **Status:** accepted; its "one full dictionary runs at a time" replaced by
  [0095](0095-every-full-language-learned-is-open-at-once.md) (2026-11-14)
- **Date:** 2026-11-09
- **Decided by:** Claude, for polyglotic-hq project 262 (248's IA.md
  section 3, answered "Q2 A, Q3 A" by the user on 2026-11-09: "Go with
  all your safe defaults"; DECISIONS.md #65: "You're learning becomes a
  list"). Reversible - a technical choice. (Numbered 0062, not the next
  free number, because 261, 263 and 267 were adding records beside it.)

## Situation

"You're learning" was one choice, Chinese or English, on Home's
Languages panel: it picked the dictionary and the learning data the app
builds at the start (`main.learner_tools`), and a change applied at the
next start. #65 makes it a list - any caption language, in tiers (full,
basic, none yet) - and the lookup asks "Learn Japanese too?". But
everything that uses Learning - the caption windows' marks, the lookup
card, Words, the sync - takes one `LearningTools`, built for one full
dictionary. Running several at once is Words per language's work
(polyglotic-hq 265), not this page's.

## Decision

- **The domain keeps the list** (`core.learning.languages`): the main
  language (`main`, whose learning data runs), the others in the order
  added (`also`), and those a lookup asked about and was told "Not now"
  (`not_now`); each caption language's tier; switching, stopping and the
  lookup's offer as rules on it.
- **The settings keep it as three keys:** `learning` as it was (the main
  language - an older version reads it unchanged), `also_learning` and
  `not_now_learning` beside it (an older version keeps them as keys it
  doesn't know).
- **One full dictionary runs at a time.** Another full one on the list
  can be used instead from the next start ("Use English instead"), and
  keeps its words; both cards say so until then. Basic and no-dictionary
  languages are on the list for what they can do now, said on their cards
  (lookups, marked basic, when the pack is on the PC; nothing yet
  otherwise).
- **Word introductions** (Off · A few per caption · Every new word) are
  `core.learning.highlights.WordIntroductions`, kept as `marks_off`
  beside `common_words_only`, so an older version still has the learner's
  cap.

## What would make us reverse it

Words per language (265) or the first run's deferral (266) needing
several full dictionaries running at once - which this makes the next
step, not a reversal: `cards(..., running)` takes a set of running
languages, the "Use X instead" button goes, and `main` builds a
`LearningTools` per full language on the list.

## How we'd reverse it

Back to one choice: read `learning` alone (it never stopped being the
main language), ignore the two newer keys, and put the Segmented back on
Learning's card. Nothing is migrated, so nothing has to be undone.
