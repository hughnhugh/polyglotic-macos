#!/usr/bin/env bash
# Debian release probe. Run only inside a fresh trixie container on a GitHub runner.
set -euo pipefail
. /etc/os-release
[[ ${GITHUB_ACTIONS:-} == true && $ID == debian && $VERSION_ID == 13 && -f /.dockerenv ]]
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -yqq --no-install-recommends dbus-daemon pipewire wireplumber \
  libpulse0 pulseaudio-utils python3-numpy > /dev/null
useradd -m listener
export PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1
export XDG_RUNTIME_DIR=/tmp/listener-runtime
install -d -m 700 -o listener "$XDG_RUNTIME_DIR"
# First exercise PipeWire and its policy manager without the Pulse protocol server.
runuser -u listener --preserve-environment -- dbus-run-session -- bash -ec '
  export HOME=/home/listener
  pipewire >/tmp/962-pipewire.log 2>&1 & pw=$!
  wireplumber >/tmp/962-wireplumber.log 2>&1 & wp=$!
  trap "kill $wp $pw 2>/dev/null || true" EXIT
  for i in {1..50}; do [[ -S $XDG_RUNTIME_DIR/pipewire-0 ]] && break; sleep 0.1; done
  [[ -S $XDG_RUNTIME_DIR/pipewire-0 && ! -S $XDG_RUNTIME_DIR/pulse/native ]]
  python3 -m tools.debian_capture disconnected
'
apt-get install -yqq --no-install-recommends pipewire-pulse xvfb > /dev/null
dpkg-query -W pipewire pipewire-pulse wireplumber libpulse0
runuser -u listener --preserve-environment -- env HOME=/home/listener LINUX_SESSION_KEYRING=none \
  dbus-run-session -- bash tools/linux_session.sh /tmp/962-session -- \
  python3 -m tools.debian_capture connected
