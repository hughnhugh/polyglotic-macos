# 0256 Sound without speech is counted in the caption timelines

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude, for polyglotic-hq project 549 (brief: "Sound
  playing, nothing heard as speech" made visible). Adds to decision 0255
  (the caption timelines) and reads decision 0254 (the reset after 5 s);
  replaces neither.

## Situation

The user's problem report of 2026-11-20 18:11 ("Another long hang", 0.1.9,
the whole system and the mic): in their caption log nothing at all was
*sent* for 28.2 s (18:03:07-18:03:35), 23.9 s and 16.5 s, while answers and
drawing around those gaps were instant. Either nothing was said, or speech
detection had stopped hearing it - project 536 found Silero's state,
carried through a song's band, stopped it hearing the singing (decision
0254 now forgets it after 5 s).

The caption timelines (decision 0255) begin at a decision to send. A
source that played sound speech detection never heard as speech leaves
nothing in them, and the next update's speech begins after the gap, so not
even a hang shows. Neither the trace nor the caption log could tell
silence from deafness.

## Decision

- **Each source's frames are also counted for sound without speech**
  (`platform/sound_unheard.py`, fed by `platform/speech_pipeline.py`). A
  stretch begins at a frame heard as not speech at -45 dBFS or louder (root
  mean square, as captured, before the detection gain) and goes on while
  nothing is heard as speech:
  - dips under the floor shorter than 1 s stay inside it (the gaps between
    a missed speaker's words); a second under the floor ends it (`quiet`);
  - speech enough to send - 0.4 s of frames heard as speech, as the timing
    counts it - ends it where that speech began (`speech`); a moment too
    short to send is part of it, as it sent nothing either;
  - the source stopping ends it (`stopped`).
- **A stretch over 3 s is a record in the caption timelines**, kind
  `sound_unheard`: the source's category, when it began and ended, its
  frames' level at p10, p50 and p90 in dBFS, how many times speech
  detection forgot its state in it (decision 0254; `FrameResult.reset`),
  how long before its end the last of them was, and what ended it. A
  stretch still going on is given to the tracer as it stands once a second,
  so a problem report sent during a hang has it (`end` `open`).
- **It goes wherever the timelines go:** the owner's `trace.jsonl` lines;
  the problem report's attachment (its own row shape); the viewer's page,
  as a lane under each source's screen track and a close-up of the three
  longest; and the session's summary, as a hang put down to
  `sound_unheard` - so the usage statistics' `hangs` counts it and
  `hangs_sound_unheard` says how many (polyglotic-server's tracking plan
  adds the property; the server drops an event with a property it doesn't
  know, so the server change deploys first).
- **"Heard just after the reset"**: a stretch ended by speech within 1 s
  of speech detection forgetting its state. The detector had most likely
  stopped hearing speech that was there, and the reset brought it back.
- **Levels and times only**: no audio, no text, no app's name or source id.

## Why

Project 549 ran the app's detector over project 536's CC BY files, the
state carried through sound heard as not speech (as before decision 0254)
and forgotten after 5 s (now), with the stretches counted as above:

| | carried: stretches, longest | after 5 s, afresh: stretches, longest, heard just after the reset |
|---|---|---|
| Four English songs | 1-3, 16-253 s (the ballad 16 s, the rest 183-253 s) | 3-12, 15-63 s, 1-5 |
| Four Mandarin songs | 1-6, 135-253 s | 8-12, 34-135 s, 3-4 |
| Two instrumentals | 1, the whole track | 1, the whole track, 0 |
| FLEURS Mandarin, a band 5 dB under it | 15, longest 29.6 s | 19, longest 8.4 s, 6 |
| FLEURS English, a band 10 dB under it | 8, longest 28.0 s | 8, longest 28.0 s, 0 |
| FLEURS speech without music | 0 | 0 |

So a stretch shows exactly the gaps the user saw (talk under music: 28-30 s
with the speech unheard), the reset shortens most of them, and "heard just
after the reset" was never seen on the two instrumentals. What the numbers can't say
on their own is whether a stretch held speech: an instrumental and a missed
speaker both make one. Its levels, its resets and what ended it are the
evidence; the trace is what makes the question answerable at all.

Not counted in the stretch's record: Silero's speech probability. Project
536 found it near 0 on singing carried through a band, the case this is
for, so it wouldn't have told the two apart.

## What would make us reverse it

- The counts are noise in every listening session (a game's or a song's
  sound counted as hangs) and the testers' `hangs` stops meaning captions
  that stopped: then `sound_unheard` leaves `hangs` and becomes counts of
  its own (`sound_unheard`, `sound_unheard_seconds`), a tracking-plan
  change.
- The floor (-45 dBFS) or the 1 s dip proves wrong on real use: the
  constants are in `platform/sound_unheard.py`.

## How we'd reverse it

- Delete `platform/sound_unheard.py`, its two lines in
  `platform/speech_pipeline.py`, `FrameResult.reset`, the `Unheard` record
  and `sounding`/`unheard` in `perf/trace.py`, and the `UNHEARD` branches
  in `perf/trace_summary.py` and `tools/trace/page.py`.
- Older trace files and reports keep their stretch records; the viewer
  without the branch would read them as updates that never showed, so it
  keeps the branch until they've aged out.
