"""Which Windows this is, and where the user's own files live (decision 0038:
`ports/system.py`'s `OsVersion` and `DataFolder`, and protocol.md's `os`).

Moved here from `connection.app` and `main` (polyglotic-hq 179) unchanged:
they ask Windows, so only `main` reaches them, through `main.os_adapters`.
"""

import os
import sys
from pathlib import Path
from typing import Literal

WINDOWS_11_BUILD = 22000
"""Windows 11 still reports itself as version 10.0; its builds start here."""


def os_name(build: int | None = None) -> Literal["windows-10", "windows-11"]:
    """`windows-10` or `windows-11` (protocol.md's `os`), from Windows' build
    number."""
    if build is None:
        build = sys.getwindowsversion().build
    return "windows-11" if build >= WINDOWS_11_BUILD else "windows-10"


def os_version() -> str:
    """Windows' version number, as feedback carries it (`10.0.26200`)."""
    found = sys.getwindowsversion()
    return f"{found.major}.{found.minor}.{found.build}"


def windows_build() -> str:
    """Windows' build and the update it's at (`19045.5131`; the build alone
    if the update can't be read): on Windows 10 the update decides whether
    one app can be captured alone (win-capture-audio asks for "an updated
    version of Windows 10 2004"; decision 0076). Content-free."""
    build = sys.getwindowsversion().build
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        ) as key:
            update, _ = winreg.QueryValueEx(key, "UBR")
    except OSError:
        return str(build)
    return f"{build}.{update}" if isinstance(update, int) else str(build)


def data_folder() -> Path:
    """The user's own files - settings, learning data, the outbox - in their
    roaming app data: the installer replaces or removes the whole install
    folder, `%LOCALAPPDATA%\\Polyglotic`, on install and uninstall (decision
    0014)."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Polyglotic"
