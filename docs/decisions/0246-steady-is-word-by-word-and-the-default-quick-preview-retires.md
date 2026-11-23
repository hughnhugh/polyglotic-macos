# 0246 Steady is word by word and the default; the modes are renamed; Quick preview retires

- **Status:** accepted; replaces [0242](0242-quick-preview-is-the-default-again.md) (its "a choice stays" rule, from 0037 and 0055, is kept)
- **Date:** 2026-11-20
- **Decided by:** Claude asked for it to be built on polyglotic-hq
  DECISIONS #230's recommendations, reversibly, before the user's formal
  answer (526's brief, Phase 2; the user, 2026-11-20: the polish and
  Steady "ship these together"; #233: "A is fine, can have them as
  options"). The user tries a preview build before any release.

## Situation

The playout ([0245](0245-captions-words-are-played-out-at-the-pace-they-were-said.md))
shows a caption's words at the pace they were said. It needs a caption
mode to live in, and the three modes' names no longer said what each did:
"Steady" showed whole captions; "Live updates" is also the glossary's word
for an update.

## Decision

- **Four modes** (`core.listening.timing.CaptionMode`, offered in this
  order - `OFFERED_MODES`):
  - **Steady** (`STEADY`, stored as `"words"`): live updates every second,
    shown through the playout. The default (`default_caption_mode`).
  - **Whole captions** (`WHOLE`, stored as `"steady"`): what was called
    Steady.
  - **Instant** (`INSTANT`, stored as `"live"`): what was called Live
    updates.
  - **Calm** (`CALM`, stored as `"calm"`): Steady, releasing only the
    words the server calls established.
- **The stored values of the two renamed modes don't change**, so a
  learner who chose the old Steady or Live updates keeps exactly what they
  chose, and no settings version is needed to tell an old "steady" from a
  new one.
- **Quick preview retires:** it is not offered; a stored choice of it is
  read as Steady, as a choice (`ui.settings._migrated`). Its timing rules
  and enum member stay until #230 is answered, then go.
- **Untouched learners follow the default** (0037, 0055, 0220): whoever
  never chose a mode is on Steady from their next start.
- **Steady's options** (Settings > Timing): the newest word shown too
  (1.5 s behind, not 1.75 s); the words ahead drawn faint (karaoke), with
  or without the newest word. Stored as `steady_newest_word` and
  `steady_words_ahead`.
- The paced modes' live updates are always translated (a clause shows its
  translation as it ends), as provisional lines' are.
- Only the caption windows are paced; the transcript, the history and
  Learning's counts take updates as they come (0245).

## Why

One name per behaviour, the name the user gave the new one ("Steady =
B"). Keeping the old stored values is the smallest migration and the
safest roll-back: an older app reading `"words"` or `"calm"` finds no such
mode and follows its own default.

Not taken: new stored values for every mode with a settings version (more
to migrate, nothing gained); deleting Quick preview's rules now (not
reversible in one line while #230 is open).

## What would make us reverse it

The user, after trying the preview build, preferring another default or
another set of names.

## How we'd reverse it

`default_caption_mode` is one line; the names are four strings in
`ui_next.caption_window.timing_name`; putting Quick preview back is adding
it to `OFFERED_MODES`, its name and tip, and dropping the line in
`_migrated`.
