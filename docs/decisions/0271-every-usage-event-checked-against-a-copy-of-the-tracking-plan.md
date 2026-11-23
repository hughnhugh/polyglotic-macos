# 0271 Every usage event the app can send is checked against a copy of the server's tracking plan

- **Status:** accepted
- **Date:** 2026-11-20
- **Decided by:** polyglotic-hq project 566 (Claude's item, 562's top
  next); Claude reviews it with the pull request.

## Situation

polyglotic-server keeps a usage event only if its name, version, every
property and every value are in its tracking plan
(`docs/tracking-plan.yaml`); anything else drops the whole event. The
plan lives in the server repo, so nothing in this repo's CI read it.
Decision 0246 renamed the caption modes, the app started sending
`caption_mode: words` and `calm`, and every Steady and Calm session
summary was dropped until polyglotic-hq 556 and 562 found it by hand
(562's `dump562.py` and `check562.py`). `caption_timeline_summarised`
(decision 0255) was merged here before the server's plan had it (server
#343).

## Decision

- **A copy of the plan in `tests/tracking_plan/`**, written only by
  `tools/tracking_plan.py copy <server checkout>`, as decision 0011 keeps
  the protocol examples: it reads the server's `origin/main` through git
  and writes `MANIFEST.txt`, the server's commit and the file's SHA-256.
  `check` says whether the copy is current.
- **`tests/test_usage_events_fit_the_plan.py`** lists every property and
  value the app can send, from its own enums and builders rather than by
  hand: the session summary's every field through
  `listening.session_ended` (its text fields from `CaptionMode`,
  `CaptureMode`, `SourceCategory` and both known-apps lists, a new text
  field failing until it says where its values come from), the caption
  timelines through `listening.timeline_summarised` with every segment
  and hang cause, `source_selected` for every mode and category,
  `line_flagged` for every language, outcome and answer, and the
  install's milestones as the outbox keeps them, on every OS and channel.
  Each is checked as the server's `problems()` checks it.
- **What the server is adding in an open pull request waits** in
  `WAITING_FOR_THE_SERVER`, named by that pull request, so a desktop
  change can merge before the server's (the app's release still waits
  for the server's deploy). A refreshed copy that closes one fails the
  test until it is taken out, so the list stays what still waits.
- **Keeping it current:** whenever the server's plan changes, `copy`, then
  make the test pass. The first entries are this project's restart
  counters (server #350).

## Why

- The failure is silent on both sides: the app sends, the server drops,
  and the numbers just look low. Only a check before merging catches it.
- A copy needs no credential in CI, as for the protocol examples
  (decision 0011); the manifest keeps it a real commit of the server's
  plan.
- Values from the app's own enums and builders, not a list kept by hand,
  mean a new caption mode, capture mode or known app is checked the day
  it's added.

## What would make us reverse it

- The copy is found stale when it mattered: the app released with an
  event the server's plan had already changed.
- CI can read the server repo (a credential becomes cheap to keep):
  then check against the server's plan directly.

## How we'd reverse it

Delete `tests/tracking_plan/`, the tool and the test; nothing in the app
depends on them. To read the server's plan in CI instead, point
`tools/tracking_plan.py check` at a checkout of it, as decision 0011's
reversal says for the examples.
