# 0048 The learner's level is kept beside the learning store as well as in it

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq project 237, brief item 3: "keep the learner's level where a set-aside store can't lose it, or ask with a line saying why ... Privacy: if the level moves to the server, say so; that's the user's call, so build the local option unless it's clearly worse". Claude reviews it with the pull request. Adds to decision 0010 (the learning data in one SQLite file) and to polyglotic-hq 206 (a store that can't be read is set aside).

## Situation

The level (a level scheme and the curve's midpoint) lives in the learning
store's `level` table, and nowhere else: the server doesn't keep it
(protocol.md's learning sync carries statuses and saved words, never the
level). When the store can't be read, `open_learning_store` sets it aside
and starts a new one (206). The statuses and saved words come back by the
sync; the level didn't. So the next start found no level and opened
"What's your level?" first, before Home said anything about the learning
data being set aside (223's QA, "Not quite right - medium" 3, 2026-11-08).

## Decision

The adapter (`adapters/sqlite_learning.py`) keeps the level twice:

- in the store, as before;
- in a small file beside it, `learning-level.json` beside `learning.sqlite`
  (`learning-en-level.json` beside the English learner's store), holding
  `{"scheme": ..., "midpoint": ...}`.

The copy is written with every change of level (`save_level`), whole or
not at all (a temporary file put in place). Each open reconciles the two
(`_follow_level_file`):

- a store with no level (new, or started again after one was set aside)
  takes the copy's;
- a store whose level reads writes it to the copy when the copy is
  missing or different. So the first start of an app with this writes
  the copy, and the store wins over a copy that differs.

A copy that can't be read is left out, and its kind (never its text) is
said in the log. A level row the store can't read is left for `load` to
count (207), and the copy is left as it is.

Like the level in the store, the copy stays when the learner deletes their
learning data (`Vocabulary.delete_learning_data`: "the level and the
categories stay"). It never leaves the PC.

Tested in `tests/test_learning_level_kept.py` and in
`tests/ui/test_damaged_learning_data.py` (the level is back after a
set-aside).

## Why

- **It fixes the cause.** The learner keeps their level, and isn't asked a
  question they answered before. The other choice the brief offered (ask
  again, with a line saying why) still loses the answer and costs them a
  step.
- **Local, not the server.** Keeping the level on the server would be new
  data about the learner held by us. That is a privacy choice for the user
  (TOPICS.md #1), and a protocol change (`learning_state` has no level).
  The local copy is just as good for this failure, because the store's
  damage doesn't reach a separate file. It isn't clearly worse, so the
  local option is built.
- **A separate file, not the settings file.** The settings file
  (`settings.json`) would have done too. But it belongs to `ui.settings`,
  and core's level goes through the `LearningStore` port. Keeping both
  copies inside the one adapter changes no port, and no core or `main`
  code. The settings file has its own damage path (it's reset when it
  can't be read), so it is no safer.
- **Not read back from the file set aside.** The damaged file's `level`
  row may be readable, but reading a damaged file is what 206 avoids.

## What would make us reverse it

- The level moving to the server, if the user decides it should follow the
  learner to another PC. Then the server's copy brings it back after a
  set-aside, and this file is dropped.
- The copy and the store disagreeing in ways this doesn't foresee, for
  example a learner restoring an old store from a backup and finding a
  newer level. The store wins over a copy that differs, so restoring the
  store restores its level.
- A store and its copy both lost. Then the learner is asked as before,
  with no word why (rare: two files). If that shows up in feedback, the
  level picker can say why when `LearningTools.learning_set_aside` is set.

## How we'd reverse it

Delete `level_file`, `read_level_file`, `_write_level_file` and
`_follow_level_file`, and make `save_level` write only the store: about 60
lines in one module, with its tests. Copies left on learners' PCs are
harmless (nothing reads them) and could be removed at the next start.
