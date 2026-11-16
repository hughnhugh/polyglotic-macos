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
#           sq.version, which channel the installed copy follows
# PACKDIR   the PyInstaller folder, with Polyglotic.exe
# OUTDIR    where the packages go (with any earlier release, for deltas)
# ICON      the installer's .ico
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

dotnet vpk pack --packId "$id" --packVersion "$version" --aumid "$id.Desktop" \
  --packTitle Polyglotic --packAuthors Polyglotic \
  --packDir "$packdir" --mainExe Polyglotic.exe \
  ${icon:+--icon "$icon"} ${notes:+--releaseNotes "$notes"} --runtime win-x64 \
  --channel "$channel" --outputDir "$outdir" --noPortable
