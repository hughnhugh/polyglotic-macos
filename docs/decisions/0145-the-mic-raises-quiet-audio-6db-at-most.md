# 0145 The mic's speech detection raises quiet audio +6 dB at most

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 352 (the user, 2026-11-15: small
  noises and the speakers' sound captioned from the mic; "these two
  sources should share the same cleaning process"); Claude reviews it with
  the pull request, and the user may overrule it. Amends
  [0039](0039-speech-detection-hears-quiet-audio-raised.md) for the mic
  only; every other source keeps its gain as it is.

## Situation

352 mapped the mic's path and an app's, from capture to the server and
back. They already share one cleaning process: the same speech detection
(Silero, the same 0.5 threshold, the same reset after digital silence, the
same gain), the same timing rules (0.4s of speech at least, the same
hangovers, cuts and joins), the same encoding and margins, and the same
server rules for captions with no words (empty, filler words only, a
phrase invented in near-silence). What only the mic has is deliberate: the
bleed check against what the PC played (decisions 0004, 0082), the
server's text check against other sources' captions, silence while the
app speaks a word (0077) and while dictation holds the mic (299).

Two things differ in effect, not in code:
- **A loopback is digital silence between sounds; the mic never is.** Its
  own hiss and the room sit under everything it hears.
- **The gain of 0039** raises any audio quieter than -20 dBFS at its peak,
  by up to +40 dB, so the model hears a quiet speaker right after a loud
  one. In an app that quiet speaker is content the learner chose. On the
  mic the learner is the closest, loudest voice; what is quiet there is
  the room: the speakers turned down, headphones' leak, a TV, someone
  across the room. Raised +40 dB, the model heard it as speech even under
  the mic's own hiss - and the bleed check, comparing loudness, can't
  follow sound that faint (correlations of 0.5-0.65, under its 0.65).

The learner's own caption log (content-free lines, 2026-11-15, Live
updates, the PC's sound captioned) shows the same signature: of the mic's
finished captions, those that came back empty, filler-only, withdrawn as
mic bleed by the server's text check, or 5 characters or fewer were 8 of
146 while the PC was silent and 263 of 1,128 while it played; and they
sat mostly at bleed correlations of 0.3-0.65 with the mic 0-200ms late -
where real bleed sits, just under the threshold.

## Decision

- The mic's speech detection raises quiet audio by **+6 dB at most**
  (`MIC_GAIN_MAX`, 2.0, in `platform/speech_detection.py`); everything
  else about detection is the same as every source's. The pipeline makes
  the mic's detector with `new_mic_detector` (`SpeechPipeline`); `main`
  and the harness pass it.
- The audio buffered and sent is unchanged, as before.
- Enforced by `tests/test_mic_quiet_room.py` (one FLEURS clip: at a
  -62 dBFS peak under a -70 dBFS hiss it is not sent from the mic, though
  an app's detector still sends it; as recorded, -44.9 dBFS, it is), and
  by the gain's and the pipeline's own tests.

## Why

352's bench (polyglotic-hq `projects/352-the-mic-cleaned-like-app-audio/work/bench`):
FLEURS speech as the learner (Mandarin) and on the speakers (English),
Wikimedia Commons recordings of keyboards, a mouse, chairs, breathing,
coughs, a sneeze and vocal noises (sighs, a yawn, laughter, clearing the
throat, mouth sounds), synthetic hiss and mains hum; four mics (a headset,
a laptop, a headset with its own noise suppression and gain, a webcam
0.6s late) in 290's synthetic rooms; the app's own `SpeechPipeline` -
detection, timing and the bleed check as `main` wires them. No real room.
The whole set (137 mixes of noise, bleed and the learner's speech, each
on four mics; Live updates, the learner's mode; Steady in brackets):

| | +40 dB (before) | +6 dB (this) |
|---|---|---|
| Sent from the mic that wasn't the learner (finished + live updates) | 287 (193) | 119 (75) |
| ... from small noises alone (vocal noises: a "hm", sighs, laughter) | 5 (5) | 0 (0) |
| The learner's speech dropped as bleed (stretches) | 30 (19) | 7 (5) |
| The learner's clips heard, -20 to -52 dBFS, with and without a video | 360 of 360 | 360 of 360 |
| Seconds of the learner's speech sent | 2,389 | 2,376 (-0.5%) |

How far to lower it was chosen on the quick set (5 clips a track; Live
updates):

| The mic's gain at most | Sent from the mic, not the learner (finished + live) | The learner's speech dropped as bleed | The learner's clips heard |
|---|---|---|---|
| +40 dB (before) | 226 | 19 | all |
| +20 dB | 144 | 16 | all |
| +10 dB | 122 | 12 | all |
| **+6 dB** | **99** | **7** | **all** |
| none | 58 | 6 | all but 1 answer 30 dB under the learner's own loud sentence, on a laptop's mic (a quarter of those seconds lost) |

- **+6 dB rather than none:** none sends the least of the room, but the
  learner's quiet answer right after their own loud sentence was the one
  place the learner lost speech; +6 dB loses none on the bench.
- **Not taken:**
  - *The mic's noise floor taken out of the bleed check's loudness*
    (power subtraction, a soft knee, a gate at the floor): tried on the
    bench, it sent as much of the room or more - sound that faint has
    little loudness to follow, whatever is done to the hiss.
  - *A reset at the mic's own floor* (its version of digital silence):
    no help to the learner's quiet answers without the gain.
  - *A lower bleed threshold:* 0082 found it drops more of the learner's
    speech.
  - *Windows' echo cancellation* (a Communications capture stream): the
    user cancelled it earlier (2026-11-13); see 0082 for its costs.
- Small noises on their own were not the problem on the bench: Silero
  called none of the Commons keyboards, mice, chairs, coughs, breathing
  or the sneeze speech at any level from -45 to -15 dBFS; only vocal
  noises (a "hm" and sigh, laughter with a cleared throat) were sent, 5
  times in 77 mixes, and none with the mic's gain at +6 dB.

## What would make us reverse it

- Testers' quiet speech on the mic not captioned (a learner far from a
  laptop's mic, a whisper): the caption log shows mic stretches as numbers
  only, so it would come from what they tell us.
- Real rooms behaving unlike the bench: the bleed check's log line
  (`mic bleed_check`, 0082) shows the correlations; if the room's sound
  still reaches the mic as captions at +6 dB, take the gain to none (one
  constant) and look at cancelling the reference (290's proposal).

## How we'd reverse it

`MIC_GAIN_MAX` back to `GAIN_MAX`, or `new_mic_detector` left out where
the pipeline is made: one line each, no other change.
