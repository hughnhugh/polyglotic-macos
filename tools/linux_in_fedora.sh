#!/usr/bin/env bash
# The app's tour on Fedora's own desktops (polyglotic-hq 550): GNOME's newest
# window manager or KDE Plasma 6's, in a `fedora:45` container on GitHub's
# Ubuntu runner - the repo mounted, Fedora's own packages, the app's from
# uv.lock - then tools/linux_desktop_tour.sh in a session made there.
#
#   bash tools/linux_in_fedora.sh gnome|kde OUT
#
# KWin 6.8 has no software-only mode and quits without a render device
# (547): the runner's virtual DRM devices (vgem, vkms) give it one.
set -euo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "$(uname -s)" != Linux ]; then
  echo "550: this runs only on GitHub's Linux runners"; exit 2
fi
desktop="${1:?gnome or kde}"; out="$(realpath -m "${2:?OUT}")"
if [ -z "${IN_FEDORA_550:-}" ]; then
  mkdir -p "$out"
  root="$(cd "$(dirname "$0")/.." && pwd)"
  devices=()
  if [ "$desktop" = kde ]; then
    sudo modprobe vgem && sudo modprobe vkms
    devices=(--device /dev/dri)
  fi
  exec docker run --rm --cap-add SYS_NICE "${devices[@]}" \
    -e GITHUB_ACTIONS=true -e IN_FEDORA_550=1 -e POLYGLOTIC_LINUX_DESKTOP=1 \
    -v "$root:/w" -v "$out:/out" -v "$(command -v uv):/usr/local/bin/uv:ro" \
    -w /w fedora:45 bash /w/tools/linux_in_fedora.sh "$desktop" /out
fi
common=(xorg-x11-server-Xwayland pipewire wireplumber pipewire-pulseaudio pulseaudio-utils pipewire-utils
  pulseaudio-libs gnome-keyring dbus-daemon dbus-tools mesa-dri-drivers mesa-libEGL mesa-libGL
  libglvnd-egl xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms xcb-util-renderutil
  libxkbcommon-x11 libwayland-client libwayland-cursor libwayland-egl fontconfig
  google-noto-sans-fonts google-noto-sans-cjk-vf-fonts findutils procps-ng
  libXtst plasma-wayland-protocols)
if [ "$desktop" = kde ]; then
  more=(kwin kf6-kwallet)
else
  more=(mutter pipewire-gstreamer gstreamer1 gstreamer1-plugins-base gstreamer1-plugins-good)
fi
dnf -y -q install --skip-unavailable "${common[@]}" "${more[@]}" > /tmp/dnf.log 2>&1 \
  || { tail -30 /tmp/dnf.log; exit 1; }
{
  . /etc/os-release; echo "$PRETTY_NAME, kernel $(uname -r)"
  # rpm -q fails for the desktop not installed here: said, not a failure
  rpm -q mutter kwin kf6-kwallet xorg-x11-server-Xwayland pipewire wireplumber gnome-keyring     2>/dev/null | grep -v "not installed" || true
} | tee /out/versions.txt
export UV_PROJECT_ENVIRONMENT=/tmp/venv UV_PYTHON=3.12.15 UV_PYTHON_PREFERENCE=only-managed
uv sync --locked > /out/uv-sync.log 2>&1 || { tail -30 /out/uv-sync.log; exit 1; }
# KDE's own keyring: does it take the app's plain session? (550) - in a
# session of its own, without gnome-keyring; nobody answers its password box
if [ "$desktop" = kde ]; then
  for daemon in ksecretd kwalletd6; do
    command -v "$daemon" > /dev/null || { echo "no $daemon" >> /out/versions.txt; continue; }
    XDG_RUNTIME_DIR="$(mktemp -d)" dbus-run-session -- bash -c "
      QT_QPA_PLATFORM=offscreen $daemon > /out/keyring-$daemon.log 2>&1 & keeper=\$!
      sleep 4
      timeout 120 uv run --no-sync python -m tools.linux_keyring_probe $daemon /out/keyring-$daemon.json
      kill \$keeper 2>/dev/null" || true
  done
fi
export LINUX_SESSION_SCREEN="$desktop"
dbus-run-session -- bash tools/linux_session.sh /out/session -- \
  bash tools/linux_desktop_tour.sh "$desktop" /out
