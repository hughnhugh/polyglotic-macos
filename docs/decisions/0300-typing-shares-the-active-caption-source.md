# 0300 Typing shares the active caption source

Polyglotic HQ project 703, 2026-11-22.

## Decision

An own-speech caption is a caption from the learner's microphone. A typing
hold is the span from pressing the typing key to releasing it. When a caption
source is already listening to that audio, the hold uses its finished captions
and their translations. Caption timing and display continue on their normal
schedule during the hold. Text at a hold boundary follows the caption line
that overlaps it, so typing and the window use the same words.

For mic dictation, the matching source is the microphone's own-speech captions.
The captions' speech language and normal transcript settings apply.
For F8, use the caption window the learner is watching, if its audio is being
captioned. An active whole-system source also covers the speaker output.
Without a matching source, record a held clip for typing as before.

This replaces the microphone hush during dictation from project 299 and the
unconditional speaker recording from decision 0296. The protocol still uses
its existing caption and typing sources.

## Reversal

If caption boundaries make typing unsuitable, replace the local caption-result
subscription with the held-clip path. This requires no server change. Keeping
captions running alongside a separate recording would send that audio twice.
