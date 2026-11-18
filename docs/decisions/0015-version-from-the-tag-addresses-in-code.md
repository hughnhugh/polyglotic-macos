# 0015 A release's version comes from its git tag; the server and update addresses are constants in code

- **Status:** accepted; what a copy run from source tells the server is
  [0224](0224-a-copy-from-source-tells-the-server-its-newest-release.md)'s
- **Date:** 2026-11-05
- **Decided by:** polyglotic-hq project 035 (D5)'s brief, from the user's
  release plan (ENGINEERING.md, "Releases", 2026-11-04) and project 032's
  checklist for D5 (item 1); the mechanism chosen by project 035 on
  2026-11-05. Claude reviews it with the pull request.

## Situation

The app told the server it was `0.0.0` (the package's version in
`pyproject.toml`), so a default server, whose minimum is `0.1.0`, answered
`update_required`. Releases are built by a workflow started by a git tag
(`v0.1.0`). The installed app also needs the live server's address and the
update feed's, which must be `https://` on a domain we own - and the
domain isn't bought yet.

## Decision

- **The tag is the version.** The release build turns `v0.1.0` into
  `0.1.0` (protocol.md's `MAJOR.MINOR.PATCH`, nothing else) and writes
  `release.json` - `{"version": "0.1.0", "channel": "win-x64-alpha"}` -
  into the app it packs. `connection.app.this_release()` reads it; run
  from source there's no stamp and the app is `0.0.0` on `win-x64-alpha`.
  `pyproject.toml`'s version stays `0.0.0`: nothing reads it.
- **A stamp that can't be read** is logged and taken as `0.0.0`, which the
  server answers with `update_required`: a broken build updates itself
  rather than failing to start. The build refuses a bad version first.
- **The addresses are constants in code**, changed only by a reviewed pull
  request: `main.SERVER` (`https://api.<domain>`) and, with the updater,
  the update feed (`https://updates.<domain>/`). Until the domain exists
  they are placeholders on `.invalid`, a top-level domain that never
  resolves (RFC 2606), so a build made before then reaches no one.
  `--server` overrides the server for development.

## Why

- **One source of truth for a release:** the tag that starts the workflow
  names the version; nobody edits a file to match it, and a forgotten bump
  can't ship two builds with one number.
- **A data file, not package metadata:** stamping `pyproject.toml` in CI
  would make `uv.lock` stale, and `uv sync --locked` - a check on the
  release path (project 032) - would fail.
- **Addresses in code, not in the workflow:** a repository variable or
  secret could be changed by anyone holding the GitHub account without
  leaving a reviewed change behind; in code, every change of where the app
  connects is a pull request in history.

## What would make us reverse it

- Builds per environment (a test server for the alpha, the live one for
  the beta) - then the server address becomes part of the stamp, chosen by
  the channel.
- A second place that needs the version (crash reports, the feedback
  form): read it through `this_release()`, not another way.

## How we'd reverse it

The stamp is written in one place (the release build) and read in one
(`connection.app.this_release`); moving to package metadata, or adding
fields, is an hour. Changing the addresses is a one-line pull request each,
once the domain exists.
