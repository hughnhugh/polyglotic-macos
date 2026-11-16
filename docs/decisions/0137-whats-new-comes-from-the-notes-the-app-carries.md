# 0137 What's new after an update comes from the notes the app carries, once per version

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 345's brief (QA batch 9, 336's top
  next items 2 and 3; DECISIONS.md #158: the user tries every release, and
  testers learn what to try from what's new). The choices below are the
  user's to overrule (345's report).

## Situation

A tester who updated saw nothing about what changed: 0.1.4 had no update
card, and 0.1.5 shows the notes only on the *next* update's card ("Version
X is ready", 299), before the learner has the version. After the restart
the new version said nothing. The notes exist - RELEASE-NOTES.md's section
for each version, the text the update feed carries - but the installed app
didn't have them.

## Decision

- **The packed app carries RELEASE-NOTES.md** beside `Polyglotic.exe`
  (`tools/package/build.py`, a required file of the build's check), the
  whole file: an updated copy knows its own version's notes and every
  earlier version's, whichever version it came from. From source, the
  repo's file.
- **Once per version, after an update** (`core.releases.notes`): the
  setting `whats_new_seen` is the version whose notes the learner has
  seen. At start, each version after it up to this one shows on Home - a
  quiet card under the update card, "What's new in Polyglotic X", the
  newest version's first three items in plain words, the other versions
  named, All the changes and Close. Close sets `whats_new_seen` to this
  version; until then the card comes back at each start.
- **Never on a fresh install's first run:** nothing saved before this
  start (`FirstRun.new`) starts at this version as seen.
- **From 0.1.5 and before,** which kept nothing: this version's notes only.
- **Help keeps them:** a What's new card lists every version's notes up to
  this one, newest first and open, the others a click away; Home's All the
  changes opens it.
- **English only:** the notes are written in English; in another
  interface language Home and Help say "The release notes are in English."

## Why

- The notes ship with the version they describe, so what's new can't be
  missing or for the wrong version, and no network is needed after the
  restart, and a skipped version's notes are there too.
- A card, not a window: the app is used over games and calls (299's
  rule: never a window over what the learner is doing).
- Once per version, until Close, rather than only on the first start:
  an update often applies when Windows starts the app into the tray, and
  the learner may not open the window in that run.

Not taken: the feed's notes kept at download time (0.1.5 didn't keep them,
so the first update from it would show nothing; and a skipped version's
notes would be lost); translated notes (none are written yet).

## What would make us reverse it

- Testers find the card a nuisance, or never see it: then a tray message
  at the first start, or showing it only once whatever happens.
- Notes in other languages: RELEASE-NOTES.md's sections per language, and
  the reader picks the interface's.
- A file too large to carry (it's about 30 KB at 0.1.5): carry only the
  last few versions' sections.

How: `show_whats_new` in `main` is the one place it's wired; the rules are
in `core.releases.notes`; the build's copy is one line.
