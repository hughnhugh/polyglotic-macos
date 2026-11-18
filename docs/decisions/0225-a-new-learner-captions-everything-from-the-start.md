# 0225 A new learner captions everything the PC plays from the first launch

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user (polyglotic-hq 484, 2026-11-18 ~05:35: "Make
  the first time launch easier, everything the PC plays should be [the
  default]"), changing polyglotic-hq DECISIONS.md #25 ("nothing is
  captured until the learner chooses"); Claude chose how it reaches new
  learners only and what the app says about it. Replaces 0220's "left
  off" for which apps are captioned.

## Situation

Since the first alpha a new learner met Home's picker after the code and
captured nothing until they added an app or chose Everything the PC plays
(DECISIONS.md #25). That was one more step - and a decision a newcomer
can't yet make well - between the install and a caption. 478 turned every
other feature on for a new learner and left this one off for the user's
call.

## Decision

- **Everything the PC plays is on for a new learner**
  (`AppSettings.whole_system`, default True) and follows the default until
  changed (`FOLLOW_DEFAULT`, 0220's record). After the code, its caption
  window opens by itself and sets itself up (0217); the first window's mic
  is on (0220).
- **What's captioned is one choice.** Apps picked by a learner who never
  chose everything (`apps` set, `whole_system` not in the record - a
  record begun under 478's default, or a file without the key) are
  captioned, not everything (`AppSettings.from_stored`).
- **Existing users keep their choice:** a file from 0.1.7 or before holds
  `whole_system`, so it counts as chosen and stays as it was.
- **A new learner's first window is still a first:** the migration of
  today's settings (`views.migration.todays_sources`) counts everything the
  PC plays as a window from before only where it was chosen, so the set-up
  asks and the mic is on.
- **It's said, and one click undoes it:** the window is labelled
  "Everything the PC plays" (it was "This PC"), its empty state says
  anything the PC plays is captioned there, and Home says a call's voices
  are in it too, with the apps playing listed under "Caption one app
  instead" - one click captions that app alone (`main.adding_app`).
- **The sample isn't offered while everything is captioned** (as before
  for any choice): played aloud, it would be heard twice.

## Why

- The user asked for it, to make the first launch easier: the shortest
  path from install to a caption is the two screens the law and the alpha
  need (Your data with the yes, and the code), then captions of whatever
  is playing.
- Following the default (not just a new default) means a later change
  reaches whoever never chose, the same way as 0220's switches.

## What would make us reverse it

- Testers surprised by what's captured - a call captioned they didn't
  expect, or a game's sound costing minutes - or the privacy notice's
  wording not holding up.
- Minutes used on sound nobody wanted captioned (the usage statistics'
  `source_selected` and minutes per category show it).

## How we'd reverse it

Set `whole_system`'s default back to False: learners who never chose
follow it (they capture nothing until they pick), those who did keep
theirs. Home's line and the "instead" list go with it (`_everything_said`,
`adding_app`'s `whole_system` branch); the label can stay. The privacy
notice's 3.3 changes back in the same release.
