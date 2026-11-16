# The samples

What Home plays when nothing else is ("Try it on a sample"; polyglotic-hq
project 176), so a learner sees a caption before they've found something
to play.

- **Source:** FLEURS (Conneau et al., "FLEURS: Few-shot Learning
  Evaluation of Universal Representations of Speech", 2022),
  <https://huggingface.co/datasets/google/fleurs>, test split - licensed
  under CC BY 4.0 (<https://creativecommons.org/licenses/by/4.0/>; the
  dataset card's `license: cc-by-4.0`, read 2026-11-08).
- **Changed:** four sentences each, joined with 0.9 s of silence between
  them, each evened to a -6 dBFS peak, as 16 kHz mono FLAC
  (`tools/samples.py`, from polyglotic-hq 086's download).
- **The app credits them** on Home beside the sample, and in
  THIRD_PARTY_NOTICES.md.

| File | FLEURS config | Sentence ids, in order |
|---|---|---|
| `zh.flac` | `cmn_hans_cn` | 2005, 1760, 1965, 1871 |
| `en.flac` | `en_us` | 1972, 1750, 1720, 1674 |

The sentences are FLEURS's own, from FLoRes-101 (Goyal et al., 2022,
<https://github.com/facebookresearch/flores>), licensed under CC BY-SA 4.0
(<https://creativecommons.org/licenses/by-sa/4.0/>; credited in
THIRD_PARTY_NOTICES.md too, polyglotic-hq project 196). No one's private
speech.
