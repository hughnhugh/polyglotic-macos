#!/usr/bin/env bash
# The packed AppImage on a Linux desktop (polyglotic-hq 574): the desktop
# made on GitHub's runner - its window manager headless with XWayland, its
# tray where it has one, the sound server, the keyring or none - a
# full-screen Wayland window focused over it (a video or a game), and then
# tools/linux_packed_tour.py, which starts the release's own AppImage and
# checks it from outside.
#
#   bash tools/linux_packed_tour.sh DESKTOP OUT APPIMAGE
#
# DESKTOP  gnome         Ubuntu 24.04's GNOME (mutter 46), no tray; dark
#          ubuntu        Ubuntu's GNOME: GNOME Shell with Ubuntu's AppIndicator
#                        extension, its tray; light; the save dialogs
#          fedora-gnome  Fedora 45's GNOME (in a fedora:45 container); dark
#          kde           KDE Plasma 6 (KWin, kded6's watcher, Plasma's shell)
#                        in fedora:45; the save dialogs
#          xfce          Xfce's window manager and panel on an X screen, and
#                        no keyring at all (the app keeps its token in a file)
# OUT      where it goes: OUT/DESKTOP/checks.json, the app's log, pictures
#
# The stand-in server speaks TLS with a certificate from a root made for the
# run and added to the system's own store (update-ca-certificates, Fedora's
# update-ca-trust): the packed app's trust in the distribution's roots
# (connection/tls.linux_roots) is part of the sign-in. Nothing here reaches
# the live server: no invite, no token, no secret.
set -uo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "$(uname -s)" != Linux ]; then
  echo "574: this runs only on GitHub's Linux runners"; exit 2
fi
desktop="${1:?gnome, ubuntu, fedora-gnome, kde or xfce}"
out="$(realpath -m "${2:?OUT}")"
appimage="$(realpath -m "${3:?APPIMAGE}")"
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$out/$desktop/desk"
here="$out/$desktop"

stand_in_root() { # the run's own root and the stand-in's certificate, in OUT/tls
  [ -s "$out/tls/server.crt" ] && return 0
  mkdir -p "$out/tls" && cd "$out/tls" || return 1
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=Polyglotic 574 stand-in root" \
    -keyout root.key -out root.crt > /dev/null 2>&1
  openssl req -newkey rsa:2048 -nodes -subj "/CN=localhost" -keyout server.key -out server.csr \
    > /dev/null 2>&1
  printf 'subjectAltName=DNS:localhost,IP:127.0.0.1\n' > san.ext
  openssl x509 -req -in server.csr -CA root.crt -CAkey root.key -CAcreateserial -days 2 \
    -extfile san.ext -out server.crt > /dev/null 2>&1
  rm -f root.key server.csr
  cd - > /dev/null || true
}

case "$desktop" in fedora-gnome|kde) fedora=1 ;; *) fedora="" ;; esac

if [ -n "$fedora" ] && [ -z "${IN_FEDORA_574:-}" ]; then
  stand_in_root
  # no FUSE here (the AppImage extracts and runs; Fedora's FUSE 3 mount is
  # linux_update_fedora.sh's): with SYS_ADMIN added, gnome-keyring-daemon
  # aborts dropping its capabilities, and the session has no keyring
  devices=()
  if [ "$desktop" = kde ]; then
    sudo modprobe vgem && sudo modprobe vkms  # KWin needs a render device (547)
    devices+=(--device /dev/dri)
  fi
  cp "$appimage" "$out/Polyglotic-under-test.AppImage"
  exec docker run --rm --cap-add SYS_NICE "${devices[@]}" \
    -e GITHUB_ACTIONS=true -e IN_FEDORA_574=1 -e POLYGLOTIC_LINUX_DESKTOP=1 \
    -v "$root:/w" -v "$out:/out" -v "$(command -v uv):/usr/local/bin/uv:ro" \
    -w /w fedora:45 bash /w/tools/linux_packed_tour.sh "$desktop" /out /out/Polyglotic-under-test.AppImage
fi

if [ -n "${IN_FEDORA_574:-}" ] && [ -z "${IN_SESSION_574:-}" ]; then  # once: not again inside the session
  more=(mutter pipewire-gstreamer gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good)
  [ "$desktop" = kde ] && more=(kwin plasma-workspace kf6-kded xdg-desktop-portal-kde)
  timeout 900 dnf -y -q install --skip-unavailable "${more[@]}" xorg-x11-server-Xwayland \
    pipewire wireplumber pipewire-pulseaudio pulseaudio-utils pipewire-utils gnome-keyring \
    dbus-daemon dbus-tools dbus-x11 mesa-dri-drivers mesa-libEGL mesa-libGL libglvnd-egl xcb-util-cursor \
    xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil libxkbcommon-x11 \
    libwayland-client libwayland-cursor libwayland-egl fontconfig google-noto-sans-fonts \
    google-noto-sans-cjk-vf-fonts findutils procps-ng glib2 desktop-file-utils xwininfo xprop \
    fuse3 fuse3-libs openssl ca-certificates xdg-desktop-portal xdg-desktop-portal-gtk \
    at-spi2-core python3-pyatspi xdotool gsettings-desktop-schemas > /tmp/dnf.log 2>&1 \
    || { tail -30 /tmp/dnf.log; exit 1; }
  echo "574: $(date +%T) Fedora's packages in"
  rpm -q mutter kwin plasma-workspace fuse3 gnome-keyring xdg-desktop-portal-kde 2>/dev/null | grep -v "not installed" | tee "$here/versions.txt"
  # (gnome-keyring-daemon aborts here: "error dropping process
  # capabilities" - so Fedora's tours keep the token in the app's own file,
  # and the Secret Service is Ubuntu's tours' (runs 44740277748, 44741788128))
  cp /out/tls/root.crt /etc/pki/ca-trust/source/anchors/polyglotic-574-stand-in.crt
  update-ca-trust
  export UV_PROJECT_ENVIRONMENT=/tmp/venv UV_PYTHON=3.12.15 UV_PYTHON_PREFERENCE=only-managed
  uv sync --locked > "$here/uv-sync.log" 2>&1 || { tail -30 "$here/uv-sync.log"; exit 1; }
  echo "574: $(date +%T) the tour's own environment made (the app is the AppImage)"
  screen=gnome; [ "$desktop" = kde ] && screen=kde
  export LINUX_SESSION_SCREEN=$screen IN_SESSION_574=1
  exec dbus-run-session -- bash tools/linux_session.sh "$here/session" -- \
    bash tools/linux_packed_tour.sh "$desktop" "$out" "$appimage"
fi

if [ -z "${IN_SESSION_574:-}" ]; then  # the runner's own session, then here again
  stand_in_root
  sudo cp "$out/tls/root.crt" /usr/local/share/ca-certificates/polyglotic-574-stand-in.crt
  sudo update-ca-certificates > /dev/null
  case "$desktop" in gnome) export LINUX_SESSION_SCREEN=gnome ;; *) export LINUX_SESSION_SCREEN=xvfb ;; esac
  # Xfce: a bare desktop with no keyring at all - the app's own file instead
  [ "$desktop" = xfce ] && export LINUX_SESSION_KEYRING=none
  export IN_SESSION_574=1
  exec dbus-run-session -- bash tools/linux_session.sh "$here/session" -- \
    bash tools/linux_packed_tour.sh "$desktop" "$out" "$appimage"
fi

# the portal's backend: GTK's, as Ubuntu's desktops have one; KDE's own on
# KDE - started here, with its log - and GTK's after it if it won't run. Set
# before the desktop starts: its shell asks the portal first, and the portal
# keeps the backends it found then (run 44744836219: no file chooser on KDE)
mkdir -p "$HOME/.config/xdg-desktop-portal"
if [ "$desktop" != kde ]; then
  printf '[preferred]\ndefault=gtk\n' > "$HOME/.config/xdg-desktop-portal/portals.conf"
else
  printf '[preferred]\ndefault=kde;gtk\n' > "$HOME/.config/xdg-desktop-portal/portals.conf"
  # no screen locker over the tour (run 44746214946: KDE locked its screen)
  if command -v kwriteconfig6 > /dev/null; then
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key Autolock false
    kwriteconfig6 --file kscreenlockerrc --group Daemon --key LockOnResume false
  fi
fi
dbus-update-activation-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR \
  > /dev/null 2>&1 || true
started=()
tray=no scheme="" pictures=gnome beneath=wayland dialogs=() voice=()
case "$desktop" in
xfce)
  export XDG_CURRENT_DESKTOP=XFCE XDG_SESSION_TYPE=x11
  conf="$HOME/.config/xfce4/xfconf/xfce-perchannel-xml"
  mkdir -p "$conf"
  cp /etc/xdg/xfce4/panel/default.xml "$conf/xfce4-panel.xml" 2>/dev/null || true
  xfwm4 > "$here/xfwm4.log" 2>&1 & started+=($!)
  xfce4-panel > "$here/xfce4-panel.log" 2>&1 & started+=($!)
  tray=yes scheme=light pictures=xfce beneath=xcb voice=(--voice)
  ;;
kde)
  export XDG_CURRENT_DESKTOP=KDE XDG_SESSION_TYPE=wayland KDE_FULL_SESSION=true
  timeout 1500 kded6 > "$here/kded6.log" 2>&1 & started+=($!)
  sleep 3
  QT_QPA_PLATFORM=wayland timeout 1500 plasmashell > "$here/plasmashell.log" 2>&1 & started+=($!)
  tray=yes pictures=kde dialogs=(--dialogs)
  ;;
gnome|fedora-gnome)
  export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_TYPE=wayland
  scheme=dark dialogs=(--dialogs)
  ;;
ubuntu)  # Ubuntu's GNOME: the shell itself, headless, with Ubuntu's AppIndicator extension
  export XDG_CURRENT_DESKTOP=ubuntu:GNOME XDG_SESSION_TYPE=wayland
  gsettings set org.gnome.shell disable-user-extensions false
  gsettings set org.gnome.shell enabled-extensions "['ubuntu-appindicators@ubuntu.com']"
  before="$(ls /tmp/.X11-unix 2>/dev/null || true)"
  gnome-shell --headless --wayland --virtual-monitor 1920x1080 --wayland-display wayland-574 \
    > "$here/gnome-shell.log" 2>&1 & started+=($!)
  for _ in $(seq 60); do [ -S "$XDG_RUNTIME_DIR/wayland-574" ] && break; sleep 0.5; done
  xs=""
  for _ in $(seq 60); do
    xs="$(comm -13 <(echo "$before" | sort) <(ls /tmp/.X11-unix 2>/dev/null | sort) | head -1)"
    [ -n "$xs" ] && break; sleep 0.5
  done
  [ -n "$xs" ] || { echo "the shell's XWayland didn't start"; tail -30 "$here/gnome-shell.log"; exit 1; }
  export WAYLAND_DISPLAY=wayland-574 DISPLAY=":${xs#X}"
  auth="$(ls "$XDG_RUNTIME_DIR"/.mutter-Xwaylandauth.* 2>/dev/null | head -1 || true)"
  [ -n "$auth" ] && export XAUTHORITY="$auth"
  echo "GNOME Shell: $(gnome-shell --version 2>&1 | head -1)" >> "$here/versions.txt"
  # the shell starts in its Overview, which hides the windows' own places
  # (run 44741788128): out of it, as a session is once its learner starts
  sleep 3
  gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell \
    --method org.freedesktop.DBus.Properties.Set org.gnome.Shell OverviewActive '<false>' \
    > "$here/overview.log" 2>&1 || true
  tray=yes scheme=light dialogs=(--dialogs)
  ;;
esac
# Save transcript's and the export's dialogs: the app's buttons pressed as a
# screen reader presses them, through AT-SPI (tools/linux_atspi_press.py)
[ ${#dialogs[@]} -gt 0 ] && export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
dbus-update-activation-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP \
  XDG_SESSION_TYPE XDG_RUNTIME_DIR > /dev/null 2>&1 || true
if [ -n "$scheme" ] && command -v gsettings > /dev/null; then
  gsettings set org.gnome.desktop.interface color-scheme "prefer-$scheme" > "$here/gsettings.log" 2>&1 || true
fi
sleep 8
if [ "$desktop" = kde ] && [ -x /usr/libexec/xdg-desktop-portal-kde ]; then
  QT_QPA_PLATFORM=wayland /usr/libexec/xdg-desktop-portal-kde > "$here/portal-kde.log" 2>&1 & started+=($!)
  sleep 3
fi
echo "574: $(date +%T) the desktop started ($desktop)"
if [ "$tray" = yes ]; then  # a host for KDE's watcher where Plasma's shell didn't start (571)
  uv run --no-sync python -m tools.linux_tray_menu "$here/tray-host.json" --host \
    > "$here/tray-host.log" 2>&1 & started+=($!)
  sleep 3
fi
# a full-screen window, focused, beneath the app: a video or a game
# (its own interpreter, so the tour can end it by its PID before Home's picture)
py="$(uv run --no-sync python -c 'import sys; print(sys.executable)')"
QT_QPA_PLATFORM=$beneath "$py" -m tools.linux_desktop_pictures fullscreen \
  > "$here/fullscreen.log" 2>&1 & started+=($!)
export POLYGLOTIC_BENEATH_PID=$!
if [ "$pictures" != xfce ]; then
  uv run --no-sync python -m tools.linux_desktop_pictures serve "$here/desk" "$pictures" \
    > "$here/pictures.log" 2>&1 & started+=($!)
fi
sleep 5
timeout 1200 uv run --no-sync python -m tools.linux_packed_tour "$here" --appimage "$appimage" \
  --desktop "$desktop" --tray "$tray" --scheme "$scheme" \
  --tls "$out/tls/server.crt" "$out/tls/server.key" --pictures "$here/desk" "${dialogs[@]}" "${voice[@]}"
code=$?
touch "$here/desk/stop"
sleep 1
for pid in "${started[@]}"; do kill "$pid" 2>/dev/null; done
chmod -R a+rwX "$out" 2>/dev/null || true
exit "$code"
