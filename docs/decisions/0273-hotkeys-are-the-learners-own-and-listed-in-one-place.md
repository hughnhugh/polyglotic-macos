# 0273 Hotkeys are the learner's own, set in one place, and Back to live has one

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** the user asked for it (polyglotic-hq 567's brief, 2026-11-20 ~12:38: "Hotkey to jump to line (consider other power user shortcuts/features) ... customiseable ... global hotkeys customisation section"); Claude chose the keys and the shape (567's report), for the user to review in the preview

## Situation

The app had three hotkeys, fixed since the proof of concept: Ctrl+Alt+L, P
and H (lock, pause, hide; ⌃⌘ on a Mac). Help said they "can't be changed
yet". A learner on a keyboard layout where Ctrl+Alt is AltGr (Polish:
AltGr+L is ł) lost a letter to them, and a power user had no way to jump
every caption window back to the newest line, or to do other things from a
game without reaching for the mouse. Dictation's key was already the
learner's own (decision 0081), set in a box that listens for the key.

## Decision

- **Each hotkey is named** (`core.listening.hotkeys.Hotkey`: lock, pause,
  hide, live, copy, preset, bigger, smaller) and its key is kept as
  dictation's is (`DictationKey`'s text: "ctrl+alt+l", "f9") in
  `AppSettings.hotkeys`, by name: "" for none; missing, its default.
- **Defaults:** Lock, Pause and Hide as before; **Back to live Ctrl+Alt+J**
  (⌃⌘J on a Mac). The rest - copy the newest caption, the next preset,
  caption text bigger and smaller - have no key until the learner gives
  one (copying takes the clipboard; the others are niche).
- **Not End**, which Remote Desktop takes with Ctrl+Alt; not the arrows,
  which some graphics drivers turn the screen with; J for "jump".
- **The OS adapters take any combination** (`GlobalHotkeys`,
  `MacHotkeys`): any key dictation's can be, with any modifiers, but never
  a modifier alone. `main`'s `AppHotkeys` registers them again whenever a
  key changes, and lets them go while a key box in Settings listens, so the
  box gets a key the app holds (and says whose it is).
- **Settings > Hotkeys** is a section of its own, after Dictation: every
  hotkey with its key (click, press the new one), Clear, Reset all; why a
  key is refused on its own line (it types, Windows keeps it, it's another
  hotkey's or dictation's, a modifier alone); another program having it,
  or two sharing one (a file edited by hand: the first keeps it). Dictation's
  key is named there with the way to change it (in Dictation). App's
  read-only list went.
- **Window keys are listed, not changed:** a transcript's Ctrl+F, End and
  Esc, and Ctrl+C, are Windows' own conventions; changing them would make
  the app's windows unlike every other program's.
- **Back to live's tip names its hotkey** in every caption window and
  transcript, as it is now; the hotkey calls the same `go_live()` the pill
  does (552's card stack uses the same call).
- **Enforced by:** `tests/test_hotkeys.py`, `tests/ui_next/test_hotkeys_settings.py`,
  the Windows and Mac adapters' tests, and the UI lab's `settings_hotkeys`
  states.

## Why

- One kept form for every key (dictation's) means one parser, one set of
  refusal rules and one capture box, already tested on both OSes.
- Unset by default for the new ones follows the brief: "unset by default
  unless it's obviously safe". Back to live is the one asked for by name.
- Registering again on change (rather than at start only) means a change
  works at once, and "another program has it" is said where it was made.
- Alternatives not taken: a key-swap when a pressed key is another
  hotkey's (it silently takes a key from something else - refused with
  whose it is instead); changeable window keys (above).

## What would make us reverse it

- Learners setting keys that keep clashing with games' own (feedback, or
  "another program has it" in logs often).
- A need for chords or several keys per hotkey.

## How we'd reverse it

- The defaults are one table (`hotkeys._LETTERS`); a new default is a
  line there.
- Going back to fixed keys means ignoring `AppSettings.hotkeys` (one call,
  `hotkeys.keys`) and removing the section - an afternoon.
