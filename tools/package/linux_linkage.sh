#!/usr/bin/env bash
# The AppImage on a clean desktop's libraries (polyglotic-hq 550; 547's
# linkage check): in a fresh container of a supported Linux - Ubuntu 24.04
# or 26.04, Fedora - with only what that desktop installs for any X11 app
# (never libxcb-cursor: no desktop is sure to have it), every library the
# packed app loads must be found, inside it or on the system; the system
# must lack libxcb-cursor and the AppImage carry it; the app's own check
# (`--check-install`, offscreen) must pass, run as a learner runs the file
# (no FUSE in a container: APPIMAGE_EXTRACT_AND_RUN=1); and fontconfig must
# not complain (547: Ubuntu 22.04's bundled copy did, 45 times, on Fedora).
#
#   docker run --rm -e GITHUB_ACTIONS -v "$PWD:/w" -w /w IMAGE \
#     bash tools/package/linux_linkage.sh APPIMAGE OUT
#
# Prints a pass or fail line for each check, writes them to OUT/linkage.txt
# with the libraries found missing, and exits 1 on any fail. GitHub's
# runners only: it installs packages into the container it runs in.
set -uo pipefail
[ "${GITHUB_ACTIONS:-}" = true ] || { echo "runs only in a container on GitHub's runners" >&2; exit 2; }
appimage=$1 out=$2
mkdir -p "$out"
summary="$out/linkage.txt"
: > "$summary"
fail=0
check() { # NAME CONDITION [DETAIL]
  if eval "$2"; then echo "pass $1 ${3:-}" | tee -a "$summary"
  else echo "fail $1 ${3:-}" | tee -a "$summary"; fail=1; fi
}
. /etc/os-release
echo "== $PRETTY_NAME, $(ldd --version | sed -n 1p)" | tee -a "$summary"
# What a desktop has for any X11 program (Qt's own list, less xcb-cursor):
# installed here so what's left missing is what no desktop promises.
case "$ID" in
ubuntu|debian)
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends ca-certificates file \
    libx11-xcb1 libxcb1 libxkbcommon0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 \
    libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-randr0 libxcb-xfixes0 \
    libxcb-xkb1 libxcb-sync1 libxcb-xinerama0 libegl1 libgl1 libfontconfig1 \
    libdbus-1-3 libglib2.0-0 libpulse0 fonts-dejavu-core > /dev/null
  cursor_on_system() { dpkg -s libxcb-cursor0 > /dev/null 2>&1; }
  ;;
fedora)
  dnf -y -q install file findutils libxkbcommon-x11 xcb-util-wm \
    xcb-util-image xcb-util-keysyms xcb-util-renderutil libglvnd-egl libglvnd-glx \
    fontconfig dbus-libs glib2 pulseaudio-libs dejavu-sans-fonts > /dev/null 2>&1
  cursor_on_system() { rpm -q xcb-util-cursor > /dev/null 2>&1; }
  ;;
*) echo "not a Linux this checks: $ID" >&2; exit 2 ;;
esac

work=$(mktemp -d)
cp "$appimage" "$work/Polyglotic.AppImage"
chmod +x "$work/Polyglotic.AppImage"
(cd "$work" && ./Polyglotic.AppImage --appimage-extract > /dev/null)
root="$work/squashfs-root"
app="$root/usr/bin"
check "the AppImage opens (no FUSE needed to extract it)" "[ -x '$app/Polyglotic' ]"

find "$app" -type f \( -name '*.so*' -o -name Polyglotic \) -print0 |
  LD_LIBRARY_PATH="$app/_internal" xargs -0 -n 40 ldd 2> /dev/null |
  grep 'not found' | awk '{print $1}' | sort -u > "$out/missing.txt"
# Qt's plugins for other platforms and GL stacks may name libraries no
# desktop has; they're never loaded on X11 (the xcb plugin is)
grep -v -E '^(libwayland|libvulkan|libdrm|libgbm|libinput|libts|libmtdev|libudev|libxcb-(util|glx|present|dri))' \
  "$out/missing.txt" > "$out/missing-for-x11.txt" || true
check "every library the app loads on X11 is found" "[ ! -s '$out/missing-for-x11.txt' ]" \
  "($(tr '\n' ' ' < "$out/missing-for-x11.txt"))"
check "the system lacks libxcb-cursor (as a desktop may)" "! cursor_on_system"
check "the AppImage carries libxcb-cursor" "[ -n \"\$(find '$app' -name 'libxcb-cursor.so*' | head -1)\" ]"
check "fontconfig and FreeType are the system's" \
  "[ -z \"\$(find '$app' -name 'libfontconfig.so*' -o -name 'libfreetype.so*' | head -1)\" ]"

data=$(mktemp -d)
APPIMAGE_EXTRACT_AND_RUN=1 timeout 300 "$work/Polyglotic.AppImage" \
  --check-install "$out/check-install.json" --data "$data" > "$out/check-install.log" 2>&1
code=$?
check "the app's own check passes (--check-install)" "[ $code = 0 ] && grep -q '\"ok\": true' '$out/check-install.json'" "(exit $code)"
check "a checked box draws its tick (SVG plugin)" "grep -q '\"checkbox_tick\": true' '$out/check-install.json'"
# a link's browser, started through xdg-open, loads the system's libraries -
# not the app's, which PyInstaller's loader put on the path (561)
check "a program the app starts gets the system's libraries" \
  "grep -q '\"programs_library_path\": \"the system' '$out/check-install.json'"
check "and none of PyInstaller's loader's own variables"   "grep -q '\"programs_loader_variables\": \[\]' '$out/check-install.json'"
complaints=$(grep -c -i fontconfig "$out/check-install.log" || true)
check "fontconfig says nothing" "[ '$complaints' = 0 ]" "($complaints lines)"

chmod -R a+rwX "$out" 2> /dev/null || true
exit "$fail"
