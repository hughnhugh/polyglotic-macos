"""Starting at sign-in on Linux (polyglotic-hq 546's slice 4, 571;
`ports.startup`, as `platform/windows/startup.py` is Windows' and
`platform/macos/startup.py` the Mac's): an XDG autostart entry,
`$XDG_CONFIG_HOME/autostart/<id>.desktop` (`~/.config/autostart`), which
GNOME, KDE, Xfce, Cinnamon and the rest start at sign-in - no
administrator, and each desktop's own startup settings list it and can
turn it off.

- **Off by default:** nothing is written until the learner turns it on
  (Settings > App, or Home's question after a good session).
- **The AppImage itself:** the entry starts the AppImage's own path
  (`$APPIMAGE`, never the mount it runs from), in the tray (`--in-tray`;
  where the desktop has no tray, `main` shows the window). Its name is the
  menu entry's (`menu_entry`: the app's ID, a preview's its own), as the
  Desktop Entry spec asks of an autostart file.
- **Moved, still started:** while it's on, each start rewrites it for the
  AppImage it runs from (`follow`), so a file moved to another folder
  still starts. `TryExec` names the file too: a deleted AppImage's entry
  is skipped, not an error at sign-in.
- **Turned off** - here or in the desktop's settings, which write
  `Hidden=true` or `X-GNOME-Autostart-enabled=false` into the same file -
  is off: `enabled` reads both.

From source there's no AppImage to start: nothing is written and it's
never on (`main` offers it only to the packed app anyway). Nothing here
can stop a start: a folder that can't be written is logged and left.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from polyglotic_desktop.platform.linux import menu_entry
from polyglotic_desktop.ports.startup import IN_TRAY

log = logging.getLogger(__name__)

OFF_KEYS = (("Hidden", "true"), ("X-GNOME-Autostart-enabled", "false"))
"""How a desktop's own settings turn an autostart entry off in place."""


def config_home(
    environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """`$XDG_CONFIG_HOME` if it's absolute, else `~/.config`."""
    given = (os.environ if environ is None else environ).get("XDG_CONFIG_HOME", "")
    if given and Path(given).is_absolute():
        return Path(given)
    return (home or Path.home()) / ".config"


def autostart_file(entry: menu_entry.MenuEntry) -> str:
    """The autostart entry's text: the menu entry's, started in the tray."""
    lines = menu_entry.desktop_file(entry).splitlines()
    lines = [
        f"{line} {IN_TRAY}" if line.startswith("Exec=") else line for line in lines
    ]
    lines += ["X-GNOME-Autostart-enabled=true", "X-KDE-autostart-phase=2"]
    return "\n".join(lines) + "\n"


class XdgAutostart:
    """`StartWithWindows` on Linux: the AppImage this copy runs from as an
    XDG autostart entry. `_executable` (the app's own, inside the AppImage's
    mount) isn't used: the AppImage's path is (`$APPIMAGE`)."""

    def __init__(
        self,
        _executable: str = "",
        environ: Mapping[str, str] | None = None,
        home: Path | None = None,
    ) -> None:
        self._entry = menu_entry.this_entry(environ)
        self._folder = config_home(environ, home) / "autostart"

    @property
    def path(self) -> Path | None:
        """The entry's file; None from source (no AppImage)."""
        if self._entry is None:
            return None
        return self._folder / f"{self._entry.id}.desktop"

    def enabled(self) -> bool:
        path = self.path
        if path is None:
            return False
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        said = {
            k.strip(): v.strip().lower()
            for k, _, v in (x.partition("=") for x in lines)
        }
        return not any(said.get(key) == off for key, off in OFF_KEYS)

    def set_enabled(self, on: bool) -> None:
        path = self.path
        if path is None or self._entry is None:
            log.info("start at sign-in: not an AppImage, nothing to start")
            return
        try:
            if on:
                path.parent.mkdir(parents=True, exist_ok=True)
                part = path.with_name(f".{path.name}.part")
                part.write_text(
                    autostart_file(self._entry), encoding="utf-8", newline="\n"
                )
                os.replace(part, path)
            else:
                path.unlink(missing_ok=True)
        except OSError as e:  # the port's rule: quietly, said in the log
            log.warning("start at sign-in: not %s (%s)", "written" if on else "removed",
                        type(e).__name__)  # fmt: skip

    def follow(self) -> None:
        """At each start, while it's on: the entry rewritten for the AppImage
        this copy runs from - a file moved since still starts."""
        path = self.path
        if path is None or self._entry is None or not self.enabled():
            return
        try:
            if path.read_text(encoding="utf-8") != autostart_file(self._entry):
                self.set_enabled(True)
                log.info("start at sign-in: brought up to date for this AppImage")
        except OSError:
            return


__all__ = ["XdgAutostart", "autostart_file", "config_home"]
