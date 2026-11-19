#!/usr/bin/env bash
# The update a learner's Mac gets, rehearsed from the release they have
# (polyglotic-hq 523; 430's rehearsal, made standard): the macOS job's
# `learner` part, after `pack`. Where 430's rehearsal packs one build twice
# (0.0.1 to 0.0.2), this starts from what learners really have:
#
# 1. the published release - the zip polyglotic.io/get/macos-arm64-alpha
#    gives today - downloaded and unzipped into ~/Applications, as a
#    learner's app is once moved there (no quarantine left: the app's own
#    move takes it off, decision 0205);
# 2. a learner's settings and sign-in planted beside it: a settings file
#    in ~/Library/Application Support/Polyglotic, and a keychain item under
#    the app's own service, trusting the published app;
# 3. this run's app packed as the next version (VERSION, or the published
#    one's patch + 1) into a feed in a folder;
# 4. the published app finds it, downloads it (`--check-install --updates`)
#    and, started again, Velopack applies it and restarts into it;
# 5. after: the app is the new version, verifies, has the published app's
#    designated requirement (what macOS keeps permissions and the keychain
#    item under - a changed certificate or identifier would cost every
#    learner their permissions), the settings file is byte for byte the
#    same, and the keychain item is still there.
#
#   bash tools/package/macos_update_from_release.sh APP OUT [VERSION]
#
# APP      the built, signed Polyglotic.app (dist/Polyglotic.app)
# OUT      where the reports go; OUT/summary.txt says each check's outcome
# VERSION  the release being made (a release run), else the next patch
#
# On a Mac only, with vpk restored (dotnet tool restore). Without the
# release certificate (ad hoc) the requirement can't match the published
# app's: said as unknown, not a fail. A learner's own data on the machine
# is moved aside first and put back at the end.
set -euo pipefail
if [ $# -lt 2 ]; then
  echo "usage: macos_update_from_release.sh APP OUT [VERSION]" >&2
  exit 2
fi
app=$1 out=$2 next=${3:-}
channel=macos-arm64-alpha
published_url=https://polyglotic.io/get/macos-arm64-alpha
mkdir -p "$out"
out=$(cd "$out" && pwd) # Velopack restarts the app from /
feed=$(mktemp -d)
download=$(mktemp -d)
installed="$HOME/Applications/Polyglotic.app"
exe="$installed/Contents/MacOS/Polyglotic"
data="$HOME/Library/Application Support/Polyglotic"
service="Polyglotic/device"
account="523-rehearsal-$(uuidgen)"
summary="$out/summary.txt"
: > "$summary"
failed=0

say() { echo "== $*"; }
outcome() { # OUTCOME CHECK SAID: one line of the summary
  echo "$1 $2: $3" | tee -a "$summary"
  [ "$1" = fail ] && failed=1
  return 0
}
limit() { perl -e 'alarm shift; exec @ARGV or die "exec: $!"' "$@"; }
wait_for() { for _ in $(seq 1 "$2"); do [ -s "$1" ] && return 0; sleep 1; done; return 1; }
version_of() { sed -n 's:.*<version>\([^<]*\)</version>.*:\1:p' "$1/Contents/Resources/sq.version" | head -1; }
designated() { codesign --display --requirements - "$1" 2>&1 | grep '^designated =>' | tail -1; }

cleanup() {
  cp "$HOME/Library/Logs/velopack_Polyglotic.log" "$out/" 2>/dev/null || true
  security delete-generic-password -s "$service" -a "$account" > /dev/null 2>&1 || true
  rm -rf "$feed" "$download" "$installed" "$data"
  if [ -d "$data.523" ]; then mv "$data.523" "$data"; fi
  echo "== the summary"
  cat "$summary"
}
trap cleanup EXIT
rm -rf "$installed"
mkdir -p "$HOME/Applications"
if [ -d "$data" ]; then mv "$data" "$data.523"; fi

say "1. the published release, as a learner downloads it"
if ! curl -fsSL --retry 3 -A "polyglotic-macos-ci" -o "$download/published.zip" "$published_url"; then
  outcome unknown published "couldn't download $published_url"
  exit 0
fi
shasum -a 256 "$download/published.zip" | tee "$out/published.sha256"
ditto -x -k "$download/published.zip" "$HOME/Applications"
previous=$(version_of "$installed")
[ -n "$previous" ] || { outcome fail published "no sq.version in the published app"; exit 1; }
before=$(designated "$installed")
echo "$before" > "$out/published-requirement.txt"
limit 300 "$exe" --check-install "$out/published.json" || true
if grep -q '"installed": true' "$out/published.json" 2>/dev/null; then
  outcome pass published "$previous, installed in ~/Applications, Velopack sees it installed"
else
  outcome fail published "$previous: Velopack doesn't see it installed"
  cat "$out/published.json" || true
  exit 1
fi

say "2. a learner's settings and sign-in beside it"
mkdir -p "$data"
cat > "$data/settings.json" << 'EOF'
{"interface_language": "en", "learning": ["zh"], "changed": ["learning"], "rehearsal_523": true}
EOF
settings_before=$(shasum -a 256 "$data/settings.json" | cut -d' ' -f1)
# a stand-in token, made here: never a real one
planted=0
if security add-generic-password -s "$service" -a "$account" -w "stand-in-$(uuidgen)" \
  -T "$installed" > "$out/keychain.txt" 2>&1; then
  planted=1
fi

say "3. this run's app packed as the next version"
if [ -z "$next" ]; then
  IFS=. read -r major minor patch <<< "$previous"
  next="$major.$minor.$((patch + 1))"
fi
bash tools/package/pack.sh "$next" "$channel" "$app" "$feed" > "$out/pack-$next.log" 2>&1 ||
  { tail -40 "$out/pack-$next.log"; outcome fail packed "vpk couldn't pack $next"; exit 1; }
ls -l "$feed" > "$out/feed.txt"

say "4. the published app finds $next, downloads it, and applies it at its next start"
limit 300 "$exe" --check-install "$out/update.json" --updates "$feed" || true
cat "$out/update.json" || true
if grep -q "\"update_found\": \"$next\"" "$out/update.json" &&
  grep -q '"update_downloaded": true' "$out/update.json"; then
  outcome pass found "$previous found $next in the feed and downloaded it"
else
  outcome fail found "$previous didn't find or download $next"
  exit 1
fi
limit 300 "$exe" --check-install "$out/applied.json" || true
if ! wait_for "$out/applied.json" 180; then
  outcome fail applied "the restarted app wrote no report"
  exit 1
fi
sleep 5 # the restarted copy's own exit
now=$(version_of "$installed")
if [ "$now" = "$next" ] && grep -q '"ok": true' "$out/applied.json"; then
  outcome pass applied "Velopack applied $next and the app restarted into it"
else
  outcome fail applied "after the restart the app is $now, its check: $(head -c 300 "$out/applied.json")"
fi

say "5. after the update, as macOS and the learner see it"
codesign --verify --deep --strict "$installed" 2> "$out/verify.txt" &&
  outcome pass verifies "codesign --verify --deep --strict" ||
  outcome fail verifies "$(tail -3 "$out/verify.txt")"
after=$(designated "$installed")
echo "$after" > "$out/updated-requirement.txt"
if [ "$after" = "$before" ]; then
  outcome pass same_app "the designated requirement is the published release's: permissions and the keychain item carry over"
elif [ -z "${POLYGLOTIC_CODESIGN_IDENTITY:-}" ]; then
  outcome unknown same_app "this run's app is signed ad hoc: its requirement can't be the release's"
else
  outcome fail same_app "the requirement changed: '$before' to '$after' - learners would be asked for permissions again"
fi
settings_after=$(shasum -a 256 "$data/settings.json" 2> /dev/null | cut -d' ' -f1)
[ "$settings_after" = "$settings_before" ] &&
  outcome pass settings_kept "the settings file is byte for byte the same" ||
  outcome fail settings_kept "the settings file changed or went"
if [ "$planted" = 0 ]; then
  outcome unknown sign_in_kept "no keychain item could be planted: $(tail -1 "$out/keychain.txt")"
elif security find-generic-password -s "$service" -a "$account" > /dev/null 2>&1; then
  outcome pass sign_in_kept "the keychain item is still there"
else
  outcome fail sign_in_kept "the keychain item went"
fi
limit 300 "$exe" --check-install "$out/after.json" || true
grep -q '"ok": true' "$out/after.json" && grep -q '"installed": true' "$out/after.json" &&
  outcome pass starts "the updated app starts as installed" ||
  outcome fail starts "the updated app's check: $(head -c 300 "$out/after.json")"
exit "$failed"
