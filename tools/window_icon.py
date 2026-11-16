r"""A window's icon as Windows has it - the one its title bar, the taskbar's
button and Alt-Tab draw - read from outside its process, as a picture
(polyglotic-hq 245).

Windows asks a window for its icon (`WM_GETICON`: the one the program set
with `WM_SETICON`) and falls back to its window class's (`GetClassLongPtr`).
Qt registers its window classes with the exe's `IDI_ICON1` resource, else
Windows' plain application icon, so a window shows the app's own only when
Qt is given one (`QApplication.setWindowIcon`). An icon handle is shared by
every process in the session, so its pixels can be copied out here - the
icon's own bitmap, nothing of the screen.

In code: `picture(icons_of(hwnd).shown("big"))`, then `is_the_app_icon(...)`.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if sys.platform != "win32":
    raise ImportError("tools.window_icon needs Windows: window icons are Windows'")

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

WM_GETICON = 0x007F
ICON_SMALL, ICON_BIG = 0, 1
GCLP_HICON, GCLP_HICONSM = -14, -34
SMTO_ABORTIFHUNG = 0x0002
BI_RGB, DIB_RGB_COLORS = 0, 0

Which = Literal["small", "big"]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class _BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", wintypes.LPVOID),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
_user32.SendMessageTimeoutW.restype = wintypes.LPARAM
_user32.GetClassLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetClassLongPtrW.restype = ctypes.c_size_t
_user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(_ICONINFO)]
_gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID]
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
    ctypes.POINTER(_BITMAPINFOHEADER),
    wintypes.UINT,
]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_gdi32.DeleteObject.argtypes = [wintypes.HANDLE]


@dataclass(frozen=True)
class WindowIcons:
    """A window's icon handles (0: none): what it was given (`WM_GETICON`)
    and its class's, small and big."""

    small: int
    big: int
    class_small: int
    class_big: int

    def shown(self, which: Which) -> int:
        """The handle Windows draws: the window's own, else its class's."""
        if which == "small":
            return self.small or self.class_small or self.class_big
        return self.big or self.class_big


def icons_of(hwnd: int) -> WindowIcons:
    """A window's icon handles, from any process on its desktop's session.
    A hung window answers none."""

    def asked(kind: int) -> int:
        result = ctypes.c_size_t()
        sent = _user32.SendMessageTimeoutW(
            hwnd, WM_GETICON, kind, 0, SMTO_ABORTIFHUNG, 2000, ctypes.byref(result)
        )
        return int(result.value) if sent else 0

    return WindowIcons(
        small=asked(ICON_SMALL),
        big=asked(ICON_BIG),
        class_small=int(_user32.GetClassLongPtrW(hwnd, GCLP_HICONSM)),
        class_big=int(_user32.GetClassLongPtrW(hwnd, GCLP_HICON)),
    )


def picture(icon: int) -> QImage | None:
    """An icon handle's colour bitmap as a picture (ARGB32), or None."""
    from PySide6.QtGui import QImage

    if not icon:
        return None
    info = _ICONINFO()
    if not _user32.GetIconInfo(icon, ctypes.byref(info)):
        return None
    dc = _gdi32.CreateCompatibleDC(None)  # in memory: nothing of the screen
    try:
        if not info.hbmColor:
            return None  # a monochrome icon: none of Qt's
        bitmap = _BITMAP()
        _gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bitmap), ctypes.byref(bitmap))
        width, height = bitmap.bmWidth, bitmap.bmHeight
        header = _BITMAPINFOHEADER(
            biSize=ctypes.sizeof(_BITMAPINFOHEADER),
            biWidth=width,
            biHeight=-height,  # top row first
            biPlanes=1,
            biBitCount=32,
            biCompression=BI_RGB,
        )
        pixels = ctypes.create_string_buffer(width * height * 4)
        rows = _gdi32.GetDIBits(
            dc, info.hbmColor, 0, height, pixels, ctypes.byref(header), DIB_RGB_COLORS
        )
        if rows != height:
            return None
        # BGRA in memory is QImage's ARGB32 on a little-endian PC
        image = QImage(
            bytes(pixels.raw), width, height, width * 4, QImage.Format.Format_ARGB32
        )
        return image.copy()
    finally:
        _gdi32.DeleteDC(dc)
        for handle in (info.hbmColor, info.hbmMask):
            if handle:
                _gdi32.DeleteObject(handle)


def difference(a: QImage, b: QImage) -> int:
    """The largest difference in any channel of any pixel, colour weighted
    by its opacity (a pixel nobody sees can hold anything); 255 if the
    sizes differ."""
    from PySide6.QtGui import QImage

    if a.size() != b.size():
        return 255
    a = a.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    b = b.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    worst = 0
    for y in range(a.height()):
        for x in range(a.width()):
            pa, pb = a.pixel(x, y), b.pixel(x, y)
            for shift in (0, 8, 16, 24):
                worst = max(worst, abs((pa >> shift & 0xFF) - (pb >> shift & 0xFF)))
    return worst


def is_the_app_icon(image: QImage | None, tolerance: int = 8) -> bool:
    """Whether a picture is Polyglotic's icon at its size, as Qt makes a
    window's icon from the app icon (`createHIcon`: `actualSize`, then the
    pixmap at a ratio of 1) - so from the master that size comes from
    (`ui.icons`). `tolerance`: the icon's round trip through Windows."""
    from PySide6.QtCore import QSize

    from polyglotic_desktop.ui.icons import app_icon

    if image is None or image.width() != image.height():
        return False
    icon, size = app_icon(), QSize(image.width(), image.height())
    expected = icon.pixmap(icon.actualSize(size), 1).toImage()
    return difference(image, expected) <= tolerance
