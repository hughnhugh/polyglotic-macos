"""A plain Windows error box, for when the app can't start.

Windows' own `MessageBoxW`, not Qt's: a start-up failure may come before
Qt is running, or from Qt itself, and this needs no event loop. It waits
until the user closes it.
"""

import ctypes

_MB_OK, _MB_ICONERROR, _MB_SETFOREGROUND = 0x0, 0x10, 0x10000

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.MessageBoxW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_uint,
]
_user32.MessageBoxW.restype = ctypes.c_int


def show_error(title: str, text: str) -> None:
    """Shows `text` in an error box titled `title`, until it's closed."""
    _user32.MessageBoxW(None, text, title, _MB_OK | _MB_ICONERROR | _MB_SETFOREGROUND)
