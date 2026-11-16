"""Calls into Qt's own libraries that don't hold Python's interpreter
(polyglotic-hq 322, decisions 0112 and 0113).

PySide6 keeps the interpreter (the GIL) for the whole of most calls into
Qt, so a long one made on any Python thread stops every other: measured, a
thread listing Qt's font families left the interface thread a tenth of its
turns. ctypes lets the interpreter go for the length of a call. So the few
long calls that need nothing of Python are made straight into Qt's library
- the one PySide6 has already loaded, never a second copy - by the name
MSVC gives the function. Each is public Qt API, and Qt keeps its libraries'
names for the whole of Qt 6; a test finds each name in the Qt this app is
built with, so an update that loses one is seen before it ships. Where a
name isn't found the call isn't made, and says so: the caller's work is
then done as before, by Qt, when it's first needed.
"""

import ctypes
from ctypes import wintypes
from typing import Any

GUI_LIBRARY = "Qt6Gui.dll"

EVERY_FAMILY_READ = (
    "?writingSystems@QFontDatabase@@SA?AV?$QList@W4WritingSystem@QFontDatabase@@@@XZ"
)
"""`static QList<QFontDatabase::WritingSystem> QFontDatabase::writingSystems()`:
it reads the list of Windows' font families, then every family's faces,
and nothing else - what Qt otherwise does at the first font used (the
list) and at the first font list that needs a fallback (every family:
`QPlatformFontDatabase::fallbacksForFamily`). `QFontDatabase` is
thread-safe (Qt's documentation)."""

WIDGETS_LIBRARY = "Qt6Widgets.dll"

NATIVE_WINDOW = "?winId@QWidget@@QEBA_KXZ"
"""`WId QWidget::winId() const`: the widget is given its window of Windows'
if it has none. The interface thread's to call, like any use of a widget."""


def exported(library: str, name: str) -> Any | None:
    """The function `name` of `library` as this process has it loaded (a
    ctypes function: its types are the caller's to set), or None: the library isn't loaded here, or has no such function."""
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    handle = kernel32.GetModuleHandleW(library)
    if not handle:
        return None
    try:
        return ctypes.CDLL(library, handle=handle)[name]
    except AttributeError:
        return None


def read_fonts() -> bool:
    """Windows' fonts read by Qt now, on this thread, without the
    interpreter: about 0.3 s on a PC with 340 families. For a thread of its
    own, once the QGuiApplication exists (Qt's font database is its
    platform's). False, and nothing done, where the call can't be made.

    Qt answers with a list of at most 34 numbers, written where the caller
    says: three pointers' room, as MSVC returns an object. It is never
    freed - about 150 bytes, once a run."""
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return False
    read = exported(GUI_LIBRARY, EVERY_FAMILY_READ)
    if read is None:
        return False
    read.restype = None
    read.argtypes = [ctypes.c_void_p]
    answer = (ctypes.c_void_p * 3)()
    read(answer)
    return True


def make_native_window(widget: int) -> bool:
    """The QWidget at the address `widget` (shiboken's pointer to it) is
    given its window of Windows' now, without the interpreter: on the
    interface thread, where every use of a widget belongs. The first one a
    process makes costs about 0.1 s, Windows' own first-time work. False,
    and nothing done, where the call can't be made."""
    if ctypes.sizeof(ctypes.c_void_p) != 8:
        return False
    make = exported(WIDGETS_LIBRARY, NATIVE_WINDOW)
    if make is None:
        return False
    make.restype = ctypes.c_size_t
    make.argtypes = [ctypes.c_void_p]
    return bool(make(widget))
