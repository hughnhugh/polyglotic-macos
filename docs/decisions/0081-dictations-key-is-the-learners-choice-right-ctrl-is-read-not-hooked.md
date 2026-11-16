# 0081 Dictation's key is the learner's choice; Right Ctrl alone is read, never hooked

- **Status:** accepted
- **Date:** 2026-11-12
- **Decided by:** polyglotic-hq project 289's brief, from the user's word
  of 2026-11-11 (~22:10): "make the key customisable can default another
  logical key". The default (Right Ctrl rather than Ctrl + Win) is the
  user's to confirm: 289's report. Extends decision 0073, which this
  doesn't replace.

## Situation

283 gave dictation a fixed list of keys (Insert by default, F8, F9, F10,
Scroll Lock, Pause), each registered with Windows (`RegisterHotKey`) so
other programs don't get it. Insert clashes with the user's own
prototype, and many laptops have no Insert key. The learner should press
the key they want. Wispr Flow holds Ctrl + Win; the key nearly every
keyboard has and almost nobody uses is Right Ctrl. Windows can't register
a modifier on its own: watching one takes either a keyboard hook (every
keystroke on the PC passes through our process) or reading that key's
state.

## Decision

- **The key is a value of its own** (`core.listening.dictation_keys.
  DictationKey`): modifiers (Ctrl, Alt, Shift, Win) and a key, or a
  modifier on its own by its side ("right_ctrl"), or modifiers alone
  held together ("ctrl+win"). It's kept as text in the settings
  ("ctrl+alt+d"); 283's values read as before, so whoever saved Insert
  keeps it. **The default is Right Ctrl, held alone.**
- **Refused before it's tried, with why** (`refusal`): a key that types
  or edits on its own or with Shift; Esc (it cancels dictation); one
  Windows keeps (Win+L, Ctrl+Alt+Del, Win+H, Ctrl+Space...); Ctrl with a
  letter or digit (copy, paste...); Alt without Ctrl (letting go of Alt
  opens a program's menu, and the words would be typed into it); a
  modifier alone other than Right Ctrl (Shift and Alt type, Left Ctrl is
  every shortcut's); one of the app's own hotkeys. Another program's key
  is found by trying it, and the one before is kept.
- **Two ways of watching it** (`platform.windows.hotkeys.HoldKey`):
  - a key, with or without modifiers, is **registered** as before: other
    programs don't get it, so holding Ctrl + Alt + D types no "d"; the
    hold ends when any of its keys comes up;
  - Right Ctrl alone, or modifiers alone, is **read**: its state every
    15 ms (`GetAsyncKeyState`, one or two keys) while dictation is on.
    Other programs still get it. While it's held, the other keys are read
    every 45 ms: one going down means a shortcut (Right Ctrl + C) - the
    hold is dropped quietly, nothing sent or said. Over a window run as
    administrator Windows reports every key up (UIPI, in
    `GetAsyncKeyState`'s documentation), so Right Ctrl doesn't start
    there - where dictation couldn't type anyway (decision 0073).
- **No keyboard hook.** Nothing else typed on the PC passes through the
  app, and nothing about the keys is kept or logged.
- **Text is never typed while the key is held** (`ui.dictation`): with
  Ctrl part of the key, a hold's text arriving during the next hold waits
  for the key to come up.

## Why

- Reading one key's state costs 0.2-0.6% of one core while dictation
  waits, and about 1% while it's held (measured 2026-11-12 on the user's
  PC, F24 read in its place: 289's report). A low-level hook would run our
  Python on every keystroke of every program, where a busy moment delays
  the learner's typing in a game, and the privacy notice would have to
  say the app sees every key pressed.
- Ctrl + Win was the alternative: it needs no side, but Win is the Start
  menu's - whether letting go of Ctrl + Win opens it couldn't be checked
  without pressing keys (only the user can, on their keyboard). Right
  Ctrl is one finger, on nearly every keyboard, and rarely used.
- Refusing Alt without Ctrl, rather than allowing it, because a menu
  opened in Notepad or Office takes the typed words as menu commands.

## What would make us reverse it

- Testers' games or programs act on Right Ctrl held (VirtualBox's host
  key, a game's crouch): a different default, or registering only.
- The 15 ms read shows up in a profile of a game, or a laptop's battery:
  read more slowly, or a hook.
- Learners want a key held alone not to reach other programs at all: a
  low-level hook, with the privacy notice's line and the cost measured.

## How we'd reverse it

- Another default: `DEFAULT_KEY`, one line; saved keys stay.
- A hook in place of reading: a second way inside `HoldKey`, behind the
  same port (`ports.system.HoldKey`), chosen for keys held alone; core
  and the Settings box don't change.
- Fewer keys allowed: a refusal more in `refusal`; a saved key it now
  refuses falls back to the default when read.
