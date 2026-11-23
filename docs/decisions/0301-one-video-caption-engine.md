# 0301 One Video caption engine

- **Date:** 2026-11-23
- **Status:** for review

## Situation

Project 725 follows the 2026-11-23 preview report. Switching to Video
played existing captions again, and interactions could restore the
centred subtitle layout. This decision supersedes the centred and depth layouts
in items 2 and 3 of decision 0282.

## Decision

Video captions use the geometry and motion of the agreed simulation
engine in HQ project 686. The live view starts with captions received
after entering Video. The transcript still retains earlier captions
for browsing. Browsing shows fixed-size, left-aligned captions using
Video's own layout. Appear and reduced-motion settings use the same
renderer with animation disabled.

Video offers Instant and Delayed translation. Instant introduces
original and translated words individually, at a faster cadence than
Steady. Delayed translation shows the translation after the original
finishes. The newer Instant cadence supersedes the simulation's
packet-sized text arrivals. The original motion comparison still
uses the agreed engine's inputs to check the port independently of
the cadence.

## Reversal

If a later preview changes the motion or timing, revise the Video
module and the reference together. The caption history, caption
protocol, and other presets' arrival rules remain independent.
