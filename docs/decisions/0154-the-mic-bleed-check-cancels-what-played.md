# 0154 The mic's bleed check cancels what played out of the mic, and judges what's left

- **Status:** accepted
- **Date:** 2026-11-15
- **Decided by:** polyglotic-hq project 363 (the user, 2026-11-15: "Sometimes
  there are artifacts resulting from speaker audio into mic captioning");
  Claude reviews it with the pull request, and the user may overrule it.
  Amends [0004](0004-mic-bleed-reference-is-system-audio.md) and
  [0082](0082-mic-bleed-lag-up-to-1s-and-quiet-loopback.md): the reference, the
  1s lag and the -66 dBFS silence stay; how the mic is judged against
  the reference changes.

## Situation

The mic's bleed check compared loudness: the mic's speech was the PC's
when its loudness envelope followed what played (a correlation of 0.65).
Loud bleed is easy to tell that way. Faint bleed is not: with the
speakers turned down, or headphones' leak reaching a headset mic, what
the speakers play reaches the mic near or under its own hiss, and the
hiss flattens the mic's envelope. 352 measured correlations of 0.5-0.65
there, under the threshold. With the mic's gain capped at +6 dB
(decision 0145), Silero still hears speech in some of it. On the real
models, with the speakers 20 dB down, 8 finished captions were still
kept as "You" across 3 mixes, mostly the speakers' own words.

## Decision

- **Cancel, then judge what's left.** For each stretch checked,
  `platform/mic_bleed.py` finds the delay from the two signals (GCC-PHAT,
  0 to 1s), fits the room per frequency (32ms STFT bins, 150-5000Hz) as a
  filter of 8 taps over about 100ms from that delay, by least squares, and
  takes it out of the mic. This is an echo canceller's filter, used only
  to judge: the audio sent is never changed.
- **It's bleed when cancelling takes away at least 0.6 of the mic's sound
  above its own noise floor** (`BLEED_CANCELLED`). The floor is a low
  percentile per bin of the last 10s of the mic (`FLOOR_SEC`). Above the
  floor, faint bleed is still almost all the speakers, while the user's
  voice is left whole however loud the speakers are under it.
- **Or when the loudness check says so** (`BLEED_CORRELATION`, 0.65, as
  before). Typing or taps on the mic leave more than cancelling can take
  away, and the loudness check's running median takes them out. On the
  bench this catches the speakers under typing (3 live updates) at the
  cost of 2 more of the learner's stretches dropped, both live updates
  with the speakers louder than the learner.
- **Seen without content:** the caption log's `mic bleed_check` line
  gains `cancelled=` (the share taken away); `correlation=` stays, as
  does the harness's `bleed`.
- **Cost**, on one core:
  - one check takes 9-14ms for a stretch of up to 3s and 39ms for 20s,
    against 2-4ms before;
  - the delay is found on the stretch's last 4s at most (`DELAY_FROM_SEC`);
  - over the bench's mic audio, the checks take 5.5ms a second while the
    speakers play (0.55% of a core; 1.3ms before) and 2.8ms a second
    overall (0.8ms before);
  - nothing is cancelled while the PC is silent.
- Enforced by `tests/test_mic_bleed.py`: the speakers under the mic's
  hiss (the loudness check's correlation 0.52-0.62) and through a room's
  echo are bleed; the user talking quietly over faint speakers, or over
  loud ones in a room, isn't; every earlier case holds.

## Why

352's bench (polyglotic-hq `projects/352-the-mic-cleaned-like-app-audio/work/bench`,
copied and extended in `projects/363-*/work/bench`): FLEURS speech as the
learner (Mandarin) and on the speakers (English), noise recordings from
Wikimedia Commons, four mics in 290's synthetic rooms, the app's own
`SpeechPipeline` with detection, timing and the check as `main` wires
them. No real room. The whole set, 137 mixes x 4 mics, Live updates
(Steady in brackets):

| | Before (main, 0.1.6) | This (with stretches from 0.35s compared) |
|---|---|---|
| The speakers' or the room's sound sent as "You", finished | 54 (56) | 0 (0) |
| ... live updates | 65 (19) | 0 (0) |
| The learner's clips heard | 360 of 360 | 360 of 360 |
| ... of them while a video plays, quietly or loud | 160 of 160 | 160 of 160 |
| Seconds of the learner's speech sent | 2,376 (2,375) | 2,372 (2,372), -0.2% |
| The learner's stretches dropped as bleed | 7 (5) | 14 (8) |

The learner's stretches dropped are all in the two mixes where a video
plays at full volume under the learner. Most are live updates whose
stretch was still mostly the speakers when it was checked. The finished
caption that follows covers the learner's speech, so every clip is still
heard and 0.4% of those mixes' seconds are lost.

Each part on its own (Live updates, finished / live updates sent from the
speakers, the learner's stretches dropped):
- cancelling alone: 2 / 3, 11;
- cancelling, or the loudness check: 2 / 0, 13;
- comparing from 0.35s (polyglotic-hq 363's other pull request) with
  the loudness check alone: 52 / 65, 8; with cancelling: 0 / 0.

Tried and not taken:
- **Cancelling alone** (no loudness check beside it): the same on the
  learner's speech, but 3 live updates of the speakers under typing got
  through.
- **Judging by the share of the whole mic, not above its floor**: misses
  headphones' leak into a headset mic with its own noise suppression.
- **Fitting on half the frames and judging on the other half** (against
  a fit that matches the learner by chance): catches less bleed (1,252
  of 1,326 checks against 1,325) for no fewer drops.
- **A running median over the cancelled frames** (as the loudness check
  has): didn't rescue the taps case and isn't needed elsewhere.
- **Windows' own echo cancellation** (290): it processes the user's
  voice before recognition, needs build 22621 to choose its reference and
  exists only where the driver ships it.

## What would make us reverse it

- Testers' caption logs (`cancelled=` beside `correlation=`) showing the
  learner's own speech cancelled as bleed in real rooms - many stretches
  marked `bleed=yes` with `cancelled` just over 0.6 while the learner
  talks.
- The check's time showing in the speech pipeline's lock: captions of
  other sources arriving late while the mic is checked.

## How we'd reverse it

`MicBleed.measure` and `BleedMeasure.bleed` in `platform/mic_bleed.py`:
drop the cancel from the verdict (one line) and the loudness check is
what it was before. Nothing outside the module depends on the cancel.
