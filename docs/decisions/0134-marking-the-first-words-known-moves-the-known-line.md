# 0134 Marking the first N words known moves the known line, and Reset is kept in the settings

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** Claude, for polyglotic-hq project 342 (the user,
  2026-11-15: "a quick select option to mark first x thousand words as
  known, make this resettable too"). The brief preferred moving the line
  over writing thousands of marks "unless the code says otherwise"; it
  didn't. Reversible.

## Situation

Learning already says the level as a known line in words: "I know about
the 3,000 most common words" (decision 0114). "Mark the first 3,000 words
known" says the same thing. It could be done two ways: write a status
"known" for each of those words, or move the line. And it has to be
undoable right after, and resettable later, without wiping the words the
learner marked one by one.

## Decision

- **A quick mark moves the known line** (`Vocabulary.set_known_words`), as
  the level picker does. No status is written per word. The rules -
  only a number past the line is offered, what Undo and Reset go back to -
  are `core/learning/first_known.py`'s.
- **Undo** (right after, this session only) puts back the line just
  before the mark. **Reset** puts back the line before the first quick
  mark since the learner last chose a level in the picker; a choice in
  the picker ends both. Before any line was set, "back" is no line: the
  store's new `clear_level` removes the level row and its copy beside the
  file (decision 0048), so a new start doesn't take the copy's.
- **Where Reset goes is kept in the settings** (`known_reset`, per
  language: `{"scale", "known"}`, or `{}` for no line), not in the
  learning file. The file keeps schema version 6.

## Why

- **Hand marks survive by construction.** A status set by hand always
  wins over the line (`statuses.status_of`), so neither a mark, an Undo
  nor a Reset can touch one: a word the learner made new again stays new.
  Writing marks per word would need a way to tell bulk marks from the
  learner's own, and a Reset that deletes thousands of rows.
- **Nothing per word leaves the PC.** Statuses set by the learner are sent
  to the server; 10,000 of them would be 10,000 events. The line isn't
  sent.
- **One number to say it.** Learning's "Your level", Words' level line and
  the learning window all read the line already; a quick mark shows in all
  of them at once.
- **Version 6 stays readable by 0.1.5.** A new table or column would move
  the file to version 7, which 0.1.5 refuses (an older app refuses a newer
  file). In the settings, 0.1.5 ignores the key; a downgrade loses only
  the Reset point.

Not taken: a status per word (above); keeping the Reset point in the
learning file (a schema version for one value, and 0.1.5 locked out).

## What would make us reverse it

- Learners need bulk marks that aren't a prefix of the frequency list
  (every word of a textbook chapter, an Anki deck's words): those are
  statuses, set in bulk (342's multi-select does that for lists).
- The level becomes something the server keeps (synced across PCs): the
  Reset point would then belong with it.

## How we'd reverse it

`first_known.py` and the three handlers in `main` (`mark_first_known`,
`undo_known`, `reset_known`) are the whole of it. Writing statuses instead
would replace `set_known_words` there with a bulk `set_statuses` over the
dictionary's first N words (`PlacedWords`), and Reset with deleting those
rows by their source. The settings key can be dropped: an unknown key is
ignored.
