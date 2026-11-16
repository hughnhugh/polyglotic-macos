# 0144 A learning window of any size: unlimited, or a number the learner types

- **Status:** accepted (extends 0114)
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 351 (the user, 2026-11-15, trying
  the preview build: "There should be a learning window for unlimited and
  custom amount")

## Situation

Decision 0114 made the learning window the next N words past the known
line, N one of 100, 500, 1,000 or 2,000 (default 1,000), chosen per
language on Learning's card and kept in the settings as
`language_choices.<code>.window`, a whole number. The user wants two more
choices: no end at all, and a number of their own.

## Decision

- **Unlimited** (`levels.UNLIMITED`): the window has no end. Every word
  past the known line is in it, on either scale: ranked words however
  rare, and words with no place (no rank, no level) too. `LearningWindow.last`
  is None; `reaches` is true for every word, `holds` for every word the
  line doesn't know. The learner's own statuses still win.
- **Custom:** any whole number from `MIN_WINDOW` (10) to `MAX_WINDOW`
  (100,000), typed in a line under the choices on the card. Below 10 a
  caption would almost never meet a word in the window; 100,000 is past
  the end of every ranked list the packs carry (Chinese's 87,125 ranks,
  English's 57,023, French's 51,559, 2026-11-15), so a bigger number would
  point out nothing more - Unlimited is there for that. A number outside
  the bounds, typed or stored, is kept at the nearest bound; text that
  isn't a number leaves the window as it was.
- **Past a line kept as a level** (HSK, an English band - not offered on
  the card, but the choice is kept per language and the line can be one):
  any number, a size or the learner's own, is the next level, as 0114
  had it; Unlimited is every level above the line, and words the scheme
  leaves out.
- **Stored:** Unlimited as the string `"unlimited"`, a number as before.
  A version before 0144 read the window as a whole number of words or
  nothing chosen, so it reads `"unlimited"` as nothing chosen - its
  default 1,000 - not as an error; a custom number it reads as it is.
- **Only the captions' marks read the window** (`highlights`, through
  `caption_marks`). Word links "past what you know", the learning load's
  entry rule, coverage, Words' bands and Learning's counts all follow the
  known line or the learner's statuses, never the window (checked
  2026-11-15), so they need nothing new.

## Why

- A sentinel (`Unlimited`, one member) beside `int`, not `None` or `0`:
  `None` already means "not chosen" and `0` is a window of no words. Code
  that reads a size has to say what no end means, and mypy makes it.
- No end includes the unranked words because "unlimited" said plainly is
  every new word; with "common words only" (the default) the cap still
  holds a few a caption, rarest last, so they show only with "every new
  word". Alternative not taken: unlimited as "every ranked word" - it
  would leave the unranked as rarer under a choice called unlimited.
- A typed number rather than more preset sizes: the user asked for "custom
  amount", and the presets stay for the usual choices.

## What would make us reverse it

Learners choosing Unlimited and finding captions too busy with unranked
words (names the dictionary doesn't know as names, rare compounds); a
second client (the phone app) needing the window as one number.

## How we'd reverse it

Unranked words out of an unlimited window: one line in
`LearningWindow.reaches` and its tests. Unlimited as a number: store
`MAX_WINDOW` instead and read `"unlimited"` as it - `_window` in
`levels.py`, the card's choices, and `docs/rule-cases/levels.json`.
