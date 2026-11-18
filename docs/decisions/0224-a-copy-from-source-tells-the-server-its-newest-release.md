# 0224 A copy run from source tells the server the newest release its notes name

- **Status:** accepted
- **Date:** 2026-11-18
- **Decided by:** polyglotic-hq project 483 ("make sure the open source
  version connects to the server", the user, 2026-11-18); Claude reviews
  it with the pull request. Amends what 0015 says a copy from source tells
  the server; 0015's stamp is unchanged.

## Situation

The app's source is public (https://github.com/hughnhugh/polyglotic-app,
Apache-2.0). A developer who builds it runs it from source, with no
`release.json`, so the app was `0.0.0` (decision 0015) and said so in
`hello` and at sign-in. The live server's minimum is `0.1.0` (asked from
outside on 2026-11-18: a `hello` at `0.0.0` on `win-x64-alpha` and on
`macos-arm64-alpha` got `update_required`, `min_app_version` `0.1.0`), so a
copy built from the public source could sign in but never caption. A copy
from source can't update itself, so it was stuck.

## Decision

- **A copy run from source tells the server the newest release its
  `RELEASE-NOTES.md` names** (`## 0.1.7 - 2026-11-17` -> `0.1.7`), on its
  OS's first channel - in `hello`, at sign-in, in feedback and problem
  reports (`AppInfo.this_app`, `connection.app.source_version`, the
  domain rule in `core.releases.notes.newest_released`). With no notes, or
  none released, it stays `0.0.0`.
- **Inside the app nothing changes:** the copy's own release
  (`this_release`) is still `0.0.0` from source - Settings > Updates, what's
  new, the dictionary packs (any `min_app` from source) and the
  apps-one-by-one trial read it, not what the server is told.
- **A release build** tells its stamp, as before; a broken stamp is still
  `0.0.0`, so the server asks for an update (0015).
- **No server change:** the minimum stays the server's lever. When it rises
  past the newest release a copy's notes name, that copy is refused until
  it's brought up to date - the same as an installed app that hasn't
  updated.

Tests: `tests/test_app_info.py` (the notes' newest release from source, a
stamp wins, a broken stamp is `0.0.0`, this repo from source tells a
released version) and `tests/releases/test_notes.py`.

## Why

- **The question the minimum asks is "does this app speak what I need?"**
  Code holding a release's changes speaks at least what that release does.
  `0.0.0` said "older than every release", which a copy of main never is.
- **RELEASE-NOTES.md is already kept at every release** (the notes cut), is
  in every clone - the private repo and the public copy alike - and needs
  no git history, which the public copy hasn't got. Nothing new to keep in
  step.
- **Not taken:**
  - *A version file written by the public copy's script* - only the public
    copy would have it, a stamp in the source tree would make the copy a
    "release" to the app (packs, what's new) and break the tests that
    expect none, and it's one more step to forget.
  - *A `dev` channel the server accepts at any version* - a protocol change
    (the server's `hello` refuses a channel it doesn't know), a server
    deploy first, and a way round the minimum for anyone who says it.
  - *A minimum of `0.0.0` on the live server* - would let every old
    installed app in too.

## What would make us reverse it

- The server needs to tell source builds from releases (their numbers, a
  fault only source builds have): then `hello` gains an optional field
  saying so (a protocol addition, server first) - the version stays.
- A copy from source that is older than its notes say (notes edited by
  hand ahead of the code).

## How we'd reverse it

`AppInfo.this_app` goes back to `this_release().version`, and its tests and
`test_sign_in`'s expectation back to `0.0.0`: under an hour.
