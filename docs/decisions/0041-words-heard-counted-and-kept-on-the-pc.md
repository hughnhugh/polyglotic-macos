# 0041 What the learner heard, counted on the PC: coverage, listening, first heard, and daily counts kept 8 weeks

- **Status:** accepted (a default, reversible: polyglotic-hq DECISIONS.md #64 is the user's to decide)
- **Date:** 2026-11-07
- **Decided by:** polyglotic-hq project 163, building 155's design (DESIGN.md 3.1-3.2, 8.1, 8.3) on the defaults DECISIONS.md #64 took while the user decides: "build the counting and Words' numbers; daily counts kept 8 weeks on the PC". Claude reviews it with the pull requests.

## Situation

Words is to show what the learner heard: coverage of the last 7 days,
listening time, words met by band, and words new this week (155). Until
this change the PC kept only totals per entry. Each finished UTC day's
counts per entry (`daily_exposures`) were handed over once - shared if the
learner opted in, dropped if not - and **forgotten either way**, so no
per-day view was possible. Nothing kept tokens per caption (no coverage),
listening time (only the session's summary, sent and forgotten), or when a
word was first heard.

## Decision

The learning store (decision 0010) gains, all on this PC and never sent:

- **version 3, `daily_coverage(day, known, deck, new)`:** each UTC day's
  tokens of finished captions from what the PC played, by the learner's
  status as each caption finished (#227).
- **version 4, `daily_listening(day, category, seconds)`:** listening with
  captions on, from the gaps between finished captions, by source
  category - never an app's name (#232).
- **version 5:** `exposures.first_heard` (the UTC day an entry was first
  heard from what the PC played; NULL for words heard before), and
  `handed_over_days(day)`. **A finished day's counts are handed over once,
  as before, then marked handed over and kept - not deleted - until
  they're 8 weeks old (`KEEP_DAILY_WEEKS`), then deleted.** What leaves the
  PC is unchanged: the same days, once, only with the learner's tick.

Coverage and listening are one row a day (or a few) and aren't expired:
they're what the coverage curve and the calendar (after launch) draw.
"Delete learning data" deletes all of it.

## Why

- The weekly view ("new this week", "most heard, still new", 155's Monday
  note and calendar) needs per-day counts on the PC; 8 weeks covers the
  views planned (the curve's 12 weeks needs only coverage, not counts per
  entry). Kept per entry, 8 weeks are a few MB: measured through the
  adapter on 2026-11-07, 1.1 MB at 500 different entries a day and 4.3 MB
  at 2,000 (polyglotic-hq `projects/163-words-heard-counting/work/size_163.py`).
- Marking a day handed over rather than deleting it keeps the hand-over
  exactly once - a late change to a handed-over day (a withdrawal just
  after midnight) is kept here, not handed over again. Before, such a
  change made a new row that was handed over as a second, partial count
  for the same day.
- `first_heard` as a column, not derived from daily counts: daily counts
  go after 8 weeks; when a word was first heard shouldn't.
- Not considered further: keeping daily counts forever (more than the
  views need, and more to delete); a separate store file (one file,
  decision 0010).

## What would make us reverse it

- **The user decides DECISIONS.md #64 the other way** (no per-day counts
  kept on the PC), or testers find keeping them unwelcome.
- Measured size or write cost on a heavy listener's PC well above the
  estimate.

## How we'd reverse it

- **Back to forgetting at hand-over:** set `KEEP_DAILY_WEEKS` to 0 - the
  next hand-over deletes every handed-over day, and every later one is
  deleted as it's handed over. One constant and its test
  (`test_daily_counts_stay_on_the_pc_8_weeks_once_handed_over`); the table
  `handed_over_days` stays, empty. The views that need per-day counts
  (after launch) would then have nothing to show.
- **A different length:** change `KEEP_DAILY_WEEKS`; nothing else moves.
- **Drop `first_heard`, coverage or listening:** stop writing it and stop
  showing it; the column or table can stay (migrations only add).
