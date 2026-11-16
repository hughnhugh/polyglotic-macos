#!/usr/bin/env bash
# `codesign` as Velopack's `vpk pack` calls it on a Mac, made to sign as
# tools/package/build.py's `sign` does (polyglotic-hq 430): pack.sh puts it
# first on vpk's PATH, under the name `codesign`.
#
# vpk 1.2.161 signs what it adds to the app (UpdateMac) and then the bundle
# with `-s ID -f -v --timestamp --options runtime --entitlements FILE
# [--deep] [--keychain KC] PATH` (its OsxBuildTools.CodeSign). Our
# certificate is self-signed: Apple's timestamp service refuses it
# (polyglotic-hq 422), so `--timestamp` becomes `--timestamp=none`. The
# hardened runtime and vpk's entitlements (written for .NET apps) are
# dropped: the build signs without them, and with them macOS's library
# validation would refuse the app's own libraries, which carry no Apple
# team ID. Everything else is passed on unchanged.
set -euo pipefail
real=${POLYGLOTIC_REAL_CODESIGN:-/usr/bin/codesign}
args=()
identity=""
while [ $# -gt 0 ]; do
  case "$1" in
    --timestamp) ;;
    --options | --entitlements) shift ;; # and its value
    -s | --sign) identity=$2; args+=("$1" "$2"); shift ;;
    *) args+=("$1") ;;
  esac
  shift
done
if [ -n "$identity" ] && [ "$identity" != - ]; then
  args=(--timestamp=none "${args[@]}")
fi
exec "$real" "${args[@]}"
