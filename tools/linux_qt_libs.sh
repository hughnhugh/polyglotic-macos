#!/usr/bin/env bash
# Qt's system libraries for PySide6 (offscreen) on the self-hosted Linux
# runner (polyglotic-hq 179; decision 0038). The runner's container runs as
# a user that can't install packages - no root, and no-new-privileges keeps
# sudo from working (polyglotic-hq scripts/RUNNERS.md) - so apt downloads
# what the image lacks into a folder of the job's own and it's unpacked
# there. Prints the environment that points the loader and fontconfig at
# it, for $GITHUB_ENV:
#
#   bash tools/linux_qt_libs.sh "$RUNNER_TEMP/qt-libs" >> "$GITHUB_ENV"
#
# What PySide6's Qt needs that a minimal Ubuntu lacks (171's probe ran with
# the same list as root): OpenGL's and EGL's dispatchers (never a GL
# context: the platform is offscreen), xkbcommon, fontconfig and a font,
# D-Bus and GLib. Their dependencies come too; what's installed is skipped.
#
# And a font with Chinese and Japanese characters (polyglotic-hq 386): with
# DejaVu alone the runner drew Chinese as empty boxes, and every Chinese
# layout was timed through Qt's fruitless search for a font that has it, so
# the pinyin tests' budgets measured something no learner sees. WenQuanYi
# Micro Hei (Apache-2.0 or GPLv3 with the font exception): 1.6 MB to
# download, 5 MB unpacked; Noto CJK's package is 61 MB and 91 MB.
set -euo pipefail

dir=$(realpath -m "$1")
apt="$dir/apt"
mkdir -p "$apt/lists/partial" "$apt/cache/archives/partial" "$dir/root" "$dir/fontconfig"
# Positive seconds per HTTP(S) request (765). Override to reproduce stalls
# quickly. Three retries (nonnegative count) allow brief mirror outages.
timeout_seconds=${POLYGLOTIC_APT_TIMEOUT_SECONDS:-20}
retries=3
opts=(
  -o "Dir::State::Lists=$apt/lists" -o "Dir::Cache=$apt/cache" -o "Debug::NoLocking=1"
  -o "Acquire::http::Timeout=$timeout_seconds" -o "Acquire::https::Timeout=$timeout_seconds"
  -o "Acquire::Retries=$retries"
)

if [[ -n ${POLYGLOTIC_APT_MIRROR:-} ]]; then
  # Use the configured source paths and preserve suites, signing keys and
  # other repositories. apt-config shell quotes the paths for the shell.
  source_paths=$(apt-config "${opts[@]}" shell source_list Dir::Etc::SourceList/f source_parts Dir::Etc::SourceParts/d)
  eval "$source_paths"
  sources=$(mktemp -d "$apt/sources.XXXXXX")
  trap 'rm -r -- "$sources"' EXIT
  mkdir "$sources/parts"
  mirror=$(printf '%s' "${POLYGLOTIC_APT_MIRROR%/}" | sed 's/[\\&@]/\\&/g')
  rewrite_ubuntu_uris() {
    sed -E "/^[[:space:]]*#/!s@\bhttps?://(([a-z]{2}\.)?archive|security)\.ubuntu\.com/ubuntu/?([[:space:]]|$)@$mirror\3@g" "$1"
  }
  if [[ -f ${source_list:-} ]]; then
    rewrite_ubuntu_uris "$source_list" >"$sources/sources.list"
  fi
  if [[ -d ${source_parts:-} ]]; then
    for source in "${source_parts%/}"/*.list "${source_parts%/}"/*.sources; do
      [[ -f $source ]] || continue
      rewrite_ubuntu_uris "$source" >"$sources/parts/${source##*/}"
    done
  fi
  opts+=(-o "Dir::Etc::SourceParts=$sources/parts" -o "Dir::Etc::SourceList=$sources/sources.list")
fi
wanted=(libgl1 libegl1 libxkbcommon0 libfontconfig1 libdbus-1-3 libglib2.0-0 fonts-dejavu-core fonts-wqy-microhei)

# Treat failed downloads as errors even when apt can reuse older indexes.
apt-get "${opts[@]}" -o APT::Update::Error-Mode=any -qq update >&2
mapfile -t closure < <(
  apt-cache "${opts[@]}" depends --recurse --no-recommends --no-suggests \
    --no-conflicts --no-breaks --no-replaces --no-enhances "${wanted[@]}" |
    grep -E '^[a-z0-9]' | grep -v ':i386$' | sort -u
)
missing=()
for package in "${closure[@]}"; do
  if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed"; then
    missing+=("$package")
  fi
done
if ((${#missing[@]})); then
  (cd "$apt" && apt-get "${opts[@]}" -qq download "${missing[@]}" >&2)
  for deb in "$apt"/*.deb; do
    dpkg-deb -x "$deb" "$dir/root"
  done
fi
echo "Unpacked for Qt: ${missing[*]:-nothing - the image has them}" >&2

cat >"$dir/fonts.conf" <<EOF
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <dir>/usr/share/fonts</dir>
  <dir>$dir/root/usr/share/fonts</dir>
  <cachedir>$dir/fontconfig</cachedir>
</fontconfig>
EOF

arch="$(uname -m)-linux-gnu"  # x86_64-linux-gnu, aarch64-linux-gnu
echo "LD_LIBRARY_PATH=$dir/root/usr/lib/$arch:$dir/root/lib/$arch${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
echo "FONTCONFIG_FILE=$dir/fonts.conf"
echo "QT_QPA_PLATFORM=offscreen"
