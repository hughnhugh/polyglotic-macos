# 0257 The live zone's captions each start a line, and the zone is as tall as what is being read

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** Claude asked for both bugs fixed before the second
  preview (polyglotic-hq 526, from 548's pictures of the release
  candidate on real speech). It changes two points of decision 0251,
  which otherwise stands.

## Situation

0251 ran the live zone's captions on as one paragraph, in a zone a fixed
number of lines tall. On real speech (548):

- at the end of speech the zone was empty and still took its lines; the
  transcript above had room for one caption, cut to its translation;
- a caption began in the middle of a line, once the caption it ran on
  from had settled;
- a long caption's first row left the zone before the caption handed
  off, so it was nowhere until then.

## Decision

- **Each caption in the live zone starts a line** (`zone_look`: no
  run-on). Lines still only grow.
- **The zone is as tall as what is being read:** its own lines
  (`Zones.live_lines`, the least while anything is read), more while a
  caption that began above them hasn't handed off - up to the window's
  room - and nothing at all when it is empty: after a pause the
  transcript has the whole window (`CaptionWindow._place_zone`,
  `ZoneCanvas.needed`).
- **The handoff** is unchanged in rule: a finished caption settles when
  all of it is above the zone's own lines (`ZoneCanvas.rolled_out`,
  `lines_tall`).

## Why

The reader's place is the foot of the zone; what they just read should
stay put above it until it is the transcript's. A row that vanishes and
comes back, or half a row, reads as a fault.

## What would make us reverse it

Short sentences taking too many lines of the zone, each on its own:
then captions run on again only where the one before is still in the
zone, with the reflow at its handoff solved.

## How we'd reverse it

`zone_look`'s `run_on` back to True; `_place_zone` without `needed`.
