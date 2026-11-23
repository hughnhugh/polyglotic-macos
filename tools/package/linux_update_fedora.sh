#!/usr/bin/env bash
# Linux updating itself on Fedora 45 (polyglotic-hq 574; 546's section 3,
# check 7): linux_update_rehearsal.sh's first part - the one a learner
# meets - in a fedora:45 container, with FUSE 3 as Fedora's desktops have it
# and no FUSE 2: the older AppImage in ~/Applications, its own check
# passing, the newer version found in a feed in a folder and downloaded,
# applied as the app exits (the file replaced in place), and the next start
# the newer version.
#
#   docker run --rm --device /dev/fuse --cap-add SYS_ADMIN \
#     --security-opt apparmor=unconfined -e GITHUB_ACTIONS -v "$PWD:/w" -w /w \
#     fedora:45 bash tools/package/linux_update_fedora.sh OUT FEED OLD_APPIMAGE NEW
#
# OUT gets summary.txt (`pass NAME` / `fail NAME` lines) and each run's
# --check-install report. GitHub's runners only, in its container.
set -uo pipefail
[ "${GITHUB_ACTIONS:-}" = true ] && grep -q '^ID=fedora' /etc/os-release ||
  { echo "a fedora container on GitHub's runners only" >&2; exit 2; }
[ $# -eq 4 ] || { echo "usage: linux_update_fedora.sh OUT FEED OLD_APPIMAGE NEW" >&2; exit 2; }
out=$1 feed=$2 old=$3 new=$4
mkdir -p "$out"
out=$(cd "$out" && pwd)
summary="$out/summary.txt"
: > "$summary"
fail=0
check() { # NAME CONDITION [DETAIL]
  if eval "$2"; then echo "pass $1 ${3:-}" | tee -a "$summary"
  else echo "fail $1 ${3:-}" | tee -a "$summary"; fail=1; fi
}
# what Fedora's desktops have for any X11 program, and FUSE 3 - never FUSE 2
dnf -y -q install fuse3 fuse3-libs file findutils libxkbcommon-x11 xcb-util-wm \
  xcb-util-image xcb-util-keysyms xcb-util-renderutil libglvnd-egl libglvnd-glx \
  fontconfig dbus-libs glib2 pulseaudio-libs dejavu-sans-fonts > /dev/null 2>&1
. /etc/os-release
echo "== $PRETTY_NAME" | tee -a "$summary"
check "no FUSE 2 (libfuse.so.2)" "! ldconfig -p | grep -q 'libfuse.so.2'"
check "fusermount3 there (fuse3, as on Fedora's desktops)" "command -v fusermount3 > /dev/null"

version_of() { # APPIMAGE: the version Velopack's manifest inside it names
  local d
  d=$(mktemp -d)
  (cd "$d" && "$1" --appimage-extract usr/bin/sq.version > /dev/null 2>&1)
  sed -n 's:.*<version>\([^<]*\)</version>.*:\1:p' "$d/squashfs-root/usr/bin/sq.version" 2> /dev/null | head -1
  rm -rf "$d"
}
becomes() { # APPIMAGE VERSION SECONDS
  for _ in $(seq 1 "$3"); do
    [ "$(version_of "$1")" = "$2" ] && return 0
    sleep 1
  done
  return 1
}

pub=/tmp/polyglotic-feed
rm -rf "$pub" && mkdir -p "$pub"
find "$feed" -maxdepth 1 -type f ! -name '*.AppImage' -exec cp {} "$pub/" \;
export QT_QPA_PLATFORM=offscreen
app="$HOME/Applications/Polyglotic.AppImage"
mkdir -p "$HOME/Applications"
cp "$old" "$app" && chmod +x "$app"
from=$(version_of "$app")
check "the downloaded file names its version" "[ -n '$from' ] && [ '$from' != '$new' ]" "($from)"
inode=$(stat -c %i "$app")
data=$(mktemp -d)
timeout 300 "$app" --check-install "$out/first.json" --data "$data" > "$out/first.log" 2>&1
check "it starts mounted (FUSE 3) and its own check passes" "grep -q '\"ok\": true' '$out/first.json'"
timeout 300 "$app" --check-install "$out/update.json" --data "$data" --updates "$pub" > "$out/update.log" 2>&1
check "the update is found" "grep -q '\"update_found\": \"$new\"' '$out/update.json'"
check "and downloaded" "grep -q '\"update_downloaded\": true' '$out/update.json'"
check "applied as the app exited: the file is $new" "becomes '$app' '$new' 120"
check "in place: the same path, a new file" "[ -x '$app' ] && [ \$(stat -c %i '$app') != $inode ]"
timeout 300 "$app" --check-install "$out/after.json" --data "$data" > "$out/after.log" 2>&1
check "the next start is $new and passes its check" "grep -q '\"ok\": true' '$out/after.json'"
cp /tmp/velopack_Polyglotic.log "$out/" 2> /dev/null || true
chmod -R a+rwX "$out" 2> /dev/null || true
exit "$fail"
