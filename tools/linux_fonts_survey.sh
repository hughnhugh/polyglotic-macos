#!/usr/bin/env bash
# The fonts a Linux desktop installs, and the interface's words in them
# (polyglotic-hq 571): in a clean container of the distribution, only the
# fonts its desktop installs by default - Ubuntu 24.04's desktop
# (ubuntu-desktop-minimal's and ubuntu-desktop's font packages), Fedora
# 45's (its `fonts` group, which Workstation and the KDE edition both
# install) - or none but DejaVu (`bare`: a minimal install, or a desktop
# without its language's fonts); then tools/linux_fonts_check.py, and what
# carrying Noto's Chinese, Japanese and Korean faces in the AppImage would
# cost.
#
#   docker run --rm -v "$PWD:/w" -v "$(command -v uv):/usr/local/bin/uv:ro" \
#     -w /w IMAGE bash tools/linux_fonts_survey.sh ubuntu|fedora|bare OUT
#
# GitHub's runners only: it installs packages into the container.
set -uo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "$(uname -s)" != Linux ]; then
  echo "571: this runs only on GitHub's Linux runners"; exit 2
fi
which="${1:?ubuntu, fedora or bare}"; out="$(realpath -m "${2:?OUT}")"
mkdir -p "$out"
qt_ubuntu=(ca-certificates libegl1 libgl1 libxkbcommon0 libfontconfig1 libglib2.0-0t64 libdbus-1-3 fontconfig zstd xz-utils)
case "$which" in
ubuntu|bare)
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq > /dev/null
  if [ "$which" = ubuntu ]; then
    fonts=$(apt-cache depends ubuntu-desktop-minimal ubuntu-desktop 2>/dev/null \
      | awk '/(Depends|Recommends): fonts-/ {print $2}' | sort -u | tr '\n' ' ')
  else
    fonts="fonts-dejavu-core"
  fi
  echo "font packages: $fonts" | tee "$out/packages.txt"
  # shellcheck disable=SC2086
  apt-get install -y -qq --no-install-recommends "${qt_ubuntu[@]}" $fonts > "$out/apt.log" 2>&1 \
    || { tail -20 "$out/apt.log"; exit 1; }
  for package in $fonts; do
    dpkg-query -W -f='${Package} ${Version} installed ${Installed-Size} KiB\n' "$package" 2>/dev/null
  done >> "$out/packages.txt"
  apt-cache show fonts-noto-cjk | grep -E '^(Package|Version|Size|Installed-Size):' | head -4 \
    > "$out/cjk-package.txt"
  ;;
fedora)
  dnf -y -q install mesa-libEGL mesa-libGL libxkbcommon fontconfig glib2 dbus-libs zstd xz \
    > "$out/dnf.log" 2>&1 || { tail -20 "$out/dnf.log"; exit 1; }
  dnf -q group info fonts > "$out/fonts-group.txt" 2>&1
  dnf -y -q group install fonts >> "$out/dnf.log" 2>&1 || { tail -20 "$out/dnf.log"; exit 1; }
  rpm -qa --qf '%{NAME} %{VERSION} installed %{SIZE} bytes\n' '*font*' | sort > "$out/packages.txt"
  rpm -q --qf '%{NAME} %{VERSION} installed %{SIZE} bytes\n' google-noto-sans-cjk-vf-fonts \
    > "$out/cjk-package.txt" 2>&1
  ;;
*) echo "ubuntu, fedora or bare"; exit 2 ;;
esac
. /etc/os-release
echo "$PRETTY_NAME" > "$out/os.txt"
fc-list : family | sort -u > "$out/families.txt"
fc-match -s 'sans-serif:lang=zh-cn' family | head -3 > "$out/fc-match.txt"
fc-match -s 'sans-serif:lang=ja' family | head -3 >> "$out/fc-match.txt"
fc-match -s 'sans-serif' family | head -3 >> "$out/fc-match.txt"

# What carrying the CJK faces would add: each file as installed, and
# compressed as the AppImage's squashfs compresses (zstd; xz beside it)
{
  echo "== the CJK font files, as installed, and compressed (zstd -19, xz -9)"
  fc-list : file family | grep -i "CJK" | cut -d: -f1 | sort -u | while read -r file; do
    raw=$(stat -c %s "$file")
    z=$(zstd -19 -q -c "$file" | wc -c)
    x=$(xz -9 -c "$file" | wc -c)
    echo "$(basename "$file") raw=$raw zstd19=$z xz9=$x"
  done
} > "$out/cjk-sizes.txt" 2>&1

export UV_PROJECT_ENVIRONMENT=/tmp/venv UV_PYTHON=3.12.15 UV_PYTHON_PREFERENCE=only-managed
uv sync --locked > "$out/uv-sync.log" 2>&1 || { tail -20 "$out/uv-sync.log"; exit 1; }
uv run --no-sync python -m tools.i18n build > "$out/i18n.log" 2>&1
QT_QPA_PLATFORM=offscreen timeout 1200 uv run --no-sync python -m tools.linux_fonts_check "$out" \
  > "$out/check.log" 2>&1
code=$?
cat "$out/fonts.md" 2>/dev/null || tail -30 "$out/check.log"
exit "$code"
