"""The taskbar: whether Windows draws it light or dark, for the tray icon;
and the ID it knows the app by.

**Light or dark.** Windows sets the taskbar ("Windows mode") apart from apps ("app mode"):
Windows 10's default is a dark taskbar with light apps, so Qt's colour
scheme - the apps' - can't say. The ink tray icon is only 1.05:1 on a dark
taskbar (polyglotic-hq project 091), so the tray picks its version from
this. `main` hands it to the UI.

**The app's ID** (its AppUserModelID, decision 0051): Windows groups,
pins and draws a process's windows on the taskbar by it. Velopack's
start-up names the installed app from the pack; the Microsoft Store's copy
has its package's (decision 0056); from source nothing does, and the app
was `python.exe` to Windows. `main` names it, before any window, if
nothing has.
"""

import ctypes
import winreg
from ctypes import wintypes

from polyglotic_desktop.platform.windows import package

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def light_taskbar() -> bool:
    """True if the taskbar is light; dark if Windows doesn't say (before
    Windows 10 1903 the taskbar was always dark)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
    except OSError:
        return False
    return value == 1


# --- the app's name on the taskbar (polyglotic-hq 245, decision 0051) --------

_shell32 = ctypes.WinDLL("shell32")
_ole32 = ctypes.WinDLL("ole32")
_shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
_shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
_shell32.GetCurrentProcessExplicitAppUserModelID.argtypes = [
    ctypes.POINTER(ctypes.c_void_p)
]
_shell32.GetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
_ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]


def app_identity(from_source: str) -> str:
    """The AppUserModelID Windows groups, pins and draws this process's
    windows by on the taskbar: the one the installer's start-up already gave
    it (Velopack: the pack's `--aumid`, the one its shortcuts get, else
    `velopack.<pack ID>`), so a rehearsal pack stays apart from the real
    app; an MSIX package's own (`<family name>!Polyglotic`), the only one a
    package may use; else - from source - `from_source`. Call before any
    window. Returns the ID Windows has, or "" if it wouldn't take one."""
    packaged = package.packaged_app_id()
    if packaged is not None:  # never set another: its pins would be another app's
        return packaged
    named = explicit_app_id()
    if named is not None:
        return named
    if _shell32.SetCurrentProcessExplicitAppUserModelID(from_source) != 0:
        return ""
    return explicit_app_id() or ""


def explicit_app_id() -> str | None:
    """This process's explicit AppUserModelID, or None if it has none
    (Windows then makes one from the exe's path, which it doesn't say)."""
    found = ctypes.c_void_p()
    if _shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(found)) != 0:
        return None
    try:
        return ctypes.wstring_at(found.value) if found.value else None
    finally:
        _ole32.CoTaskMemFree(found)
