# 0025 CI runs on self-hosted runners on the user's PC

- **Status:** accepted; "`package.yml` doesn't install the build on the PC"
  replaced, for runs by hand, by
  [0045](0045-install-test-in-the-runners-own-account.md) (in the runner's
  own account, then uninstalled)
- **Date:** 2026-11-06
- **Decided by:** the user, 2026-11-06 ("lets do the self-hosted runner",
  polyglotic-hq DECISIONS.md, "Blocking", option A); set up by
  polyglotic-hq project 069. Changes where
  [0021](0021-installer-built-on-main-not-pull-requests.md)'s build runs,
  not when: it still runs on `main`, by hand and for a release, not on
  pull requests.

## Situation

GitHub Actions stopped starting jobs on 2026-11-05: the private repos'
$12 of free minutes a month went in about 19 hours (polyglotic-hq project
055). Since then every pull request has been checked on the PC by hand
(polyglotic-hq `scripts/local_ci.sh`), with no checks on GitHub.

## Decision

Every job runs on a GitHub runner on the user's PC, at no Actions cost:

- **Windows jobs** (`[self-hosted, windows]`: the checks, the dependency
  audit, the installer build, a release's publishing) on the official
  runner in a folder under the user's profile, running as the user - not
  as a service, no admin - started at logon from the Startup folder.
- **Linux jobs** (`[self-hosted, linux]`: the secret scan, the feed
  check, a release's tag check) in a Docker container: the official
  runner image pinned by digest, its non-root user unable to become root,
  no Docker socket, no folders from the PC.

Tools come with the job, never installed on the PC: uv by `setup-uv`,
Python by uv, the .NET SDK for `vpk` by `setup-dotnet` into the runner's
own folder (its default, Program Files, needs admin). A release still
builds without a uv cache (`UV_NO_CACHE`), as on GitHub's runners.

**`package.yml` doesn't install the build on the PC.** Its install and
update test (`Setup.exe --silent`, then the installed copy finding the
next version) would install a test build into the user's own Windows
account - `%LOCALAPPDATA%\Polyglotic`, shortcuts, the list of installed
apps - so those two steps run only on GitHub's own runner: Actions >
Package > Run workflow with "github_hosted" ticked (it uses Actions
minutes). Everything else in it - the build, the pack, the feed published
over a folder, checked and signed - runs on the PC.

The setup, and how to stop, update and remove the runners, are in
polyglotic-hq `scripts/RUNNERS.md`. `scripts/local_ci.sh` stays as the
fallback when the PC is off or a runner is down.

**Outside contributors' pull requests never run here** (polyglotic-hq
project 066, Medium 2): on the Windows runner a pull request's code runs
as the user, with everything the user can reach. That holds while every
author is the user or Claude's agents and the repository is private.

## Amendment, 2026-11-06: Dependabot's pull requests skip the Windows jobs

A Windows job runs as the user, and Dependabot's weekly pull requests would
run there with no human first (polyglotic-hq project 074, finding 1): a
compromised release of a dependency would run with the user's credentials.
Until the runner has its own standard Windows account (polyglotic-hq
DECISIONS.md #38), `ci.yml`'s and `audit.yml`'s jobs skip Dependabot's pull
requests (`if:` on the actor and the pull request's author). GitHub shows a
skipped job as "Skipped", and a required check from a skipped job counts as
passing, so the pull request is not blocked, but nothing has checked it: the
user runs `scripts/local_ci.sh` on it, or reads it, before merging. The
secret scan stays: it runs in Docker. The daily feed check no longer needs
`gh` (the Linux image has none): it reads the GitHub API with `GH_TOKEN`.
Remove the `if:` lines when the account exists.

## Amendment, 2026-11-06 (evening): the runner has its own account

The Windows runner now runs as a Windows service under its own standard
account (`polyglotic-runner`: not an administrator, not in `docker-users`,
no `gh` login, no WSL distribution), from `C:\polyglotic-runner\win`,
outside the user's profile (polyglotic-hq `scripts/runner-account.ps1`,
DECISIONS.md #38, run by the user). A pull request's code no longer runs
as the user, so the `if:` lines that skipped Dependabot's pull requests are
removed: its updates are checked on the PC again. Outside contributors'
pull requests still never run here.

## Why

- Free and unlimited, with the green ticks back on GitHub.
- Alternatives (055): a spending limit (about $11-12 a busy day at
  2026-11-05's pace); local checks for good (no checks on GitHub, run by
  hand one at a time); waiting for the monthly reset (down most of the
  month).
- The Windows runner as the user, not as a service: no admin, and the
  same as `local_ci.sh`, which already runs the checks as the user.

## What would make us reverse it

The repository going public or taking outside contributors (open source,
DECISIONS.md #33); checks that queue too long because the PC is off or
busy (GPU tests); a release that needs the install test and no Actions
minutes to run it; or a paid plan that makes hosted minutes cheap.

## How we'd reverse it

`runs-on: windows-latest` / `ubuntu-latest` again in the six workflows (a
line each; the `setup-dotnet` steps and the `github_hosted` input can
stay or go), then remove the runners as `scripts/RUNNERS.md` says.
Minutes.
