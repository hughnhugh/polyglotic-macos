#!/usr/bin/env bash
# A Linux desktop session, as the Linux checks need one (polyglotic-hq 550):
# on GitHub's Ubuntu runner, inside `dbus-run-session`, start
# - the sound server: PipeWire, WirePlumber and pipewire-pulse (no systemd
#   user session there), with an output "Speakers" made the default and a
#   microphone "Microphone" made the default input - a real input, fed by
#   whatever is played into the sink named in $POLYGLOTIC_MIC_SINK
#   (547's arrangement: a null sink and a source remapped from its monitor);
# - the keyring: gnome-keyring's Secret Service, unlocked with a password
#   made for the run and never kept (none with LINUX_SESSION_KEYRING=none);
# - a screen: Xvfb at 1920x1080, as $DISPLAY, unless one is set already;
# then run COMMAND in it, and stop them all. What each said is in OUT.
#
#   dbus-run-session -- bash tools/linux_session.sh OUT -- COMMAND...
#
# GitHub's runners only: it starts daemons and loads sound modules that a
# person's own session has already.
set -uo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "$(uname -s)" != Linux ]; then
  echo "550: this runs only on GitHub's Linux runners"; exit 2
fi
out="$(realpath -m "${1:?OUT}")"; shift
[ "${1:-}" = -- ] && shift
mkdir -p "$out"
XDG_RUNTIME_DIR="$(mktemp -d)"; export XDG_RUNTIME_DIR; chmod 700 "$XDG_RUNTIME_DIR"
started=()

pipewire > "$out/pipewire.log" 2>&1 & started+=($!)
sleep 1
wireplumber > "$out/wireplumber.log" 2>&1 & started+=($!)
pipewire-pulse > "$out/pipewire-pulse.log" 2>&1 & started+=($!)
for _ in $(seq 50); do [ -S "$XDG_RUNTIME_DIR/pulse/native" ] && break; sleep 0.2; done
sleep 2  # WirePlumber settles
pactl load-module module-null-sink sink_name=session_speakers \
  sink_properties=device.description=Speakers > /dev/null
pactl set-default-sink session_speakers
POLYGLOTIC_MIC_SINK=session_mic_feed; export POLYGLOTIC_MIC_SINK
pactl load-module module-null-sink sink_name="$POLYGLOTIC_MIC_SINK" \
  sink_properties=device.description=MicFeed > /dev/null
pactl load-module module-remap-source master="$POLYGLOTIC_MIC_SINK.monitor" \
  source_name=session_mic source_properties=device.description=Microphone > /dev/null
pactl set-default-source session_mic
{
  echo "== the sound server"; pactl info
  echo "== outputs"; pactl list short sinks
  echo "== inputs"; pactl list short sources
} > "$out/sound.txt" 2>&1

# The screen ($LINUX_SESSION_SCREEN): a bare X server (xvfb, the default),
# or a desktop's own window manager, headless, with XWayland - GNOME's
# (mutter) or KDE's (KWin), as 547's harness ran them.
case "${LINUX_SESSION_SCREEN:-xvfb}" in
gnome)
  before="$(ls /tmp/.X11-unix 2>/dev/null || true)"
  GSETTINGS_BACKEND=memory mutter --wayland --headless --virtual-monitor 1920x1080 \
    --wayland-display wayland-550 > "$out/mutter.log" 2>&1 & started+=($!)
  for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/wayland-550" ] && break; sleep 0.5; done
  xs=""
  for _ in $(seq 60); do
    xs="$(comm -13 <(echo "$before" | sort) <(ls /tmp/.X11-unix 2>/dev/null | sort) | head -1)"
    [ -n "$xs" ] && break; sleep 0.5
  done
  [ -n "$xs" ] || { echo "mutter's XWayland didn't start"; tail -20 "$out/mutter.log"; exit 1; }
  export WAYLAND_DISPLAY=wayland-550 DISPLAY=":${xs#X}"
  # as GNOME's own session says it is (570: the hotkeys read them)
  export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_TYPE=wayland
  auth="$(ls "$XDG_RUNTIME_DIR"/.mutter-Xwaylandauth.* 2>/dev/null | head -1 || true)"
  [ -n "$auth" ] && export XAUTHORITY="$auth"
  echo "GNOME: $(mutter --version 2>&1 | head -1)" >> "$out/sound.txt"
  ;;
kde)
  KWIN_SCREENSHOT_NO_PERMISSION_CHECKS=1 KWIN_WAYLAND_NO_PERMISSION_CHECKS=1 \
    kwin_wayland --virtual --xwayland --width=1920 --height=1080 --socket=wayland-550 \
    > "$out/kwin.log" 2>&1 & started+=($!)
  for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/wayland-550" ] && break; sleep 0.5; done
  [ -S "$XDG_RUNTIME_DIR/wayland-550" ] || { echo "KWin didn't start"; tail -20 "$out/kwin.log"; exit 1; }
  export WAYLAND_DISPLAY=wayland-550 DISPLAY=:0
  # as Plasma's own session says it is (570: the hotkeys read them)
  export XDG_CURRENT_DESKTOP=KDE KDE_SESSION_VERSION=6 XDG_SESSION_TYPE=wayland
  sleep 2
  auth="$(ls "$XDG_RUNTIME_DIR"/xauth_* 2>/dev/null | head -1 || true)"
  [ -n "$auth" ] && export XAUTHORITY="$auth"
  echo "KDE: $(kwin_wayland --version 2>&1 | head -1)" >> "$out/sound.txt"
  ;;
*)
  if [ -z "${DISPLAY:-}" ]; then
    Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp > "$out/xvfb.log" 2>&1 & started+=($!)
    export DISPLAY=:99 XDG_SESSION_TYPE=x11  # an Xorg session's (570)
    for _ in $(seq 50); do [ -S /tmp/.X11-unix/X99 ] && break; sleep 0.1; done
  fi
  ;;
esac

# The keyring, made new for this session (its own folder: a login keyring
# left by an earlier session has another password, and would ask for it),
# after the screen, so a box it shows has somewhere to show
# - none with LINUX_SESSION_KEYRING=none: a bare desktop with no Secret
#   Service at all, where the app keeps its token in a file (574)
if [ "${LINUX_SESSION_KEYRING:-gnome}" != none ]; then
  password="$(head -c 18 /dev/urandom | base64)"
  keyrings="$(mktemp -d)"
  eval "$(printf '%s' "$password" | XDG_DATA_HOME="$keyrings" gnome-keyring-daemon --unlock --components=secrets 2> "$out/keyring.log")"
  unset password
  export GNOME_KEYRING_CONTROL
fi

"$@"; code=$?

# the keyring ends with the session's bus (dbus-run-session's)
for pid in "${started[@]}"; do kill "$pid" 2>/dev/null; done
exit "$code"
