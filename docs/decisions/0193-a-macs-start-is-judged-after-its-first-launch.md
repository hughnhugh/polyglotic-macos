# 0193 A Mac's start is judged on the launch after its first

- **Status:** accepted
- **Date:** 2026-11-16
- **Decided by:** Claude (polyglotic-hq 419), a reversible tooling choice
  inside the agreed start budget (DECISIONS.md #53)

## Situation

The packed app's build launches it once with `--check-install` and fails
if the main window takes longer than `START_PACKED` (1000 ms) from the
launch. On GitHub's Mac (polyglotic-hq 419's run 1, 2026-11-16) the first
launch of the newly signed `Polyglotic.app` took 1.775 s. A newly signed
app's first launch on a Mac includes macOS' own first look at it:
Gatekeeper's assessment and the checking of every code page's signature
as it loads. That happens once per build on each Mac, not on the
learner's everyday starts.

## Decision

On a Mac, `tools.package.build` launches the packed app's check twice
(`settled_check_install`): the first launch settles it and is kept in the
report as `first_launch` (its time reported, not judged; it must still
exit cleanly), and the second launch is judged against `START_PACKED`.
Windows launches once, as before.

## Why

The budget is about the wait a learner has when they start the app, and
on a Mac that's the second launch onwards. Judging the first would fail
every build on the OS's one-time work, or push the budget up for
everyone. The alternatives: a larger Mac budget (hides a real slowdown in
the everyday start), or no start check on a Mac (loses the regression
guard).

## What would make us reverse it

If testers' Macs show that the first launch after each update is what
learners notice (every update is a newly signed app, so it's a first
launch), the first launch would need a budget of its own.

## How we'd reverse it

`settled_check_install` returns `check_install`'s result for both
layouts, or judges `first_launch` against a budget of its own: a few lines
in `tools/package/build.py` and its test.
