# 0217 The first caption window sets itself up; new windows start like the last, its spoken language only when asked

- **Status:** accepted
- **Date:** 2026-11-17
- **Decided by:** the user asked for it (polyglotic-hq 465, 2026-11-17);
  Claude chose 449's design 3A for the 0.1.8 preview (DECISIONS.md #195
  item 5), which the user judges there

## Situation

A caption window's three language choices - what its app speaks
(Detect, or a language named), what it's translated into, and what to do
with lines already in that language (its second language) - were behind
the window's settings button, and the third was named differently in
Settings ("Second language") and in the window ("Lines already in
English"). A new window copied the last one's translation language and
text size, and always heard Detect.

The user, 2026-11-17: "make detect, translation selection and secondary
language selection more noticeable / easier to reach. Maybe introduce a
set up screen on first caption window opening which sets it as a default,
existing behaviour remains where last behaviour remains as default on
open."

## Decision

- **The first caption window on a PC asks** the three choices in it,
  filled in, with Start captions (`ui_next.caption_set_up`). It never
  blocks: its first caption closes it, unless the learner is at it then.
  **Changed 2026-11-18 (polyglotic-hq 478, before this merged):** it asks
  in every window that opens until the learner chooses **Use as my
  default** in it (`StoredWindows.set_up`, saved) - the user: "need a
  caption open quick configuration screen, select translate language
  (selecting as default on start up gets rid of the screen for future
  opens), select secondary language, default to detect language". Closed
  without it, its answers are that window's alone. A window's language
  chip brings it back ("Ask when a window opens"). A learner with windows
  from before it came is never asked. Only `main` offers it
  (`CaptionWindows(offer_set_up=True)`), so the UI lab's and the tests'
  windows don't.
- **New windows start like the last one**, as before - and, with "Start
  new windows like this" on (`StoredWindows.start_like_this`, one value
  for every window), with its spoken language too. Use as my default in
  the set-up turns it on: its answers are how new windows start. Off, a new window
  hears Detect, as before.
- **A language chip on every window's bar**, "Detect → English ▾", opens
  the three choices and "Start new windows like this"
  (`settings_popover.LANGUAGE_ROWS`). Where the strip is too narrow for
  it and a readable label, it goes; the settings popover keeps the rows.
- **One name** for the second language, the window's language's: "When
  they already speak English" in the window, "When they already speak the
  window's language" in Settings, each of its rows "Caption windows translating
  into English - when someone already speaks English, also translate
  into:".

## Why

- 449's walk-through as a newcomer (Ida) found the three choices hidden
  and one of them under two names.
- The set-up is the popover's own rows in a wider popover over the
  window: one way of choosing a language in the whole window, and no menu
  or other window that could take focus from a full-screen game.
- Not taken: a set-up that waits for Start captions (a gate over a video
  already playing - 449's 3A says never); carrying a named spoken language
  to every new window always (a new app may speak anything - 263's
  reason for Detect stands unless the learner asks).

## What would make us reverse it

The user's preview: the set-up feels like a gate, or testers dismiss it
without reading; or new windows hearing the last one's language surprises
learners who caption apps in different languages.

## How we'd reverse it

- The set-up: `main` stops passing `offer_set_up` (one line); the module
  and its tests go.
- Start like this: `StoredWindows.for_new` stops reading
  `start_like_this`; the switch row leaves `LANGUAGE_ROWS`. Saved values
  are ignored by an older reader (unknown keys are kept, not read).
- The chip: the strip's widget and its popover go; the rows stay in the
  settings popover.
