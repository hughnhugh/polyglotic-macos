# 0004 Mic bleed is checked against the whole system's audio

- **Status:** accepted
- **Date:** 2026-11-04
- **Decided by:** project 016 (build project D2), 2026-11-04 - the design
  question its brief asked to settle; Claude reviews it with the pull
  request, and the user may overrule it.
- **Amended by:** [0082](0082-mic-bleed-lag-up-to-1s-and-quiet-loopback.md)
  (how the mic is compared with this reference: up to 1s late, a quieter
  loopback, a correlation of 0.65) and
  [0154](0154-the-mic-bleed-check-cancels-what-played.md) (what played is
  cancelled out of the mic, and what's left is judged)

## Situation

Mic bleed is the PC's own audio picked up by the mic, from speakers or
leaky headphones. The proof of concept catches it by comparing the
loudness of the mic's speech with what the PC was playing
(`platform/mic_bleed.py`). It always captured the whole system, so "what
the PC played" was simply that stream.

The product captions **one app at a time** (MVP.md). The speakers still
play every app: music, a second video, notifications. So when one app is
captioned, what should the mic be compared with - that app's audio, or the
whole system's?

## Decision

**The whole system's audio:** loopback on the output device the PC plays
through (Windows' default, followed as it changes), captured **only while
the mic is on and only for this check** - kept in memory for 30s like any
source, never sent, never written to disk, never run through speech
detection. When the user captions the whole system, that stream doubles as
the reference and nothing extra is opened.

## Why

- **It's what the mic actually hears.** The speakers play the mix of every
  app, so bleed is the mix's loudness, not one app's. Comparing with one
  app misses bleed from every other app - the user's mic captions would
  pick up song lyrics from a music app while they caption a call - and
  correlates worse even for the captioned app when something else plays
  at the same time.
- The system's audio contains the captioned app's, so nothing caught today
  is lost.
- It's cheap: a loopback stream costs almost nothing (no speech detection
  on it; 30s of 16kHz audio is about 1.9MB of memory).
- Privacy holds: the other apps' audio never leaves the PC and is never
  stored; it is compared with the mic and dropped.
- **Alternative not taken - the captioned app's audio:** no extra stream,
  but it fails exactly in the "something else is playing" case that
  per-app capture exists for.

## What would make us reverse it

- Users on headphones only, where bleed is rare, and the extra stream is a
  measurable cost (it isn't, as far as measured).
- Apps routed to a different output device than Windows' default (Windows
  allows per-app output devices): the default device's loopback then
  misses that app. If testers do this, compare with both streams and call
  it bleed if either matches.

## How we'd reverse it

`MicBleed` takes the buffer to compare against; `main` (or the harness)
chooses which buffer to hand it. Switching to the app's own buffer is a
one-line change in the wiring, plus not opening the extra stream.
