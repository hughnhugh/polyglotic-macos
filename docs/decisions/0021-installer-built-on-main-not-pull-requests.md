# 0021 The installer is built and tried on main, not on every pull request

- **Status:** accepted
- **Date:** 2026-11-05
- **Decided by:** the user, 2026-11-05 ("yes go ahead" to far fewer
  GitHub Actions minutes, polyglotic-hq DECISIONS.md, "Blocking"); built
  by polyglotic-hq project 055. Replaces "on pull requests" in decisions
  [0016](0016-pyinstaller-one-folder-build.md) and
  [0020](0020-feed-signed-as-served.md): what `package.yml` checks is
  unchanged, only when it runs.

## Situation

GitHub Actions stopped starting jobs on 2026-11-05: the private repos'
free minutes ran out. Windows runners count twice, and `package.yml`
(PyInstaller, Velopack, installing the build on the runner, the feed
published to a folder and the update found from it) took about 3.5
minutes on every push to a pull request that touched `src/` - 4 minutes
billed, so 8 counted. From 2026-11-04 to 2026-11-05 it was about 480 of
the desktop repo's 1,650 counted minutes.

## Decision

`package.yml` runs on pushes to `main` that could change the build (the
same paths as before), when run by hand (Actions > Package > Run
workflow, on any branch), and when the release workflow calls it with a
tag. Not on pull requests. On `main` and by hand it does everything it
did on a pull request - installs the build on the runner, publishes it to
a folder standing in for the update storage, checks the merged and signed
feed, and has the installed app find and download the next version. A
newer push to `main` cancels the older build; a release is never
cancelled and never shares a group with a check.

A pull request that changes packaging (`tools/package/`, the workflow,
`pyproject.toml` or `uv.lock`) is built by hand before it merges -
`package.yml` on its branch, or polyglotic-hq's `scripts/local_ci.sh
desktop <number> --package`, which builds and packs on this PC without
installing.

## Why

- Most pull requests change the app's code, not how it's packed; the
  build has broken on packaging changes, not on ordinary ones. Building
  once per merge instead of once per push halves the cost or better (2-3
  pushes per pull request on 2026-11-04 and 2026-11-05).
- Not on release tags only: a break would then be found at release time,
  days later, with many merges to search.

## What would make us reverse it

A merge to `main` that breaks the build or the install and wasn't built
by hand first - more than once - or Actions minutes that no longer matter
(a self-hosted runner, a paid plan).

## How we'd reverse it

Put `pull_request:` with the same paths back in `package.yml`'s `on:` and
`github.event_name == 'pull_request'` back for the steps that install and
publish; a few lines.
