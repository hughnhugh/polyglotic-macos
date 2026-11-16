# 0024 Caption timing is a mode the learner picks - Steady by default - and the rules' own defaults stay the proof of concept's

- **Status:** accepted; its default (Steady) replaced by [0037](0037-quick-preview-by-default.md)
- **Date:** 2026-11-05
- **Decided by:** the user accepted Steady as the default with Quick
  preview as the other choice (polyglotic-hq DECISIONS.md #4,
  2026-11-05); polyglotic-hq project 064 wired it; Claude reviews

## Situation

Project 033 added the timing options (a shorter hangover, breath cuts,
one glimpse, joins only onto fragments) to `TimingRules`, all off by
default, and projects 021, 037 and 046 measured every capacity and cost
figure with two sets of them: Y (Steady) and Z (Steady with a preview).
The app still ran the proof of concept's timing - live updates every
1.5s, a 0.8s hangover, whole-run joins - which 021 found the biggest
waste (project 062). Settings saved by earlier versions hold a
live-update interval (1.5s by default, or "Off"), never a mode.

## Decision

- `core.listening.timing.CaptionMode`: **Steady** (the default), **Quick
  preview** and **Live updates**, each a set of `TimingRules` plus a
  live-update interval (none; 1.5s; the learner's). All three join only
  onto a caption under 2s (`FRAGMENT_SEC`). The app always runs a mode's
  rules; `CaptionTiming.change` switches them mid-session.
- `TimingRules()`'s defaults stay the proof of concept's: the rule cases,
  the timing tests and polyglotic-server's bench (`--joins today`, the
  0.8s hangover by default) are written against them.
- Settings: `caption_timing` (`steady` / `preview` / `live`). Settings
  saved before modes existed get one from their interval: the old default
  (1.5s), "Off" or anything not valid is Steady; any other interval was a
  choice, so it is kept, with Live updates. The interval list loses "Off"
  (that's Steady now).
- Only Live updates asks the server to translate live updates; Quick
  preview's line is what was said only.

## Why

- A mode is what the learner chooses between (049's wireframes, 7.3;
  DECISIONS.md #4's tiers name the same three) - not a dozen options.
- Every saved file holds an interval, so only a changed one shows a
  choice; carrying 1.5s forward as Live updates would keep everyone on the
  costly timing the user decided against.
- Not taken: changing `TimingRules`' defaults to Steady's. Every timing
  test, the rule cases and the bench would change meaning at once, for no
  gain - the app never used the defaults as they were.

## What would make us reverse it

The user's first real runs (TESTING.md) or the alpha's `caption_mode`
statistics show a mode isn't wanted, or the rules move to the server
(protocol v2), where the mode becomes a setting the app sends.

## How we'd reverse it

Change `_MODE_RULES` (one table) or drop a mode: the settings key reads
leniently, so an unknown stored mode falls back to Steady. Moving the
rules to the server moves `CaptionMode` with them; the page's choice
stays.
