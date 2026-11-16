# 0050 One job builds a release and publishes it: nothing goes through GitHub's artifact storage

- **Status:** accepted; replaces two points of
  [0018](0018-release-workflow.md): "the release workflow calls
  [package.yml]", and "`contents: read` everywhere but the publish job"
  (now the one release job)
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq DECISIONS.md #98's default, option A,
  "keep $0, and make the release not need artifact storage" (the user's
  $0 limit, 2026-11-08 ~18:30); the choice between the two ways it named,
  polyglotic-hq project 244. Claude reviews it with the pull request.

## Situation

- GitHub's artifact storage (0.5 GB a month on the free plan, shared by the
  three repos) was full on 2026-11-08 and stays full until the cycle resets
  on 2026-12-01. The account's $0 limit blocks uploads rather than billing
  them (DECISIONS.md #98).
- `release.yml` built in one job (package.yml, called as a workflow) and
  published in another. The build reached the publish job only as an
  artifact, about 160 MB. A promotion handed its repacked build over the
  same way. So `v0.1.0` (Thursday 2026-11-12) would have failed at that
  hand-over, as 225's dry run did on 2026-11-08 ("Artifact storage quota
  has been hit").
- DECISIONS.md #98 named two ways out:
  - build and publish in one job;
  - or upload the build straight to R2 from the build job, and have the
    publish job read it from there.

## Decision

- **One job, `release`, builds (or promotes) and publishes.** It runs on the
  Windows runner and takes everything the upload and the GitHub Release need
  from its own disk:
  - a release, a hotfix or a dry run is built from source;
  - a promotion downloads the tag's recorded build from its GitHub Release
    and repacks it (decision 0044, unchanged);
  - its publishing steps (`publish.sh`, the public feed's check, the GitHub
    Release) run on a tag only;
  - a step every run takes, dry runs included, checks that each file the
    publish takes is there and not empty.
- **The build's steps are written once**, in `.github/actions/build-and-pack`
  (dictionaries, PyInstaller, `vpk pack` through `pack.sh`, and the
  promotion rehearsal when asked). Package runs the same action on main, so
  main's check is how a release is built. Package now has its own triggers
  only (no `workflow_call`), and its path filter includes the action, so
  `tools/release_check.py` sees a change to it.
- **The job may write** (`contents: write`, as the publish job could) and
  takes the `release` environment on a tag only:
  `environment: ${{ github.ref_type == 'tag' && 'release' || '' }}`. So a
  dry run on a branch needs no deployment to the environment, which is
  limited to `v*` tags. The R2 and signing secrets still reach only the
  upload step's environment variables.
- **Package's own uploads may fail** (`continue-on-error`): nothing a release
  needs comes from them, and a full storage mustn't fail Package on main,
  whose result is release check item 1.
- Enforced by tests (`tests/test_workflows.py`):
  - release.yml has no upload-artifact or download-artifact step and calls
    no workflow;
  - one job holds the build, the promotion, `publish.sh` and
    `gh release create`;
  - Package and the release both build through the shared action, and
    neither runs `tools.package.build` itself;
  - every upload in Package is `continue-on-error`.

## Why

- **It works on Thursday whatever state R2 is in.** Until the user creates
  the `release` environment and its R2 secrets (planned Mon-Tue
  2026-11-09/10), a tag's run builds and records a draft Release, as 0018
  intended. Uploading the build to R2 from the build job would need those
  secrets before any of that could run, and a dry run on a branch couldn't
  rehearse it at all, since the environment is limited to tags.
- **No staging copy in a public bucket.** The R2 bucket is served at
  `updates.<domain>`, so a build staged there before its checks would be
  public, or would need a second bucket and token.
- **On this runner, the second job's separation was mostly nominal.**
  - Both jobs ran on the same self-hosted Windows runner, as the same user,
    on the user's PC (decision 0025).
  - The publish job already ran `uv sync` of the app's locked dependencies
    and `uv run` with the R2 secrets in its environment.
  - What one job adds: PyInstaller and the dictionary build now run while
    the job's token may write this repo's Releases. They never get the token
    in their environment, and the checkout keeps no credentials.
- **A GitHub Release is the record, not the hand-over.** Release assets
  don't count against Actions storage. The build, its SHA-256s and each
  channel's installer and feed were already recorded there (0044). A
  promotion already read its build from there, and still does.
- **Not taken:**
  - a small Actions budget (DECISIONS.md #98's option B), which leaves the
    release depending on a store that has filled twice in three days;
  - handing the build over in a folder on the runner outside the job's
    workspace, which works only while there is one Windows runner and
    leaves 160 MB behind that someone must clear.

## What would make us reverse it

- The release moves to a runner that isn't the user's PC (GitHub-hosted, or
  a machine of its own), where a second job is real isolation. Or code
  signing arrives (paid launch) with a signing key that the build's
  dependencies shouldn't share a job with.
- The artifact storage has room to spare (a paid plan, or a budget). A
  separate build job then costs only the hand-over's minutes.

## How we'd reverse it

- Split `release` into a build job, which runs the same action (or calls
  Package again), uploads `releases/` and `build/package/SHA256SUMS` with
  `retention-days: 1`, and a publish job that downloads them: the layout
  before this record, in git history at 2026-11-08's
  `.github/workflows/release.yml`.
- The publishing steps don't change; `test_workflows.py`'s first test would
  go with it. About an hour, plus a dry run.
