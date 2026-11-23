#!/usr/bin/env bash
# The desktop's manners on a Linux desktop (polyglotic-hq 571): the tray and
# its menu where the desktop has one, the window back from the launcher where
# it has none (tools/linux_manners_check.py), on GitHub's runners only.
#
#   bash tools/linux_manners.sh gnome|ubuntu|xfce|kde OUT
#
# - gnome: GNOME's own window manager (mutter, headless, with XWayland), and
#   no tray - as Fedora's GNOME is, and Ubuntu's without its extension;
# - ubuntu: Ubuntu's GNOME - GNOME's shell itself (headless, with XWayland)
#   and Ubuntu's AppIndicator extension, its tray;
# - xfce: Xfce's window manager and panel, its status tray in it, on an X
#   screen (Xvfb);
# - kde: KDE's KWin (headless, with XWayland) in a fedora:45 container, KDE's
#   StatusNotifierWatcher (kded6's) and Plasma's shell where it starts there.
#   Without Plasma's shell a stand-in host registers with KDE's watcher - the
#   app's side is the same either way: its menu read over D-Bus.
#
# Pictures: OUT/<desktop>/*.png by the app's own windows' grab(), and the
# virtual screen of the runner (never a person's) as desk-*.png.
set -uo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "$(uname -s)" != Linux ]; then
  echo "571: this runs only on GitHub's Linux runners"; exit 2
fi
desktop="${1:?gnome, xfce or kde}"; out="$(realpath -m "${2:?OUT}")"
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$out"

if [ "$desktop" = kde ] && [ -z "${IN_FEDORA_571:-}" ]; then
  sudo modprobe vgem && sudo modprobe vkms  # KWin needs a render device (547)
  exec docker run --rm --cap-add SYS_NICE --device /dev/dri \
    -e GITHUB_ACTIONS=true -e IN_FEDORA_571=1 \
    -v "$root:/w" -v "$out:/out" -v "$(command -v uv):/usr/local/bin/uv:ro" \
    -w /w fedora:45 bash /w/tools/linux_manners.sh kde /out
fi

if [ -n "${IN_FEDORA_571:-}" ] && [ -z "${IN_SESSION_571:-}" ]; then  # once: not again inside the session
  timeout 900 dnf -y -q install --skip-unavailable kwin plasma-workspace kf6-kded xorg-x11-server-Xwayland \
    pipewire wireplumber pipewire-pulseaudio pulseaudio-utils pipewire-utils gnome-keyring \
    dbus-daemon dbus-tools mesa-dri-drivers mesa-libEGL mesa-libGL libglvnd-egl xcb-util-cursor \
    xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil libxkbcommon-x11 \
    libwayland-client libwayland-cursor libwayland-egl fontconfig google-noto-sans-fonts \
    google-noto-sans-cjk-vf-fonts findutils procps-ng glib2 desktop-file-utils > /tmp/dnf.log 2>&1 \
    || { tail -30 /tmp/dnf.log; exit 1; }
  echo "571: $(date +%T) Fedora's packages in"
  rpm -q kwin plasma-workspace kf6-kded 2>/dev/null | tee "$out/versions.txt"
  export UV_PROJECT_ENVIRONMENT=/tmp/venv UV_PYTHON=3.12.15 UV_PYTHON_PREFERENCE=only-managed
  uv sync --locked > "$out/uv-sync.log" 2>&1 || { tail -30 "$out/uv-sync.log"; exit 1; }
  uv run --no-sync python -m tools.i18n build > /dev/null
  echo "571: $(date +%T) the app's environment made"
  export LINUX_SESSION_SCREEN=kde IN_SESSION_571=1
  exec dbus-run-session -- bash tools/linux_session.sh "$out/session" -- \
    bash tools/linux_manners.sh kde "$out"
fi

if [ -z "${IN_SESSION_571:-}" ]; then  # the runner's own session, then here again
  case "$desktop" in gnome) export LINUX_SESSION_SCREEN=gnome ;; *) export LINUX_SESSION_SCREEN=xvfb ;; esac
  export IN_SESSION_571=1
  exec dbus-run-session -- bash tools/linux_session.sh "$out/session" -- \
    bash tools/linux_manners.sh "$desktop" "$out"
fi

started=()
tray=no
case "$desktop" in
xfce)
  export XDG_CURRENT_DESKTOP=XFCE XDG_SESSION_TYPE=x11
  conf="$HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
  mkdir -p "$conf"
  # the panel's own default (with its status tray), never its first-run question
  cp /etc/xdg/xfce4/panel/default.xml "$conf/xfce4-panel.xml" 2>/dev/null || true
  xfwm4 > "$out/xfwm4.log" 2>&1 & started+=($!)
  xfce4-panel > "$out/xfce4-panel.log" 2>&1 & started+=($!)
  tray=yes
  ;;
kde)
  export XDG_CURRENT_DESKTOP=KDE XDG_SESSION_TYPE=wayland KDE_FULL_SESSION=true
  timeout 900 kded6 > "$out/kded6.log" 2>&1 & started+=($!)
  sleep 3
  QT_QPA_PLATFORM=wayland timeout 900 plasmashell > "$out/plasmashell.log" 2>&1 & started+=($!)
  tray=yes
  ;;
gnome)
  export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_TYPE=wayland
  ;;
ubuntu)  # Ubuntu's GNOME: the shell itself, headless, with Ubuntu's AppIndicator extension
  export XDG_CURRENT_DESKTOP=ubuntu:GNOME XDG_SESSION_TYPE=wayland
  gsettings set org.gnome.shell disable-user-extensions false
  gsettings set org.gnome.shell enabled-extensions "['ubuntu-appindicators@ubuntu.com']"
  before="$(ls /tmp/.X11-unix 2>/dev/null || true)"
  gnome-shell --headless --wayland --virtual-monitor 1920x1080 --wayland-display wayland-571 \
    > "$out/gnome-shell.log" 2>&1 & started+=($!)
  for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/wayland-571" ] && break; sleep 0.5; done
  xs=""
  for _ in $(seq 60); do
    xs="$(comm -13 <(echo "$before" | sort) <(ls /tmp/.X11-unix 2>/dev/null | sort) | head -1)"
    [ -n "$xs" ] && break; sleep 0.5
  done
  [ -n "$xs" ] || { echo "the shell's XWayland didn't start"; tail -30 "$out/gnome-shell.log"; exit 1; }
  export WAYLAND_DISPLAY=wayland-571 DISPLAY=":${xs#X}"
  auth="$(ls "$XDG_RUNTIME_DIR"/.mutter-Xwaylandauth.* 2>/dev/null | head -1 || true)"
  [ -n "$auth" ] && export XAUTHORITY="$auth"
  echo "GNOME Shell: $(gnome-shell --version 2>&1 | head -1)" >> "$out/versions.txt"
  tray=yes
  ;;
esac
# the portal's backend for every interface: GTK's (its Settings read GNOME's
# gsettings), as Ubuntu's own desktops have one - none is configured for Xfce,
# and GNOME's own backend isn't installed here (KDE: its own, as installed)
if [ "$desktop" != kde ]; then
  mkdir -p "$HOME/.config/xdg-desktop-portal"
  printf '[preferred]\ndefault=gtk\n' > "$HOME/.config/xdg-desktop-portal/portals.conf"
fi
# the bus starts the portal when it's first asked: with this session's screen
dbus-update-activation-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP \
  XDG_SESSION_TYPE XDG_RUNTIME_DIR > /dev/null 2>&1 || true
# light or dark as the desktop's settings say it, read by the settings portal
# (xdg-desktop-portal, started by the bus when asked)
if command -v gsettings > /dev/null && [ -n "${POLYGLOTIC_COLOR_SCHEME:-}" ]; then
  gsettings set org.gnome.desktop.interface color-scheme "$POLYGLOTIC_COLOR_SCHEME" \
    > "$out/gsettings.log" 2>&1 || true
fi
sleep 10
echo "571: $(date +%T) the desktop started ($desktop)"
if [ "$tray" = yes ]; then  # a host for KDE's watcher where Plasma's shell didn't start
  uv run --no-sync python -m tools.linux_tray_menu "$out/tray-host.json" --host \
    > "$out/tray-host.log" 2>&1 & started+=($!)
  sleep 3
fi
# what the desktop says over D-Bus, asked for real (tests/test_linux_hints.py)
timeout 180 uv run --no-sync pytest -q -p no:cacheprovider -rs tests/test_linux_hints.py \
  > "$out/hints-tests.log" 2>&1; tests=$?
QT_QPA_PLATFORM=xcb timeout 600 uv run --no-sync python -m tools.linux_manners_check "$out/$desktop" \
  --tray "$tray"
code=$?
[ "$tests" = 0 ] || code=1
# start at sign-in: the autostart entry an AppImage writes (its runtime's
# variables made up: a path with a space), checked by the spec's own tool
if command -v desktop-file-validate > /dev/null; then
  mount="$out/autostart-mount"; mkdir -p "$mount/usr/bin"
  APPIMAGE="/opt/My Apps/Polyglotic.AppImage" APPDIR="$mount" XDG_CONFIG_HOME="$out/autostart" \
    uv run --no-sync python -c "from polyglotic_desktop.platform.linux.startup import XdgAutostart as A; a = A(); a.set_enabled(True); print(a.path, a.enabled())" \
    > "$out/autostart.log" 2>&1
  if desktop-file-validate "$out"/autostart/autostart/*.desktop >> "$out/autostart.log" 2>&1; then
    echo "[pass] the autostart entry passes desktop-file-validate"
  else
    echo "[FAIL] the autostart entry passes desktop-file-validate"; code=1
  fi
  cat "$out/autostart.log" "$out"/autostart/autostart/*.desktop
fi
for pid in "${started[@]}"; do kill "$pid" 2>/dev/null; done
exit "$code"
