# 0294 Linux says a word in its recording, else speech-dispatcher's voice, talked to over its socket

- **Status:** accepted
- **Date:** 2026-11-21
- **Decided by:** the user, 2026-11-20 (polyglotic-hq DECISIONS #243 item 3:
  "recordings, then the system's basic voice; a natural voice later, as
  its own decision"); how, Claude (polyglotic-hq 591, Linux's slice 5)

## Situation

Windows and the Mac say a looked-up word in the OS's own voices, behind
the `Speaker` port (decision 0077), with a pack's recordings first
(decision 0133). Linux has no voice of that kind. Its desktops' speech
server is speech-dispatcher: Ubuntu 24.04's desktop installs it with
espeak-ng's voices (0.12.0~rc2, its release manifest, read 2026-11-21),
and Orca speaks through it. espeak-ng is robotic, and GPL-3; Piper, the
natural one, is GPL-3 too, and some of its voices are non-commercial
(546's PLAN.md, section 1.4).

speech-dispatcher plays the sound itself: its protocol (SSIP) has no way
to hand the samples to a client. Windows' and the Mac's voices hand the
app a word's samples, which the app trims and plays.

## Decision

- **Recordings first, then speech-dispatcher.** `RecordedVoices` over
  `platform/linux/voices.DispatcherVoices`, as on the other two. Without
  speech-dispatcher (not installed, or not starting) the recordings still
  play, and the card says why there's no other voice.
- **Over its socket, nothing loaded.** The app speaks SSIP on
  speech-dispatcher's Unix socket (`$XDG_RUNTIME_DIR/speech-dispatcher/
  speechd.sock`) with the standard library - no libspeechd, no espeak-ng
  library in the app's process, so neither licence reaches the app. Where
  nothing listens (no systemd user session), the app starts it as
  speech-dispatcher's own library does, `speech-dispatcher --spawn`.
- **A voice may say a chunk itself.** `speaking.SaysItself` joins
  `speaking.Clip` as what a voice makes of a chunk. The speaker sends it,
  watches it to its end (`END`) or stops it (`CANCEL`); the captions are
  hushed from when it was asked, `HUSH_AHEAD_SEC` (0.6 s) ahead at a time
  while it plays, since its length is known only when it ends. Nothing is
  trimmed or kept. Windows and the Mac are unchanged.
- **Which voices:** every output module's, the system's default module
  first; only the plain voices (espeak-ng lists 13,362 on Ubuntu 24.04,
  131 of them plain, the rest variants such as `+Adam`); espeak-ng's
  Mandarin `cmn` as `zh-CN` and Cantonese `yue` as `zh-HK`. All are
  `Quality.BASIC`.
- **518's notice, worded for Linux:** each word said in speech-dispatcher's
  voice says it was the system's basic voice, that Polyglotic can't use a
  more natural one on Linux yet, and that recorded words sound natural -
  with "Don't show again" and Dismiss, as on a Mac. No voice for a
  language says why (speech-dispatcher missing, or without that language)
  and which packages add it; there is no settings page to open, so no
  button.
- **The app's own sound** - a recorded word, Home's sample - plays through
  the sound server (libpulse, as capture uses it: `platform/linux/sound`).

## Why

- It is the decision the user made (DECISIONS #243 item 3), on what every
  supported desktop already has.
- The socket keeps the app's licence its own and needs nothing installed
  beyond what Ubuntu ships; Fedora and KDE package the same daemon.
- Measured on GitHub's Ubuntu 24.04 runner (591's probe, 2026-11-21): the
  sound began within 20 ms of being sent; a cancel stopped it within
  20 ms; speech-dispatcher said `END` about 0.3 s after the last sound -
  so a hush that runs ahead while it plays covers it without knowing its
  length.

## What would make us reverse it

A natural voice for Linux agreed as its own decision (Piper run as a
downloaded program, or a voice of our own server's), or learners finding
espeak-ng worse than no voice at all.

## How we'd reverse it

A natural voice is another `speaking.Voices` beside `DispatcherVoices` in
`main.linux_adapters` (one that hands samples back plays through
`sound.PulseOutput`); `Quality.GOOD` for it ends the notice. Taking the
system voice away is `RecordedVoices` over no OS voices.
