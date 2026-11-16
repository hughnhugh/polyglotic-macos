# 0003 The speech-detection model is committed, pinned by its checksum

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** project 016 (build project D2), 2026-11-04, choosing
  between the options its brief listed; Claude reviews it with the pull
  request.

## Situation

Speech detection runs Silero VAD v6.2 on ONNX Runtime (polyglotic-hq MVP.md;
project 005). The app needs the model file at run time, the installer (D5)
must include it, and the tests need it. The full model,
`silero_vad.onnx`, is 2,327,524 bytes; the repo's large-file check stops
anything over 500KB. Silero also publishes `silero_vad_16k_op15.onnx`,
1,289,603 bytes, for 16kHz only - the only rate the app uses.

## Decision

- Use **`silero_vad_16k_op15.onnx` from Silero VAD's v6.2.3 tag**
  (SHA-256 `7ed98ddbad84ccac4cd0aeb3099049280713df825c610a8ed34543318f1b2c49`),
  committed as package data at
  `src/polyglotic_desktop/platform/data/`.
- The large-file check has an exception for that one path
  (`.pre-commit-config.yaml`).
- `tests/test_speech_detection.py` fails if the file doesn't match the
  checksum in `platform/speech_detection.py`.
- Silero is MIT: its notice is in `THIRD_PARTY_NOTICES.md`.

## Why

- **Measured 2026-11-04 on 40 public FLEURS clips (13,207 frames): the 16kHz
  variant made the same speech / not-speech decision as the full model on
  100% of frames** (mean probability difference under 0.0001), at the same
  speed (0.072 vs 0.074 ms per frame on one thread). It's 45% smaller.
- Committing it keeps every build, every test run and CI working offline
  and identically, with no download step to break or to trust. The model
  changes rarely, so the repo grows by about 1.3MB per model update.
- **Alternatives not taken:**
  - *Fetch at build time with a pinned checksum:* no binary in git, but CI,
    every developer setup and the installer build would need a download
    step from GitHub, and tests needing the model would need the network.
    More moving parts for 1.3MB.
  - *The `silero-vad` package from PyPI:* it carries the model, but depends
    on torch, which the app avoids (project 005).
  - *The full 2.3MB model:* no benefit at 16kHz (above).

## What would make us reverse it

- Models updated often enough that the repo's size matters.
- A model we may not redistribute in the repo (Silero's MIT licence allows
  it).

## How we'd reverse it

Delete the file and its large-file exception; add a fetch step (a small
script with the URL and checksum) to CI and the build. `model_path()` is
the one place that finds the file. About an hour.
