# 0108 Every language the speech model hears can be named, from one list

- **Status:** accepted
- **Date:** 2026-11-14
- **Decided by:** the user asked for the outcome, 2026-11-14 (polyglotic-hq
  317's brief: "Detect modes should be made obvious. Right now it looks
  like many languages aren't supported ... see if you can expand that
  list ... we'd prefer users to select the language rather than us
  depending on detect mode all the time. Both modes should work"); the
  list, its order and its wording are 317's, the wording waiting for the
  user's pick by eye (polyglotic-hq 317's report). Claude reviews them with
  the pull request.

## Situation

A caption window's Spoken language offered Detect, English, Mandarin and
Cantonese (polyglotic-hq 248's IA.md 1.1). A learner watching Russian or
Japanese found neither and concluded they weren't supported; they were,
through Detect, which said nothing about what it covers. Dictation
already offered all 30 languages the speech model can be told
(polyglotic-hq 283), from a list of its own. Settings > Speech had a
four-way switch; the tray and Settings > Dictation said "Detect the
language".

The server takes any language code as a spoken language (protocol.md,
`spoken_language`); its speech model adapter tells the model the 30 on
its own list (Qwen3-ASR's `support_languages`, polyglotic-server
`adapters/qwen_asr.py`) and hears any other code as Detect.

## Decision

- **One list:** `core.listening.spoken.SPOKEN_LANGUAGES`, the speech
  model's 30, is every spoken language a caption window, Settings >
  Speech, a transcript's rail or dictation can be set to
  (`dictation.DICTATION_LANGUAGES` is it). A stored choice of any of them
  is kept; anything else is read as before (the base's).
- **Only what the model can be told:** Mandarin (`zh`, its captions in
  Simplified characters) and Cantonese (`yue`, in Hong Kong characters)
  are the Chinese entries; no other dialect or script is offered, since
  the model can't be told one. Ukrainian is a caption language but not on
  the model's list, so it can't be named (Detect may hear it).
- **One way of saying the two modes,** in every place (`ui_next.languages`):
  Detect is "Detect automatically", saying how many languages it covers
  (on a chip: "Detect · 30 languages"); a language named is under "Always
  hear as" and shows as "Always Russian". The wording is one set of
  functions, so the user's pick among the candidates changes it in one
  place.
- **One order:** the languages named last (up to 3, remembered with the
  caption windows' own setting), then the learner's own (Windows'
  languages), then the rest by name in the interface's language; each as
  the interface names it and as its speakers write it ("Russian ·
  Русский"). Settings and a transcript's rail find one as it's typed, by
  any of its names or its code; a caption window's settings have no box,
  since they never take the keyboard (a full-screen game behind them
  could minimise).
- **Made when first opened:** the list isn't built with the page
  (Settings is built at start, which is measured: polyglotic-hq 314).
- **Detect stays the default** for a new window (a new app may speak
  anything) and keeps working as before.

Enforced by `tests/ui_next/test_spoken_language_list.py`.

## Why

- The model's own list is the honest one: offering a language the model
  can't be told would quietly be Detect.
- Recent first: a learner names the same one or two languages for most
  apps, so the list opens on them; the full list of 30 still scrolls in a
  caption window's settings without a box.
- Own names beside the interface's: the learner looks for the language
  they hear, often by the name they see on screen in it.
- Not taken: a combo box in Settings (no search, no recent group); a
  search box in the popover (it would take the keyboard from a game).

## What would make us reverse it

- A speech model with a different list (the router polyglotic-hq 316
  researches): the list should then come from the server (a `welcome`
  field) rather than this constant.
- Learners naming a language and getting worse captions than Detect for
  mixed speech, often enough that Detect should be the suggestion again.

## How we'd reverse it

`SPOKEN_LANGUAGES` is one constant: a server-sent list replaces it in
`main` and the views, without touching the widgets. The wording is in
`ui_next.languages`' few functions. Going back to four choices is
shortening the constant; stored choices outside it are read as the
base's, as before.
