#!/usr/bin/env bash
# The packed app's input methods (polyglotic-hq 571): in a clean
# `ubuntu:24.04` container with what a desktop has for any X11 program
# (linux_linkage.sh's list) and IBus, the PyInstaller folder the build made
# started on an X screen (Xvfb) with `QT_IM_MODULE=ibus` and Qt saying which
# plugins it loads (`QT_DEBUG_PLUGINS`), for 25 s, in a data folder of its
# own; passes when it loaded IBus's plugin and its D-Bus - so a learner can
# type Chinese into the packed app as into the app from source
# (tools/linux_typing_check.py).
#
#   docker run --rm -e GITHUB_ACTIONS -v "$PWD:/w" -w /w ubuntu:24.04 \
#     bash tools/package/linux_input_methods.sh DIST OUT
#
# DIST  the build's folder (OUT/dist/Polyglotic of linux_build.sh)
set -uo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "$(uname -s)" != Linux ]; then
  echo "571: this runs only on GitHub's Linux runners"; exit 2
fi
dist="$(realpath "${1:?DIST}")"; out="$(realpath -m "${2:?OUT}")"
mkdir -p "$out"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq > /dev/null
apt-get install -y -qq --no-install-recommends ca-certificates xvfb dbus dbus-bin dbus-daemon \
  ibus ibus-libpinyin \
  libx11-xcb1 libxcb1 libxkbcommon0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-randr0 libxcb-xfixes0 \
  libxcb-xkb1 libxcb-sync1 libxcb-xinerama0 libegl1 libgl1 libfontconfig1 \
  libdbus-1-3 libglib2.0-0 libpulse0 fonts-dejavu-core > "$out/apt.log" 2>&1 \
  || { tail -20 "$out/apt.log"; exit 1; }
dbus-uuidgen --ensure=/etc/machine-id
dbus-run-session -- bash -c '
  XDG_RUNTIME_DIR="$(mktemp -d)" XDG_DATA_HOME="$(mktemp -d)" XDG_CONFIG_HOME="$(mktemp -d)"
  XDG_CACHE_HOME="$(mktemp -d)"; export XDG_RUNTIME_DIR XDG_DATA_HOME XDG_CONFIG_HOME XDG_CACHE_HOME
  chmod 700 "$XDG_RUNTIME_DIR"
  Xvfb :96 -screen 0 1600x1000x24 -nolisten tcp > /dev/null 2>&1 & x=$!
  export DISPLAY=:96; sleep 2
  ibus-daemon --replace --panel=disable > /dev/null 2>&1 & i=$!; sleep 3
  QT_IM_MODULE=ibus QT_QPA_PLATFORM=xcb QT_DEBUG_PLUGINS=1 timeout 25 "$1/Polyglotic" \
    > "$2/packed-start.log" 2>&1
  kill $i $x 2>/dev/null; true' _ "$dist" "$out"
grep -E "platforminputcontexts|inputcontext" "$out/packed-start.log" | head -20 > "$out/packed-plugins.txt"
cat "$out/packed-plugins.txt"
if grep -i "libibusplatforminputcontextplugin" "$out/packed-start.log" \
  | grep -q -i -E "loaded library|succeeded"; then
  echo "pass: the packed app loaded IBus's input method plugin"
else
  echo "FAIL: the packed app didn't load IBus's input method plugin"; exit 1
fi
