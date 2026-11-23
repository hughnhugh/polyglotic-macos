"""Dictation's text typed into the app that has the keyboard, on a Mac
(polyglotic-hq 429) - `platform/windows/text_input.py`'s counterpart, with
the same design (polyglotic-hq 283, decision 0073):

- each character is sent as a key event carrying the character itself
  (Quartz's `CGEventKeyboardSetUnicodeString`), not a key code, so the app
  gets it whatever the keyboard layout - Chinese types as Chinese;
- the clipboard is never touched;
- the events carry no modifiers, so a Command or Option still held never
  turns a letter into a shortcut;
- a line break or tab becomes a space, as on Windows.

macOS lets an app send key events only with the learner's leave: its
Accessibility permission (System Settings > Privacy & Security >
Accessibility). `allowed` asks macOS whether the app has it, and the first
time it hasn't, during a run, macOS's own box asks the learner and opens
System Settings (`AXIsProcessTrustedWithOptions`); until it's given,
nothing is typed and dictation says "Couldn't type it here".

**The Mac's one file that may send input**, as the Windows file is
Windows' (polyglotic-hq DECISIONS #116). No test types for real: the tests
pass a stand-in for macOS's call, and inside a test run `type_text`
without one sends nothing.

`Permission` is the `TypingPermission` port: whether the app has it,
asking nothing, and System Settings opened at Privacy & Security >
Accessibility, for Settings > Dictation's "Open System Settings"
(polyglotic-hq 438).

`keyboard_window` is the front app's frontmost ordinary window
(`window_list.front_window`): dictation types only into the one that had
the keyboard when the speech was cut. Never logs the text.
"""

import ctypes
import ctypes.util
import logging
import os
import subprocess
from collections.abc import Callable, Sequence
from functools import cache

from polyglotic_desktop.platform.macos import cf, window_list

log = logging.getLogger(__name__)

HID_EVENT_TAP = 0
"""`kCGHIDEventTap`: where a keyboard's own events enter."""
NO_KEY = 0
"""The key code each event carries: macOS's apps read the character, not
the key."""

Piece = tuple[int, ...]
"""One character as UTF-16 units: one, or two outside the Basic
Multilingual Plane (an emoji)."""


def pieces(text: str) -> list[Piece]:
    """The characters `text` is typed as, each its UTF-16 units; a line
    break or tab a space (a character most apps ignore, and Return would
    send a message)."""
    out = []
    for character in text:
        typed = " " if character in "\r\n\t" else character
        units = memoryview(typed.encode("utf-16-le")).cast("H")
        out.append(tuple(units))
    return out


class _Quartz:
    def __init__(self) -> None:
        path = ctypes.util.find_library("ApplicationServices")
        if path is None:
            raise OSError("macOS's ApplicationServices framework isn't here")
        self.lib = ctypes.CDLL(path)
        p = ctypes.c_void_p
        for name, restype, argtypes in (
            ("CGEventCreateKeyboardEvent", p, [p, ctypes.c_uint16, ctypes.c_bool]),
            (
                "CGEventKeyboardSetUnicodeString",
                None,
                [p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_uint16)],
            ),
            ("CGEventSetFlags", None, [p, ctypes.c_uint64]),
            ("CGEventPost", None, [ctypes.c_uint32, p]),
            ("AXIsProcessTrusted", ctypes.c_bool, []),
            ("AXIsProcessTrustedWithOptions", ctypes.c_bool, [p]),
        ):
            call = getattr(self.lib, name)
            call.restype = restype
            call.argtypes = argtypes


@cache
def _quartz() -> _Quartz:
    return _Quartz()


_asked = False
"""Whether macOS's box has asked for the permission during this run."""


def allowed(ask: bool = True) -> bool:
    """Whether the app may send key events (the Accessibility permission).
    If it may not and `ask`, macOS's box asks the learner - once a run."""
    global _asked
    quartz = _quartz()
    if not ask or _asked:
        return bool(quartz.lib.AXIsProcessTrusted())
    _asked = True
    prompt = int(
        ctypes.c_void_p.in_dll(quartz.lib, "kAXTrustedCheckOptionPrompt").value or 0
    )
    true = cf.libraries().constant("kCFBooleanTrue", "cf")
    options = cf.create_dictionary({prompt: true})
    with cf.owned(options):
        trusted = bool(quartz.lib.AXIsProcessTrustedWithOptions(options))
    if not trusted:
        log.info("dictation: macOS asked for the Accessibility permission")
    return trusted


ACCESSIBILITY_SETTINGS = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
)
"""System Settings at Privacy & Security > Accessibility (macOS 13 and
later read the old pane's address too)."""


class Permission:
    """`TypingPermission` on a Mac: the Accessibility permission."""

    def __init__(self, run: Callable[[list[str]], object] | None = None) -> None:
        self._run = run or _open

    def allowed(self) -> bool:
        return allowed(ask=False)

    def open_settings(self) -> None:
        self._run(["/usr/bin/open", ACCESSIBILITY_SETTINGS])


def _open(args: list[str]) -> object:
    try:
        return subprocess.run(args, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        log.exception("System Settings didn't open")
        return None


Post = Callable[[Sequence[Piece]], int]
"""Sends the characters as key events, in order; returns how many it sent."""


def _post(typed: Sequence[Piece]) -> int:
    quartz = _quartz().lib
    sent = 0
    for units in typed:
        buffer = (ctypes.c_uint16 * len(units))(*units)
        for down in (True, False):
            event = quartz.CGEventCreateKeyboardEvent(None, NO_KEY, down)
            if not event:
                return sent
            with cf.owned(event):
                quartz.CGEventKeyboardSetUnicodeString(event, len(units), buffer)
                quartz.CGEventSetFlags(event, 0)  # Command held isn't a shortcut
                quartz.CGEventPost(HID_EVENT_TAP, event)
        sent += 1
    return sent


def type_text(text: str, post: Post | None = None) -> bool:
    """Types `text` into the app that has the keyboard; False if none or
    only some of it was sent (the permission not given). `post` stands in
    for macOS's call in the tests; without one, inside a test run, nothing
    is sent at all - a test must never type into whatever has the
    keyboard."""
    typed = pieces(text)
    if not typed:
        return True
    if post is None:
        if "PYTEST_CURRENT_TEST" in os.environ:
            log.warning("dictation: nothing is typed inside a test run")
            return False
        if not allowed():
            return False
        post = _post
    return post(typed) == len(typed)


def keyboard_window() -> int:
    """The window that has the keyboard now: the front app's frontmost
    ordinary window, by its number (0: none)."""
    pid = window_list.front_pid()
    return window_list.front_window(window_list.on_screen(), pid) if pid else 0


def window_is_ours(_window: int) -> bool:
    return window_list.front_pid() == os.getpid()


def type_text_for(text: str, window: int) -> bool:
    """Type only while the intended external window still has focus."""
    return bool(
        window
        and keyboard_window() == window
        and not window_is_ours(window)
        and type_text(text)
    )
