# 0267 Speech over music is heard through a floor filter and a lower threshold

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** polyglotic-hq project 558 (brief: "speech under a music bed is heard"); Claude reviews it with the pull request. Adds to decision 0254's reset and decision 0039's gain (`platform/speech_detection.py`'s docstring); replaces neither. The mic is left as decision 0145 tuned it.

## Situation

The user, on preview 1 (2026-11-20 ~19:45): "Music doesn't work still,
not sure if it's music dependent. Maybe it just doesn't work sometimes in
capture all PC." Earlier that day their caption log showed 28 s, 24 s and
16 s with nothing sent. Project 549 then found 28 s of English speech
unheard under a rock bed "10 dB under the speech", even with decision
0254's reset.

Project 558 found that mix was not what it said: it set the bed against
the clips' *average* level, and half of FLEURS' English clips sit near
-60 dBFS, 15-20 dB *under* that bed - three in a row made the 28 s. With
every clip at the same level, main hears speech 10 dB over a bed (the
longest unheard stretch 2.3 s in 1 of 36 mixes, none at another frame
alignment). What it does miss is speech over a louder bed, the case of
game music, a loud video, or a whole PC playing music beside a video:

| Bed under the speech (36 mixes each: 4 languages x 9 CC BY beds) | main: mixes with over 2 s unheard in a row | the longest |
|---|---|---|
| 15 dB | 0 | 1.5 s |
| 10 dB | 1 | 2.3 s |
| 5 dB | 6 | 5.9 s |
| as loud | 19 | 20.2 s |

Silero (decision 0003) hears speech over music as music: on those frames
its probability is either high or near 0, rarely between.

## Decision

For every source but the mic:
- **A floor filter** (`FloorFilter`): the model hears each frame with
  each frequency's floor taken out - the lowest its smoothed power has
  been, rising at 3 dB a second; twice the floor is taken out, never
  below a tenth of the power. A bed of music is mostly floor; speech rises
  over it syllable by syllable. 512-sample windows every 256 samples, so
  the model hears each frame 16 ms late. The audio sent is never changed.
- **A lower threshold under a steady bed of sound:** when every frame of
  the last 2 s peaked at -45 dBFS or louder, a frame is speech at 0.25,
  not 0.5. Speech in a clean recording dips under -45 dBFS between words
  and keeps 0.5; speech recorded with noise can count as a bed too (4-49 %
  of the frames of 558's FLEURS speech, each clip brought up to -26 dBFS),
  and it was heard and sent as before (the table below).

The mic is made with `beds=False`: neither rule, as decision 0145 tuned it.

Tested in `tests/test_speech_under_music.py`: the threshold rules and the
filter through a stand-in model; a recorded mix (30 s of FLEURS English
over Josh Woodward's CC BY rock instrumental) through the app's own
detection and caption timing, at four frame alignments. With the bed as
loud as the speech, the rules before this heard 55-78 % of it with
5.7-9.5 s unheard in a row; with this, 83-100 % and at most 1.8 s (the
test fails before). With the bed 10 dB under, and with no bed, both pass
(guards).

## Why

558's bench (`polyglotic-hq/projects/558-speech-under-music-is-heard/`):
FLEURS dev speech in English, Mandarin, Vietnamese and Cantonese (20 clips
each, every clip at -26 dBFS), under nine CC BY beds (rock, ballad,
electronic, orchestral, funk, accordion, chiptune, lounge, quirky) at 15,
10, 5 and 0 dB under it; the beds alone; 352's noises (keyboards, chairs,
coughs, laughs) and a game-like pink bed; 536's eight CC BY songs. The
app's detection and caption timing (Steady), fed 10 ms at a time. At two
frame alignments (0 and 256 samples):

| | main | this |
|---|---|---|
| 10 dB under: mixes over 2 s unheard / the longest | 1 and 0 / 2.3 s | 0 and 0 / 1.6 s |
| 5 dB under | 6 and 4 / 6.0 s | 0 and 0 / 1.7 s |
| as loud | 19 and 19 / 20.2 s | 11 and 9 / 12.7 s |
| speech alone: heard, captions, end-of-speech delay p50 / p90 | 99.7 %, 169, 0.29 / 0.91 s | the same; p90 0.92 s |
| audio sent per minute: speech alone | 137 s | 139 s |
| music alone (9 beds, 30 min): finished captions; seconds sent a minute | 5; 0.6 | 14; 1.8 |
| sound effects (3 x 200 s): finished captions, at each alignment | 6 and 7 | 6 and 10 |
| songs: share of the song sent as finished captions | 24 % | 36 % |
| a ballad's singing heard (from its instrumental) | 75 % | 91 % |

Alternatives measured and not taken:
- **A lower threshold everywhere** (0.15-0.3): about as good under a bed,
  but it sent more of speech alone (146 s a minute at 0.15) and of sound
  effects.
- **The threshold alone, under a bed, with the reset after 2 s:** 2 of 36
  mixes still over 2 s 5 dB under, and more of music alone and of sound
  effects sent (19 and 11 captions).
- **Silero's own hysteresis** (on at 0.5, off at 0.35): no better than main.
- **A band filter** (250-4000 Hz) and **Silero's 8 kHz mode:** worse; the
  model the app carries is the 16 kHz one only.
- **A second detector**, YAMNet (AudioSet, Apache 2.0): 5 dB under a bed
  it scored only 66 % of its 1-second windows of speech as speech (Silero
  heard 99 % of the speech frames), and almost none of the singing.
- **Sending sound that plays on with nothing heard** (after 4 s, 3 s of
  it, again and again): half a rock song's singing sent instead of a
  quarter, but 255 finished captions sent in 30 minutes of instrumentals
  and 65 in 10 minutes of sound effects.

**What the extra music sent turns into** (live's speech model,
Qwen3-ASR-0.6B, through the validation copy, 2026-11-20). The 14 pieces of
music alone this sends in 30 minutes of instrumentals, against main's 5:
- on Detect, the default: all come back empty - no caption;
- with Chinese fixed as the spoken language: "嗯。" or "啊。", which the
  server drops as filler words;
- with English fixed: 13 come back as a word - "The." (9), "Music." (2),
  "Okay." (2) - and one as a lone full stop, and the words are shown.
  That is about 26 such lines an hour of instrumental music, against 10
  on main (all 5 of main's are "The."). A server filter for
  these lone words would drop them on main too (558's report).

The real app on the validation copy (346's loop, as a video player on
Detect; English speech 5 dB over a ballad, 60 s of electronic music alone,
60 s of a rock song) showed the same lines as main plus one more of them
whole, nothing for the music alone, and the same end-of-speech delay.

## What would make us reverse it

Sound that isn't speech captioned as invented lines under music - a game's
effects over its music, crowd noise, a TV - or speech alone heard later
or less. 558 measured these on recordings and the validation copy, not on
real game audio, and only for Windows' app audio.

## How we'd reverse it

Construct the detectors with `beds=False` in `main.py` and `harness.py`
(one argument each), or remove `FloorFilter`, the `BED_*` constants and the
two lines in `SpeechDetector._is_speech` that use them, and
`tests/test_speech_under_music.py`. Nothing else depends on them.
