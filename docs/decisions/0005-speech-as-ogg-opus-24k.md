# 0005 Speech is sent as Ogg Opus at 24 kbit/s, encoded by libsndfile

- **Status:** accepted for the app; the framing and bitrate are proposed
  to polyglotic-server's protocol.md (still "open" there), which settles
  them
- **Date:** 2026-11-04
- **Decided by:** project 016 (build project D2), 2026-11-04; Claude
  reviews it with the pull request; the protocol part goes to S1.

## Situation

The app sends only speech, compressed, to the server (MVP.md): a binary
`speech` frame per live update and finished caption, with `codec`
`"ogg_opus"` and `sample_rate` 16000 (protocol.md). It needs an Opus
encoder from Python on Windows - small, with Windows wheels, under a
licence that fits a closed app - and a bitrate.

## Decision

- **Encoder: `soundfile` 0.14.0** (BSD-3), which wraps **libsndfile
  1.2.2** (LGPL-2.1, a separate DLL in the wheel) built with libopus 1.5.2.
  `platform/opus.py` is the one module that uses it.
- **24 kbit/s target, VBR** (libsndfile's default mode; it can't set
  constant bitrate for Opus), mono, 16kHz input, 20ms Opus frames,
  complexity 10.
- **Framing: each speech frame's audio is one complete Ogg Opus stream**
  (RFC 7845): `OpusHead`, `OpusTags`, audio pages - so every frame decodes
  on its own, as protocol.md requires ("each binary frame stands alone").
  The `OpusTags` padding libsndfile reserves (about 760 bytes) is removed.

## Why

**Measured 2026-11-04 on this PC, all 236 public FLEURS dev clips in
bench/ (English, Mandarin, Cantonese, Vietnamese; 2,501s of speech):**

| Target | Actual average | Per second of speech | 1.5s live update | 6s section | 20s caption |
|---|---|---|---|---|---|
| 16 kbit/s | 14.9 kbit/s | 1.87 kB | 3.30 kB* | 11.6 kB* | 39.0 kB* |
| **24 kbit/s** | **20.6 kbit/s** | **2.57 kB** | **3.54 kB** | **15.5 kB** | 56.8 kB* |
| 32 kbit/s | 27.6 kbit/s | 3.46 kB | 5.36 kB* | 21.1 kB* | 75.8 kB* |

\* before the tag padding was trimmed (add ~0.76 kB to any figure without
a star to compare; trimming takes 0.77 kB off each starred one).

- CPU: 6.3 ms per second of audio encoded (one thread). Live updates
  re-send each second of speech about 3.5 times (below), so encoding costs
  about 2% of one core while someone speaks.
- Raw 16-bit PCM would be 32 kB per second: Opus at 24k is about 12x
  smaller.
- **Why 24 rather than 16:** Opus wideband speech at 16-24 kbit/s is
  generally reported as near-transparent for speech recognition, but **we
  haven't measured the effect on Qwen3-ASR** (no GPU in this project). 24k
  leaves a margin for noisy, music-backed and mixed-language audio for
  about 0.7 kB/s more. S2's accuracy check (FLEURS error rates) should
  compare 16k, 24k and PCM, and lower it if 16k loses nothing.
- **Upload, as an estimate from the timing rules:** at the default 1.5s
  live-update interval, a 9s stretch is sent as live updates of 1.5, 3,
  4.5, 6, 1.5 and 3s plus the 9s finished caption, each padded 0.2s each
  side: about 31s of audio for 9s of speech, about 9 kB/s (70 kbit/s)
  while someone is speaking - fine for home upload speeds.
- **Libraries not taken:** PyOgg (last release 0.6.14a1, 2020, an alpha);
  opuslib / opuslib-next (need a system libopus, no Ogg muxer); PyAV (a
  28MB wheel, all of FFmpeg).
- **Licence:** soundfile is BSD-3; libsndfile is LGPL-2.1, loaded as a
  separate DLL that a user could replace - PyInstaller's one-folder build
  (D5) keeps it a separate file. The installer must carry libsndfile's
  licence (the wheel's `_soundfile_data/COPYING`) and its bundled
  libraries' notices (libopus and libogg are BSD). Not a legal opinion.

## What would make us reverse it

- S2's accuracy check shows 24k hurts recognition (raise it) or 16k
  doesn't (lower it): change `OPUS_BITRATE`.
- libsndfile's LGPL terms become a problem for distribution (for example
  a single-file build): switch to libopus (BSD) through ctypes with our
  own Ogg muxer - `platform/opus.py` is the only module to change.
- The server prefers a stream per source (protocol version 2): Ogg pages
  can be sent as they're made; the encoder would then run per source.

## How we'd reverse it

The bitrate is one constant. The encoder is one function behind
`encode_ogg_opus(audio) -> bytes`; replacing libsndfile is a day's work
(ctypes libopus plus an Ogg page writer, whose checksum code is already
here).
