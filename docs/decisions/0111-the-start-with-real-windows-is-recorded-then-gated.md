# 0111 The start a learner sees is recorded in CI with real windows, and gated once it holds steady

- **Status:** accepted (reversible; adds to decisions 0046, 0103 and 0106)
- **Date:** 2026-11-14
- **Decided by:** polyglotic-hq project 322 (the user, 2026-11-14, DECISIONS #140: "ideally we keep the app performant as we keep developing rather than retroactively address performance"; brief: "a real-windows start on a private desktop on the runners, its parts recorded as #570 does, first recorded beside main's, then gated at the budget once it holds steady"). Claude reviews it with the pull request. No budget is set or changed here: the budgets for this start are the user's to accept (decision 0031).

## Situation

The start gate (decision 0046) times `main()` to the window's first paint
offscreen: 290-370 ms at every release, against a 400 ms budget. Offscreen
skips most of what a learner's start is. Measured by 322 on the runners' PC
(a Ryzen 7 9850X3D), 12 starts each in shuffled turns, the PC 30-46 % busy:

| Commit | Offscreen | Real windows | Then until a click is answered |
|---|---|---|---|
| 2026-11-08 (b2584f4c) | 292 ms | 790 ms | 250 ms |
| 0.1.0 (f07746df) | 352 ms | 827 ms | 228 ms |
| 0.1.4 (9fb2c0ca) | 355 ms | 872 ms | 228 ms |
| main (9f00d852) | 294 ms | 744 ms | 240 ms |

The 450 ms between the two columns was there from the first day the start
was timed, and nothing measured it:
- Windows' fonts, read by Qt the first time a font is used (about 100 ms)
  and again, family by family, the first time a font list needs a fallback
  (about 200 ms);
- the first native window (about 110 ms).

After the paint the window can't answer a click until the libraries the
window didn't need have finished importing: about 230 ms more.

## Decision

- **A second start is timed in CI:** `tests/ui/test_start_with_real_windows.py`, in the UI lab job after the gate. It runs `main()` with Qt's `windows` platform on a private desktop (`tools/private_desktop.py`), with the gate's learner (30,000 words met, the real CC-CEDICT), five starts.
- **It goes on past the paint** to the event loop's first turn: the first moment a click is answered (`TimedStart.answers_ms`). That start is signed out, so nothing is captured, and its server is an address nothing answers at.
- **Recorded as decision 0106 records the gate's parts:** each part beside main's last record on the PC, the grown ones marked, with `after_paint` as the part after the last. The record is its own file (`start-real-windows-main-<account>.json`).
- **Main's runs are kept, a row each** (`start-real-windows-history-<account>.jsonl`, the last 200): the time, the commit, the window, the whole to the answered click, and how busy the PC was. Each run prints the last 20 in a line.
- **Not gated yet.** The test fails only if a start never reaches its window, or paints and never answers.
- **Gated when both hold:**
  1. the user has accepted budgets for this start (the window painted; the window answering);
  2. main's last 20 runs on a calm PC (under 30 % busy, decision 0103) lie within 15 % of their median, for both numbers.

  Then the test holds the median of its five starts to each budget, judged as the gate is: a calm PC waited for, a try over on a busy PC taken again up to 4 tries, and "over on a busy PC" named (decision 0103).
- **A pull request that grows a recorded part says so,** and why, in its description: the reviewer reads the table on the run's page.

## Why

- **A private desktop, not the user's screen and not offscreen:** it makes real windows with Windows' own fonts and nothing reaches a screen (`docs/real-windows.md`). On the runners, which are services in session 0, the windows are made and painted but never shown by Windows; the fonts and the native windows are read and made the same way.
- **Recorded first:** nobody has seen this number on the runners yet. A gate set from one PC's afternoon would flap, as the offscreen gate did on 2026-11-13 (decision 0103), or be set too loose to mean anything.
- **To the first answered click, not only the paint:** a window that is painted and can't be clicked is not started. Moving work from before the paint to after it would otherwise read as a gain.
- **Not the first caption shown:** it needs a server, sound and a signed-in learner. The first caption's delay is measured by the server's own bench.
- **Alternatives not taken:**
  - **Gating at once at a loose number** (say 1,200 ms): it would pass every regression under 400 ms.
  - **Replacing the offscreen gate:** it stays the stricter check of the Python work, and runs anywhere.
  - **Timing the packed app with real windows:** the packed app takes the session's hotkeys and reads the account's own credentials; a packed start is timed offscreen by the build's own check (`START_PACKED`).

## What would make us reverse it

- The start on the runners (session 0) turning out not to follow a learner's: a cut that shows on a signed-in desktop and not there, or the reverse.
- The step adding more to the UI lab job than it is worth (it takes about 25 s).

## How we'd reverse it

Drop the step from `ci.yml` and the test file (minutes). `timed_start`'s
`real_windows` and the record's kinds can stay for use by hand, or go with
them (an hour).
