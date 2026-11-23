"""Dictation's text typed into the program that has the keyboard (polyglotic-hq 283, decision 0073).

The design: each character sent as a Unicode key event (Windows' input
call with `KEYEVENTF_UNICODE`), so the program gets the character itself
whatever the keyboard layout - Chinese types as Chinese. The clipboard is
never touched (pasting would leave the dictation where a clipboard manager
keeps it), and the letters aren't real key presses, so W, A, S and D typed
into a game don't move the player. A program running as administrator
ignores input from one that isn't (UIPI), and Windows doesn't say so.

**The one file that may send input.** polyglotic-hq's guard refuses any
code that sends input to the desktop, and allows it here alone (the user,
2026-11-11, DECISIONS #116). `unicode_events` builds the events and
`type_text` sends them in one call, so nothing else typed at the same
moment lands between the characters. No test types for real: the tests
pass a stand-in for Windows' call, and inside a test run `type_text`
without one sends nothing.

`keyboard_window` is the foreground window: dictation types only into the
one that had the keyboard when the speech was cut. Never logs the text.
"""

import ctypes
import ctypes.wintypes
import logging
import os
from collections.abc import Callable

log = logging.getLogger(__name__)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    """Only for the union's size: `INPUT` is as big as its biggest kind."""

    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.wintypes.DWORD), ("u", _INPUTUNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.POINTER(ctypes.wintypes.DWORD),
]
_user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD


def unicode_events(text: str) -> "ctypes.Array[INPUT]":
    """The key events that type `text`: each UTF-16 unit (a character, or
    half of one outside the Basic Multilingual Plane, such as an emoji) a
    key down and a key up. A line break or tab becomes a space: as a
    character most programs ignore it, and Enter would send a message."""
    text = "".join(" " if c in "\r\n\t" else c for c in text)
    units = memoryview(text.encode("utf-16-le")).cast("H")
    events = (INPUT * (2 * len(units)))()
    for i, unit in enumerate(units):
        for j, up in enumerate((0, KEYEVENTF_KEYUP)):
            event = events[2 * i + j]
            event.type = INPUT_KEYBOARD
            event.u.ki = KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | up, 0, 0)
    return events


_user32.SendInput.argtypes = [
    ctypes.wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
]
_user32.SendInput.restype = ctypes.wintypes.UINT

Send = Callable[[int, "ctypes.Array[INPUT]", int], int]
"""Windows' input call: how many events, the events, one event's size;
returns how many it took."""


def type_text(text: str, send: Send | None = None) -> bool:
    """Types `text` into the program that has the keyboard; False if any
    of it wasn't taken (another program blocked input, or the window is an
    administrator's). `send` stands in for Windows' call in the tests;
    without one, inside a test run, nothing is sent at all - a test must
    never type into whatever has the keyboard on the PC."""
    events = unicode_events(text)
    if not len(events):
        return True
    if send is None:
        if "PYTEST_CURRENT_TEST" in os.environ:
            log.warning("dictation: nothing is typed inside a test run")
            return False
        send = _user32.SendInput
    return send(len(events), events, ctypes.sizeof(INPUT)) == len(events)


def keyboard_window() -> int:
    """The window that has the keyboard now (0: none)."""
    return int(_user32.GetForegroundWindow() or 0)


def window_is_ours(window: int) -> bool:
    pid = ctypes.wintypes.DWORD()
    if window:
        _user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    return pid.value == os.getpid()


def type_text_for(text: str, window: int) -> bool:
    """Type only while the intended external window still has focus."""
    return bool(
        window
        and keyboard_window() == window
        and not window_is_ours(window)
        and type_text(text)
    )
