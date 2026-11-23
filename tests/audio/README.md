# Test audio

Recorded public speech for the tests that need real speech. Nothing here
comes from a real call or anyone's microphone.

| File | What it is | Used by |
|---|---|---|
| `fleurs-en-10098964113747380446.flac` | FLEURS (Google), English (`en_us`), dev split, clip `10098964113747380446.wav`: one read sentence, 4.14 s, 16 kHz mono. Stored scaled to a peak of 0.9 (16-bit FLAC); as recorded it peaks at -44.9 dBFS. One of the 7 of 56 quiet English clips polyglotic-hq project 180 found missed after a noise floor. | `tests/test_quiet_speech.py` |
| `song-zh-mengzhong-0-48.opus` | 梦中的你 by Adeline Yeo (HP), its first 48 s, 16 kHz mono, stored as Ogg Opus (about 29 kbit/s). Carried through the band, the old speech detection heard none of the singing after the first notes (polyglotic-hq 536); with the reset after 5 s (decision 0254) it hears some. | `tests/test_sound_unheard.py` |
| `talk-under-music-zh-236-272.opus` | FLEURS Mandarin (`cmn_hans_cn`, dev split: the end of `1074188475771767661.wav`, then `10758748325753795769.wav`, `10878784572167100857.wav` and the start of `11004428545382500251.wav`, 1.5 s apart) with the instrumental of Words Fall Apart by Josh Woodward under it, 5 dB below the speech's level and running on between the clips; 36 s, 16 kHz mono, Ogg Opus. Made by polyglotic-hq 536's `prep536.py` (`som-zh-5`, 236-272 s), cut by 549. Carried through the band, 29 s of the speech went unheard. | `tests/test_sound_unheard.py` |
| `fleurs-en-558-speech.opus` | FLEURS English (`en_us`, dev split): the end of `10493474598526206030.wav`, then `10511964668971448587.wav` and the start of `10567709020684252271.wav`, 1.5 s of digital silence between, each clip brought to -26 dBFS (the RMS of its frames within 20 dB of its loudest); 30 s, 16 kHz mono, Ogg Opus. Made by polyglotic-hq 558's `prep558.py` and `testmix558.py` (English, 150-180 s). | `tests/test_speech_under_music.py` |
| `music-bed-rock-558.opus` | The instrumental ("NoVox") of I Want to Destroy Something Beautiful by Josh Woodward, 2:40-3:10, at the level of the speech above (its RMS from 0:10 to 3:33 brought to -26 dBFS); 30 s, 16 kHz mono, Ogg Opus. The test mixes it under the speech at 0 and -10 dB. | `tests/test_speech_under_music.py` |

**Licence:** FLEURS is published under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) by Google:
Conneau et al., "FLEURS: Few-shot Learning Evaluation of Universal
Representations of Speech" (2022),
<https://huggingface.co/datasets/google/fleurs>. Changed here: scaled in
level and stored as 16-bit FLAC or Ogg Opus. The songs are published
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) by their
artists: 梦中的你 (Meng Zhong De Ni) by Adeline Yeo (HP),
<https://freemusicarchive.org/music/adeline-yeo-hp/single/meng-zhong-de-ni/>;
Words Fall Apart by Josh Woodward,
<https://www.joshwoodward.com/song/WordsFallApart>, and I Want to Destroy
Something Beautiful by Josh Woodward,
<https://www.joshwoodward.com/song/IWanttoDestroySomethingBeautiful> (their
instrumentals, the "NoVox" versions). Changed here: cut, mixed down to
16 kHz mono, scaled in level, an instrumental mixed under speech, and
stored as Ogg Opus. These files are for the tests only and are not part of
the app or its installer.
