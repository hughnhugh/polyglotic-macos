# 0072 The account's cohort is known the moment a code signs in

- **Status:** accepted
- **Date:** 2026-11-11
- **Decided by:** polyglotic-hq project 279's brief (from project 275's
  report, its "next" projects), 2026-11-11. Claude reviews it with the
  pull request. Replaces what decision 0067 said about where the cohort
  comes from ("with every session's `welcome`").

## Situation

Decision 0067 gives alpha testers "Report a problem" with everything
attached, and turns their diagnostics on, by the account's cohort - which
the app learned only from a session's `welcome`. Until the first one, a
tester who had just signed in got the old feedback form, and their usage
statistics and crash reports stayed as the first run's screen left them.
The redeem answer (`POST /v1/redeem`, protocol.md "Signing in") carries
the cohort already, and the app dropped it.

## Decision

- **The redeem answer's cohort is applied as `welcome`'s is**
  (`main.cohort_known`): kept in the settings (`cohort`), the caption
  windows' "Report a problem" shown to a tester, and a tester's
  diagnostics on.
- **Where:** each code that signs in - the first run's (applied once the
  rest of the app is built, right after the first run's consent choice is
  recorded), the sign-in over the window, and a Plus email's code signed in
  (whose answer is the account's own cohort). `main.SignedInCohort` hands
  it from the sign-in thread to the interface's.
- `welcome` still says it on every session, and still wins: the cohort an
  account has can change between sign-in and the next session.

## Why

- Friends connect as soon as the live server is up; their first problem
  report should be the tester's window, from the first minute.
- No protocol change: the answer has carried `cohort` since version 1.

## What would make us reverse it

The redeem answer stops carrying the cohort, or carries one that isn't
the account's.

## How we'd reverse it

Drop `SignedInCohort` and its three `take()` calls in `main`: the cohort
comes from `welcome` alone again, as decision 0067 first said.
