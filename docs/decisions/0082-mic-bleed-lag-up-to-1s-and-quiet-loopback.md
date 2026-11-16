# 0082 Mic bleed is looked for up to 1s late, and from a quiet loopback

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** polyglotic-hq project 290 (from a bug report from the
  user's own use of 0.1.3, 2026-11-11); Claude reviews it with the pull
  request, and the user may overrule it. Amends
  [0004](0004-mic-bleed-reference-is-system-audio.md): the reference is
  still the whole system's audio; how the mic is compared with it changes.
- **Amended by:** [0154](0154-the-mic-bleed-check-cancels-what-played.md)
  (the loudness correlation is no longer the only verdict: what played is
  cancelled out of the mic, and what's left is judged; the lag and the
  silence threshold stay)

## Situation

The mic's bleed check (`platform/mic_bleed.py`, from the proof of concept)
compares the loudness of the mic's speech with what the PC played, the mic
up to 0.5s behind, a correlation of 0.6 or more being bleed, and calls
nothing bleed while what played is under -46 dBFS. Two things the proof
of concept never met:

- **Bluetooth speakers and wireless mics.** Windows' loopback hands us the
  mix before the output device's own delay. Bluetooth's alone is typically
  0.1-0.3s (RTINGS measured SBC at 173ms), Windows can add to it, and a
  wireless mic adds its own.
- **A loopback at the volume slider's level.** On some PCs loopback
  follows Windows' volume (reports differ by driver), so with the slider
  low and the speakers' own knob up, what played reads as near silence.

290's bench (polyglotic-hq `projects/290-the-mic-captions-what-the-speakers-play/bench`)
plays FLEURS speech "through a room" - a delay, a synthetic room's echo,
the speaker and mic's band, noise, gain, some with a headset's noise
suppression and gain - and runs it through the app's own speech detection
and Steady timing with the check wired as the app wires it. No real room
or device. Today's check catches the speakers alone in every stretch up to
a 0.5s lag, even in a reverberant room on a webcam mic, and past it misses
most: 9 of 25 at 0.55s, 21 or 22 of 25 at 0.6s, 20 of 24 at 0.7s, 21 of
24 at 0.9s. With the loopback 30dB quieter than what the speakers play,
it misses about half.

## Decision

- The mic is compared with what played **up to 1s earlier**
  (`BLEED_MAX_LAG_SEC` 0.5 -> 1.0).
- What played counts as nearly silent only **under about -66 dBFS**
  (`SILENT_PLAYBACK_RMS` 0.005 -> 0.0005).
- A correlation of **0.65** is bleed (`BLEED_CORRELATION` 0.6 -> 0.65):
  twice the lags give a chance match twice the room, and at 0.6 the wider
  range drops more of the user's own speech than today.
- Enforced by `tests/test_mic_bleed.py`: a stretch 0.8s late, and one from
  a loopback 40dB down, are bleed; the user talking over either isn't; the
  proof of concept's cases hold.

## Why

The bench, finished stretches in every scenario but one (the speakers on
another output than the reference, which no comparison with it can
catch):

| | Bleed sent as the user's (misses) | The user's speech dropped (false alarms) |
|---|---|---|
| Today (0.5s, 0.6, -46 dBFS) | 521 of 1,544 (34%) | 89 of 1,557 (5.7%) |
| 1s and -66 dBFS, at 0.6 | 20 of 1,554 (1.3%) | 105 of 1,557 (6.7%) |
| **1s and -66 dBFS, at 0.65** | **22 of 1,554 (1.4%)** | **85 of 1,557 (5.5%)** |
| 1s and -66 dBFS, at 0.7 | 32 of 1,553 (2.1%) | 67 of 1,557 (4.3%) |

0.65 rather than 0.7: 0.7 drops less of the user's speech but misses
more, and fails the proof of concept's case of bleed with taps and clicks
on the mic. All of the false alarms are with something playing while the
user talks; none with the PC silent or music under the user's voice.

A check costs 1-2.5ms on the capture thread (0.7ms before), for stretches
of 1-20s.

**Not taken now:**
- **Windows' echo cancellation for the mic** (a capture stream in the
  Communications category): while a communication stream is open Windows
  turns other sounds down by 80% by default (the Sound control panel's
  Communications tab) - the sound the learner is captioning; only drivers
  that ship it, or Windows 11's Voice Clarity, provide it; choosing its
  reference needs build 22621 (none on Windows 10); and it processes the
  user's voice before it's recognised.
- **Cancelling the reference out of the mic and measuring what's left**
  (the delay by GCC-PHAT, a short per-frequency filter fitted by least
  squares): on the bench it drops 6 of 1,557 of the user's stretches, not
  85, and misses 5 of 1,557, at about 9ms a check. Worth building once a
  real room confirms it - a project of its own.

## How we see it

Without content (290's next pull request): each stretch of the mic checked
is a line in the caption log - `mic bleed_check seconds=4.00
correlation=0.84 lag_ms=800 played=sound outputs_playing=2 bleed=yes` -
and `uv run python -m polyglotic_desktop.harness bleed` lets a learner
check their own PC for 20 seconds, a video playing on the speakers and
they silent: numbers only, nothing kept.

## What would make us reverse it

- The caption log's `mic bleed_check` lines, or reports, showing the
  learner's own speech dropped more often than bleed caught.
- Real rooms showing lags over 1s (raise it) or none over 0.5s (lower it
  back: fewer chance matches).
- Still from 0004: apps playing to another output than Windows' default.

## How we'd reverse it

Three constants in `platform/mic_bleed.py` and their tests.
