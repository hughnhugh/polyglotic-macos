#!/usr/bin/env bash
# Velopack packs the app for one channel: the installer, the full package
# and the channel's feed (decision 0017). The one way the app is packed -
# package.yml packs each build with it, and a promotion packs the same
# build again for another channel (decision 0044) - so the two can't drift.
#
#   bash tools/package/pack.sh VERSION CHANNEL PACKDIR OUTDIR [ICON [NOTES]]
#
# VERSION   MAJOR.MINOR.PATCH (Velopack refuses 0.0.0)
# CHANNEL   win-x64-alpha, -beta or -stable: stamped into Velopack's
#           sq.version, which channel the installed copy follows; or a
#           Mac's, macos-arm64-alpha (below)
# PACKDIR   the PyInstaller folder, with Polyglotic.exe; on a Mac, the
#           signed Polyglotic.app
# OUTDIR    where the packages go (with any earlier release, for deltas)
# ICON      the installer's .ico (a Mac's icon is in its bundle: ignored)
# NOTES     the version's release notes, Markdown (RELEASE-NOTES.md's
#           section: `python -m tools.package.release_notes vX.Y.Z --out`):
#           the feed carries them, and the app's offer to restart into
#           the update shows their first lines (decision 0090). Every
#           pack of one version - its build and each promotion - passes
#           the same notes, or `promote compare` finds the manifests
#           differ. Empty or left out: no notes
#
# The pack's ID names the app to Velopack, and its `.Desktop` is the ID
# Windows' taskbar knows the app by (`--aumid`). Velopack gives it to the
# installed app's process and to its Start-menu and desktop shortcuts, so a
# pin and the running app are one button - and it's the app's own from
# source too (main.TASKBAR_ID; decision 0057). A rehearsal packed under
# another ID gets another taskbar ID with it.
set -euo pipefail

if [ $# -lt 4 ] || [ $# -gt 6 ]; then
  echo "usage: pack.sh VERSION CHANNEL PACKDIR OUTDIR [ICON [NOTES]]" >&2
  exit 2
fi
version=$1 channel=$2 packdir=$3 outdir=$4 icon=${5:-} notes=${6:-}
id=Polyglotic

# A Mac (polyglotic-hq 430; decision 0202), on a Mac only (Velopack can't
# pack one elsewhere): the full package, the portable zip testers download
# first - Polyglotic.app with Velopack's UpdateMac and sq.version in it, so
# it can update itself - and the channel's feed; no .pkg installer, which
# would need Apple's installer certificate. Adding those files breaks the
# bundle's signature, so vpk signs it again (only what it adds and the
# bundle: the rest was signed by the build) with the identity the build
# signed with, POLYGLOTIC_CODESIGN_IDENTITY - ad hoc without one - through
# macos_codesign.sh, which signs as the build does: vpk asks for Apple's
# timestamp service, which refuses our self-signed certificate.
case "$channel" in
macos-*)
  here=$(cd "$(dirname "$0")" && pwd)
  shim=$(mktemp -d)
  trap 'rm -rf "$shim"' EXIT
  printf '#!/bin/bash\nexec bash "%s" "$@"\n' "$here/macos_codesign.sh" > "$shim/codesign"
  chmod +x "$shim/codesign"
  PATH="$shim:$PATH" dotnet vpk pack --packId "$id" --packVersion "$version" \
    --packTitle Polyglotic --packAuthors Polyglotic \
    --packDir "$packdir" --mainExe Polyglotic \
    ${notes:+--releaseNotes "$notes"} --runtime osx-arm64 \
    --channel "$channel" --outputDir "$outdir" --noInst \
    --signAppIdentity "${POLYGLOTIC_CODESIGN_IDENTITY:--}" --signDisableDeep \
    ${SIGNING_KEYCHAIN:+--keychain "$SIGNING_KEYCHAIN"}
  exit
  ;;
esac

dotnet vpk pack --packId "$id" --packVersion "$version" --aumid "$id.Desktop" \
  --packTitle Polyglotic --packAuthors Polyglotic \
  --packDir "$packdir" --mainExe Polyglotic.exe \
  ${icon:+--icon "$icon"} ${notes:+--releaseNotes "$notes"} --runtime win-x64 \
  --channel "$channel" --outputDir "$outdir" --noPortable
