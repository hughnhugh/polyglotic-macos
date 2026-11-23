# 0254 Speech detection forgets its state after five seconds heard as not speech

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** polyglotic-hq project 536 (brief: songs in captions, "make sure it's not a bug first"); Claude reviews it with the pull request. Adds to #219's reset after digital silence and to decision 0039's gain (`platform/speech_detection.py`'s docstring); replaces neither.

## Situation

The user played songs in Spotify on 2026-11-20 and "it didn't seem to work
on many songs". Speech detection (Silero VAD, decision 0003) decides what
the app sends, and Silero carries a state from frame to frame. #219 starts
it afresh after 0.25 s of exact zeros, because carried through silence the
state stopped the model hearing quiet speech that followed (project 145).
A song's band, like a game's music, is never digitally silent, so that
reset never comes.

Project 536 ran the app's own detector and timing (Quick preview) over
CC BY songs: it heard each song's intro, while the accompaniment was
sparse, then nothing for the rest of the song - 0 % of Swansong, 2 % of
I Want to Destroy Something Beautiful, 7 % of Let It In (its first 22 s
only), 1-13 % of four Mandarin songs. The same songs cut into 20 s
stretches, each on a fresh detector, were heard at up to 42 % (Swansong
2:00-2:20: 0 % carried, 42 % fresh). So it is the carried state, not only
the music. The speech model transcribes what is sent well: of the lines
the app sent, 40 of 42 matched the lyrics.

## Decision

- After `QUIET_RESET_SEC` (5 s) of frames heard as not speech - sound
  that isn't exact zeros - the model's state and context start afresh,
  as at the start of a stream. The gain carries on (the level is still
  the source's level).
- Speech under way is never touched: the count restarts at every frame
  heard as speech, and 5 s is far longer than any pause the timing joins
  across.
- Tested in `tests/test_speech_detection.py`: after 5 s of noise the next
  frame is judged as by a fresh detector (fails without this); after a
  frame less, the state carries on. `tests/test_quiet_speech.py`'s noises
  and speech are unchanged.

## Why

Project 536's measures (`polyglotic-hq/projects/536-songs-in-captions/`,
the app's detector and timing, the default caption mode; the speech
model's answers through the validation copy):

| | today | after 5 s, afresh |
|---|---|---|
| Four English songs (CC BY): share of the song sent, finished captions | 0-7 % (one ballad 56 %); 25 | 15-24 % (the ballad 52 %); 66 |
| Four Mandarin songs (CC BY) | 1-13 %; 17 | 12-23 %; 57 |
| Two instrumentals (the same songs without vocals) | 0 % | 0 % |
| FLEURS speech, 20 clips, English / Mandarin, no music | 68 % / 52 % | 68 % / 52 % |
| The same speech over music at -20 / -10 dB (English, a rock bed) | 43 % / 30 % | 47 % / 31 % |
| The same, Mandarin over piano at -10 / -5 dB | 46 % / 38 % | 52 % / 51 % |

Alternatives measured and not taken:
- **A lower speech threshold** (0.3, 0.15 instead of 0.5): Silero's
  probability on carried-state singing is near 0, so it barely moves
  (Let It In 7 % to 10 % at 0.15).
- **Afresh sooner** (2 s): a little more singing heard (one Mandarin song
  33 % against 23 %), but an instrumental's frames began to be heard as
  speech (1 %).
- **Only for music players:** the deafness comes from any long stretch of
  music, a game's or a video's too, and speech over music was heard a
  little better with the reset; nothing measured was worse.

What it costs: more of a song is sent, so a music source uses more of the
speech model and of the learner's minutes - each song line now sent is one
someone was singing. Songs are still not a promise (Help: "Music and
effects aren't captioned"); a songs mode is project 536's proposal, not
this.

## What would make us reverse it

Sounds that aren't speech sent after a reset: game effects, crowd noise or
a TV's room tone captioned as invented lines, or quiet speech heard later
than before. 536 measured songs, instrumentals and FLEURS speech with and
without music, and the unit tests' nine noises; not game audio.

## How we'd reverse it

Remove `QUIET_RESET_SEC` and the three lines in `SpeechDetector._is_speech`
that count and reset (and the two tests); or raise it (at 10 s, less
singing was heard: 14-21 % of three English songs sent) - a constant, no other code.
