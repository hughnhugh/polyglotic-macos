"""The Mac's system-wide hotkeys (polyglotic-hq 428; `ports.system.Hotkeys`):
⌃⌘L, ⌃⌘P and ⌃⌘H - lock, pause, hide - work whatever app is in front,
as Ctrl+Alt+ the letter does on Windows.

**Control+Command** (polyglotic-hq DECISIONS #193's recommendation, 420):
⌥⌘H is "Hide Others" in every Mac app, and ⌥⌘L and ⌥⌘P are Finder's; no
app of macOS's own uses ⌃⌘L, P or H. The menus show the same keys
(`ui.app.DesktopApp`: Qt's Meta is the Control key, its Ctrl Command).

**Carbon's `RegisterEventHotKey`** - still how Mac apps take a global
hotkey (Apple has no newer call for it) and, unlike watching every key
press, it needs no Accessibility or Input Monitoring permission. macOS
calls the handler on the app's main thread, from the event loop Qt runs
there; `start` and `stop` are called on that thread too (`main`).

A combination another app already has (registered exclusively) can't be
taken: `start` says which, the rest still work, and the log names them,
as on Windows. Nothing pressed is ever logged.

**Keys by position:** Carbon takes a key's code - where it is on the
keyboard - and the codes here are the US layout's letters. L, P and H are
in the same place on QWERTY, AZERTY and QWERTZ keyboards; on Dvorak and
other layouts the hotkeys are the keys where L, P and H are on a US
keyboard (docs/macos.md).
"""

import ctypes
import itertools
import logging
from collections.abc import Callable, Mapping
from functools import cache
from typing import Protocol

log = logging.getLogger(__name__)

COMMAND, SHIFT, OPTION, CONTROL = 0x0100, 0x0200, 0x0800, 0x1000
"""Carbon's modifier flags (`cmdKey`, `shiftKey`, `optionKey`, `controlKey`)."""
CONTROL_COMMAND = CONTROL | COMMAND
EXISTS = -9878
"""`eventHotKeyExistsErr`: another app has the combination."""
EXCLUSIVE = 1
"""`kEventHotKeyExclusive`: ours alone, or refused - as Windows' are."""

KEY_CODES = {
    **dict(zip("ASDFHGZXCV", range(0x0A), strict=True)),
    **dict(zip("BQWERYT", range(0x0B, 0x12), strict=True)),
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17,
    "9": 0x19, "7": 0x1A, "8": 0x1C, "0": 0x1D,
    "O": 0x1F, "U": 0x20, "I": 0x22, "P": 0x23, "L": 0x25, "J": 0x26,
    "K": 0x28, "N": 0x2D, "M": 0x2E,
}  # fmt: skip
"""Each letter's and digit's key code on a US keyboard (`kVK_ANSI_*`,
Carbon's Events.h)."""


def four(code: str) -> int:
    """A four-character code ('keyb') as Carbon's number."""
    return int.from_bytes(code.encode("ascii"), "big")


SIGNATURE = four("PGLT")
"""Our hotkeys' signature: an event carrying another's isn't ours."""
_HOTKEY_IDS = itertools.count(1)


def combination(modifiers: int, key: str) -> str:
    """A combination as a Mac's menus write it: "⌃⌘L" (Control, Option,
    Shift, Command, in Apple's order)."""
    marks = [
        mark
        for flag, mark in ((CONTROL, "⌃"), (OPTION, "⌥"), (SHIFT, "⇧"), (COMMAND, "⌘"))
        if modifiers & flag
    ]
    return "".join([*marks, key])


class Carbon(Protocol):
    """The calls the hotkeys make (`CarbonEvents`; a fake in tests)."""

    def listen(self, pressed: Callable[[int, int], None]) -> None:
        """Calls `pressed(signature, id)` whenever a hotkey of this app's is
        pressed, until `quiet`."""
        ...

    def quiet(self, pressed: Callable[[int, int], None]) -> None:
        """No more calls to `pressed`."""
        ...

    def register(self, key_code: int, modifiers: int, hotkey_id: int) -> int:
        """Takes one combination: its reference, or raises `Refused`."""
        ...

    def unregister(self, ref: int) -> None: ...


class Refused(OSError):
    """macOS wouldn't register a combination: `status` says why
    (`EXISTS`: another app has it)."""

    def __init__(self, status: int) -> None:
        super().__init__(f"RegisterEventHotKey: {status}")
        self.status = status


class MacHotkeys:
    """`Hotkeys` on a Mac: each a letter or digit with Control+Command (or
    `modifiers`), its binding called on the app's main thread."""

    def __init__(
        self,
        bindings: Mapping[str, Callable[[], None]],
        modifiers: int = CONTROL_COMMAND,
        carbon: Carbon | None = None,
    ) -> None:
        for key in bindings:
            if key not in KEY_CODES:
                raise ValueError(f"not a letter or digit key: {key!r}")
        self._keys = list(bindings)
        # ids of the app's own, never another MacHotkeys' in this process
        self._ids = {key: next(_HOTKEY_IDS) for key in bindings}
        self._calls = {self._ids[key]: call for key, call in bindings.items()}
        self._modifiers = modifiers
        self._carbon = carbon
        self._refs: list[int] = []
        self._started = False
        self.taken: list[str] = []
        """The keys another app already has (not working here)."""

    def start(self) -> list[str]:
        """Takes the hotkeys; returns those another app already has."""
        if self._started:
            raise RuntimeError("already started")
        self._started = True
        carbon = self._carbon if self._carbon is not None else carbon_events()
        try:
            carbon.listen(self._pressed)
        except OSError:
            log.exception("macOS's hotkeys can't be listened for")
            self.taken = list(self._keys)
            return self.taken
        self._carbon = carbon
        for key in self._keys:
            try:
                self._refs.append(
                    carbon.register(KEY_CODES[key], self._modifiers, self._ids[key])
                )
            except Refused as refused:
                self.taken.append(key)
                if refused.status != EXISTS:
                    log.warning("macOS refused a hotkey: %s", refused)
        if self.taken:
            log.warning(
                "hotkey(s) already taken by another app: %s",
                ", ".join(combination(self._modifiers, key) for key in self.taken),
            )
        return self.taken

    def stop(self) -> None:
        """Gives the hotkeys back."""
        carbon = self._carbon
        if not self._started or carbon is None:
            return
        for ref in self._refs:
            carbon.unregister(ref)
        self._refs.clear()
        carbon.quiet(self._pressed)
        self._started = False

    def post(self, key: str) -> None:
        """As if `key`'s combination had been pressed - for tests, without
        pressing anything."""
        self._pressed(SIGNATURE, self._ids[key])

    def _pressed(self, signature: int, hotkey_id: int) -> None:
        call = self._calls.get(hotkey_id) if signature == SIGNATURE else None
        if call is None:
            return
        try:
            call()
        except Exception:  # a failing action must not end the hotkeys
            log.exception("a hotkey's action failed")


# --- Carbon, through ctypes --------------------------------------------------

_KEYBOARD = four("keyb")  # kEventClassKeyboard
_HOT_KEY_PRESSED = 5  # kEventHotKeyPressed
_DIRECT_OBJECT = four("----")  # kEventParamDirectObject
_HOT_KEY_ID = four("hkid")  # typeEventHotKeyID
_NOT_HANDLED = -9874  # eventNotHandledErr


class _EventTypeSpec(ctypes.Structure):
    _fields_ = (("event_class", ctypes.c_uint32), ("event_kind", ctypes.c_uint32))


class _HotKeyId(ctypes.Structure):
    _fields_ = (("signature", ctypes.c_uint32), ("id", ctypes.c_uint32))


_HANDLER = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class CarbonEvents:
    """`Carbon` through the Carbon framework's HIToolbox: one handler for
    the app's hotkey events, installed while any hotkeys are listened for."""

    def __init__(self) -> None:
        from polyglotic_desktop.platform.macos import objc  # its library finder

        self._lib = ctypes.CDLL(objc._found("Carbon"))
        p, u32, i32 = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32
        lib = self._lib
        lib.GetApplicationEventTarget.restype = p
        lib.GetApplicationEventTarget.argtypes = []
        lib.InstallEventHandler.restype = i32
        lib.InstallEventHandler.argtypes = [
            p, _HANDLER, ctypes.c_ulong, ctypes.POINTER(_EventTypeSpec), p,
            ctypes.POINTER(p),
        ]  # fmt: skip
        lib.RemoveEventHandler.restype = i32
        lib.RemoveEventHandler.argtypes = [p]
        lib.RegisterEventHotKey.restype = i32
        lib.RegisterEventHotKey.argtypes = [
            u32, u32, _HotKeyId, p, u32, ctypes.POINTER(p),
        ]  # fmt: skip
        lib.UnregisterEventHotKey.restype = i32
        lib.UnregisterEventHotKey.argtypes = [p]
        lib.GetEventParameter.restype = i32
        lib.GetEventParameter.argtypes = [
            p, u32, u32, ctypes.POINTER(u32), ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), p,
        ]  # fmt: skip
        self._handler = _HANDLER(self._event)  # kept: Carbon holds its address
        self._installed: ctypes.c_void_p | None = None
        self._listeners: list[Callable[[int, int], None]] = []

    def listen(self, pressed: Callable[[int, int], None]) -> None:
        if self._installed is None:
            ref = ctypes.c_void_p()
            spec = _EventTypeSpec(_KEYBOARD, _HOT_KEY_PRESSED)
            status = self._lib.InstallEventHandler(
                self._lib.GetApplicationEventTarget(),
                self._handler,
                1,
                ctypes.byref(spec),
                None,
                ctypes.byref(ref),
            )
            if status != 0:
                raise OSError(f"InstallEventHandler: {status}")
            self._installed = ref
        self._listeners.append(pressed)

    def quiet(self, pressed: Callable[[int, int], None]) -> None:
        if pressed in self._listeners:
            self._listeners.remove(pressed)
        if not self._listeners and self._installed is not None:
            self._lib.RemoveEventHandler(self._installed)
            self._installed = None

    def register(self, key_code: int, modifiers: int, hotkey_id: int) -> int:
        ref = ctypes.c_void_p()
        status = self._lib.RegisterEventHotKey(
            key_code,
            modifiers,
            _HotKeyId(SIGNATURE, hotkey_id),
            self._lib.GetApplicationEventTarget(),
            EXCLUSIVE,
            ctypes.byref(ref),
        )
        if status != 0 or not ref.value:
            raise Refused(status)
        return ref.value

    def unregister(self, ref: int) -> None:
        self._lib.UnregisterEventHotKey(ref)

    def _event(self, _next: int | None, event: int | None, _data: int | None) -> int:
        found = _HotKeyId()
        status = self._lib.GetEventParameter(
            event,
            _DIRECT_OBJECT,
            _HOT_KEY_ID,
            None,
            ctypes.sizeof(found),
            None,
            ctypes.byref(found),
        )
        if status != 0 or found.signature != SIGNATURE:
            return _NOT_HANDLED
        for pressed in list(self._listeners):
            pressed(found.signature, found.id)
        return 0


@cache
def carbon_events() -> CarbonEvents:
    """One handler for the app: made on first use, never at import."""
    return CarbonEvents()
