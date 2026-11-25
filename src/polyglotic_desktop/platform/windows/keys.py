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
_VK_CONTROL, _VK_MENU, _VK_C = 0x11, 0x12, 0x43
_VK_LWIN, _VK_RWIN = 0x5B, 0x5C
_DOWN, _SINCE = 0x8000, 0x0001
"""Held now; pressed since the last time this process asked."""
_copy_was_down = False

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def held(name: str) -> bool:
    """Whether "escape", "backspace", "mouse" (any button) or "copy" (Ctrl+C)
    is held now, or was pressed since it was last asked about - wherever the
    keyboard and mouse are."""
    global _copy_was_down
    if name == "copy":
        ctrl = bool(_user32.GetAsyncKeyState(_VK_CONTROL) & _DOWN)
        alt = bool(_user32.GetAsyncKeyState(_VK_MENU) & _DOWN)
        win = bool(
            (_user32.GetAsyncKeyState(_VK_LWIN) & _DOWN)
            or (_user32.GetAsyncKeyState(_VK_RWIN) & _DOWN)
        )
        c_state = _user32.GetAsyncKeyState(_VK_C)
        c_down = bool(c_state & _DOWN)
        c_since = bool(c_state & _SINCE)
        down = ctrl and not alt and not win and c_down
        pressed = (
            ctrl
            and not alt
            and not win
            and (c_since or (c_down and not _copy_was_down))
        )
        _copy_was_down = down
        return pressed
    return any(
        _user32.GetAsyncKeyState(code) & (_DOWN | _SINCE) for code in _KEYS[name]
    )
