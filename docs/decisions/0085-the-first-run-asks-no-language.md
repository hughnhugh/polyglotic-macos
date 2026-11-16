# 0085 The first run asks no language: the app opens for anyone, and the dictionary in use is a guess until one is chosen

- **Status:** accepted; replaces the language step of 0054
- **Date:** 2026-11-11
- **Decided by:** the user, 2026-11-11 ~23:15 ("I don't really like the
  setup screens that ask you to select chinese or english. Keep that in
  the main app configuration rather than a prerequisite step to entering
  the app. It makes it feel like the app is only for chinese / english"),
  built in polyglotic-hq 293. The guess and the defaults are Claude's
  reversible choices.

## Situation

The first run's first screen asked "Which language are you learning?"
with two answers, Chinese and English, because the app has a full
learner's dictionary for those two only (CC-CEDICT, ECDICT). The answer
picked the dictionary and the learning data, and an English learner's
"Translate into" became Chinese (062's option B). Closed without an
answer, Chinese ran and the screen came back at every start.

Every setting it fed already lives elsewhere: the language learned on
Learning (262), "Translate into" on Home's app rows and each caption
window, the spoken language in Settings > Captions, the interface's
language in Settings > App (decision 0034, Windows' by default).

## Decision

- **No language screen.** The run is the level (while it has none), Your
  data and the code (0054's order and Back are unchanged).
- **`learning` stays None until the learner chooses** on Learning (or a
  lookup's "Learn Chinese too?"); Learning says "None yet" until then.
- **The dictionary in use until then** (`core.learning.languages.
  starting_language`): English, unless Windows' first display language
  is English, then Chinese. Learning data kept on this PC for the other
  full dictionary, and none for the guess, keeps that one running - an
  install from before, where Chinese ran unanswered, keeps its words in
  view.
- **New settings** (nothing saved yet) translate into the first of
  Windows' display languages that captions are translated into, else
  English (`ui_next.languages.own_targets`). Saved settings are never
  changed. The spoken language stays Detect; the interface stays
  Windows' where we have it (0034).
- **Home's sample** is in the language learned, or the running
  dictionary's until one is chosen.
- `ui.learning_language` (the dialog) and main's `ENGLISH_LEARNERS_TARGETS`
  are deleted; the codes with a full dictionary are core's `FULL`.

### The level, too (a separate pull request, to take back on its own)

- **No level screen either** (Claude's default; the user was asked and
  hasn't answered): the first run is Your data and the code.
- **Words are estimated at a middle level until the learner sets theirs**
  (`core.learning.levels.STARTING_LEVEL`, 3: HSK 3, or the 3,000 most
  common English words) - in memory, never saved: the learner's level is
  still None, and Learning and Words say "Not set yet".
- **Home has one quiet line** under the state - "Set your level so we know
  which words to explain", Set your level and Not now - until the level is
  set or Not now is pressed (`level_line_dismissed`, kept), and only
  while there's a level to set - not for a learner of languages with no
  levels. Set your level
  opens the level picker when the language learned is the one in use, else
  Learning, where a language is chosen first.
- To take it back: revert that pull request's commit; the level step
  returns as it was.

## Why

- The question made the app look like a Chinese-English product to anyone
  else, before they had seen a caption - and the answer mattered only to
  lookups, which the learner meets later and can change then.
- The guess is right for the two groups the dictionaries serve (English
  speakers learning Chinese, Chinese speakers learning English) and for
  most others (English is the most learned language), and costs nothing
  when it's wrong: captions and translation don't depend on it, and a
  lookup in a language without a dictionary says so.
- Not saving the guess keeps Learning honest ("None yet") and lets the
  first real choice be the learner's.

Not taken: asking the language on first lookup (a question in the middle
of a game); saving the guess as the language learned (Learning would
claim a choice nobody made); inferring it from the captions heard (needs
the restart a dictionary change takes today - worth it once Words keeps
several languages at once, 265).

## What would make us reverse it

- Testers who learn Chinese on a non-English PC (or English on an English
  one) finding the wrong dictionary and not finding Learning.
- Words keeping a section per language (265): then the guess goes, and
  every full dictionary runs at once.

## How we'd reverse it

- To ask again: restore `ui/learning_language.py` from before this
  record and its step in `main.first_run`'s list (one `Step`); `run`
  doesn't care what the steps are.
- To change the guess: `starting_language`, one function with its tests
  in `tests/learning/test_learning_languages.py`.
- To change the new-settings default: the four lines at the top of
  `main.first_run`.
