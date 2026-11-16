# 0077 A looked-up word is said in Windows' own voices, behind a `Speaker` port, and kept out of the captions

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** polyglotic-hq project 286 (the user, 2026-11-11 ~20:45:
  "a simple implementation of this for now but have an upgrade path to
  ideal speech later"); its DESIGN.md. Claude reviews it with the pull
  requests.

## Situation

The lookup card should say its word aloud at one click. The app's Qt is
`pyside6-essentials`, which has no QtTextToSpeech, and decision 0006 chose
our own ctypes code over audio libraries. Windows has three ways to speak:
WinRT's `Windows.Media.SpeechSynthesis` (the OneCore voices), SAPI 5 (the
older desktop voices) and Qt's module (in `pyside6-addons`, over either).
The app also captions what the PC plays: with "everything the PC plays",
"everything else" and the mic, its own word would come back as a caption.

## Decision

- **A port:** `ports/speaker.py`'s `Speaker` - which voices exist, say this
  text in this voice at this pace, stop - with `sounding` (when the app's
  own sound plays) and `ended`. Which voice says a word is a rule outside
  the speaker (`ui_next.views.speech`), from the word's language.
- **The first speaker** is `platform.speaking.SpeakerThread` (a thread of
  its own: voices listed in the background, one word at a time, the last
  click wins) over `platform.windows.voices`: WinRT's synthesizer through
  ctypes, read out as WAV samples, silence trimmed, played by winmm's
  `waveOut` on Windows' default output. `main.os_adapters` hands it over.
- **Kept out of the captions:** while the app's own word plays (from
  `sounding`, with a margin each side), the sources that hear the PC's mix
  - everything the PC plays, everything else, and the mic - hear silence
  (`SpeechPipeline.hush`): their speech detector and the speech sent both.
  An app captioned on its own (process loopback) never hears the app.
- Nothing is sent anywhere: the word is made and played on the PC.

## Why

- **The voices it reaches:** on the user's PC (2026-11-11) WinRT listed 10
  voices, SAPI 4 - no Vietnamese and no Kangkang, Yaoyao, Yating, Zhiwei or
  Mark. Voices added in Settings > Time & language > Speech are OneCore
  voices: WinRT has them, SAPI doesn't.
- **Installer size:** our ctypes adds nothing; Qt's module needs
  `pyside6-addons` beside essentials (the module and its plugins would be
  a few MB packed, the dependency far more to install for development).
- **The samples in hand:** the WAV gives the word's length (the hush's
  span) and its leading silence (0.13-0.18 s, trimmed - the word comes
  sooner), and tests check samples without a speaker. Qt's and SAPI's
  own playback give neither.
- **Speed:** 15-65 ms to make a word on the user's PC, listing 1-12 ms.
- **waveOut, not PlaySound:** PlaySound plays one sound per process, so a
  word would cut off the sample (176) playing beside it.
- **Hush, not exclusion:** Windows leaves out one process tree per process
  loopback capture, and "everything else" already leaves out the app
  captioned beside it; Windows 10 before 2004 has no process loopback at
  all. A hush works for every source. Its cost: up to about a second of
  the other app's audio isn't captioned while a word plays.

## What would make us reverse it

- A better voice is wanted (DESIGN.md's upgrade path): that's a new
  `Speaker` and a setting, not a reversal.
- Learners say the hush loses lines they wanted: subtract the known word
  from the mix (an echo canceller) instead of silencing it.
- WinRT's speech through ctypes breaks on a Windows build: Qt's module, as
  another adapter.

## How we'd reverse it

Swap the adapter `main.os_adapters` hands over (`speaker`); the port, the
card and the hush don't change. The hush is one method of the speech
pipeline and one flag per source in `main`.
