#!/usr/bin/env bash
# A Mac updating itself, rehearsed on GitHub's Mac (polyglotic-hq 430;
# decision 0202), as package.yml rehearses Windows' (361, 402): the built
# Polyglotic.app packed as 0.0.1 and as 0.0.2 into one feed in a folder;
# 0.0.1's portable zip unzipped into ~/Applications as a tester would; the
# copy finds and downloads 0.0.2 from the folder (`--check-install
# --updates`); started again, Velopack applies it at the start and restarts
# it into 0.0.2 with the same arguments; and the updated app must still
# verify, with the built app's designated requirement (what macOS keeps the
# learner's permissions under).
#
#   bash tools/package/macos_update_rehearsal.sh APP OUT
#
# APP   the built, signed Polyglotic.app (dist/Polyglotic.app)
# OUT   where the reports go (each --check-install's JSON, what was seen)
#
# On a Mac only, with vpk restored (dotnet tool restore) and
# POLYGLOTIC_CODESIGN_IDENTITY / SIGNING_KEYCHAIN as the build signed with.
# Its own copy only: ~/Applications/Polyglotic.app is removed first and at
# the end, and nothing else in the account is touched.
set -euo pipefail
if [ $# -ne 2 ]; then
  echo "usage: macos_update_rehearsal.sh APP OUT" >&2
  exit 2
fi
app=$1 out=$2
channel=macos-arm64-alpha
mkdir -p "$out"
# absolute: Velopack restarts the updated app through `open`, from `/`,
# with the arguments it was started with
out=$(cd "$out" && pwd)
feed=$(mktemp -d)
installed="$HOME/Applications/Polyglotic.app"
exe="$installed/Contents/MacOS/Polyglotic"
cleanup() { # Velopack's own log kept with the reports, then this copy removed
  cp "$HOME/Library/Logs/velopack_Polyglotic.log" "$out/" 2>/dev/null || true
  rm -rf "$feed" "$installed"
}
trap cleanup EXIT
rm -rf "$installed"
mkdir -p "$HOME/Applications"

say() { echo "== $*"; }
check_app() { # APP VERSION: the macos_release checks on an app in place
  uv run --no-sync python -m tools.package.macos_release app "$1" --version "$2" --like "$app"
}
limit() { # SECONDS COMMAND...: a time limit (macOS has no `timeout`)
  perl -e 'alarm shift; exec @ARGV or die "exec: $!"' "$@"
}
wait_for() { # FILE SECONDS: whether FILE appears in time
  for _ in $(seq 1 "$2"); do [ -s "$1" ] && return 0; sleep 1; done
  return 1
}

say "0.0.1 packed into a feed in a folder"
bash tools/package/pack.sh 0.0.1 "$channel" "$app" "$feed" > "$out/pack-0.0.1.log" 2>&1 ||
  { tail -40 "$out/pack-0.0.1.log"; exit 1; }
uv run --no-sync python -m tools.package.macos_release check "$feed" \
  --version 0.0.1 --channel "$channel" --built "$app" > "$out/packed-0.0.1.json" ||
  { cat "$out/packed-0.0.1.json"; exit 1; }

say "0.0.1 unzipped into ~/Applications, as a tester would"
ditto -x -k "$feed/Polyglotic-$channel-Portable.zip" "$HOME/Applications"
check_app "$installed" 0.0.1 > "$out/installed-0.0.1.json" || { cat "$out/installed-0.0.1.json"; exit 1; }
limit 300 "$exe" --check-install "$out/first.json"
grep -q '"ok": true' "$out/first.json"
grep -q '"installed": true' "$out/first.json" || { echo "Velopack doesn't see it installed"; cat "$out/first.json"; exit 1; }

say "0.0.2 packed into the same feed"
bash tools/package/pack.sh 0.0.2 "$channel" "$app" "$feed" > "$out/pack-0.0.2.log" 2>&1 ||
  { tail -40 "$out/pack-0.0.2.log"; exit 1; }
uv run --no-sync python -m tools.package.macos_release check "$feed" \
  --version 0.0.2 --channel "$channel" --built "$app" > "$out/packed-0.0.2.json" ||
  { cat "$out/packed-0.0.2.json"; exit 1; }
ls -l "$feed" > "$out/feed.txt"

say "the installed copy finds and downloads 0.0.2"
limit 300 "$exe" --check-install "$out/update.json" --updates "$feed"
cat "$out/update.json"
grep -q '"update_found": "0.0.2"' "$out/update.json"
grep -q '"update_downloaded": true' "$out/update.json"

say "started again: Velopack applies 0.0.2 and restarts into it"
limit 300 "$exe" --check-install "$out/applied.json" || true
wait_for "$out/applied.json" 180 || { echo "the restarted copy wrote no report"; exit 1; }
sleep 5 # the restarted copy's own exit
grep -q '"ok": true' "$out/applied.json"
check_app "$installed" 0.0.2 > "$out/updated-0.0.2.json" || { cat "$out/updated-0.0.2.json"; exit 1; }

say "the updated app, as macOS sees it"
{
  echo "codesign:"
  codesign --display --verbose=2 "$installed" 2>&1 | grep -E '^(Identifier|Authority|Signature)=' || true
  codesign --display --requirements - "$installed" 2>&1 | tail -1
  echo "Gatekeeper (spctl --assess --type execute):"
  spctl --assess --type execute -vv "$installed" 2>&1 || true
  echo "quarantine on the updated app (none expected: nothing that quarantines downloaded it):"
  xattr -r "$installed" 2>/dev/null | grep -c com.apple.quarantine || true
} | tee "$out/updated-seen.txt"
limit 300 "$exe" --check-install "$out/after.json"
grep -q '"ok": true' "$out/after.json"
grep -q '"installed": true' "$out/after.json"
say "updated in place from 0.0.1 to 0.0.2, still signed as built"
