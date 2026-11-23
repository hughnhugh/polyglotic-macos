#!/usr/bin/env bash
# Chinese and Japanese typed into the app on Linux (polyglotic-hq 571): on
# GitHub's Ubuntu runner, in a clean `ubuntu:24.04` container (the repo
# mounted; Ubuntu's own input methods; the app's from uv.lock), each in a
# `dbus-run-session` of its own with an X screen (Xvfb) and one input method
# framework - IBus (`ibus-daemon`, no panel) or Fcitx5 (`fcitx5`, its IBus
# frontend on, pinyin in its profile) - then tools/linux_typing_check.py in
# it. What each said is in OUT.
#
#   bash tools/linux_typing_session.sh OUT
#
# GitHub's runners only: it installs packages, starts daemons a person's own
# session has already, and writes Fcitx5's profile in this HOME.
set -uo pipefail
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "$(uname -s)" != Linux ]; then
  echo "571: this runs only on GitHub's Linux runners"; exit 2
fi
out="$(realpath -m "${1:?OUT}")"
if [ -z "${IN_UBUNTU_571:-}" ]; then
  mkdir -p "$out"
  root="$(cd "$(dirname "$0")/.." && pwd)"
  exec docker run --rm -e GITHUB_ACTIONS=true -e IN_UBUNTU_571=1 -e UV_PYTHON -e UV_PYTHON_PREFERENCE \
    -v "$root:/w" -v "$out:/out" -v "$(command -v uv):/usr/local/bin/uv:ro" \
    -w /w ubuntu:24.04 bash /w/tools/linux_typing_session.sh /out
fi

if [ -z "${IN_SESSION_571:-}" ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq > /dev/null
  apt-get install -y -qq --no-install-recommends \
    ca-certificates xvfb xdotool dbus dbus-bin dbus-daemon \
    ibus ibus-libpinyin ibus-mozc mozc-server \
    fcitx5 fcitx5-chinese-addons fcitx5-modules \
    libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
    libegl1 libgl1 libfontconfig1 libdbus-1-3 libglib2.0-0t64 fonts-noto-core fonts-noto-cjk \
    > "$out/apt.log" 2>&1 || { tail -20 "$out/apt.log"; exit 1; }
  # Anthy, where the archive has it (24.04's doesn't): Mozc is Ubuntu's own
  apt-get install -y -qq --no-install-recommends ibus-anthy >> "$out/apt.log" 2>&1 || true
  apt-get install -y -qq --no-install-recommends fcitx5-mozc >> "$out/apt.log" 2>&1 || true
  dbus-uuidgen --ensure=/etc/machine-id
  dpkg-query -W -f='${Package} ${Version}\n' ibus ibus-libpinyin ibus-anthy ibus-mozc \
    fcitx5 fcitx5-chinese-addons fcitx5-mozc xdotool | tee "$out/versions.txt"
  export UV_PROJECT_ENVIRONMENT=/tmp/venv UV_PYTHON_INSTALL_DIR=/opt/uv-python
  uv sync --locked > "$out/uv-sync.log" 2>&1 || { tail -20 "$out/uv-sync.log"; exit 1; }
  # each session as a learner, not root: Mozc's server won't run as root
  useradd -m learner
  mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix
  chmod 777 "$out"
  code=0
  for im in ibus fcitx5 fcitx5-kubuntu; do
    # Kubuntu has no IBus installed: the container's own copy hidden
    [ "$im" = fcitx5-kubuntu ] && mv /usr/bin/ibus-daemon /usr/bin/ibus-daemon.571
    runuser -u learner -- env HOME=/home/learner IN_SESSION_571="$im"       dbus-run-session -- bash /w/tools/linux_typing_session.sh "$out/$im-session" || code=1
  done
  mv /usr/bin/ibus-daemon.571 /usr/bin/ibus-daemon
  exit "$code"
fi

im="$IN_SESSION_571"
mkdir -p "$out"
XDG_RUNTIME_DIR="$(mktemp -d)"; export XDG_RUNTIME_DIR; chmod 700 "$XDG_RUNTIME_DIR"
export GSETTINGS_BACKEND=memory
started=()
Xvfb :97 -screen 0 1600x1000x24 -nolisten tcp > "$out/xvfb.log" 2>&1 & started+=($!)
export DISPLAY=:97
for _ in $(seq 50); do [ -S /tmp/.X11-unix/X97 ] && break; sleep 0.1; done

code=0
check=(/tmp/venv/bin/python -m tools.linux_typing_check)
case "$im" in
ibus)
  # Mozc on in Hiragana from the start, as a learner who types Japanese
  # sets it (Mozc's own setting; IBus's Mozc starts in direct input)
  mkdir -p "$HOME/.config/mozc"
  # (the file is Mozc's whole IBus setting: its engine's entry as Mozc
  # writes it by default, and on at launch instead of off)
  cat > "$HOME/.config/mozc/ibus_config.textproto" <<'MOZC'
engines {
  name : "mozc-jp"
  longname : "Mozc"
  layout : "default"
  layout_variant : ""
  layout_option : ""
  rank : 80
}
active_on_launch: True
MOZC
  ibus-daemon --replace --panel=disable --xim > "$out/ibus.log" 2>&1 & started+=($!)
  for _ in $(seq 50); do ibus address > /dev/null 2>&1 && break; sleep 0.2; done
  sleep 2
  { echo "== $(ibus version 2>&1)"; ibus list-engine 2>&1 | grep -E -i "pinyin|anthy|mozc"; } \
    > "$out/engines.txt" 2>&1
  QT_IM_MODULE=ibus "${check[@]}" "$out/ibus" ibus || code=1
  { echo "== Mozc's processes after typing"; ps -eo pid,args | grep -i [m]ozc
    echo "== Mozc's files"; ls -la "$HOME/.config/mozc" "$HOME/.mozc" 2>&1; } > "$out/mozc.txt" 2>&1
  # a session that names no input method: Qt's own pick (compose alone) is
  # a finding; the app's own environment must type
  env -u QT_IM_MODULE -u QT_IM_MODULES "${check[@]}" "$out/ibus-unnamed" ibus-unnamed || true
  env -u QT_IM_MODULE -u QT_IM_MODULES "${check[@]}" "$out/ibus-unnamed-app" ibus-unnamed-app --app-env || code=1
  ;;
fcitx5|fcitx5-kubuntu)
  mkdir -p "$HOME/.config/fcitx5"
  cat > "$HOME/.config/fcitx5/profile" <<'PROFILE'
[Groups/0]
Name=Default
Default Layout=us
DefaultIM=pinyin

[Groups/0/Items/0]
Name=keyboard-us
Layout=

[Groups/0/Items/1]
Name=pinyin
Layout=

[Groups/0/Items/2]
Name=mozc
Layout=

[GroupOrder]
0=Default
PROFILE
  fcitx5 --replace --verbose='*=3' > "$out/fcitx5.log" 2>&1 & started+=($!)
  sleep 6
  {
    echo "== fcitx5 $(fcitx5 --version 2>&1)"
    echo "== the ibus address file(s) Fcitx5 wrote:"; ls -la "$HOME/.config/ibus/bus" 2>&1
    echo "== on the bus:"
    dbus-send --session --print-reply --dest=org.freedesktop.DBus /org/freedesktop/DBus       org.freedesktop.DBus.ListNames 2>&1 | grep -E -o '"[^"]*(IBus|Fcitx|fcitx)[^"]*"'
  } > "$out/engines.txt" 2>&1
  if [ "$im" = fcitx5 ]; then
    QT_IM_MODULE=ibus "${check[@]}" "$out/fcitx5" fcitx5 || code=1
    # Kubuntu's own setting asks Qt for Fcitx's plugin, which the app
    # doesn't carry: what Qt does alone is a finding; IBus's named after it
    QT_IM_MODULE=fcitx "${check[@]}" "$out/fcitx5-own-plugin" fcitx5-own-plugin || true
    QT_IM_MODULE=fcitx QT_IM_MODULES="fcitx;ibus" "${check[@]}" "$out/fcitx5-fallback"       fcitx5-fallback || true
  else
    # no IBus installed: Qt's IBus plugin gives up unless it's asked to use
    # the portal's IBus, which Fcitx5 also answers; the app's own
    # environment must type
    QT_IM_MODULE=fcitx QT_IM_MODULES="fcitx;ibus" "${check[@]}" "$out/fcitx5-no-ibus"       fcitx5-no-ibus || true
    QT_IM_MODULE=fcitx "${check[@]}" "$out/fcitx5-kubuntu-app" fcitx5-kubuntu-app --app-env       || code=1
  fi
  ;;
*) echo "ibus or fcitx5"; code=2 ;;
esac

for pid in "${started[@]}"; do kill "$pid" 2>/dev/null; done
exit "$code"
