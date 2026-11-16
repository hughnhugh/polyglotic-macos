# 0083 A cut while the speech goes on falls at its quietest moment, and the two pieces' audio doesn't overlap

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** Claude, under polyglotic-hq brief 291 (the user,
  2026-11-11: "Check reports for bugs"); reversible. How captions are cut
  in general (polyglotic-hq topic D1) stays the user's: this fixes the
  plain faults of the cut there is.

## Situation

Steady and Quick preview finish a caption at a breath once it has run 3s,
or cut it at 6s anyway (the breath cut, `BREATH_CUTS`); every mode splits
at 20s (the long-speech split). A tester's problem reports (polyglotic-hq
291, 2026-11-11) showed a fast-talking video in Steady: 30-odd captions in
a row, each exactly 6.02s, each ending in a full stop, and in about half
the next caption began with the last one to three characters of the one
before. The tester's words: the text arrived "sucked in together and
released together".

Replaying the report's 84 seconds through the app's own speech detection
and timing (offline, numbers only): speech detection said speech for all
but three single frames, so the breath cut never found its 0.3s pause and
the 6s limit fired every time - at the frame it fell on, whose loudness
was the stretch's median: mid-word. Each piece's audio then ran 0.2s past
the cut each side (`SLICE_PAD_SEC`), so 0.4s - one to three characters of
that speech - went to both pieces.

## Decision

- **Each frame carries its loudness** (`FrameResult.level`, its RMS as
  captured), and `CaptionTiming.frame` takes it.
- **At a breath cut's limit or a long-speech split, the caption is cut at
  the quietest moment of the last 1.5s** (`CUT_LOOKBACK_SEC`): the middle
  of its quietest run of three frames (~100ms, longer than a stop
  consonant's closure inside a word). The next caption starts there; the
  speech heard since is its own. Without loudness (None), the cut falls at
  the limit, as before.
- **The two sides of such a cut say so** (`TranscriptionRequest.cut_after`
  and `cut_before`; on the wire, the server's decision 0058): neither
  carries the slice's 0.2s margin at the cut, so the pieces' audio meets
  without overlapping, and the server leaves the first piece's text open
  at its end (no full stop).
- A pause still ends a caption as before, margins and all.

Tested in `tests/test_timing.py` (the quietest moment; a dip outside the
1.5s isn't used; both sides marked and their audio meeting; the 20s split;
a pause unchanged; no loudness, no change), `tests/test_speech_pipeline.py`
(the pieces' audio adds up to the stretch) and `tests/test_protocol.py`.

## Why

- On the report's own audio, the cut moved from the stretch's median
  loudness (0 of 13 cuts below a tenth of it) to under a tenth in 8 of 15,
  and pieces of 4.1-6.0s instead of 6.02s. Speech detection can't place
  the cut here: its probability stayed at 1.0 through the gaps between
  words that the loudness shows.
- Looking back, not ahead: the limit is the promise (a caption every 6s at
  most, polyglotic-hq 268); waiting past it for a quieter moment would
  break it. 1.5s back keeps each piece at least 4.5s, past the breath
  cut's 3s.
- Removing the overlap rather than de-duplicating the text: matching words
  across pieces is fuzzy, and the speech model was paid for the same audio
  twice.
- Not done (the user's, D1): cutting by meaning (the speech model's own
  sentence ends), a longer limit for fast speech, or one caption that keeps
  growing on screen while its pieces are finished underneath.

## What would make us reverse it

- The real speech model dropping or inventing a word at a margin-less
  edge more often than it repeated one (a FLEURS continuous-speech run,
  cut at 6s, with and without: the run needs the GPU).
- Cuts landing inside words often on other audio (music under speech,
  noisy calls): the loudness is the whole mix's, not the voice's.

## How we'd reverse it

Pass no `level` from the pipeline (the cut falls at the limit again) and
leave `cut_before`/`cut_after` False (margins again): two lines in
`platform/speech_pipeline.py`. The rest is unused then and can go.
