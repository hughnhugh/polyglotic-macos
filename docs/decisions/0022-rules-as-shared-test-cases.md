# 0022 The app's rules are written down as shared test cases, in JSON, for any later port to pass

- **Status:** accepted
- **Date:** 2026-11-05
- **Decided by:** polyglotic-hq project 051 (brief item 8, from project
  050's "code now" list, under the user's "build with mobile in mind",
  2026-11-05); Claude reviews

## Situation

The rules that decide what a learner sees are in Python here: the
live-update timing rules, the level curve, highlights, the Chinese word
split and the caption display rules (about 1,300 lines of `core`). A
phone app (project 050: Kotlin Multiplatform, Android first) would write
them again, and protocol v2 may move the timing rules to the server.
Rules written twice drift apart unless both are held to the same answers,
and the answers are cheapest to write down while the rules are fresh.

## Decision

- `docs/rule-cases/` holds JSON cases - inputs and the answers this app's
  rules give - for those five rules, with a README saying how to read each
  file (the timing cases' frame rule, caption ids, units, rounding).
- The inputs are the ones this repo's tests of each rule use; the answers
  are written by `tools/rule_cases.py` (`write`, `check`).
- `tests/test_rule_cases.py` reads only the JSON and checks this app's
  rules against it, and fails if the files aren't what the tool writes -
  so a rule changed on purpose means rewriting them, and the diff shows
  every answer a port must follow.
- A port copies the files (as this app copies the server's protocol
  examples, decision 0011) and runs its own rules on them.

## Why

- The same idea as the protocol examples: data both sides test against is
  the cheapest contract between two implementations.
- Answers written by the tool, not by hand: there are hundreds of
  numbers (the timing cases alone record every live update), and the
  existing tests already assert the meaningful properties; the cases add
  the exact answers.
- Not taken: one shared rules library (e.g. the rules in Kotlin, called
  from Python): a bigger change than the phone app needs yet, and the
  desktop would depend on a second language now.

## What would make us reverse it

- A shared implementation of the rules (one library both apps use): the
  cases would then test that library instead, or go.
- The cases changing with almost every rule change and no port reading
  them: the cost without the benefit - drop the replay to the few rules a
  port exists for.

## How we'd reverse it

Delete `docs/rule-cases/`, `tools/rule_cases.py` and
`tests/test_rule_cases.py`; the rules' own tests are unchanged.
