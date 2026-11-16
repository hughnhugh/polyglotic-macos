# Test audio

Recorded public speech for the tests that need real speech. Nothing here
comes from a real call or anyone's microphone.

| File | What it is | Used by |
|---|---|---|
| `fleurs-en-10098964113747380446.flac` | FLEURS (Google), English (`en_us`), dev split, clip `10098964113747380446.wav`: one read sentence, 4.14 s, 16 kHz mono. Stored scaled to a peak of 0.9 (16-bit FLAC); as recorded it peaks at -44.9 dBFS. One of the 7 of 56 quiet English clips polyglotic-hq project 180 found missed after a noise floor. | `tests/test_quiet_speech.py` |

**Licence:** FLEURS is published under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) by Google:
Conneau et al., "FLEURS: Few-shot Learning Evaluation of Universal
Representations of Speech" (2022),
<https://huggingface.co/datasets/google/fleurs>. Changed here: scaled in
level and stored as 16-bit FLAC. These files are for the tests only and
are not part of the app or its installer.
