"""The windows on screen, front to back, as macOS's window list gives them
(polyglotic-hq 429): each one's number, layer (its level), owner's process
and place - never its title or what it shows - and which app is in front. No Screen Recording
permission is needed for these, and none is asked; nothing is captured.

Dictation types only into the window that had the keyboard when the speech
was cut (`text_input.keyboard_window`: the front app's frontmost ordinary
window), and the Mac's checks read where the caption windows are against
a full-screen app (`tools.macos_full_screen_checks`).
"""

import ctypes
import ctypes.util
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from polyglotic_desktop.platform.macos import cf, objc

ON_SCREEN_ONLY = 1 << 0
"""`kCGWindowListOptionOnScreenOnly`."""
EXCLUDE_DESKTOP = 1 << 4
"""`kCGWindowListExcludeDesktopElements`: not the desktop's picture or icons."""
SINT64 = 4
"""`kCFNumberSInt64Type`."""


@dataclass(frozen=True, slots=True)
class Listed:
    """A window on screen: its number (`NSWindow.windowNumber`), its layer
    (its level: 0 ordinary, 1000 the screen saver's), its owner's process,
    and its place (left, top, width, height; the main screen's top left is
    0, 0)."""

    number: int
    layer: int
    pid: int
    bounds: tuple[float, float, float, float]


def front_window(listed: Iterable[Listed], pid: int) -> int:
    """The number of `pid`'s frontmost ordinary window (layer 0) in a
    front-to-back list; 0 if it has none."""
    for window in listed:
        if window.pid == pid and window.layer == 0:
            return window.number
    return 0


class _CGRect(ctypes.Structure):
    _fields_ = (
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("width", ctypes.c_double),
        ("height", ctypes.c_double),
    )


class _Graphics:
    def __init__(self) -> None:
        path = ctypes.util.find_library("CoreGraphics")
        if path is None:
            raise OSError("macOS's CoreGraphics framework isn't here")
        self.cg = ctypes.CDLL(path)
        p, index = ctypes.c_void_p, ctypes.c_long
        self.cg.CGWindowListCopyWindowInfo.restype = p
        self.cg.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        self.cg.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
        self.cg.CGRectMakeWithDictionaryRepresentation.argtypes = [
            p,
            ctypes.POINTER(_CGRect),
        ]
        core = cf.libraries().cf
        self.count = ctypes.CFUNCTYPE(index, p)(("CFArrayGetCount", core))
        self.at = ctypes.CFUNCTYPE(p, p, index)(("CFArrayGetValueAtIndex", core))
        self.number = ctypes.CFUNCTYPE(ctypes.c_bool, p, ctypes.c_long, p)(
            ("CFNumberGetValue", core)
        )
        self.keys = {
            name: ctypes.c_void_p.in_dll(self.cg, f"kCGWindow{name}").value
            for name in ("Number", "Layer", "OwnerPID", "Bounds")
        }


@cache
def _graphics() -> _Graphics:
    return _Graphics()


def _integer(dictionary: int, key: int | None) -> int | None:
    found = cf.value(dictionary, key) if key else None
    if found is None:
        return None
    out = ctypes.c_int64()
    if not _graphics().number(found, SINT64, ctypes.byref(out)):
        return None
    return out.value


def on_screen() -> list[Listed]:
    """The windows on screen now, front to back (the desktop's left out)."""
    g = _graphics()
    array = g.cg.CGWindowListCopyWindowInfo(ON_SCREEN_ONLY | EXCLUDE_DESKTOP, 0)
    if not array:
        return []
    listed = []
    with cf.owned(array):
        for i in range(g.count(array)):
            info = g.at(array, i)
            number = _integer(info, g.keys["Number"])
            layer = _integer(info, g.keys["Layer"])
            pid = _integer(info, g.keys["OwnerPID"])
            if number is None or layer is None or pid is None:
                continue
            rect = _CGRect()
            bounds = cf.value(info, g.keys["Bounds"]) if g.keys["Bounds"] else None
            if bounds:
                g.cg.CGRectMakeWithDictionaryRepresentation(bounds, ctypes.byref(rect))
            listed.append(
                Listed(number, layer, pid, (rect.x, rect.y, rect.width, rect.height))
            )
    return listed


def front_pid() -> int:
    """The process of the app in front (0: none)."""
    objc.load("AppKit")
    with objc.pool():
        workspace = objc.send(objc.cls("NSWorkspace"), "sharedWorkspace")
        app = objc.send(workspace, "frontmostApplication")
        if not app:
            return 0
        return int(objc.send(app, "processIdentifier", restype=ctypes.c_int))
