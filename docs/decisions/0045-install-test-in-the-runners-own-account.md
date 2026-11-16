# 0045 The install-and-update test runs by hand in the PC runner's own Windows account, then uninstalls

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** the user, 2026-11-06 evening (polyglotic-hq
  DECISIONS.md #39, "safe defaults"): "the install-and-update loop runs
  once - in the runner's own account if the installer works without a
  desktop session, otherwise with the user at the PC during the first
  real run". Built by polyglotic-hq project 225 before the first tag,
  v0.1.0 (2026-11-12). Replaces, for runs by hand, decision 0025's
  "`package.yml` doesn't install the build on the PC".

## Situation

- **Package's install-and-update test** runs `Setup.exe --silent`, checks
  the installed copy, and has it find and download the next version from
  a feed published over a folder. It is the loop friends will go through.
- It ran only on GitHub's own runner, last on 2026-11-05 (run
  41960837167). GitHub's minutes then ran out. On 2026-11-08 a run was
  refused: "the job was not started because ... your spending limit needs
  to be increased".
- **Decision 0025 kept it off the PC** because the Windows runner then
  ran as the user, so the test would have installed into their own
  account. Since 2026-11-06 each Windows runner is a service under its own
  standard account (`polyglotic-runner`, `polyglotic-runner2`; 0025's
  amendment).
- **0025's own reversal signal** has come: "a release that needs the
  install test and no Actions minutes to run it".

## Decision

- **By hand only.** Package by hand, with `install_here` ticked, runs
  the install-and-update test on the PC's runner. It never runs on a push
  or in a release.
- **Never in the user's account.**
  1. The job first checks it runs as `polyglotic-runner` or
     `polyglotic-runner<digit>`. Anything else fails before anything is
     installed.
  2. Velopack's own `Update.exe uninstall --silent` then removes the
     install, even when an earlier step failed. It runs only if that check
     passed, so a job in the user's account can neither install nor
     uninstall their copy.
- **The same steps as on GitHub's runner,** in the runner account's own
  `%LOCALAPPDATA%\Polyglotic`, shortcuts and list of installed apps,
  none of them the user's.
- A test (`tests/test_workflows.py`) holds:
  - the check runs first;
  - the two installing steps' conditions;
  - the uninstall's condition;
  - `install_here` is off by default.

## Why

- **The release isn't the first time the loop runs since 2026-11-05.**
  The friends' first install (the alpha, 2026-11-16) and the user's own
  loop on the tag's day (2026-11-12) come after a run on the PC.
- **No money:** GitHub's minutes need a spending limit; the PC's runner
  is free.
- **Nothing reaches the user's profile.** The runner's account is a
  standard account outside it (polyglotic-hq `scripts/RUNNERS.md`).
- **By hand, not on every push:** about 20 installs and uninstalls a day
  in the runner's account would add minutes to every main build. Its
  leftovers, if an uninstall ever failed, would build up.
- **Not taken:**
  - GitHub's runner with a spending limit (money, the user's call);
  - waiting for the user at the PC (#39's fallback, kept for when the
    installer needs a desktop session).

## What would make us reverse it

- The installer needs a desktop session the runner's service doesn't
  have: `Setup.exe` hangs or fails in the runner's account. Then #39's
  fallback applies: the user at the PC, on the tag's day.
- An uninstall leaves files behind in the runner's account, run after
  run. Then clean it by hand, or move the test to a throwaway VM.
- The runner going back to the user's account (0025's amendment
  reversed). Then the account check fails the job, by design.

## How we'd reverse it

Remove `install_here` and its two extra steps from `package.yml`, and
put the two installing steps' `if:` back to `runner.environment ==
'github-hosted'`.
