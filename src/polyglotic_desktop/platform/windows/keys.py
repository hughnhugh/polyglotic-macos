"""Whether Esc, Backspace or a mouse button is held now, anywhere - read,
not taken.

A caption window's settings popover and the lookup card never take the
focus (a full-screen game can minimise when it loses it), so they get no
key events and Windows doesn't tell them about clicks in other apps. While
one is open (the card: pinned) it asks here, every so often, so Esc or a
click elsewhere can close it, and Backspace go back (`GetAsyncKeyState`). Nothing is hooked or consumed: the app that has the
keyboard or the click still gets it. `main` hands this to the interface.
"""

import ctypes

_KEYS = {
    "escape": (0x1B,),  # VK_ESCAPE
    "backspace": (0x08,),  # VK_BACK
    "mouse": (0x01, 0x02, 0x04),  # VK_LBUTTON, VK_RBUTTON, VK_MBUTTON
}
_DOWN, _SINCE = 0x8000, 0x0001
"""Held now; pressed since the last time this process asked."""

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def held(name: str) -> bool:
    """Whether "escape", "backspace" or "mouse" (any button) is held now, or was pressed
    since it was last asked about - wherever the keyboard and mouse are."""
    return any(
        _user32.GetAsyncKeyState(code) & (_DOWN | _SINCE) for code in _KEYS[name]
    )
