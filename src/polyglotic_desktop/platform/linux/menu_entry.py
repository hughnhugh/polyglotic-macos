"""The app's own menu entry and icon on Linux (polyglotic-hq 546 section 1.7,
561) - the `TaskbarIdentity` port: Velopack's AppImage installs nothing,
so at each start the app writes them itself, for this user:

- `$XDG_DATA_HOME/applications/<id>.desktop` (`~/.local/share/...`): the
  menu entry (GNOME's Activities, KDE's launcher), started by the
  AppImage's own path - rewritten when the file has moved, so it still
  starts; `TryExec` names the file too, so the desktops leave the entry
  out once it's deleted. Its name is the app's ID (`io.polyglotic.
  Polyglotic`), as the keyring's and the sound server's (and, later, the
  shortcuts portal's) identity - a preview's pack its own, so it never
  takes the real app's entry over;
- `$XDG_DATA_HOME/icons/hicolor/scalable/apps/<id>.svg`: the app's icon,
  the entry's and the windows' in the panel.

The windows are matched to the entry by `StartupWMClass` (Qt's window
class is the application's name, `Polyglotic`) and Qt's desktop file name.
Only an AppImage writes them (`$APPIMAGE` and `$APPDIR`, as its runtime
sets them): from source there's no file to start. Nothing written can stop
a start: a folder that can't be written is logged and left.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

log = logging.getLogger(__name__)

APP_ID = "io.polyglotic.Polyglotic"
"""The desktop file's name: the app's ID (as `secret_service.APP_ID`)."""
PACK_ID = "Polyglotic"
"""The released app's Velopack pack ID (`tools/package/pack.sh`)."""
WINDOW_CLASS = "Polyglotic"
"""Qt's X11 window class: the application's name, as `main` sets it."""
CATEGORIES = "Education;Languages;"
_RESERVED = set(" \t\n\"'\\><~|&;$*?#()`")
"""What makes the Desktop Entry spec's `Exec` need its argument quoted."""


@dataclass(frozen=True, slots=True)
class MenuEntry:
    """What the menu entry says: its ID, the name shown, and the AppImage
    it starts."""

    id: str
    name: str
    appimage: str


def entry_id(pack_id: str) -> str:
    """The desktop file's name for a pack: the app's ID for the released
    app's, and `io.polyglotic.<pack>` for any other (a preview's)."""
    if pack_id in ("", PACK_ID):
        return APP_ID
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", pack_id)
    return f"io.polyglotic.{safe}"


def read_pack(mount: Path) -> tuple[str, str]:
    """The pack's ID and title, from Velopack's manifest inside the
    AppImage (`usr/bin/sq.version`, a nuspec); the released app's if it
    can't be read."""
    try:
        root = ElementTree.parse(mount / "usr" / "bin" / "sq.version").getroot()
    except (OSError, ElementTree.ParseError):
        return PACK_ID, PACK_ID
    pack = (root.findtext(".//{*}id") or "").strip() or PACK_ID
    title = (root.findtext(".//{*}title") or "").strip() or pack
    return pack, title


def this_entry(environ: Mapping[str, str] | None = None) -> MenuEntry | None:
    """The entry for the AppImage this copy runs from; None from source."""
    env = os.environ if environ is None else environ
    file, mount = env.get("APPIMAGE", ""), env.get("APPDIR", "")
    if not file.startswith("/") or not mount:
        return None
    pack, title = read_pack(Path(mount))
    return MenuEntry(entry_id(pack), title, file)


def _string(value: str) -> str:
    """A desktop file's string value, escaped (the spec's `\\s`, `\\n`...)."""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )


def exec_line(appimage: str) -> str:
    """`Exec`'s value: the AppImage's path - quoted where the spec asks, its
    `"`, `` ` ``, `$` and `\\` escaped inside the quotes - and `%` doubled,
    then escaped as a string."""
    path = appimage
    if any(c in _RESERVED for c in path):
        inner = re.sub(r'(["`$\\])', r"\\\1", path)
        path = f'"{inner}"'
    return _string(path.replace("%", "%%"))


def desktop_file(entry: MenuEntry) -> str:
    """The `.desktop` file's text."""
    lines = (
        "[Desktop Entry]",
        "Type=Application",
        f"Name={_string(entry.name)}",
        f"Exec={exec_line(entry.appimage)}",
        f"TryExec={_string(entry.appimage)}",
        f"Icon={entry.id}",
        "Terminal=false",
        f"Categories={CATEGORIES}",
        f"StartupWMClass={WINDOW_CLASS}",
    )
    return "\n".join(lines) + "\n"


def data_home(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """`$XDG_DATA_HOME` if it's absolute, else `~/.local/share`."""
    given = (os.environ if environ is None else environ).get("XDG_DATA_HOME", "")
    if given and Path(given).is_absolute():
        return Path(given)
    return (home or Path.home()) / ".local" / "share"


def _kept(path: Path, content: bytes) -> bool:
    """`content` at `path` - written (atomically, 0644) only if it differs:
    whether anything was written."""
    try:
        if path.read_bytes() == content:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f".{path.name}.part")
    part.write_bytes(content)
    part.chmod(0o644)
    os.replace(part, path)
    return True


def write_entry(entry: MenuEntry, icon: Path, data: Path) -> bool:
    """The entry and its icon under `data` (`$XDG_DATA_HOME`); whether
    either changed. OSError if they can't be written."""
    desktop = data / "applications" / f"{entry.id}.desktop"
    svg = data / "icons" / "hicolor" / "scalable" / "apps" / f"{entry.id}.svg"
    changed = _kept(svg, icon.read_bytes())
    return _kept(desktop, desktop_file(entry).encode("utf-8")) or changed


def taskbar_identity(
    name: str,
    icon: Path,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    desktop_name: Callable[[str], None] | None = None,
) -> str:
    """`TaskbarIdentity` on Linux: as an AppImage, its menu entry and icon
    written (or brought up to date) and Qt told the entry's name, which is
    the ID returned; from source, `name` as it is. `desktop_name`: what
    takes the entry's name (Qt's `setDesktopFileName`, unless a test's)."""
    entry = this_entry(environ)
    if entry is None:
        return name
    if "\n" in entry.appimage:
        log.warning("menu entry: the AppImage's path can't be written into one")
        return name
    try:
        if write_entry(entry, icon, data_home(environ, home)):
            log.info("menu entry: written for this AppImage")
    except OSError as e:  # never a reason not to start
        log.warning("menu entry: not written (%s)", type(e).__name__)
    if desktop_name is None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.setDesktopFileName(entry.id)
    else:
        desktop_name(entry.id)
    return entry.id
