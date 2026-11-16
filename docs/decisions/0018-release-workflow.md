# 0018 Releases are built, packed and published by a tag-only workflow, and the public feed is checked daily

- **Status:** accepted; what is recorded for the feed - the feed as
  served, not as built - replaced by [0020](0020-feed-signed-as-served.md);
  "one build per channel" replaced by
  [0044](0044-one-build-per-tag-promoted-not-rebuilt.md) (one build per
  tag, repacked for each channel; one GitHub Release per tag); the
  release calling package.yml, and a publish job of its own, replaced by
  [0050](0050-one-job-builds-and-publishes-a-release.md) (one job builds
  and publishes; nothing through GitHub's artifact storage)
- **Date:** 2026-11-05
- **Decided by:** the release plan - a version tag builds the app on
  GitHub (PyInstaller, then Velopack) and uploads it to Cloudflare R2
  behind our domain - the user, 2026-11-04 (polyglotic-hq ENGINEERING.md,
  "Releases"); its security: project 032's checklist for D5 (items 2-8),
  recommended to the user 2026-11-05 (DECISIONS.md #13). The workflows:
  project 035 (D5), 2026-11-05. Claude reviews them with the pull request.

## Situation

Whoever can run the release workflow, hold the upload token or change the
feed can put code on every tester's PC: the installer and feed aren't
signed yet (DECISIONS.md #13). The domain and the update storage don't
exist yet, so nothing can be published - but everything else can be built
and tried now.

## Decision

- **`package.yml`** builds and packs: PyInstaller (decision 0016), then
  `vpk pack` (Velopack 1.2.161, pinned in `.config/dotnet-tools.json` and
  kept equal to the `velopack` library by a test). On pull requests that
  could change the result, it also installs the build on the runner
  (`Setup.exe --silent`, whose first run is the self-check), and has the
  installed copy find and download a next version from a feed packed on
  the spot. The release workflow calls it.
- **`release.yml`**, started only by a `v*` tag or by hand (a run by hand
  on a branch is a dry run; only a tag publishes):
  - the tag must be `v` plus `MAJOR.MINOR.PATCH`; once
    `.github/allowed_signers` exists, it must be signed by a key there
    (`git verify-tag`; until then a warning);
  - `permissions: contents: read` everywhere but the publish job, which
    may write only this repo's Releases;
  - everything pinned (actions by commit, vpk by version, Python by
    `uv.lock`), the checkout without credentials, no caches on the release
    path;
  - the upload (`vpk upload s3` to R2) uses the `release` environment's
    secrets `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`,
    `R2_BUCKET` - **not created yet**; until they exist the upload is
    skipped and the Release is a draft;
  - what was made is recorded: every file's SHA-256 in the job summary
    and on a GitHub Release for the tag, with the installer and the feed;
    after an upload, the public feed must equal what was uploaded;
  - the last release is fetched from the public feed for delta packages
    once the repository variable `UPDATE_FEED` is set.
- **`feed-check.yml`**, daily: each channel's public feed, installer and
  full package must match the SHA-256s on that channel's latest
  (non-draft) Release (`tools/package/feed_check.py`); any difference
  fails the run, which emails the owner. It runs only once `UPDATE_FEED`
  is set. (Per channel since 2026-11-06, polyglotic-hq project 066, Low 5:
  the latest Release overall would leave the alpha's feed unchecked once a
  beta release is newest.)
- **One build per channel**, so the release stamp's channel (decision
  0015) matches the installer's: a beta release is the workflow run again
  with the beta channel.

## Why

- **Only reviewed code with the release's secrets:** pull requests never
  start it, so a dependency update or a branch can't reach the secrets.
- **Detection while the feed is unsigned:** if the bucket, DNS or token is
  misused, the daily check notices within a day; the Release is the record
  to compare with and to republish from.
- **A build that's tried as installed:** the installer, the first run and
  the updater are exercised on every relevant pull request, so the release
  is never the first time they run.
- **Alternatives not taken:** GitHub Releases as the feed (a private repo
  would need a token in the app - project 010); publishing from the PC
  (the PC holds everything else - project 010, 032).

## What would make us reverse it

- The signed feed (DECISIONS.md #13, before the beta): the workflow also
  signs `releases.<channel>.json` with an Ed25519 key from the `release`
  environment, and the app checks it (decision 0017's adapter).
- Code signing (paid launch): `vpk pack --signParams` or Artifact Signing
  in the same job.
- Percentage rollouts: the feed comes from our server; the upload stays.

## How we'd reverse it

Three workflow files. Moving the upload elsewhere is one step; the build
and the checks don't change.
