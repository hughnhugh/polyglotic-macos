# 0241 A word plays at its own pace, and a basic voice says a better one can be added

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** the user, 2026-11-18 (polyglotic-hq DECISIONS #228; project 518)

## Situation

Since decision 0077 a second press of a word's speaker said it slower
(0.7). Where the word was recorded (decision 0133) a recording slowed
would drop in pitch, so the slower press went to the OS's voice instead.
On a Mac that is often the compact Tingting: on 2026-11-18 the user heard
every second press switch from the recording to "robotic and unnatural"
speech, and asked for "just the normal version only". They also asked
for a notice "everytime you play something that is not the ideal voice
pack available until you select a don't show again checkbox, then the
dismiss".

## Decision

- **One pace.** Every press of a word's speaker, Say it and the card's
  play are said at the voice's own pace (`views.speech.NORMAL`): the
  recording if there is one, else the best voice of the language. The
  second-press path (`SLOWER`, `pace`, "Say it again, slower") is gone;
  `RecordedVoices` plays a recording at any pace asked.
- **A voice's quality is part of the port.** `ports.speaker.Voice` carries
  a `Quality`: `BASIC` (a compact voice, where the OS offers a better one
  of its language for free: a Mac's default quality), `GOOD` (the best
  kind the OS lets an app use - every Windows voice - or a Mac's
  enhanced) and `PREMIUM`. Its numbers are macOS's own
  (`AVSpeechSynthesisVoiceQuality`). A Mac already lists the best of a
  language first, so the best installed voice is the one used.
- **The notice** (`views.speech.BetterVoice`): each time a word or a
  selection plays in a `BASIC` voice - never a recording - the place it
  was asked from says how to add a better one (macOS's steps), with
  "Don't show again for {language}" and Dismiss. Ticked, never again for
  that language (the settings' `better_voice_quiet`). The lookup card and
  the sentence card show it inside themselves (no new window: they never
  take focus, and they are already above a full-screen app); the
  transcript, a window of its own with the keyboard, in a box.

## Why

- A learner hears a word the same way at every press; a slower press was
  a second, worse voice for most recorded words.
- Windows has no `BASIC` voices to an app: WinRT's OneCore voices are all
  of one kind, and Narrator's natural voices aren't open to other apps
  (`platform/windows/voices.py`; NaturalVoiceSAPIAdapter's README, read
  2026-11-18). Telling a Windows learner to add natural voices would send
  them to install something the app can't use, so on Windows the notice
  never shows.
- Inside the cards rather than a popover: a popover beside a pinned card
  would count as a click elsewhere and close it.

## What would make us reverse it

Learners asking for a slower word again (then: a slow recording made by
our own speech model, not the OS's voice), or Windows opening its natural
voices to apps (then: Windows' standard voices become `BASIC` where a
natural one exists for the language).

## How we'd reverse it

A slower pace is a rate passed to `Speaker.say` again (the port kept its
`rate`). Windows' quality is one value set in `platform/windows/voices.py`.
