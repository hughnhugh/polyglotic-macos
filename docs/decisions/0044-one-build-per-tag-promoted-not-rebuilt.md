# 0044 One build per tag: promoted to another channel by repacking it, not rebuilt; a hotfix tag publishes only where it's sent

- **Status:** accepted
- **Date:** 2026-11-08
- **Decided by:** polyglotic-hq project 225 (G3 in RELEASING.md
  section 11: "promotion to another channel, and hotfix tags off `main`",
  needed by the beta). Its brief asked that a promotion publish "the same
  build that alpha got, with no rebuild, checked by SHA-256", and that a
  hotfix tag off `release/vX.Y` build and publish like a tag on `main`.
  Claude reviews it with the pull request. Replaces decision 0018's "one
  build per channel: a beta release is the workflow run again with the
  beta channel".

## Situation

- **0018** made each channel its own build: Release run again on the
  tag, with the beta channel, rebuilt the app from the same commit and
  lockfile. That run was broken in two ways:
  - it ended in `gh release create` for a tag that already had its
    Release;
  - a rebuild isn't the build the alpha tested. PyInstaller's output and
    the dictionaries are rebuilt, and two builds needn't match byte for
    byte.
- **The channel is stamped twice** into a packed build (checked
  2026-11-08 with `vpk` 1.2.161 on a test folder):
  - the app's `release.json` (decision 0015), which `hello` reports and
    the signed feed's folder follows;
  - Velopack's `sq.version` in the full package, which decides the feed
    the installed copy follows.

  So the alpha's package can't simply be listed in the beta's feed: beta
  testers who installed it would follow the alpha's feed from then on.
- **A hotfix tag** on `release/vX.Y` went to the alpha automatically.
  The alpha follows `main`, so its feed may already be ahead, and
  publish.sh's check of the merged feed refuses that ("nothing newer
  that wasn't built here"). The run failed (RELEASING.md section 3).

## Decision

- **One build per tag.** The tag's own run builds it from source and
  packs it for `win-x64-alpha`, the build's first channel. Its Release
  records:
  - its full package, `Polyglotic-X.Y.Z-win-x64-alpha-full.nupkg`;
  - `SHA256SUMS-build`.
- **One GitHub Release per tag**, titled `Polyglotic X.Y.Z`. It holds the
  notes (RELEASE-NOTES.md), the build, and a `SHA256SUMS-<channel>` with
  the installer and feed for each channel the build is published to.
  The daily feed check follows each channel's highest version that
  records it, not the newest by date. A promotion adds a channel to an
  older tag's Release.
- **A promotion** is Release run by hand on the tag, with a channel:
  1. The build is downloaded from the Release and checked against
     `SHA256SUMS-build`. Once the feed is public, the copy it serves is
     checked too.
  2. It is unpacked, leaving out Velopack's own files.
  3. Its `release.json` is given the channel.
  4. Velopack packs it again for that channel. This is
     `tools/package/pack.sh`, the same script as the build's pack.
  5. `tools/package/promote.py compare` passes only if every file is the
     build's, byte for byte by SHA-256, except `release.json` and
     `sq.version`, which differ only in the channel.

  Then it is published like any release.
- **A hotfix:** a tag pushed on its `release/vX.Y` branch (not on
  `main`) builds and records like a tag on `main`, but publishes nowhere.
  Each channel that has the bug is then a promotion by hand, the alpha
  too if its feed isn't ahead. A tag on neither `main` nor its release
  branch is refused before anything is built.
- **The choice is one function:** `tools/package/release_plan.py`'s
  `plan()`, unit-tested case by case. The tag job runs it and the jobs
  follow its outputs. A promotion is refused when:
  - the tag has no published Release with its build (a draft published
    nothing);
  - the channel already has the tag.
- **Tried on every build:** Package runs the promotion's own steps on
  each build except a release's: pushes to `main`, runs by hand, and a
  release's dry run.

## Why

- **What beta testers get is what the alpha tested.** Every file is the
  same bytes; only the channel's name changes, in two small text files
  that are checked. That's the point of an alpha before a beta.
- **No rebuild means no new failure point at promotion.** A promotion
  doesn't depend on the dictionaries' sources still being downloadable,
  or on PyInstaller behaving the same on another day. It takes about a
  minute, not 15.
- **The user's approval stays one action per step** (RELEASING.md
  section 2): pushing the signed tag approves the build; starting
  Release on that tag with a channel approves each promotion. A hotfix
  needs both: the tag, then the channel.
- **Not taken:**
  - **Listing the alpha's package in the beta's feed:** the channel in
    `sq.version` would move beta testers to the alpha.
  - **A channel-free build that asks Velopack for its channel at run
    time:** the app reads its channel from `release.json` (`hello`,
    the signed feed's folder), and a run from source has no Velopack.
  - **A second Release (or tag) per channel:** tags are the user's, and
    one tag is one release.
  - **A hotfix tag that publishes to the alpha when its feed isn't
    ahead:** that needs the feed read before every hotfix, and the alpha
    rarely wants an old line's fix.

## What would make us reverse it

- **Code signing** (the paid launch): signing changes the bytes of every
  signed file. If the files are signed before Velopack packs them, the
  promotion repacks signed files and nothing changes. If Velopack signs
  them as it packs (`--signParams`), the compare would see different
  bytes in each promotion. Then the compare should check the signed
  files' content without their signatures, or the build should be signed
  once before its first pack.
- **A Velopack that adds or changes other files by channel:** the
  compare fails, and the promotion with it. That is a safe failure. Read
  what changed and widen the compare only for that.
- **The server building the feed per install** (percentage rollouts): a
  channel may become a feed setting rather than a package. Then one
  package serves every channel, and the repack goes.

## How we'd reverse it

- **Back to one build per channel:** `release_plan.plan()` returns
  `build=True` for a promotion, and the `promote` job goes. Two files.
- **The Release layout** (`SHA256SUMS-<channel>`) can stay either way.
