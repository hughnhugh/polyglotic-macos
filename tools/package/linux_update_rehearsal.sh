#!/usr/bin/env bash
# Linux updating itself, rehearsed on GitHub's Ubuntu runner (polyglotic-hq
# 550; desktop decision 0259), as macos_update_rehearsal.sh rehearses a
# Mac's: the AppImage of OLD put in ~/Applications as a learner would (copy,
# make it executable, run it), with no libfuse2 on the machine; the copy
# finds NEW in a feed in a folder and downloads it (`--check-install
# --updates`) into this user's own cache, never Velopack's shared
# /var/tmp/velopack; as that run exits the update is applied - the file
# replaced in place - and the next start is NEW. Then a second user of the
# same machine updates their own copy (547: Velopack's shared folder blocked
# them), and a copy in a folder the user can't change refuses the download
# and says why, keeping the version it has.
#
#   bash tools/package/linux_update_rehearsal.sh OUT FEED OLD_APPIMAGE NEW
#
# OUT           where the reports go (each --check-install's JSON, summary.txt)
# FEED          Velopack's releases folder with both versions (linux_build.sh)
# OLD_APPIMAGE  the older version's AppImage (OUT/Polyglotic-0.0.1.AppImage)
# NEW           the newer version (0.0.2)
#
# GitHub's runners only: it removes libfuse2 and adds a user.
set -uo pipefail
[ "${GITHUB_ACTIONS:-}" = true ] && [ "$(uname)" = Linux ] ||
  { echo "GitHub's Ubuntu runner only: it removes packages and adds a user" >&2; exit 2; }
if [ $# -ne 4 ]; then
  echo "usage: linux_update_rehearsal.sh OUT FEED OLD_APPIMAGE NEW" >&2
  exit 2
fi
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
say() { echo "== $*"; }

version_of() { # APPIMAGE: the version Velopack's manifest inside it names
  local d
  d=$(mktemp -d)
  (cd "$d" && "$1" --appimage-extract usr/bin/sq.version > /dev/null 2>&1)
  sed -n 's:.*<version>\([^<]*\)</version>.*:\1:p' "$d/squashfs-root/usr/bin/sq.version" 2> /dev/null | head -1
  rm -rf "$d"
}
becomes() { # APPIMAGE VERSION SECONDS: whether it is VERSION within SECONDS
  for _ in $(seq 1 "$3"); do
    [ "$(version_of "$1")" = "$2" ] && return 0
    sleep 1
  done
  return 1
}
as_learner2() { sudo -n -u learner2 -H env QT_QPA_PLATFORM=offscreen "$@" < /dev/null; }

say "no libfuse2: Velopack's AppImage carries the static runtime"
for p in libfuse2t64 libfuse2; do
  dpkg -s "$p" > /dev/null 2>&1 && sudo apt-get remove -y -qq "$p" > /dev/null 2>&1
done
check "libfuse2 absent" "! ldconfig -p | grep -q 'libfuse.so.2'"
check "fusermount3 there (fuse3, on every desktop)" "command -v fusermount3 > /dev/null"
# what a desktop has for any X11 program (the runner's image lacks libEGL)
sudo apt-get update -qq > /dev/null 2>&1
sudo apt-get install -y -qq --no-install-recommends libegl1 libgl1 libxkbcommon0   libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 libglib2.0-0 xvfb > /dev/null 2>&1
check "libEGL there, as on a desktop" "ldconfig -p | grep -q 'libEGL.so.1'"

pub=/tmp/polyglotic-feed # readable by every user (a home folder is 750)
rm -rf "$pub" && mkdir -p "$pub"
find "$feed" -maxdepth 1 -type f ! -name '*.AppImage' -exec cp {} "$pub/" \;
chmod -R a+rX "$pub"
ls -la "$pub" > "$out/feed.txt"
export QT_QPA_PLATFORM=offscreen

say "the older AppImage in ~/Applications, as a learner puts it"
app="$HOME/Applications/Polyglotic.AppImage"
mkdir -p "$HOME/Applications"
cp "$old" "$app" && chmod +x "$app"
from=$(version_of "$app")
check "the downloaded file names its version" "[ -n '$from' ] && [ '$from' != '$new' ]" "($from)"
inode=$(stat -c %i "$app")
data=$(mktemp -d)
timeout 300 "$app" --check-install "$out/first.json" --data "$data" > "$out/first.log" 2>&1
check "it starts and its own check passes" "grep -q '\"ok\": true' '$out/first.json'"
check "Velopack sees it installed" "grep -q '\"installed\": true' '$out/first.json'"

say "it finds $new in the feed and downloads it; applied as it exits"
timeout 300 "$app" --check-install "$out/update.json" --data "$data" --updates "$pub" > "$out/update.log" 2>&1
check "the update is found" "grep -q '\"update_found\": \"$new\"' '$out/update.json'"
check "and downloaded" "grep -q '\"update_downloaded\": true' '$out/update.json'"
check "into this user's own cache" "ls ~/.cache/Polyglotic/packages/*.nupkg > /dev/null 2>&1"
check "not Velopack's shared folder" "! ls /var/tmp/velopack/Polyglotic/packages/*.nupkg > /dev/null 2>&1"
check "applied as the app exited: the file is $new" "becomes '$app' '$new' 120"
check "in place: the same path, a new file" "[ -x '$app' ] && [ \$(stat -c %i '$app') != $inode ]"
timeout 300 "$app" --check-install "$out/after.json" --data "$data" > "$out/after.log" 2>&1
check "the next start is $new and passes its check" "grep -q '\"ok\": true' '$out/after.json' && grep -q '\"installed\": true' '$out/after.json'"

say "the updated AppImage started as a learner starts it, on X11 (Xvfb)"
Xvfb :93 -screen 0 1280x800x24 > /dev/null 2>&1 &
xvfb=$!
sleep 2
shown=$(mktemp -d)
# nothing outside this machine: no server (a closed port), the feed in a folder
DISPLAY=:93 QT_QPA_PLATFORM=xcb "$app" --data "$shown" --server http://127.0.0.1:9   --updates "$pub" > "$out/started.log" 2>&1 &
started=$!
sleep 25
check "it is still running 25 s after it started" "kill -0 $started 2> /dev/null"
# 561: PyInstaller's loader started the app again with its own folder on the
# library path (the process's environment as it began) - which a link's
# browser inherited until the start put the outside one back
apps_running="" loader_path=""
for p in /proc/[0-9]*; do # the app's processes, by their executable
  case "$(readlink "$p/exe" 2> /dev/null)" in
    */Polyglotic) apps_running="$apps_running ${p#/proc/}"
      found=$(tr '\0' '\n' < "$p/environ" 2> /dev/null | grep '^LD_LIBRARY_PATH=')
      [ -n "$found" ] && loader_path="$found" ;;
  esac
done
check "the packed app began with its own folder on the library path" \
  "echo '$loader_path' | grep -q '_internal'" "(processes:$apps_running; $loader_path)"
kill "$started" 2> /dev/null
sleep 3
kill -9 "$started" 2> /dev/null
kill "$xvfb" 2> /dev/null
cp "$shown/logs/polyglotic.log" "$out/started-polyglotic.log" 2> /dev/null
check "its log says it started, on Linux's channel" "grep -q -E 'Polyglotic [0-9.]+ \(linux-x64-alpha\)' '$out/started-polyglotic.log'"
check "and no crash" "! grep -q -E 'Traceback|crashed' '$out/started-polyglotic.log' '$out/started.log'"
# its own menu entry and icon, written at the start (561): Velopack makes none
entry="${XDG_DATA_HOME:-$HOME/.local/share}/applications/io.polyglotic.Polyglotic.desktop"
cp "$entry" "$out/" 2> /dev/null
check "its menu entry is written, starting this AppImage" "grep -qx 'Exec=$app' '$entry' && grep -qx 'TryExec=$app' '$entry'"
check "with its icon" "[ -s '${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/io.polyglotic.Polyglotic.svg' ]"
sudo apt-get install -y -qq --no-install-recommends desktop-file-utils > /dev/null 2>&1
check "and the entry is valid (desktop-file-validate)" "desktop-file-validate '$entry' > '$out/desktop-file-validate.txt' 2>&1" "($(desktop-file-validate "$entry" 2>&1 | head -3 | tr '\n' ' '))"

say "a second user updates their own copy"
sudo useradd -m learner2 2> /dev/null || true
sudo -u learner2 mkdir -p /home/learner2/Applications
sudo cp "$old" /home/learner2/Applications/Polyglotic.AppImage
sudo chown learner2: /home/learner2/Applications/Polyglotic.AppImage
sudo chmod 755 /home/learner2/Applications/Polyglotic.AppImage
theirs=/home/learner2/Applications/Polyglotic.AppImage
as_learner2 timeout 300 "$theirs" --check-install /tmp/learner2-update.json \
  --data /tmp/learner2-data --updates "$pub" > "$out/learner2.log" 2>&1
sudo cp /tmp/learner2-update.json "$out/learner2-update.json" 2> /dev/null
check "their update is found and downloaded" "grep -q '\"update_downloaded\": true' '$out/learner2-update.json'"
check "into their own cache" "sudo ls /home/learner2/.cache/Polyglotic/packages/ | grep -q nupkg"
check "and applied to their file" "becomes '$theirs' '$new' 120"

say "a copy in a folder the user can't change"
sudo mkdir -p /srv/polyglotic
sudo cp "$old" /srv/polyglotic/Polyglotic.AppImage
sudo chmod 755 /srv/polyglotic /srv/polyglotic/Polyglotic.AppImage
as_learner2 timeout 300 /srv/polyglotic/Polyglotic.AppImage --check-install /tmp/learner2-nw.json \
  --data /tmp/learner2-data --updates "$pub" > "$out/not-writable.log" 2>&1
sudo cp /tmp/learner2-nw.json "$out/not-writable.json" 2> /dev/null
check "the download is refused, saying why" "grep -q 'NotWritable' '$out/not-writable.json'"
sleep 5
check "and it keeps the version it has" "[ \"\$(version_of /srv/polyglotic/Polyglotic.AppImage)\" = '$from' ]"

cp /tmp/velopack_Polyglotic.log "$out/" 2> /dev/null || true
sudo chmod -R a+rwX "$out" 2> /dev/null || true
exit "$fail"
