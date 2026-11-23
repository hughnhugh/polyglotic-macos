# 0275 A music player is heard on Detect

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, from polyglotic-hq 558's measurements (558's
  report, "Music players always heard on Detect"), briefed as project 568.
  It is groundwork for a songs mode, which is still the user's call
  (polyglotic-hq DECISIONS.md #248).

## Situation

A caption window's spoken language is its own (polyglotic-hq 263). A new
window starts on Detect unless the learner chose "Start new windows like
this" (465, decision 0217), and Settings' Spoken language sets every
window's at once.
So a learner who names English for their videos also has a music player
heard as English.

Told a language, live's speech model turns music into words. With English
fixed, 544 of 558's 580 pieces of instrumental music came back as
captions, mostly "The.", "Music." and "Piano.". On Detect it wrote nothing
for any of the 580. The server now drops most of those words
(polyglotic-server #351), but not all: with Japanese or Cantonese fixed,
music turns into real replies such as "うん。" and "係。", which a filter
can't tell from speech.

## Decision

- **Which apps:** an app whose category on the known-apps list is music
  (`platform/*/categories.py`: Spotify, Apple Music, foobar2000, QQ Music
  and the rest), known by its name whether it plays yet or not
  (`OsAdapters.app_category`, handed to `CaptionWindows.music_player`).
- **What it does:** that app's window is heard on Detect, whatever the
  learner named elsewhere:
  - its new window starts on Detect, even with "Start new windows like
    this" (`StoredWindows.for_new`);
  - Settings' Spoken language leaves it be (`set_spoken_everywhere`);
  - its Detect never becomes the language new windows start with
    (`CaptionWindows._changed`).
- **What the learner can still do:** name a language in that window's own
  settings. The window keeps it, as any window does.
- **Enforced by:** `tests/ui_next/test_music_players_on_detect.py`.

## Why

- **Detect is what works for music:** on Detect the model wrote nothing
  for any of 580 instrumental pieces. With a language fixed it wrote
  something for most of them.
- **It's the learner's own case:** music players are where it was seen
  (558: Spotify).
- **Honest:** the window shows what it hears. The rule changes the
  window's stored choice; it isn't applied quietly when sending.

**Not taken:**
- **Overriding the language when sending to the server:** the window would
  say English while hearing Detect.
- **All music, games and videos included:** their dialogue needs the
  learner's language.

## What would make us reverse it

- A songs mode that wants a music player heard in a named language.
- Learners naming a language in their music player's window often. That
  would say Detect is the wrong start for them.

## How we'd reverse it

- Drop the `music_player` hook from `CaptionWindows` and `for_new`
  (a few lines each), and the test file.
- Windows already on Detect stay there until the learner names a language.
- **What it doesn't move:** a music player's window from before this,
  given English by Settings' Spoken language or "Start new windows like
  this", keeps it. Nothing records whether the learner named it there.
