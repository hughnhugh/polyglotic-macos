"""Which macOS this is, where the user's own files live, how long ago the
process was launched, whether the menu bar is light, and the box an app
shows when it can't start (decision 0038: `ports/system.py`'s pieces, and
protocol.md's `os`) - Windows' `platform/windows/system.py`,
`process.py`, `taskbar.py` and `error_box.py` for the Mac.
"""

import ctypes
import ctypes.util
import platform
import time
from pathlib import Path

from polyglotic_desktop.platform.macos import cf

APP_FOLDER = "Polyglotic"
"""The app ID (ENGINEERING.md, "Releases"), as the Windows folder's."""

_IMPORTED = time.monotonic()


def os_name(version: str | None = None) -> str:
    """`macos-<major>` (protocol.md's `os`: `macos-26`), from macOS's
    version - `platform.mac_ver()`'s, unless one is given."""
    found = version if version is not None else platform.mac_ver()[0]
    major = found.split(".", 1)[0]
    if not major.isdigit() or int(major) < 1:
        raise OSError(f"macOS's version can't be read ({found!r})")
    return f"macos-{int(major)}"


def os_version() -> str:
    """macOS's version number, as feedback carries it (`26.1`)."""
    return platform.mac_ver()[0]


def data_folder(home: Path | None = None) -> Path:
    """The user's own files - settings, learning data, the outbox - in
    `~/Library/Application Support/Polyglotic` (decision 0185): where
    macOS apps keep theirs, which removing the app from Applications
    leaves alone."""
    return (home or Path.home()) / "Library" / "Application Support" / APP_FOLDER


def light_menu_bar(style: str | None = None) -> bool:
    """`LightTaskbar` on a Mac: True unless macOS is in Dark Mode (the menu
    bar the menu-bar icon sits in follows it). `style`: the user's
    `AppleInterfaceStyle`, read from macOS's preferences unless given
    ("Dark", or none at all in Light Mode)."""
    if style is None:
        style = _interface_style()
    return style != "Dark"


def _interface_style() -> str | None:
    """The user's `AppleInterfaceStyle`; None in Light Mode, or if it can't
    be read."""
    try:
        libs = cf.libraries()
        key = cf.create_string("AppleInterfaceStyle")
        with cf.owned(key):
            found = libs.cf.CFPreferencesCopyAppValue(
                key, libs.constant("kCFPreferencesAnyApplication", "cf")
            )
        with cf.owned(found):
            return cf.text(found)
    except OSError:
        return None


class _BsdInfo(ctypes.Structure):
    """libproc's `struct proc_bsdinfo`, as far as the start time."""

    _fields_ = [
        ("ids", ctypes.c_uint32 * 12),  # flags, status ... rfu_1
        ("comm", ctypes.c_char * 16),
        ("name", ctypes.c_char * 32),
        ("more", ctypes.c_uint32 * 5),  # nfiles, pgid, pjobc, e_tdev, e_tpgid
        ("nice", ctypes.c_int32),
        ("start_tvsec", ctypes.c_uint64),
        ("start_tvusec", ctypes.c_uint64),
    ]


_PROC_PIDTBSDINFO = 3


def seconds_since_launch() -> float:
    """Seconds since macOS started this process (libproc's start time);
    since this module was imported if macOS won't say - the interpreter's
    own start then isn't counted."""
    import os

    try:
        path = ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib"
        libproc = ctypes.CDLL(path)
        info = _BsdInfo()
        size = ctypes.sizeof(info)
        if (
            libproc.proc_pidinfo(
                os.getpid(), _PROC_PIDTBSDINFO, 0, ctypes.byref(info), size
            )
            == size
        ):
            started = info.start_tvsec + info.start_tvusec / 1_000_000
            return max(0.0, time.time() - started)
    except OSError:
        pass
    return time.monotonic() - _IMPORTED


def show_error(title: str, text: str) -> None:
    """`ErrorBox`: Core Foundation's own alert (no Qt, no event loop), until
    it's closed; printed if even that can't be shown."""
    try:
        libs = cf.libraries()
        header, message = cf.create_string(title), cf.create_string(text)
        with cf.owned(header, message):
            libs.cf.CFUserNotificationDisplayAlert(
                0.0, 0, None, None, None, header, message, None, None, None, None
            )
    except OSError:
        print(f"{title}: {text}")
