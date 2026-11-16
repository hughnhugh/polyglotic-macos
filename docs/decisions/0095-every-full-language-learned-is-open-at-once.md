# 0095 Every full language learned is open at once, each line in its own; each keeps its own learning data and categories

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** Claude, for polyglotic-hq project 306 (DECISIONS #110,
  the user, 2026-11-11: "before sales open: every added language's
  dictionary active at once on both caption lines; words saved from
  either line"; #122's order). Reversible - a technical choice. Replaces
  0062's "one full dictionary runs at a time"; the rest of 0062 stands.

## Situation

0062 made the languages being learned a list but ran one full
dictionary's learning data at a time: `main.learner_tools` built one
`LearningTools` (CC-CEDICT or ECDICT, and one `Vocabulary`) for the main
language, and every view - the caption windows' marks, the lookup card,
Words, the caption feed's counting - took that one. With Chinese and
English both learned, a word on the other language's line was looked up
in the wrong dictionary ("Chinese for it" on an English line), never
marked, never counted, and couldn't be saved; Words had a section per
language (250) with only ever one in it. Each full language already had
its own learning data file (`learning.sqlite`, `learning-en.sqlite`).

## Decision

- **Every full language learned is open at once** (`core.learning.languages.open_beside`):
  as the app starts - just after its window's first paint, so reading a
  second learning data file (about 60 ms at 10,000 words met) never
  delays the window - and again as one is added during the run
  (Learning's "Learn it", a lookup's "Learn it too"), `main.tools_beside` builds a
  `LearningTools` for each full language on the list not open yet - its
  own dictionary, its own learning data file, opened exactly as the main
  one's - and hangs it on the main one (`LearningTools.learn_beside`,
  `also`). One whose learning data is from a newer app stays closed (it
  would stop a start for the main language); one stopped during the run
  closes at the next start.
- **A line goes to its own language's tools** (`LearningTools.of`): the
  lookup (hover, click, pin, a dragged phrase, its word split), the marks
  on both lines, the caption feed's counting and listening time, and
  saving all ask the main tools for the line's language's. A basic
  dictionary's line, a language not learned and a line of unknown
  language stay with the main tools, as before ("Learn it too?" for one
  with a dictionary).
- **Views connect to the main tools alone:** another language's
  `changed` and `dictionary_ready` come out of the main one's; `ready`
  waits for every word split.
- **Each language keeps its own learning data, categories included.**
  A word is saved, put in the deck or marked known in its own language's
  file, with that file's categories; a category made from an English word
  is English's. Nothing is copied, merged or moved between files, so
  nothing can be lost by it. Each language has its own level, Words
  section and Anki export.
- **The main language** stays: Words' first section, Home's sample and
  level line, and the one the server's learning sync brings in
  (`DataExchange` keeps one dictionary's cursor). Every open language's
  changes and exposure days go out. Learning's "Make X your main
  language" changes it from the next start.
- **One dictionary out, or one learning data file set aside, leaves the
  other working:** each `LearningTools` has its own `dictionary_problem`
  and set-aside file; the lookup card says so on that language's lines,
  and Home's banner names it.
- **Deleting on this PC covers every open language** (DECISIONS #135,
  the user, 2026-11-14): Account's "Also delete it from this PC" empties
  each open language's file and deletes the copies set aside from each,
  as 207 and 213 do for one. A store that can't be emptied, or a copy
  that can't be deleted, says so for its own language (Home names it);
  the others are deleted all the same.

## Why

- It is the smallest change that makes both lines work: the per-language
  files, the per-language Words sections and `LearningTools` itself
  already existed; what was missing was routing by the line's language.
- One `of(language)` route keeps the views' interface (`Learner`) as it
  was, so the caption windows, transcripts and the lookup card changed
  in a few lines each.
- Shared categories across files were the alternative: they need a
  merge rule for names, colours, order and deletions, and a place to keep
  them, and a wrong merge loses a learner's organisation. Per-file
  categories can't lose anything and can be shared later by copying.
- A single `Vocabulary` over both dictionaries (one file) was the other
  alternative: a migration of every learner's data, and a level, bands
  and coverage that mean nothing across two languages.

## What would make us reverse it

- Learners wanting one set of categories across languages (then copy
  categories between files, as a later step - this needn't be reversed).
- A third full dictionary (Japanese, Russian as full languages) making
  start time or memory too large to open every one at the start (then
  open each on its first line, not at the start).
- The server's sync for the second language (one `DataExchange` follows
  one dictionary) proving to matter before it's extended.

## How we'd reverse it

Open only the main language's tools again: drop `tools_beside` from
`main` (one call) and `of` returns the main tools for every line - the
views need no change. The learning data files are untouched either way.
