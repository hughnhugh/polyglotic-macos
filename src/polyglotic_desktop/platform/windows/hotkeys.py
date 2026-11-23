"""System-wide hotkeys: Ctrl+Alt+L, P, H and J - or the keys the learner chose - work even while a game has focus.

A Qt shortcut only fires while one of the app's windows has the keyboard;
Windows' `RegisterHotKey` fires whatever has it. The proof of concept
(`ui/app.py`, `_Hotkeys`) registered them on Qt's thread and read
`WM_HOTKEY` through a Qt native event filter; here they live on a thread
of their own with its own message loop, so this module needs no Qt:
`GlobalHotkeys` calls each binding on that thread, and `main` hands the
call to the interface's thread.

Each is a combination as `core.listening.dictation_keys.DictationKey`
keeps it ("ctrl+alt+l", "f9": polyglotic-hq 567, decision 0273): any key
`HoldKey` takes, with any modifiers - but a modifier alone, which Windows
can't register. A combination another app has already registered can't be
taken: `start` says which, and the rest still work, and the log names
which of ours they were ("Ctrl+Alt+H": polyglotic-hq 291 - a tester's log
said only "1 hotkey(s)"). Windows doesn't say which app has it, and
nothing pressed is ever logged.

`HoldKey` is dictation's key or combination, held (polyglotic-hq 283,
289; decision 0081): the same `RegisterHotKey` for when a key goes down,
then its state read until it comes up - or, for Right Ctrl alone or
modifiers alone, which Windows can't register, their state read all the
time.
"""

import ctypes
import ctypes.wintypes
import logging
import threading
from collections.abc import Callable, Mapping

from polyglotic_desktop.core.listening.dictation_keys import (
    HOLD_RELEASE_POLLS,
    DictationKey,
    Modifier,
)

log = logging.getLogger(__name__)

MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x0001, 0x0002, 0x0004
MOD_NOREPEAT = 0x4000  # held down, it fires once
WM_QUIT, WM_HOTKEY = 0x0012, 0x0312
_PM_NOREMOVE, _PM_REMOVE = 0x0000, 0x0001

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [
    ctypes.wintypes.HWND,
    ctypes.c_int,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
_user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = ctypes.wintypes.BOOL
_user32.GetMessageW.argtypes = [
    ctypes.POINTER(ctypes.wintypes.MSG),
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
_user32.GetMessageW.restype = ctypes.wintypes.BOOL
_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(ctypes.wintypes.MSG),
    ctypes.wintypes.HWND,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
    ctypes.wintypes.UINT,
]
_user32.PeekMessageW.restype = ctypes.wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [
    ctypes.wintypes.DWORD,
    ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]
_user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL


def combination(key: str) -> str:
    """A combination as Windows' own menus write it: "Ctrl+Alt+L"."""
    parsed = DictationKey.parse(key)
    if parsed is None:
        return key
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}
    return "+".join(
        names.get(part)
        or (part.upper() if len(part) == 1 or part[1:].isdigit() else part)
        .replace("_", " ")
        .title()
        for part in parsed.parts
    )


def registered(key: str) -> tuple[int, int]:
    """`key`'s modifiers and virtual key, as `RegisterHotKey` takes them.
    Raises `ValueError` for a key that can't be registered: not a key kept,
    or a modifier alone."""
    parsed = DictationKey.parse(key)
    if parsed is None or parsed.key is None or parsed.key not in VK_KEYS:
        raise ValueError(f"not a hotkey: {key!r}")
    modifiers = 0
    for modifier in parsed.modifiers:
        modifiers |= MODIFIER_KEYS[modifier][0]
    return modifiers, VK_KEYS[parsed.key]


class GlobalHotkeys:
    """Hotkeys for the whole system, each a combination as kept
    ("ctrl+alt+l"), on a thread of their own."""

    def __init__(self, bindings: Mapping[str, Callable[[], None]]) -> None:
        """`bindings`: a combination as kept -> what to call, on the
        hotkeys' thread, when it's pressed."""
        self._keys = list(bindings)
        self._codes = [registered(key) for key in bindings]
        self._calls = dict(enumerate(bindings.values(), start=1))
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self.taken: list[str] = []
        """The keys another app had already registered (not working here)."""

    def start(self) -> list[str]:
        """Registers the hotkeys and starts listening; returns the keys
        another app already has."""
        if self._thread is not None:
            raise RuntimeError("already started")
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait()
        return self.taken

    def stop(self) -> None:
        """Unregisters the hotkeys and ends their thread."""
        thread = self._thread
        if thread is None:
            return
        _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        thread.join(timeout=5)
        self._thread = None

    def post(self, key: str) -> None:
        """As if `key`'s combination had been pressed - for tests, without
        pressing anything."""
        _user32.PostThreadMessageW(
            self._thread_id, WM_HOTKEY, self._keys.index(key) + 1, 0
        )

    def _run(self) -> None:
        msg = ctypes.wintypes.MSG()
        # the thread's message queue exists from its first message call:
        # before it, a stop's WM_QUIT would be lost
        _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_NOREMOVE)
        self._thread_id = threading.get_native_id()
        done = []
        for hotkey_id, (key, (modifiers, vk)) in enumerate(
            zip(self._keys, self._codes, strict=True), start=1
        ):
            if _user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk):
                done.append(hotkey_id)
            else:
                self.taken.append(key)
        if self.taken:
            log.warning(
                "hotkey(s) already taken by another app: %s",
                ", ".join(combination(key) for key in self.taken),
            )
        self._ready.set()
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message != WM_HOTKEY:
                    continue
                call = self._calls.get(msg.wParam)
                if call is None:
                    continue
                try:
                    call()
                except Exception:  # a failing action must not end the hotkeys
                    log.exception("a hotkey's action failed")
        finally:
            for hotkey_id in done:
                _user32.UnregisterHotKey(None, hotkey_id)


MOD_WIN = 0x0008  # either Windows key

VK_KEYS = {
    **{chr(code).lower(): code for code in range(0x41, 0x5B)},  # A-Z
    **{str(digit): 0x30 + digit for digit in range(10)},
    **{f"f{n}": 0x6F + n for n in range(1, 25)},  # F1 0x70 ... F24 0x87
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "page_down": 0x22,
    "insert": 0x2D,
    "escape": 0x1B,
    "pause": 0x13,
    "scroll_lock": 0x91,
    "print_screen": 0x2C,
    "menu": 0x5D,  # VK_APPS
}
"""Each of `core.listening.dictation_keys.KEYS` and its virtual-key code."""
LONE_VKS = {
    "right_ctrl": 0xA3,
    "left_ctrl": 0xA2,
    "right_shift": 0xA1,
    "left_shift": 0xA0,
    "right_alt": 0xA5,
    "left_alt": 0xA4,
    "left_win": 0x5B,
    "right_win": 0x5C,
}
"""A modifier on its own, by its side (`dictation_keys.LONE_MODIFIERS`)."""
_GENERIC = {0xA2: 0x11, 0xA3: 0x11, 0xA0: 0x10, 0xA1: 0x10, 0xA4: 0x12, 0xA5: 0x12}
"""Each sided Ctrl, Shift and Alt's either-side code, down with it."""
MODIFIER_KEYS: dict[Modifier, tuple[int, tuple[int, ...], tuple[int, ...]]] = {
    # RegisterHotKey's flag; the codes down when it's held; all its codes
    Modifier.CTRL: (MOD_CONTROL, (0x11,), (0x11, 0xA2, 0xA3)),
    Modifier.ALT: (MOD_ALT, (0x12,), (0x12, 0xA4, 0xA5)),
    Modifier.SHIFT: (MOD_SHIFT, (0x10,), (0x10, 0xA0, 0xA1)),
    Modifier.WIN: (MOD_WIN, (0x5B, 0x5C), (0x5B, 0x5C)),
}
OTHER_VKS = tuple(
    vk
    for vk in range(0x01, 0xFF)
    if vk not in (0x03, 0xE7)  # Ctrl+Break's own code; typed characters (VK_PACKET)
)
"""Every key (and mouse button) that, down with a key held alone, means a
shortcut - read only while it's held."""
POLL_SEC = 0.015
"""How often the key's state is read: while it's held until it comes up;
for a key held alone, all the time dictation is on (measured 2026-11-12:
0.2-0.6% of one core, polyglotic-hq 289)."""
OTHERS_EVERY = 3
"""While a key held alone is down, the other keys are read every this
many reads (45 ms - shorter than a key's tap): all 250 each time cost 4%
of one core while held, a third of that this way."""
_DOWN = 0x8000
_HOLD_ID = 0x283  # its own id, apart from GlobalHotkeys' 1, 2, 3...

_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short


def _key_down(vk: int) -> bool:
    return bool(_user32.GetAsyncKeyState(vk) & _DOWN)


class HoldKey:
    """Dictation's key or combination, held (polyglotic-hq 283, 289):
    `on_down` when the whole of it is down, `on_up` when any of its keys
    comes up, all on a thread of its own. Two ways, by the key:

    - **A key, with or without modifiers** (Insert, F9, Ctrl+Alt+D):
      `RegisterHotKey` takes it from other programs while it's ours (Insert
      stops toggling an editor's overwrite; holding Ctrl+Alt+D types no
      "d") and says when it goes down, once (`MOD_NOREPEAT`); then its keys'
      state is read every `POLL_SEC` until one is up.
    - **Right Ctrl alone, or modifiers alone** (Ctrl+Win): Windows can't
      register a modifier, so its state is read every `POLL_SEC` all the
      time (`GetAsyncKeyState`, as `keys` reads Esc) - one or two keys,
      nothing else. Other programs still get it. While it's held, the other
      keys are read too: one going down (Right Ctrl + C) means a shortcut,
      and `on_other` is called; `on_up` still follows when it comes up. A
      shortcut begun before it (C, then Right Ctrl) never starts it.

    No keyboard hook: nothing else typed on the PC passes through the app.
    Nothing about the keys is logged."""

    def __init__(
        self,
        key: str,
        on_down: Callable[[], None],
        on_up: Callable[[], None],
        on_other: Callable[[], None] = lambda: None,
        *,
        key_down: Callable[[int], bool] = _key_down,
        poll: float = POLL_SEC,
        release_polls: int | None = None,
    ) -> None:
        """`key`: a `DictationKey` as kept ("ctrl+alt+d", "right_ctrl").
        `key_down`: whether a virtual key is down now (Windows', or a
        test's)."""
        parsed = DictationKey.parse(key)
        if parsed is None:
            raise ValueError(f"not a dictation key: {key!r}")
        self.held_alone = parsed.held_alone
        self._modifiers = 0
        self._parts: list[tuple[int, ...]] = []
        """The codes of each of its keys - a part is down if one of its is."""
        own: set[int] = set()
        for modifier in parsed.modifiers:
            flag, down, every = MODIFIER_KEYS[modifier]
            self._modifiers |= flag
            self._parts.append(down)
            own.update(every)
        self._vk = 0
        if parsed.key in LONE_VKS:
            vk = LONE_VKS[parsed.key]
            self._parts.append((vk,))
            own.update((vk, _GENERIC.get(vk, vk)))
        elif parsed.key is not None:
            self._vk = VK_KEYS[parsed.key]
            self._parts.append((self._vk,))
        self._others = tuple(vk for vk in OTHER_VKS if vk not in own)
        self._on_down, self._on_up, self._on_other = on_down, on_up, on_other
        self._key_down, self._poll = key_down, poll
        self._release_polls = max(
            1,
            int(HOLD_RELEASE_POLLS.configured)
            if release_polls is None
            else release_polls,
        )
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._ours = False

    def start(self) -> bool:
        """Takes the key and starts listening; False if another program has
        it (a key held alone is never another's)."""
        if self._thread is not None:
            raise RuntimeError("already started")
        run = self._watch if self.held_alone else self._run
        self._thread = threading.Thread(target=run, name="hold-key", daemon=True)
        self._thread.start()
        self._ready.wait()
        return self._ours

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stopping.set()
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        thread.join(timeout=5)
        self._thread = None

    def post(self) -> None:
        """As if a registered key had gone down - for tests, without
        pressing it."""
        _user32.PostThreadMessageW(self._thread_id, WM_HOTKEY, _HOLD_ID, 0)

    def _all_down(self) -> bool:
        return all(any(self._key_down(vk) for vk in part) for part in self._parts)

    def _other_down(self) -> bool:
        return any(self._key_down(vk) for vk in self._others)

    def _drain_hotkeys(self) -> bool:
        """Remove any queued WM_HOTKEY messages for this key; True if any arrived."""
        msg = ctypes.wintypes.MSG()
        found = False
        while _user32.PeekMessageW(
            ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, _PM_REMOVE
        ):
            if msg.wParam == _HOLD_ID:
                found = True
        return found

    def _run(self) -> None:
        """A registered key: down when Windows says, up when a key is."""
        msg = ctypes.wintypes.MSG()
        _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, _PM_NOREMOVE)
        self._thread_id = threading.get_native_id()
        self._ours = bool(
            _user32.RegisterHotKey(
                None, _HOLD_ID, self._modifiers | MOD_NOREPEAT, self._vk
            )
        )
        if not self._ours:
            log.warning("the dictation key is already taken by another app")
        self._ready.set()
        if not self._ours:
            return
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message != WM_HOTKEY or msg.wParam != _HOLD_ID:
                    continue
                self._drain_hotkeys()
                self._call(self._on_down)
                up_polls = 0
                while not self._stopping.is_set():
                    self._stopping.wait(self._poll)
                    if self._stopping.is_set():
                        break
                    repeated = self._drain_hotkeys()
                    if self._all_down() or repeated:
                        up_polls = 0
                    else:
                        up_polls += 1
                        if up_polls >= self._release_polls:
                            break
                self._drain_hotkeys()
                self._call(self._on_up)
        finally:
            _user32.UnregisterHotKey(None, _HOLD_ID)

    def _watch(self) -> None:
        """A key held alone: its state read until stopped."""
        self._ours = True
        self._ready.set()
        held = False  # down for dictation
        apart = False  # down as part of a shortcut: waits to come up
        reads = 0  # while held: the other keys are read every OTHERS_EVERY
        while not self._stopping.wait(self._poll):
            if not self._all_down():
                if held:
                    self._call(self._on_up)
                held = apart = False
                continue
            if apart:
                continue
            reads = reads + 1 if held else 0
            if reads % OTHERS_EVERY == 0 and self._other_down():
                apart = True
                if held:
                    self._call(self._on_other)
            elif not held:
                held = True
                self._call(self._on_down)
        if held:
            self._call(self._on_up)

    @staticmethod
    def _call(call: Callable[[], None]) -> None:
        try:
            call()
        except Exception:  # a failing action must not end the key
            log.exception("the dictation key's action failed")
