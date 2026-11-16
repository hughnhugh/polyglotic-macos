# 0109 A caption window asks to name the language Detect hears steadily

- **Status:** accepted; where it sits and "until answered" replaced by 0142
- **Date:** 2026-11-14
- **Decided by:** the user asked for the outcome, 2026-11-14 (polyglotic-hq
  317: "we'd prefer users to select the language rather than us depending
  on detect mode all the time. Both modes should work though"); the brief
  suggested the question ("This sounds like Russian. Always hear it as
  Russian?"). The rule's numbers are 317's guess, for the user's review.

## Situation

Detect is the default for a new caption window (a new app may speak
anything; decision 0108), and most learners never open Spoken language.
Naming the language stops short or mumbled speech being heard as another
language, so the app should make naming it the easy step - without
removing Detect, changing the default, or asking anything of a learner
who hasn't heard anything yet.

## Decision

- **When:** a window whose app is heard as Detect has shown
  `STEADY_CAPTIONS` (5) finished captions in a row in one of the spoken
  languages, none of them mixed with another language
  (`core.listening.spoken.SteadyLanguage`). My speech never counts.
- **What:** at the top of the window, "This sounds like Russian. Always
  hear it as Russian?" with **Yes** and **Not now** (`ui_next.spoken_nudge`).
  Yes names the language for that window (it's then first in every
  spoken-language list); Not now keeps Detect and the window never asks
  about that language again (`StoredWindows.declined_spoken`, by the
  window's key). It stays until answered, or until the learner names a
  language another way; it hides while the window is locked.
- **Once a run:** the caption that makes the run steady asks; the ones
  after don't. Another language, a mixed line or a line in no known
  language starts the run again.

Enforced by `tests/ui_next/test_spoken_nudge.py`.

## Why

- Five finished captions is about half a minute of talk: long enough that
  one stray line doesn't trigger it, short enough to ask while the learner
  is still looking at the window. A guess - the number is one constant.
- Asking in the window, not on Home or as a toast: it's where the learner
  is, about the app they're watching, and answering is one click that
  never takes the keyboard from a game.
- Not taken: switching to the heard language by itself (a mixed call
  would flip back and forth, and the learner wouldn't know why short
  lines changed); asking at the first run (293 took the first run's
  language question out); a new window copying the last named language (a
  new app may speak another).

## What would make us reverse it

- Testers finding the question a nuisance, or answering Not now to most
  of them: the run should be longer, or the question should come once a
  session.
- Captions under a named language turning out worse than Detect for the
  apps people name (a mixed-language stream): the question should say
  so, or not be asked for such apps.

## How we'd reverse it

Delete `SteadyLanguage`'s use in `CaptionWindows._steady_language` and the
window's `suggest_spoken`; the stored `declined_spoken` is ignored by an
app that doesn't read it. Changing when it asks is `STEADY_CAPTIONS`.
