# 0039 Speech detection hears quiet audio raised to -20 dBFS; the audio sent is unchanged

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq project 186 (brief: "a level gain in front of speech detection"), from project 180's finding; Claude reviews it with the pull request. Adds to decision 0003 (the model) and to #219's reset after digital silence (`platform/speech_detection.py`'s docstring); replaces neither.
- **Amended by:** [0145](0145-the-mic-raises-quiet-audio-6db-at-most.md) - the mic's audio is raised +6 dB at most.

## Situation

Speech detection (Silero VAD, decision 0003) decides what the app sends.
Silero carries a state from frame to frame. After loud speech, that state
stops it hearing quiet speech that follows:
- **Project 145 (2026-11-07):** quiet FLEURS clips after digital silence
  lost seconds of speech, or all of it. #219 fixed that by starting the
  stream afresh after 0.25s of exact zeros.
- **Project 180 (2026-11-08):** the reset only fires on exact zeros. With
  a quiet noise floor between the clips instead (pink noise at -60 or
  -50 dBFS RMS - a call's comfort noise, a video's room tone), 7 of 56
  quiet English clips again started over 1s late or never.
- **Project 186 (2026-11-08)** reproduced that through the app's own
  detection and Steady's timing rules (8 of 56 captions late or never),
  and found what sets it off: **a loud speaker before the noise floor.**
  The quiet clips alone after the same noise were heard on time. With a
  loud (-3 dBFS) and a quiet (-45 dBFS) speaker taking turns over a
  noise floor, the app never sent 28 of 28 quiet English speakers and
  18 of 28 Mandarin ones.

## Decision

- The model hears every frame through a gain (`DetectionGain`): raised so
  the loudest sample of the last 1.5s reaches -20 dBFS, by at most +40 dB,
  never lowered. Audio already peaking above -20 dBFS - ordinary speech -
  is heard exactly as before.
- **Only the model hears it.** The audio buffered, cut and sent to the
  server is the audio as captured; the gain returns new arrays.
- The reset after digital silence forgets the gain too: after it, the
  stream is heard exactly as a new one.
- Tested in `tests/test_quiet_speech.py` on one public FLEURS clip
  (`tests/audio/`, CC BY 4.0): a loud speaker, a noise floor, the same
  clip quiet - sent with the gain, never sent without it. Also: sounds
  that aren't speech at -60, -45 and -30 dBFS are never sent; reversed
  speech and babble are (known, gain or not); the audio given is
  unchanged.

## Why

Project 186's probe (`polyglotic-hq/projects/186-quiet-speech-after-noise/`,
FLEURS dev clips, the app's detector and Steady's rules):

| | today | with the gain |
|---|---|---|
| English as recorded, 1.5s gaps of pink noise at -60 / -50 / -40 dBFS: captions late or never | 8 / 8 / 8 of 56 | 0 / 0 / 0 |
| ... gaps of digital silence (#219's case) | 0 of 56 | 0 of 56 |
| Loud then quiet speaker (-3 / -45 dBFS), pink noise at -60 dBFS, 1.5s or 0.5s gaps: quiet ones late or never | 28 of 28, both | 0 of 28, both |
| The same, Mandarin | 18 of 28 | 0 of 28 |
| Mandarin as recorded, any gap | 1 of 56 | the same 1 of 56 |
| 9 kinds of noise (white, pink, brown, hiss, engine hum, gunfire, chords and drums, clicks, a tone) at -70 to -18 dBFS: anything sent | nothing | nothing |
| Captions sent wholly inside noise gaps (English, -40 dBFS gaps) | 2 | 0 |
| Finished caption decided after the last speech, median (English as recorded) | 0.296s | 0.298s |
| Where captions start, against the clip's first speech heard alone, median | 0.30-0.32s before | 0.30-0.42s before |
| CPU per 32 ms frame | detection ~0.1 ms | +0.005 ms |

- **-20 dBFS rather than 180's -6:** both found the missed speech, but -6
  raises ordinary speech too, so it changes how every caption is timed
  (on FLEURS as recorded the finished caption's median came 28 ms later,
  its mean 18 ms sooner - mixed, not clearly worse). At -20 the gain
  changes nothing for ordinary speech, so the fix can't move what it
  wasn't meant to.
- **A 1.5s hold rather than 180's 3s:** with 3s, 12 of 28 quiet speakers
  half a second after a loud one were still missed; with 1-2s, none.
- **+40 dB at most:** the quietest of the 56 English clips peaks at
  -51 dBFS; anything quieter than -60 dBFS (hiss) stays below the target.
- **Alternatives not taken:**
  - *A reset on near-silence* (below a level, not only exact zeros): the
    quiet clips peak at -29 to -48 dBFS, and the noise floors that hide
    them peak at -37 to -49 dBFS - no level separates the two.
  - *A local speech model listening all the time* (project 180): it
    caught 5 of 6 misses, later than the gain, at far more CPU.
  - *Leaving it to the timing rules:* they only see the detector's
    verdicts.

**Cost:** on quiet speech (-45 dBFS) the finished caption is decided a
little later - at the mean +10 ms in English, +70 ms in Mandarin - perhaps
because its soft last syllable is now heard (not checked against a speech
model). With a 0.5s gap between speakers, a quiet speaker now heard can
join the loud one's caption (1 of 28 at -45 dBFS) where before it was lost. Reversed speech and babble were speech to the detector before and
still are. **What the gain newly sends: quiet background voices after a
loud speaker.** Babble at -60 or -50 dBFS RMS, 1.5s after a loud speaker
stops, was sent 6 times of 6 with the gain and 0 of 6 without
(`probe_babble_186.py`). Without a loud speaker before it, today already
sends babble down to -70 dBFS: the gain makes that consistent rather than
new, but a game's quiet crowd after its dialogue will now be captioned -
mostly as made-up text, for project 180's server-side filter to catch.
No level tells a quiet speaker from a quiet crowd.

## What would make us reverse it

- Real game, film or call audio where quiet background voices are sent
  often enough to annoy - made-up captions the learner didn't want, or
  GPU time spent on them. Project 186 only had synthetic noise, FLEURS
  and babble made from it.
- A detector without the state problem (a newer Silero, or another model)
  that hears quiet speech after loud speech on its own.

## How we'd reverse it

`SpeechDetector._is_speech` calls `self._gain.apply(frame)`; remove that
call and `DetectionGain`, and the tests in `tests/test_quiet_speech.py`
that need it (they fail without it). Tuning instead is three constants
in `platform/speech_detection.py`. Minutes either way; nothing else
depends on it.
