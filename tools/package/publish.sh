#!/usr/bin/env bash
# Publishing a release: its packages and its feed, the feed signed and
# recorded as the update storage serves it (decisions 0018-0020).
#
#   bash tools/package/publish.sh CHANNEL STORAGE RELEASES SUMS
#
# CHANNEL   the update channel: win-x64-alpha, -beta or -stable
# STORAGE   "s3": the update storage (R2), through R2_ENDPOINT, R2_BUCKET,
#           R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY; or a folder on this
#           machine standing in for it
# RELEASES  what `vpk pack` made (the packages, the installer, the feed)
# SUMS      where to write every file's SHA-256, as published
#
# With FEED_SIGNING_KEY set, the feed is signed. release.yml runs it against
# the storage; package.yml runs it on pull requests against a folder, so
# the steps a release takes are tried before a release takes them. Run it
# from the repo's root, with the locked environment synced.
#
# Why this order: `vpk upload` doesn't upload the feed it was given - it
# merges it with the one already in the storage (the built assets first,
# then the storage's, one per file name), prunes releases beyond
# --keepMaxReleases and uploads the merge (Velopack's _ObjectStore.cs,
# lines 188-224, read 2026-11-05). So the feed is signed and recorded only
# after the upload, as fetched back - and only if it's our merge.
set -euo pipefail

if [ $# -ne 4 ]; then
  echo "usage: publish.sh CHANNEL STORAGE RELEASES SUMS" >&2
  exit 2
fi
channel=$1 storage=$2 releases=$3 sums=$4
feed="releases.$channel.json"
legacy="RELEASES-$channel" # Velopack's older feed, merged and uploaded too
served=$(mktemp -d)
trap 'rm -rf "$served"' EXIT

r2() {
  AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    AWS_DEFAULT_REGION=auto aws "$@" --endpoint-url "$R2_ENDPOINT" --only-show-errors
}

fetch() { # a file as the storage serves it -> a local path
  if [ "$storage" = s3 ]; then r2 s3 cp "s3://$R2_BUCKET/$1" "$2"; else cp "$storage/$1" "$2"; fi
}

put() { # a local file -> the storage, under its own name
  if [ "$storage" = s3 ]; then r2 s3 cp "$1" "s3://$R2_BUCKET/$(basename "$1")"; else cp "$1" "$storage/"; fi
}

# 1. Velopack uploads the packages and the installer, then the merged feed.
if [ "$storage" = s3 ]; then
  dotnet vpk upload s3 --outputDir "$releases" --channel "$channel" \
    --endpoint "$R2_ENDPOINT" --bucket "$R2_BUCKET" \
    --keyId "$R2_ACCESS_KEY_ID" --secret "$R2_SECRET_ACCESS_KEY" \
    --keepMaxReleases 10
else
  mkdir -p "$storage"
  dotnet vpk upload local --outputDir "$releases" --channel "$channel" \
    --path "$storage" --keepMaxReleases 10
fi

# 2. The feed as served: what testers' apps will read.
fetch "$feed" "$served/$feed"
fetch "$legacy" "$served/$legacy"

# 3. Our merge, not a tamper - every asset built is in it unchanged, nothing
#    newer that wasn't built here - then, with the key, signed as served:
#    the channel's name and the feed's bytes. Nothing is signed or recorded
#    if the check fails, and the run fails.
if [ -n "${FEED_SIGNING_KEY:-}" ]; then
  uv run --no-sync python -m tools.package.sign_feed sign "$served/$feed" \
    --channel "$channel" --built "$releases/$feed"
  # 4. The signature beside the feed (vpk uploads only Velopack's files).
  put "$served/$feed.sig"
else
  uv run --no-sync python -m tools.package.sign_feed check "$releases/$feed" "$served/$feed"
fi

# 5. Recorded as published: the served feeds (and the signature) replace the
#    built ones, and every file's SHA-256 is taken again.
cp "$served"/* "$releases/"
(cd "$releases" && sha256sum -- *) > "$sums"
echo "Published $feed as served:"
cat "$sums"
