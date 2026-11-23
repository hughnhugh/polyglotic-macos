"""Read X11 focus and paste the clipboard through XTEST.

Wayland uses the clipboard without injecting input. The Qt application
owns the clipboard and is responsible for checking its own windows.
"""

import ctypes as c
import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache

_NO_FOCUS, _POINTER_ROOT = 0, 1  # X11's GetInputFocus special window IDs
_CONTROL_L = 0xFFE3  # X11's Control_L keysym
_V = ord("v")
_NO_DELAY = 0  # XTEST's CurrentTime, no delay between the key events


@cache
def _xlib() -> c.CDLL:
    x = c.CDLL("libX11.so.6")
    x.XOpenDisplay.argtypes = [c.c_char_p]
    x.XOpenDisplay.restype = c.c_void_p
    x.XGetInputFocus.argtypes = [c.c_void_p, c.POINTER(c.c_ulong), c.POINTER(c.c_int)]
    x.XKeysymToKeycode.argtypes = [c.c_void_p, c.c_ulong]
    x.XKeysymToKeycode.restype = c.c_ubyte
    x.XSync.argtypes = [c.c_void_p, c.c_int]
    x.XCloseDisplay.argtypes = [c.c_void_p]
    return x


@contextmanager
def _display() -> Iterator[tuple[c.CDLL, int]]:
    x = _xlib()
    display = x.XOpenDisplay(None)
    if not display:
        raise OSError("No X11 connection")
    try:
        yield x, display
    finally:
        x.XCloseDisplay(display)


def _focus(x: c.CDLL, display: int) -> int:
    window, revert = c.c_ulong(), c.c_int()
    x.XGetInputFocus(display, c.byref(window), c.byref(revert))
    return window.value if window.value not in (_NO_FOCUS, _POINTER_ROOT) else 0


def keyboard_window() -> int:
    try:
        with _display() as (x, display):
            return _focus(x, display)
    except OSError:
        return 0


def paste(window: int) -> bool:
    """Paste into the X11 window that still has the keyboard."""
    if not window or "PYTEST_CURRENT_TEST" in os.environ:
        return False
    try:
        with _display() as (x, display):
            xtest = c.CDLL("libXtst.so.6")
            fake_key = xtest.XTestFakeKeyEvent
            fake_key.argtypes = [c.c_void_p, c.c_uint, c.c_int, c.c_ulong]
            fake_key.restype = c.c_int
            ctrl, v = (
                int(x.XKeysymToKeycode(display, key)) for key in (_CONTROL_L, _V)
            )
            if not ctrl or not v or _focus(x, display) != window:
                return False
            results = [
                fake_key(display, code, pressed, _NO_DELAY)
                for code, pressed in (
                    (ctrl, True),
                    (v, True),
                    (v, False),
                    (ctrl, False),
                )
            ]
            x.XSync(display, False)
            return all(results)
    except OSError:
        return False
