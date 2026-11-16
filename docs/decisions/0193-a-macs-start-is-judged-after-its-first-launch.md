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

**On GitHub's own Mac runner** (added 2026-11-16, polyglotic-hq 420; the
choice Claude made from 419's option B): the settled launch is reported and
held to a ceiling of 2.5 s (`GITHUB_MAC_CEILING_MS`, picked by
`start_limit_ms` when `RUNNER_ENVIRONMENT` is `github-hosted`), not to
`START_PACKED`. On the same code that VM's settled launch took 1.051 s
(419's run 2) and 1.627 s (run 3): its noise is more than half the budget,
so it can't tell a slow app from a slow VM. The ceiling still catches a
doubling, such as a heavy import on the start path. The 1000 ms budget is
unchanged for people's Macs and is measured on one (a person's Mac, not
the runner). The build's summary says which limit it judged against
(`start_judged_against_ms`).

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

The ceiling: `start_limit_ms` returns `START_PACKED` on every runner.
