# 0020 The update feed is signed and recorded as the storage serves it, with its channel inside the signature

- **Status:** accepted; when `package.yml` runs replaced by
  [0021](0021-installer-built-on-main-not-pull-requests.md) (2026-11-05)
- **Date:** 2026-11-05
- **Decided by:** polyglotic-hq project 042 (the third deep review),
  finding Medium 1, option A, and Low 6; Claude's check of it confirmed
  the merge at the source on 2026-11-05 and put both into project 044's
  brief. Built by project 044 on 2026-11-05. Claude reviews it with the
  pull request. Replaces what decision 0019 said is signed and when, and
  what decision 0018 said is recorded.

## Situation

The release workflow signed the feed `vpk pack` wrote
(`releases/releases.<channel>.json`) and recorded its SHA-256, then ran
`vpk upload s3`. But `vpk upload` doesn't upload that file: it merges the
built assets with the feed already in the storage (the built ones first,
then the storage's, one per file name), prunes releases beyond
`--keepMaxReleases` and uploads the merge from a temporary file (Velopack
1.2.161, `src/vpk/Velopack.Deployment/_ObjectStore.cs` lines 188-224, and
`ReleaseEntryHelper.MergeAssets`; read 2026-11-05). From the second
release on, the signature and the recorded hash describe a file nobody is
served: with the signed feed on, every app would refuse the feed and
updates would freeze; with it off, the "public feed is what was uploaded"
step and the daily feed check would fail every time - a false alarm
exactly when the check should be trusted.

Separately, the signature covered only the feed's bytes, so whoever holds
the storage could serve the beta's signed feed under the alpha's name and
move alpha testers to the beta (project 042, Low 6).

## Decision

- **Upload, fetch back, check, then sign** (`tools/package/publish.sh`,
  used by `release.yml`):
  1. `vpk upload` as before;
  2. the feed fetched back from the storage - the bytes testers' apps will
     read;
  3. checked to be our merge, not a tamper (`sign_feed check_merge`):
     every asset built is in it with the same fields (SHA-256, size,
     version, type, name), and nothing in it is this release's version or
     newer unless it was built here - so the newest full package, the one
     the app installs, is ours, and nobody's newer package rides on our
     signature. Older releases the storage already had are kept as they
     are; the app never installs them. If the check fails, nothing is
     signed or recorded and the run fails - the storage then serves the
     merge beside the previous release's signature, which apps with a key
     refuse: updates pause, nothing installs. (The same holds for the
     seconds between `vpk upload` and the new `.sig`.);
  4. with `FEED_SIGNING_KEY`, *that* feed is signed and its `.sig`
     uploaded beside it;
  5. the served feed (and its signature) replace the built ones in
     `releases/`, and `SHA256SUMS` is taken again - so the GitHub Release,
     the "public feed is what was uploaded" step and the daily feed check
     all compare with what is served.
- **The channel inside the signature:** what is signed is
  `Polyglotic update feed 1\n` + the channel's name + `\n` + the feed's
  exact bytes (`adapters.signed_feed.signed_message`). The app checks the
  signature for the channel it asked for; one channel's feed served as
  another's is refused. Changed now, while the signed feed is still off:
  no signature in the old format was ever published, and no app has a key
  built in.
- **Tried on every pull request that could change it** (on `main` since
  decision [0021](0021-installer-built-on-main-not-pull-requests.md)): `package.yml`
  runs `publish.sh` against a folder standing in for the storage (`vpk
  upload local` runs the same upload and merge code as `vpk upload s3`;
  only reading and writing the storage differ): it publishes the build as 0.0.1, packs 0.0.2 and
  publishes it over that, checks the served feed is a merge that differs
  from the built one, verifies its signature for its channel (and not for
  another), and has the installed 0.0.1 find and download 0.0.2 from that
  served feed. The key is made on the spot and thrown away.
- `python -m tools.package.sign_feed verify FEED --channel C --key K` checks
  a published feed's signature as the app would - the step before a public
  key goes into `main.FEED_KEYS`.

## Why

- **The signature and the record must describe what is served,** or the
  signed feed freezes updates and the daily check cries wolf.
- **Option A of project 042's three:** B (`--keepMaxReleases 1` and no
  `vpk download`, so local equals served) loses deltas and old installers
  and still leaves `vpk` writing the file; C (upload the feed ourselves
  after `vpk upload`) reproduces Velopack's merge by hand. A moves one step
  and adds a check.
- **The signed bytes now come from the storage,** which is what the
  signature exists to distrust. The merge check stands between them: the
  only thing the app takes from a signed feed is the newest full package,
  and the check refuses a served feed whose newest is anything but the
  package built in this run with its SHA-256.
- **A prefix and the channel, not the channel in the feed's JSON:** the
  feed is written by Velopack (and now merged in the storage); a field we
  added would be dropped by the next upload.

## What would make us reverse it

- Velopack gaining feed signatures of its own, or an upload that doesn't
  merge (then sign the built feed, as decision 0019 first did).
- Feeds served from our own server (percentage rollouts, project 010): the
  server builds each install's feed and signs it there.
- A second publisher (TUF's roles and thresholds; decision 0019).

## How we'd reverse it

`publish.sh` is one script and `check_merge` one function; going back to
signing the built feed is reordering the script's steps (an hour), and
apps already in the field keep checking whatever the workflow signs as
long as the message format stays. Changing the message format (dropping
the channel) needs every app updated first: a release that accepts both,
then one that accepts only the new - a week of releases, so only before
the signed feed is switched on is it free.
