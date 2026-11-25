"""Whether Esc, Backspace or a mouse button is held now, or was pressed
since last asked, anywhere - on a Mac (polyglotic-hq 438):
`platform/windows/keys.py`'s counterpart, the `ports.system.KeyState`
port. Dictation's Esc cancels whatever isn't typed; a settings popover and
the pinned lookup card close on Esc or a click elsewhere, and the card
goes back on Backspace - none of them ever has the keyboard, so macOS
tells them nothing about keys and clicks in other apps.

Two readings, as Windows' `GetAsyncKeyState` gives both:

- **Pressed since last asked:** AppKit's global monitor
  (`NSEvent addGlobalMonitorForEventsMatchingMask:handler:`), which hears
  the presses that go to other apps. Mouse buttons need no permission;
  key presses reach it only once the app has the **Accessibility**
  permission ("Key-related events may only be monitored if accessibility
  is enabled or if your application is trusted for accessibility access",
  Apple's `NSEvent` documentation) - the one dictation's typing already
  asks for (`text_input`). Without it Esc and Backspace read as never
  pressed and the mouse still works. No **Input Monitoring** permission:
  no event tap, and `CGEventSourceKeyState` isn't called.
- **Held now:** a mouse button, from Quartz's `CGEventSourceButtonState`
  (no permission) - a press inside the app's own windows too.

**Short-lived:** the monitor is added when it's first asked about and
taken away once nothing has asked for `IDLE_SEC` - at the next press it
hears, on its own call (macOS calls it on the interface's thread, where
the asking is done). Nothing is consumed: the app in front still gets the
key or the click. Only whether Esc, Backspace or a button went down is
kept - never another key, and nothing is logged.
"""

import ctypes
import ctypes.util
import logging
import time
from collections.abc import Callable
from functools import cache
from typing import Protocol

from polyglotic_desktop.platform.macos import objc

log = logging.getLogger(__name__)

IDLE_SEC = 2.0
"""How long the monitor stays after the last ask: the asking is every
40-50 ms while a popover is open, the card pinned or dictation listening."""

LEFT_DOWN, RIGHT_DOWN, KEY_DOWN, OTHER_DOWN = 1, 3, 10, 25
"""`NSEventType`'s mouse-down and key-down types."""
MOUSE_DOWNS = frozenset({LEFT_DOWN, RIGHT_DOWN, OTHER_DOWN})
MASK = sum(1 << kind for kind in (*MOUSE_DOWNS, KEY_DOWN))
"""The monitor's `NSEventMask`: the presses, never key-ups or moves."""
KEY_CODES = {"escape": 0x35, "backspace": 0x33}
"""`kVK_Escape`, `kVK_Delete` (a Mac's Backspace), Carbon's Events.h."""
C_KEY = 0x08
"""`kVK_ANSI_C`, Carbon's Events.h."""
COMMAND_FLAG = 1 << 20
"""`NSEventModifierFlagCommand`."""
ALT_OR_CTRL_FLAGS = (1 << 18) | (1 << 19)
"""`NSEventModifierFlagControl | NSEventModifierFlagOption`."""
NAMES = ("escape", "backspace", "mouse", "copy")


def pressed_name(kind: int, key_code: int, modifiers: int = 0) -> str | None:
    """Which of `NAMES` an event is, if any."""
    if kind in MOUSE_DOWNS:
        return "mouse"
    if kind == KEY_DOWN:
        if (
            key_code == C_KEY
            and (modifiers & COMMAND_FLAG)
            and not (modifiers & ALT_OR_CTRL_FLAGS)
        ):
            return "copy"
        for name, code in KEY_CODES.items():
            if code == key_code:
                return name
    return None


class Mac(Protocol):
    """What `MacKeys` asks of macOS (`_AppKit`; a fake in tests)."""

    def add(self, heard: Callable[..., None]) -> object | None:
        """Adds the global monitor for `MASK`, calling `heard(type, key
        code[, modifiers])` for each press; the monitor, or None if macOS gave none."""

    def remove(self, monitor: object) -> None: ...

    def button_held(self) -> bool:
        """Whether any mouse button is held now."""


class MacKeys:
    """`KeyState` on a Mac: callable with "escape", "backspace" or "mouse"."""

    def __init__(
        self, mac: Mac | None = None, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._mac = mac
        self._clock = clock
        self._monitor: object | None = None
        self._asked = 0.0
        self._pressed: set[str] = set()
        self._failed = False

    def __call__(self, name: str) -> bool:
        if name not in NAMES:
            raise KeyError(name)
        self._asked = self._clock()
        mac = self._macos()
        if mac is None:
            return False
        if self._monitor is None:
            self._pressed.clear()  # nothing from before it listened
            try:
                self._monitor = mac.add(self._heard)
            except OSError:
                log.exception("macOS gave no monitor for Esc and clicks elsewhere")
                self._failed = True
                return False
        pressed = name in self._pressed
        self._pressed.discard(name)
        if name == "mouse" and not pressed:
            pressed = mac.button_held()
        return pressed

    @property
    def listening(self) -> bool:
        """Whether the monitor is there now."""
        return self._monitor is not None

    def _macos(self) -> Mac | None:
        if self._failed:
            return None
        if self._mac is None:
            try:
                self._mac = _AppKit()
            except OSError:
                log.exception("no AppKit: Esc and clicks elsewhere read as none")
                self._failed = True
                return None
        return self._mac

    def _heard(self, kind: int, key_code: int, modifiers: int = 0) -> None:
        if self._clock() - self._asked > IDLE_SEC:
            self.stop()
            return
        name = pressed_name(kind, key_code, modifiers)
        if name is not None:
            self._pressed.add(name)

    def stop(self) -> None:
        """Takes the monitor away, forgetting what it heard."""
        if self._monitor is not None and self._mac is not None:
            self._mac.remove(self._monitor)
        self._monitor = None
        self._pressed.clear()


_COMBINED = 0
"""`kCGEventSourceStateCombinedSessionState`."""
_BUTTONS = (0, 1, 2)
"""Left, right, middle: `CGMouseButton`."""


@cache
def _quartz() -> ctypes.CDLL:
    path = ctypes.util.find_library("ApplicationServices")
    if path is None:
        raise OSError("macOS's ApplicationServices framework isn't here")
    lib = ctypes.CDLL(path)
    lib.CGEventSourceButtonState.restype = ctypes.c_bool
    lib.CGEventSourceButtonState.argtypes = [ctypes.c_int32, ctypes.c_uint32]
    return lib


class _AppKit:
    """The global monitor, through Objective-C's runtime (`objc`)."""

    def __init__(self) -> None:
        objc.load("AppKit")
        self._ns_event = objc.cls("NSEvent")
        self._quartz = _quartz()
        self._block: objc.Block | None = None
        self._heard: Callable[..., None] = lambda *_args: None

    def add(self, heard: Callable[..., None]) -> object | None:
        self._heard = heard
        if self._block is None:  # one block for the run: macOS may call it late
            self._block = objc.Block(self._event)
        with objc.pool():
            monitor = objc.send(
                self._ns_event,
                "addGlobalMonitorForEventsMatchingMask:handler:",
                MASK,
                self._block.address,
                argtypes=[ctypes.c_uint64, ctypes.c_void_p],
            )
            if not monitor:
                return None
            objc.send(int(monitor), "retain")  # autoreleased: kept until removed
            return int(monitor)

    def remove(self, monitor: object) -> None:
        if not isinstance(monitor, int):
            return
        with objc.pool():
            objc.send(
                self._ns_event,
                "removeMonitor:",
                monitor,
                restype=None,
                argtypes=[ctypes.c_void_p],
            )
            objc.send(monitor, "release", restype=None)

    def button_held(self) -> bool:
        return any(
            self._quartz.CGEventSourceButtonState(_COMBINED, b) for b in _BUTTONS
        )

    def _event(self, event: int) -> None:
        try:
            if not event:
                return
            kind = int(objc.send(event, "type", restype=ctypes.c_uint64))
            code = (
                int(objc.send(event, "keyCode", restype=ctypes.c_uint16))
                if kind == KEY_DOWN
                else 0
            )
            modifiers = (
                int(objc.send(event, "modifierFlags", restype=ctypes.c_uint64))
                if kind == KEY_DOWN
                else 0
            )
            self._heard(kind, code, modifiers)
        except Exception:  # never out into macOS's call
            log.exception("the monitor for Esc and clicks elsewhere failed")
