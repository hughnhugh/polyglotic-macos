#!/usr/bin/env bash
# The Linux build (polyglotic-hq 550; desktop decision 0259): the app packed
# as one Velopack AppImage, inside an Ubuntu 22.04 container so it runs on
# glibc 2.35 and newer (Ubuntu 22.04+, Debian 12+, Fedora, Mint 21+). A
# PyInstaller build runs only on the glibc it was built on or newer, and
# PySide6 6.12's wheels need 2.34 (546's plan, 1.7).
#
#   docker run --rm -v "$PWD:/w" -w /w ubuntu:22.04 \
#     bash tools/package/linux_build.sh TAG CHANNEL OUT [VERSION...]
#
# TAG       the release's tag (v0.1.0): the app's own stamp (build.py)
# CHANNEL   linux-x64-alpha, -beta or -stable
# OUT       where it goes, inside the repo: OUT/dist/Polyglotic (the
#           PyInstaller folder), OUT/releases (Velopack's packages and the
#           channel's feed), OUT/Polyglotic-VERSION.AppImage (each version's
#           AppImage, kept aside: every pack writes Polyglotic.AppImage)
# VERSION   the versions to pack the one build as, in order (default: TAG's);
#           two for the update rehearsal (linux_update_rehearsal.sh)
#
# RELEASE_FROM (polyglotic-hq 592), the update host's address: the last
# VERSION is packed as the release is - into OUT/release, beside the
# channel's published releases (`vpk download`; none yet is fine), so its
# feed lists them and a delta is made from the newest, as Windows' build
# does - with RELEASE_NOTES (the version's notes, Markdown) in the feed.
# The versions before it stay in OUT/releases (the rehearsal's older copy).
#
# The dictionaries come built (build/dictionaries: tools.dictionaries.build,
# the same on every OS). In the image, from Ubuntu's archive: libxcb-cursor0
# and the xcb libraries Qt's X11 plugin needs, which PyInstaller then
# bundles (no desktop is sure to have libxcb-cursor0: 547); squashfs-tools,
# zstd (for the deltas) and .NET 10 (DOTNET_ROOT) for vpk, at the version
# .config/dotnet-tools.json pins; uv's own Python at the exact version the Mac's build uses. The
# container's environment is its own (/opt/venv), never the checkout's
# .venv. Files are left writable by the runner's user.
set -euo pipefail
if [ $# -lt 3 ]; then
  echo "usage: linux_build.sh TAG CHANNEL OUT [VERSION...]" >&2
  exit 2
fi
tag=$1 channel=$2 out=$3
shift 3
case "$channel" in linux-*) ;; *) echo "not a Linux channel: $channel" >&2; exit 2 ;; esac
versions=("$@")
[ ${#versions[@]} -gt 0 ] || versions=("${tag#v}")
grep -q 'VERSION_ID="22.04"' /etc/os-release || { echo "build in ubuntu:22.04 (glibc 2.35)" >&2; exit 2; }
trap 'chmod -R a+rwX "$out" build/package 2>/dev/null || true' EXIT

export DEBIAN_FRONTEND=noninteractive
echo "== the build image: $(grep -E '^PRETTY_NAME=' /etc/os-release), $(ldd --version | sed -n 1p)"
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl binutils file python3-pip squashfs-tools zstd libicu70 \
  libxcb-cursor0 libxkbcommon0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-randr0 libxcb-xfixes0 \
  libxcb-xkb1 libxcb-xinerama0 libxcb-sync1 libx11-xcb1 libegl1 libgl1 \
  libfontconfig1 libdbus-1-3 libglib2.0-0 fonts-dejavu-core > /dev/null
dpkg -s libxcb-cursor0 | grep -E '^Version'

pip3 install -q uv==0.13.5
export UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON=3.12.15 UV_PYTHON_PREFERENCE=only-managed \
  UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
# as a release builds it: the app and PyInstaller only (no dev tools, no
# word splits: decision 0123 keeps simplemma out)
uv sync --locked --no-default-groups --group package
uv run --no-sync python -c "import sys, PySide6; print('python', sys.version.split()[0], 'PySide6', PySide6.__version__)"

echo "== the app, built ($tag, $channel)"
mkdir -p "$out"
# a rehearsal channel (`linux-x64-rehearsal`, polyglotic-hq 640) keeps a
# protocol channel in release.json so no real install follows it, while
# Velopack stamps the rehearsal channel into sq.version for its signed feed
stamp_channel=$channel
case "$channel" in *-rehearsal) stamp_channel="${channel%-rehearsal}-alpha" ;; esac
status=0
uv run --no-sync python -m tools.package.build "$tag" --channel "$stamp_channel" --out "$out/dist" || status=$?
cp build/package/summary.json build/package/check-install.json "$out/" 2>/dev/null || true
[ -x "$out/dist/Polyglotic/Polyglotic" ] || { echo "no Polyglotic built" >&2; exit 1; }

echo "== .NET 10 and vpk"
curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh
bash /tmp/dotnet-install.sh --channel 10.0 --install-dir /opt/dotnet > /dev/null
export DOTNET_ROOT=/opt/dotnet PATH="/opt/dotnet:$PATH" DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
dotnet tool restore > /dev/null
dotnet vpk --help 2>/dev/null | head -1 || true

release_from=${RELEASE_FROM:-}
last=${versions[${#versions[@]}-1]}
for version in "${versions[@]}"; do
  folder="$out/releases" notes=""
  if [ -n "$release_from" ] && [ "$version" = "$last" ]; then
    # the release's own pack: what's published is this folder's
    folder="$out/release" notes=${RELEASE_NOTES:-}
    mkdir -p "$folder"
    echo "== the channel's published releases, from $release_from"
    dotnet vpk download http --url "$release_from" --channel "$channel" \
      --outputDir "$folder" --allowEmptyChannel
  fi
  echo "== packed as $version into $folder${notes:+, with $notes}"
  bash tools/package/pack.sh "$version" "$channel" "$out/dist/Polyglotic" "$folder" \
    build/package/Polyglotic.png ${notes:+"$notes"}
  cp "$folder/Polyglotic.AppImage" "$out/Polyglotic-$version.AppImage"
done
ls -la "$out/releases" "$out/release" 2> /dev/null || true
# the build's own problems after packing, so a broken build still shows
# whether it packs (the job fails either way)
exit "$status"
