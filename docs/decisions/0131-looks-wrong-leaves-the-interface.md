# 0131 "Looks wrong?" leaves the interface; the protocol and the server keep the recheck

- **Status:** accepted; replaces the interface part of [0030](0030-looks-wrong-checked-with-the-best-model.md)
- **Date:** 2026-11-15
- **Decided by:** the user, 2026-11-15 ~06:55: "get rid of the looks wrong report button."; polyglotic-hq project 339's brief

## Situation

"Looks wrong?" (0030, project 101) let a learner send a finished line's
held speech to the server's best models and compare the two versions. It
was reachable four ways: a pill on a hovered finished caption in a
caption window, the same on a hovered transcript line, the transcript
line's right-click menu, and Ctrl+Alt+W (the newest finished line), which
Settings > App listed among the hotkeys. The user asked for it to go.

## Decision

- **Gone from the interface:** the caption window's and the transcript's
  hover pill, the transcript line menu's item, Ctrl+Alt+W (it is no
  longer registered with Windows, and Settings no longer lists it), and
  the comparison card (`ui/looks_wrong.py`) with the wiring in `main`
  that sent a line, counted a closed comparison and passed the answer on.
  Help's "What we keep" no longer names it.
- **Kept, unused by anything a learner can reach:** the protocol message
  (the binary recheck frame and `recheck_result`, owned by
  polyglotic-server's protocol.md) and the server's side; on this side,
  `core.listening.recheck`, the connection's `recheck` and
  `listening.recheck_frame` / `recheck_result` / `line_flagged`, the
  listener's `rechecked` (it now only logs the outcome), the session
  summary's `lines_flagged` count, the speech pipeline's `get` by caption
  id, and the "checked by the best model" display path
  (`CaptionFeed.use_checked`, the views' `use_checked`, a transcript
  line's mark). Whether to delete them is polyglotic-hq 339's report's
  question.
- Enforced by tests: `test_nothing_offers_looks_wrong` (the app has no
  card, no command and no tray item), the hotkeys test (L, P and H only),
  and the caption window's, transcript's and line menu's tests.

## Why

- The user's call (the words above; no further reason was recorded).
- The protocol and the server stay because the server is deployed first
  and the protocol is the server repo's (CLAUDE.md, "The protocol"); an
  app that never asks costs the server nothing.

## What would make us reverse it

- Learners asking for a way to say a caption was wrong, or the user
  wanting the best model's second opinion back - perhaps in another
  form (a menu item in the transcript only, say).

## How we'd reverse it

Revert the pull request that took it out (polyglotic-hq 339): the card,
the pills, the menu item and the hotkey come back as they were, and the
protocol and the server never changed. If the unused code is deleted
first (a second pull request), the revert takes that one too. About an
hour, plus the translations of the card's strings, which were dropped.
