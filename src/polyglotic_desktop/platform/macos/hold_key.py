"""Dictation's key, held, on a Mac (polyglotic-hq 429) - the counterpart of
`HoldKey` in `platform/windows/hotkeys.py` (polyglotic-hq 283, 289;
decision 0081).

A key is kept by Qt's names, and on a Mac Qt's Ctrl is Command (Settings'
key box hears Command as Qt's Control): "ctrl" is Command, "alt" Option,
"shift" Shift and "win" Control (Qt's Meta). So "right_ctrl", the
default, is Right Command - on every Mac's keyboard, rarely used alone.

Two ways, as on Windows, by the key:

- **A key, with or without modifiers** (F9, Control+Command+D): Carbon's
  `RegisterEventHotKey` takes it from other apps while it's ours - no
  permission is needed - and says when it goes down and when it comes up
  (`kEventHotKeyPressed`, `kEventHotKeyReleased`, on the interface's
  thread). While it's held, its modifiers' state is read every `POLL_SEC`:
  one let go first ends it too.
- **A modifier alone (Right Command), or modifiers alone**: macOS can't
  register a modifier, so the modifiers' state is read every `POLL_SEC`
  all the time (`CGEventSourceFlagsState`, whose low bits say which side
  is down). Other apps still get it. While it's held, another modifier
  down, or any key gone down since it was pressed
  (`CGEventSourceSecondsSinceLastEventType`), means a shortcut (Command+C):
  `on_other`, and `on_up` still follows when it comes up.

No event tap: nothing else typed passes through the app, and neither the
Input Monitoring nor the Accessibility permission is needed for the key
(typing the words needs Accessibility: `text_input`). Nothing about the
keys is logged.
"""

import ctypes
import ctypes.util
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache

from polyglotic_desktop.core.listening.dictation_keys import DictationKey, Modifier

log = logging.getLogger(__name__)

POLL_SEC = 0.015
"""How often the modifiers are read: Windows' rate."""
SIGNATURE = int.from_bytes(b"PGdk", "big")
"""Dictation's hotkey signature: an event carrying another's (the app's
own hotkeys', polyglotic-hq 428) isn't this key's."""
_NOT_HANDLED = -9874  # eventNotHandledErr: the next handler gets it
_EXCLUSIVE = 1 << 0  # kEventHotKeyExclusive: refused if another app has it
_KEYBOARD = int.from_bytes(b"keyb", "big")
_PRESSED, _RELEASED = 5, 6  # kEventHotKeyPressed, kEventHotKeyReleased
_DIRECT = int.from_bytes(b"----", "big")
_HOTKEY_ID = int.from_bytes(b"hkid", "big")


@dataclass(frozen=True, slots=True)
class Held:
    """A modifier's ways of being read: its Carbon flag (for registering),
    the state's bit for either side, and each side's own bit."""

    carbon: int
    either: int
    left: int
    right: int


MODIFIERS = {
    Modifier.CTRL: Held(1 << 8, 0x100000, 0x08, 0x10),  # Command
    Modifier.ALT: Held(1 << 11, 0x080000, 0x20, 0x40),  # Option
    Modifier.SHIFT: Held(1 << 9, 0x020000, 0x02, 0x04),
    Modifier.WIN: Held(1 << 12, 0x040000, 0x01, 0x2000),  # Control
}
"""Qt's modifier names, as a Mac reads them."""
LONE = {
    f"{side}_{modifier.value}": getattr(held, side)
    for modifier, held in MODIFIERS.items()
    for side in ("left", "right")
}
"""A modifier alone, by its side: the state's bit for it."""
ANY_MODIFIER = sum(held.either for held in MODIFIERS.values())

KEY_CODES = {
    **dict(zip("asdfhgzxcv", (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), strict=True)),
    **dict(zip("bqweryt", (11, 12, 13, 14, 15, 16, 17), strict=True)),
    **dict(zip("123465", (18, 19, 20, 21, 22, 23), strict=True)),
    "9": 25,
    "7": 26,
    "8": 28,
    "0": 29,
    "o": 31,
    "u": 32,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "k": 40,
    "n": 45,
    "m": 46,
    **dict(
        zip(
            (f"f{n}" for n in range(1, 21)),
            (122, 120, 99, 118, 96, 97, 98, 100, 101, 109)
            + (103, 111, 105, 107, 113, 106, 64, 79, 80, 90),
            strict=True,
        )
    ),
    "space": 49,
    "enter": 36,
    "tab": 48,
    "backspace": 51,
    "delete": 117,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "home": 115,
    "end": 119,
    "page_up": 116,
    "page_down": 121,
    "escape": 53,
    "insert": 114,  # a PC keyboard's Insert is a Mac's Help
    "print_screen": 105,  # F13 on a Mac
    "scroll_lock": 107,  # F14
    "pause": 113,  # F15
    "menu": 110,
}
"""macOS's key codes (the US layout's places) for `dictation_keys.KEYS`;
F21 to F24 have none."""


@dataclass(frozen=True, slots=True)
class Plan:
    """How a key is held on a Mac: registered (`key_code` and `carbon`
    modifiers) or read (`alone`: each part's bit, all down), and the
    modifiers' state bits that must stay down while it's held."""

    key_code: int | None
    carbon: int
    alone: tuple[int, ...]
    modifiers: int
    """The modifiers' bits (either side) held with it."""


def plan(key: DictationKey) -> Plan | None:
    """How `key` is held here; None if a Mac has no such key (F21-F24)."""
    carbon = sum(MODIFIERS[m].carbon for m in key.modifiers)
    either = sum(MODIFIERS[m].either for m in key.modifiers)
    if key.key is None:  # modifiers alone, held together
        together = tuple(h.either for m, h in MODIFIERS.items() if m in key.modifiers)
        return Plan(None, 0, together, either)
    if key.key in LONE:
        return Plan(None, 0, (LONE[key.key],), 0)
    code = KEY_CODES.get(key.key)
    return None if code is None else Plan(code, carbon, (), either)


def all_down(flags: int, parts: tuple[int, ...]) -> bool:
    return all(flags & part for part in parts)


def other_modifier(flags: int, own: int) -> bool:
    """Whether a modifier other than the key's own is down."""
    return bool(flags & ANY_MODIFIER & ~own)


# -- macOS's calls ------------------------------------------------------------------


class _EventTypeSpec(ctypes.Structure):
    _fields_ = (("event_class", ctypes.c_uint32), ("kind", ctypes.c_uint32))


class _HotKeyId(ctypes.Structure):
    _fields_ = (("signature", ctypes.c_uint32), ("id", ctypes.c_uint32))


_Handler = ctypes.CFUNCTYPE(
    ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)


class _Libraries:
    def __init__(self) -> None:
        carbon = ctypes.util.find_library("Carbon")
        quartz = ctypes.util.find_library("ApplicationServices")
        if carbon is None or quartz is None:
            raise OSError("macOS's Carbon or ApplicationServices isn't here")
        self.carbon = ctypes.CDLL(carbon)
        self.quartz = ctypes.CDLL(quartz)
        p, u32, i32 = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32
        for lib, name, restype, argtypes in (
            (self.carbon, "GetApplicationEventTarget", p, []),
            (
                self.carbon,
                "InstallEventHandler",
                i32,
                [
                    p,
                    _Handler,
                    ctypes.c_ulong,
                    ctypes.POINTER(_EventTypeSpec),
                    p,
                    ctypes.POINTER(p),
                ],
            ),
            (self.carbon, "RemoveEventHandler", i32, [p]),
            (
                self.carbon,
                "RegisterEventHotKey",
                i32,
                [u32, u32, _HotKeyId, p, u32, ctypes.POINTER(p)],
            ),
            (self.carbon, "UnregisterEventHotKey", i32, [p]),
            (self.carbon, "GetEventKind", u32, [p]),
            (
                self.carbon,
                "GetEventParameter",
                i32,
                [p, u32, u32, p, ctypes.c_ulong, p, p],
            ),
            (self.quartz, "CGEventSourceFlagsState", ctypes.c_uint64, [i32]),
            (
                self.quartz,
                "CGEventSourceSecondsSinceLastEventType",
                ctypes.c_double,
                [i32, u32],
            ),
        ):
            call = getattr(lib, name)
            call.restype = restype
            call.argtypes = argtypes


@cache
def _libraries() -> _Libraries:
    return _Libraries()


_COMBINED = 0  # kCGEventSourceStateCombinedSessionState
_KEY_DOWN = 10  # kCGEventKeyDown


def flags_now() -> int:
    """The modifiers held now, anywhere, with each side's bit."""
    return int(_libraries().quartz.CGEventSourceFlagsState(_COMBINED))


def since_key_down() -> float:
    """Seconds since any key last went down, anywhere."""
    return float(
        _libraries().quartz.CGEventSourceSecondsSinceLastEventType(_COMBINED, _KEY_DOWN)
    )


class CarbonKey:
    """One hotkey through Carbon, calling `pressed` and `released` on the
    interface's thread (where Carbon's events come)."""

    _next_id = 1

    def __init__(
        self, pressed: Callable[[], None], released: Callable[[], None]
    ) -> None:
        self._pressed, self._released = pressed, released
        self._handler = _Handler(self._event)  # kept alive while installed
        self._handler_ref = ctypes.c_void_p()
        self._key_ref = ctypes.c_void_p()
        self._id = CarbonKey._next_id
        CarbonKey._next_id += 1

    def register(self, key_code: int, modifiers: int) -> bool:
        lib = _libraries().carbon
        target = lib.GetApplicationEventTarget()
        kinds = (_EventTypeSpec * 2)(
            _EventTypeSpec(_KEYBOARD, _PRESSED), _EventTypeSpec(_KEYBOARD, _RELEASED)
        )
        status = lib.InstallEventHandler(
            target, self._handler, 2, kinds, None, ctypes.byref(self._handler_ref)
        )
        if status != 0:
            log.warning("Carbon refused dictation's key handler (%d)", status)
            return False
        status = lib.RegisterEventHotKey(
            key_code,
            modifiers,
            _HotKeyId(SIGNATURE, self._id),
            target,
            _EXCLUSIVE,
            ctypes.byref(self._key_ref),
        )
        if status != 0:
            self.unregister()
            return False
        return True

    def unregister(self) -> None:
        lib = _libraries().carbon
        if self._key_ref.value:
            lib.UnregisterEventHotKey(self._key_ref)
            self._key_ref = ctypes.c_void_p()
        if self._handler_ref.value:
            lib.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()

    def _event(self, _next: int | None, event: int | None, _data: int | None) -> int:
        try:
            lib = _libraries().carbon
            found = _HotKeyId()
            status = lib.GetEventParameter(
                event,
                _DIRECT,
                _HOTKEY_ID,
                None,
                ctypes.sizeof(found),
                None,
                ctypes.byref(found),
            )
            if status != 0 or found.signature != SIGNATURE or found.id != self._id:
                return _NOT_HANDLED  # another hotkey's: the next handler's
            if lib.GetEventKind(event) == _PRESSED:
                self._pressed()
            else:
                self._released()
            return 0
        except Exception:  # never out into Carbon's call
            log.exception("dictation's key: Carbon's event couldn't be read")
            return _NOT_HANDLED


# -- the key ------------------------------------------------------------------------


class MacHoldKey:
    """Dictation's key or combination, held, on a Mac: `on_down` when the
    whole of it is down, `on_up` when any of it comes up, `on_other` when a
    key held alone turns out to be a shortcut - all on a thread of its own.
    Made as Windows' `HoldKey` is (the `HoldKey` port)."""

    def __init__(
        self,
        key: str,
        on_down: Callable[[], None],
        on_up: Callable[[], None],
        on_other: Callable[[], None] = lambda: None,
        *,
        flags: Callable[[], int] = flags_now,
        since_key: Callable[[], float] = since_key_down,
        carbon: Callable[
            [Callable[[], None], Callable[[], None]], CarbonKey
        ] = CarbonKey,
        poll: float = POLL_SEC,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """`key`: a `DictationKey` as kept ("ctrl+win+d", "right_ctrl").
        `flags`, `since_key`, `carbon`: macOS's, or a test's."""
        parsed = DictationKey.parse(key)
        if parsed is None:
            raise ValueError(f"not a dictation key: {key!r}")
        self.held_alone = parsed.held_alone
        self._plan = plan(parsed)
        self._on_down, self._on_up, self._on_other = on_down, on_up, on_other
        self._flags, self._since_key, self._carbon = flags, since_key, carbon
        self._poll, self._clock = poll, clock
        self._said: queue.SimpleQueue[str] = queue.SimpleQueue()
        """What Carbon said: "down", "up" - or "stop"."""
        self._key: CarbonKey | None = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    def start(self) -> bool:
        """Takes the key and starts listening; False if another app has it,
        or a Mac has no such key (a key held alone is never another's)."""
        if self._thread is not None:
            raise RuntimeError("already started")
        if self._plan is None:
            log.warning("dictation's key has no Mac counterpart")
            return False
        if self._plan.key_code is not None:
            self._key = self._carbon(self._carbon_pressed, self._carbon_released)
            if not self._key.register(self._plan.key_code, self._plan.carbon):
                log.warning("the dictation key is already taken by another app")
                self._key = None
                return False
        run = self._watch if self._plan.key_code is None else self._run
        self._thread = threading.Thread(target=run, name="hold-key", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._key is not None:
            self._key.unregister()
            self._key = None
        thread = self._thread
        if thread is None:
            return
        self._stopping.set()
        self._said.put("stop")
        thread.join(timeout=5)
        self._thread = None

    def post(self, said: str) -> None:
        """As if Carbon had said the key went "down" or came "up" - for
        tests and the Mac's checks, without pressing it."""
        self._said.put(said)

    def _carbon_pressed(self) -> None:
        self._said.put("down")

    def _carbon_released(self) -> None:
        self._said.put("up")

    def _run(self) -> None:
        """A registered key: down and up when Carbon says - or up when one
        of its modifiers is let go first."""
        assert self._plan is not None
        own = self._plan.modifiers
        while not self._stopping.is_set():
            said = self._said.get()
            if said != "down":
                continue
            # read the modifiers only if they're seen held now: else their
            # state can't be read here, and Carbon's "up" alone ends it
            watch_modifiers = own != 0 and self._flags() & own == own
            self._call(self._on_down)
            while not self._stopping.is_set():
                try:
                    said = self._said.get(timeout=self._poll)
                except queue.Empty:
                    if watch_modifiers and self._flags() & own != own:
                        break
                    continue
                if said in ("up", "stop"):
                    break
            self._call(self._on_up)

    def _watch(self) -> None:
        """A modifier, or modifiers, held alone: their state read until
        stopped."""
        assert self._plan is not None
        parts, own = self._plan.alone, self._plan.modifiers or ANY_MODIFIER
        if len(parts) == 1:  # one side's bit: its modifier's own is set with it
            own = next(
                (h.either for h in MODIFIERS.values() if parts[0] in (h.left, h.right)),
                own,
            )
        held = False
        apart = False  # down as part of a shortcut: waits to come up
        since = 0.0
        while not self._stopping.wait(self._poll):
            flags = self._flags()
            if not all_down(flags, parts):
                if held:
                    self._call(self._on_up)
                held = apart = False
                continue
            if apart:
                continue
            if not held:
                if other_modifier(flags, own):
                    apart = True  # a shortcut begun with another modifier
                    continue
                held, since = True, self._clock()
                self._call(self._on_down)
                continue
            pressed = self._clock() - since
            if other_modifier(flags, own) or self._since_key() < pressed:
                apart = True
                self._call(self._on_other)
        if held:
            self._call(self._on_up)

    @staticmethod
    def _call(call: Callable[[], None]) -> None:
        try:
            call()
        except Exception:  # a failing action must not end the key
            log.exception("the dictation key's action failed")
