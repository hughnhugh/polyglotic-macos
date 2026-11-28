"""Linux's system-wide hotkeys (polyglotic-hq 546's slice 3, 570;
`ports.system.Hotkeys`): lock, pause and hide from wherever the learner is.

**X11's key grab** (`X11Hotkeys`): the X server hands this app each
combination grabbed on the root window, whatever window has the keyboard.
- In an Xorg session (Ubuntu's "Ubuntu on Xorg", Mint, Xfce) that is every
  window.
- On KDE's Wayland session KWin hands an X11 app the keys typed with Ctrl,
  Alt or Meta held, whatever app has the keyboard (its "Legacy X11 App
  Support" default), so a combination grabbed through XWayland works there
  too.
- On GNOME's Wayland session only while an X11 window has the keyboard -
  not over Firefox or a Wayland game - so it isn't offered there: the keys
  answer "not working here", and the learner binds `polyglotic --lock` and
  the like in GNOME's keyboard settings (`main`'s arguments; Help says how).

Which one runs is the session's (`for_this_session`). The app is an X11
program on every desktop (decision 0258), so the grab goes through the
same X server its windows are on.

**libxcb, by ctypes** (`Xcb`): the library Qt's own X11 plugin uses, on
every desktop; a connection of its own, so nothing here touches Qt's. A
grab another program holds fails with `BadAccess`, which libxcb gives back
for the request itself (no process-wide error handler, as Xlib would
need): `start` says which keys, and the rest still work. The keys are
found by what they type ("L"), on the keyboard's first layout; a layout
with no Latin letters gets the US keyboard's positions. NumLock and Caps
Lock on or off are grabbed alike. Held down, a combination fires once:
the X server's repeats (a release and a press at the same moment) are
let go.

Each binding's key is a combination as the settings keep it
("ctrl+alt+shift+l", "f9": `core.listening.dictation_keys.DictationKey`,
polyglotic-hq 567); Linux's own are Ctrl+Alt+Shift with the letter
(`core.listening.hotkeys.OWN_MODIFIERS`, decision 0293).

Each combination's binding is called on the hotkeys' own thread; `main`
hands the call to the interface's thread. Nothing pressed is ever logged.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import os
import select
import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Protocol

from polyglotic_desktop.core.listening.dictation_keys import DictationKey, Modifier
from polyglotic_desktop.core.listening.type_theirs import HOLD_REPEAT_SEC
from polyglotic_desktop.platform.linux.system import desktop_names, wayland_session

log = logging.getLogger(__name__)

SHIFT, LOCK, CONTROL, MOD1, MOD2, MOD4 = 0x01, 0x02, 0x04, 0x08, 0x10, 0x40
"""X11's modifier masks: Shift, Caps Lock, Ctrl, Alt (Mod1), NumLock
(Mod2 on every current keyboard map), Super (Mod4)."""
CTRL_ALT_SHIFT = CONTROL | MOD1 | SHIFT
"""Linux's own hotkeys' modifiers (decision 0293)."""
WATCHED = SHIFT | CONTROL | MOD1 | MOD4
"""The modifiers a combination is told apart by; Caps Lock and NumLock
aren't."""
IGNORED = (0, LOCK, MOD2, LOCK | MOD2)
"""Caps Lock and NumLock, on or off: each combination is grabbed four times."""
KEY_PRESS, KEY_RELEASE = 2, 3
BAD_ACCESS = 10
"""X11's error for a grab another client holds."""
US_KEYCODES = {
    **{key: 8 + code for key, code in zip("QWERTYUIOP", range(16, 26), strict=True)},
    **{key: 8 + code for key, code in zip("ASDFGHJKL", range(30, 39), strict=True)},
    **{key: 8 + code for key, code in zip("ZXCVBNM", range(44, 51), strict=True)},
    **{key: 8 + code for key, code in zip("1234567890", range(2, 12), strict=True)},
}
"""Each letter's and digit's X key code where a US keyboard has it (the
kernel's code plus 8): for a first layout with no Latin letters."""


MODIFIER_MASKS = {
    Modifier.CTRL: CONTROL,
    Modifier.ALT: MOD1,
    Modifier.SHIFT: SHIFT,
    Modifier.WIN: MOD4,
}
NAMED_KEYSYMS = {
    "minus": 0x002D, "equal": 0x003D, "bracket_left": 0x005B, "bracket_right": 0x005D,
    "backslash": 0x005C, "semicolon": 0x003B, "apostrophe": 0x0027, "grave": 0x0060,
    "comma": 0x002C, "period": 0x002E, "slash": 0x002F,
    "space": 0x0020, "enter": 0xFF0D, "tab": 0xFF09, "backspace": 0xFF08,
    "delete": 0xFFFF, "left": 0xFF51, "up": 0xFF52, "right": 0xFF53,
    "down": 0xFF54, "home": 0xFF50, "end": 0xFF57, "page_up": 0xFF55,
    "page_down": 0xFF56, "insert": 0xFF63, "escape": 0xFF1B, "pause": 0xFF13,
    "scroll_lock": 0xFF14, "print_screen": 0xFF61, "menu": 0xFF67,
    "media_play": 0x1008FF14, "media_stop": 0x1008FF15, "media_next": 0x1008FF17,
    "media_prev": 0x1008FF16, "volume_up": 0x1008FF13, "volume_down": 0x1008FF11,
    "volume_mute": 0x1008FF12,
    **{f"f{n}": 0xFFBE + n - 1 for n in range(1, 25)},
}  # fmt: skip
"""X11's keysym for each key a kept combination can name beside its
letters and digits (X11's keysymdef.h)."""


def binding_key(key: str) -> tuple[int, str]:
    """A kept combination's ("ctrl+alt+shift+l") modifiers and key. Raises
    ValueError for anything else: a modifier alone can't be pressed, and a
    letter or digit alone would never be typed anywhere again."""
    found = DictationKey.parse(key)
    lone = found is not None and not found.modifiers and len(found.key or "") == 1
    if found is None or found.key is None or found.held_alone or lone:
        raise ValueError(f"not a letter, digit or combination: {key!r}")
    held = 0
    for modifier in found.modifiers:
        held |= MODIFIER_MASKS[modifier]
    named = found.key.upper() if len(found.key) == 1 else found.key
    return held, named


def combination(modifiers: int, key: str) -> str:
    """A combination as Linux's desktops write it: "Ctrl+Alt+Shift+L"."""
    names = [
        name
        for mask, name in (
            (CONTROL, "Ctrl"),
            (MOD1, "Alt"),
            (SHIFT, "Shift"),
            (MOD4, "Super"),
        )
        if modifiers & mask
    ]
    return "+".join([*names, key])


def keysyms_for(key: str) -> tuple[int, ...]:
    """The X keysyms a key types: a letter's lower and upper case, a
    digit's, or a named key's ("f9")."""
    if len(key) > 1:
        return (NAMED_KEYSYMS[key],)
    return tuple(dict.fromkeys((ord(key.lower()), ord(key.upper()))))


def keycode_for(
    key: str, mapping: Sequence[Sequence[int]], first_keycode: int
) -> int | None:
    """The key code that types `key` on the first layout (a keycode's
    first two keysyms), else on any layout, else where a US keyboard has
    it. `mapping`: each keycode's keysyms, from `first_keycode` on."""
    wanted = set(keysyms_for(key))
    for columns in (slice(0, 2), slice(0, None)):
        for offset, syms in enumerate(mapping):
            if wanted.intersection(syms[columns]):
                return first_keycode + offset
    return US_KEYCODES.get(key)


class Xcb(Protocol):
    """The X server calls the hotkeys make (`LibXcb`; a fake in tests)."""

    def keyboard(self) -> tuple[int, list[list[int]]]:
        """The first keycode and each keycode's keysyms from there."""
        ...

    def grab(self, keycode: int, modifiers: int) -> bool:
        """Grabs one combination on the root window; False if another
        program holds it."""
        ...

    def ungrab(self, keycode: int, modifiers: int) -> None: ...

    def fileno(self) -> int:
        """The connection's socket, readable when events come."""
        ...

    def events(self) -> list[tuple[int, int, int, int]]:
        """The key events waiting: (kind, keycode, modifiers, time)."""
        ...

    def broken(self) -> bool:
        """The connection ended (the X server went away)."""
        ...

    def close(self) -> None: ...


class X11Hotkeys:
    """`Hotkeys` through X11's key grab: each a kept combination
    (`binding_key`), its binding called on the hotkeys' own thread."""

    def __init__(
        self,
        bindings: Mapping[str, Callable[[], None]],
        connect: Callable[[], Xcb] | None = None,
        *,
        passthrough: Collection[str] = (),
    ) -> None:
        self._passthrough = frozenset(passthrough)
        # X11's root-window grab always swallows: pass-through typing keys are
        # never grabbed so typing in other apps isn't broken.
        self._combinations = {
            key: binding_key(key) for key in bindings if key not in self._passthrough
        }
        """Each grabbed binding's modifiers and key."""
        self._bindings = dict(bindings)
        self._connect = connect or LibXcb
        self._xcb: Xcb | None = None
        self._grabbed: dict[tuple[int, int], str] = {}
        """Each grabbed key code and its modifiers: the binding's key."""
        self._thread: threading.Thread | None = None
        self._wake_r, self._wake_w = -1, -1
        self._down: set[int] = set()
        self._released: dict[int, int] = {}
        self.available = True
        """Whether this session can take global hotkeys (False if no X server)."""
        self.taken: list[str] = []
        """The keys another program already has (not working here)."""

    def start(self) -> list[str]:
        """Grabs the hotkeys and starts listening; returns the keys another
        program already has - all of them if there's no X server to ask."""
        if self._xcb is not None:
            raise RuntimeError("already started")
        self.taken = [key for key in self._bindings if key in self._passthrough]
        if not self._combinations:
            return self.taken
        try:
            xcb = self._connect()
        except OSError:
            log.exception("X11's hotkeys can't be taken")
            self.available = False
            self.taken = list(self._bindings)
            return self.taken
        self._xcb = xcb
        first, mapping = xcb.keyboard()
        for key, (held, pressed) in self._combinations.items():
            keycode = keycode_for(pressed, mapping, first)
            if keycode is None or not self._grab(xcb, keycode, held):
                self.taken.append(key)
                continue
            self._grabbed[keycode, held & WATCHED] = key
        if self.taken:
            log.warning(
                "hotkey(s) already taken by another program: %s",
                ", ".join(
                    combination(*self._combinations[key])
                    if key in self._combinations
                    else key
                    for key in self.taken
                ),
            )
        self._wake_r, self._wake_w = os.pipe()
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()
        return self.taken

    def probe(self, keys: Sequence[str]) -> list[str]:
        """Return which of `keys` X11 cannot grab right now, ungrabbing any
        free ones immediately."""
        xcb = self._xcb
        if xcb is None or xcb.broken():
            return list(keys)
        first, mapping = xcb.keyboard()
        busy: list[str] = []
        for key in keys:
            try:
                held, pressed = binding_key(key)
            except ValueError:
                busy.append(key)
                continue
            keycode = keycode_for(pressed, mapping, first)
            if keycode is None or not self._grab(xcb, keycode, held):
                busy.append(key)
                continue
            for extra in IGNORED:
                xcb.ungrab(keycode, held | extra)
        return busy

    def _grab(self, xcb: Xcb, keycode: int, held: int) -> bool:
        """Every Caps Lock and NumLock variant of one combination, or none."""
        done: list[int] = []
        for extra in IGNORED:
            if not xcb.grab(keycode, held | extra):
                for undo in done:
                    xcb.ungrab(keycode, undo)
                return False
            done.append(held | extra)
        return True

    def stop(self) -> None:
        """Gives the hotkeys back and ends their thread."""
        xcb, thread = self._xcb, self._thread
        if xcb is None:
            return
        if thread is not None:
            os.write(self._wake_w, b"x")
            thread.join(timeout=5)
            os.close(self._wake_r)
            os.close(self._wake_w)
        if not xcb.broken():
            for keycode, held in self._grabbed:
                for extra in IGNORED:
                    xcb.ungrab(keycode, held | extra)
        xcb.close()
        self._grabbed.clear()
        self._xcb = self._thread = None

    def handle(self, kind: int, keycode: int, modifiers: int, time: int) -> None:
        """One key event from the X server (the thread's; a test's own): a
        grabbed combination's first press calls its binding."""
        if kind == KEY_RELEASE:  # whatever's held with it by now
            self._down.discard(keycode)
            self._released[keycode] = time
            return
        key = self._grabbed.get((keycode, modifiers & WATCHED))
        if kind != KEY_PRESS or key is None:
            return
        repeat = keycode in self._down or self._released.get(keycode) == time
        self._down.add(keycode)
        if repeat:  # held down: the X server's repeat
            return
        try:
            self._bindings[key]()
        except Exception:  # a failing action must not end the hotkeys
            log.exception("a hotkey's action failed")

    def _run(self) -> None:
        xcb = self._xcb
        assert xcb is not None
        while True:
            ready, _, _ = select.select(
                [xcb.fileno(), self._wake_r], [], [], self._release_wait()
            )
            if self._wake_r in ready:
                return
            if not ready:
                self._flush_release()
                continue
            for event in xcb.events():
                self.handle(*event)
            if xcb.broken():
                log.warning(
                    "X11's hotkeys stopped: the connection to the X server ended"
                )
                return

    def _release_wait(self) -> float | None:
        return None

    def _flush_release(self) -> None:
        pass


class _HeldHotkey(X11Hotkeys):
    """A grabbed combination with one release per physical press."""

    def __init__(
        self,
        key: str,
        down: Callable[[], None],
        up: Callable[[], None],
        connect: Callable[[], Xcb] | None,
    ) -> None:
        super().__init__({key: down}, connect)
        self._up = up
        self._active: int | None = None
        self._pending: tuple[int, int] | None = None

    def handle(self, kind: int, keycode: int, modifiers: int, time: int) -> None:
        if self._pending is not None:
            if kind == KEY_PRESS and (keycode, time) == self._pending:
                self._pending = None
                return
            self._flush_release()
        if kind == KEY_RELEASE and keycode == self._active:
            self._pending = (keycode, time)
            return
        if kind == KEY_PRESS and (keycode, modifiers & WATCHED) in self._grabbed:
            self._active = keycode
        super().handle(kind, keycode, modifiers, time)

    def _release_wait(self) -> float | None:
        return HOLD_REPEAT_SEC.value if self._pending is not None else None

    def _flush_release(self) -> None:
        if self._pending is not None:
            keycode, time = self._pending
            self._pending = self._active = None
            super().handle(KEY_RELEASE, keycode, 0, time)
            self._up()


class HoldCombination:
    """The hold-key port for Linux sessions with an X11 key grab."""

    def __init__(
        self,
        key: str,
        down: Callable[[], None],
        up: Callable[[], None],
        _other: Callable[[], None],
        *,
        connect: Callable[[], Xcb] | None = None,
    ) -> None:
        try:
            self._key: _HeldHotkey | None = _HeldHotkey(key, down, up, connect)
        except (ValueError, KeyError):
            self._key = None

    def start(self) -> bool:
        return self._key is not None and not self._key.start()

    def stop(self) -> None:
        if self._key is not None:
            self._key.stop()


class NoHotkeys:
    """`Hotkeys` on a desktop that gives this app none (GNOME's Wayland
    session without the GlobalShortcuts portal): every key answers "not
    working here", so the interface says how else to lock, pause or hide -
    and the learner can bind `polyglotic --lock` and the like in the
    desktop's own keyboard settings."""

    available = False

    def __init__(
        self,
        bindings: Mapping[str, Callable[[], None]],
        *,
        passthrough: Collection[str] = (),
    ) -> None:
        del passthrough
        self._keys = list(bindings)

    def start(self) -> list[str]:
        return list(self._keys)

    def stop(self) -> None:
        pass


def grab_works_here(environ: Mapping[str, str]) -> bool:
    """Whether X11's key grab hears the keys whatever app has the keyboard:
    an Xorg session, or Plasma 6's Wayland session (KWin hands X11 apps the
    combinations with Ctrl, Alt or Meta held: `XwaylandEavesdrops`'s
    default is `Combinations` in Plasma 6, `None` in 5.27 - 570's survey of
    each one's kwin.kcfg)."""
    if not wayland_session(environ):
        return True
    version = environ.get("KDE_SESSION_VERSION", "")
    return "KDE" in desktop_names(environ) and version.isdigit() and int(version) >= 6


def for_this_session(
    bindings: Mapping[str, Callable[[], None]],
    environ: Mapping[str, str] | None = None,
    *,
    passthrough: Collection[str] = (),
) -> X11Hotkeys | NoHotkeys:
    """The hotkeys this session can give: X11's grab where it hears every
    app, else none."""
    env = os.environ if environ is None else environ
    if grab_works_here(env):
        return X11Hotkeys(bindings, passthrough=passthrough)
    return NoHotkeys(bindings, passthrough=passthrough)


# --- libxcb, through ctypes ---------------------------------------------------

_u8, _u16, _u32 = ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32


class _Setup(ctypes.Structure):
    _fields_ = (
        ("status", _u8), ("pad0", _u8), ("protocol_major_version", _u16),
        ("protocol_minor_version", _u16), ("length", _u16), ("release_number", _u32),
        ("resource_id_base", _u32), ("resource_id_mask", _u32),
        ("motion_buffer_size", _u32), ("vendor_len", _u16),
        ("maximum_request_length", _u16), ("roots_len", _u8),
        ("pixmap_formats_len", _u8), ("image_byte_order", _u8),
        ("bitmap_format_bit_order", _u8), ("bitmap_format_scanline_unit", _u8),
        ("bitmap_format_scanline_pad", _u8), ("min_keycode", _u8),
        ("max_keycode", _u8), ("pad1", _u8 * 4),
    )  # fmt: skip


class _ScreenIterator(ctypes.Structure):
    _fields_ = (
        ("data", ctypes.c_void_p),
        ("rem", ctypes.c_int),
        ("index", ctypes.c_int),
    )


class _Cookie(ctypes.Structure):
    _fields_ = (("sequence", ctypes.c_uint),)


class _MappingReply(ctypes.Structure):
    _fields_ = (
        ("response_type", _u8), ("keysyms_per_keycode", _u8), ("sequence", _u16),
        ("length", _u32), ("pad0", _u8 * 24),
    )  # fmt: skip


class _Error(ctypes.Structure):
    _fields_ = (("response_type", _u8), ("error_code", _u8), ("sequence", _u16))


class _KeyEvent(ctypes.Structure):
    _fields_ = (
        ("response_type", _u8), ("detail", _u8), ("sequence", _u16), ("time", _u32),
        ("root", _u32), ("event", _u32), ("child", _u32), ("root_x", ctypes.c_int16),
        ("root_y", ctypes.c_int16), ("event_x", ctypes.c_int16),
        ("event_y", ctypes.c_int16), ("state", _u16), ("same_screen", _u8), ("pad0", _u8),
    )  # fmt: skip


_GRAB_ASYNC = 1


class LibXcb:
    """`Xcb` through the system's libxcb: a connection of its own to the
    display Qt's windows are on (`DISPLAY`), and its first screen's root
    window - or the screen `DISPLAY` names."""

    def __init__(self) -> None:
        lib = ctypes.CDLL("libxcb.so.1")
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        vp, u8, u16, u32 = ctypes.c_void_p, _u8, _u16, _u32
        lib.xcb_connect.restype = vp
        lib.xcb_connect.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        lib.xcb_connection_has_error.restype = ctypes.c_int
        lib.xcb_connection_has_error.argtypes = [vp]
        lib.xcb_disconnect.argtypes = [vp]
        lib.xcb_get_setup.restype = ctypes.POINTER(_Setup)
        lib.xcb_get_setup.argtypes = [vp]
        lib.xcb_setup_roots_iterator.restype = _ScreenIterator
        lib.xcb_setup_roots_iterator.argtypes = [ctypes.POINTER(_Setup)]
        lib.xcb_screen_next.argtypes = [ctypes.POINTER(_ScreenIterator)]
        lib.xcb_get_keyboard_mapping.restype = _Cookie
        lib.xcb_get_keyboard_mapping.argtypes = [vp, u8, u8]
        lib.xcb_get_keyboard_mapping_reply.restype = ctypes.POINTER(_MappingReply)
        lib.xcb_get_keyboard_mapping_reply.argtypes = [vp, _Cookie, vp]
        lib.xcb_get_keyboard_mapping_keysyms.restype = ctypes.POINTER(u32)
        lib.xcb_get_keyboard_mapping_keysyms.argtypes = [ctypes.POINTER(_MappingReply)]
        lib.xcb_grab_key_checked.restype = _Cookie
        lib.xcb_grab_key_checked.argtypes = [vp, u8, u32, u16, u8, u8, u8]
        lib.xcb_ungrab_key.restype = _Cookie
        lib.xcb_ungrab_key.argtypes = [vp, u8, u32, u16]
        lib.xcb_request_check.restype = ctypes.POINTER(_Error)
        lib.xcb_request_check.argtypes = [vp, _Cookie]
        lib.xcb_flush.argtypes = [vp]
        lib.xcb_get_file_descriptor.restype = ctypes.c_int
        lib.xcb_get_file_descriptor.argtypes = [vp]
        lib.xcb_poll_for_event.restype = vp
        lib.xcb_poll_for_event.argtypes = [vp]
        libc.free.argtypes = [vp]
        self._lib, self._libc = lib, libc
        screen = ctypes.c_int(0)
        conn = lib.xcb_connect(None, ctypes.byref(screen))
        if not conn or lib.xcb_connection_has_error(conn):
            if conn:
                lib.xcb_disconnect(conn)
            raise OSError("xcb_connect: no X server to take hotkeys from")
        self._conn = conn
        setup = lib.xcb_get_setup(conn)
        self._setup = setup.contents
        roots = lib.xcb_setup_roots_iterator(setup)
        for _ in range(screen.value):
            lib.xcb_screen_next(ctypes.byref(roots))
        if not roots.data:
            lib.xcb_disconnect(conn)
            raise OSError("xcb: no screen")
        self._root = _u32.from_address(roots.data).value  # xcb_screen_t's first field

    def keyboard(self) -> tuple[int, list[list[int]]]:
        first, last = self._setup.min_keycode, self._setup.max_keycode
        count = last - first + 1
        lib = self._lib
        reply = lib.xcb_get_keyboard_mapping_reply(
            self._conn, lib.xcb_get_keyboard_mapping(self._conn, first, count), None
        )
        if not reply:
            return first, []
        try:
            per = reply.contents.keysyms_per_keycode
            syms = lib.xcb_get_keyboard_mapping_keysyms(reply)
            flat = [syms[i] for i in range(per * count)]
        finally:
            self._libc.free(reply)
        return first, [flat[i * per : (i + 1) * per] for i in range(count)]

    def grab(self, keycode: int, modifiers: int) -> bool:
        lib = self._lib
        cookie = lib.xcb_grab_key_checked(
            self._conn, 1, self._root, modifiers, keycode, _GRAB_ASYNC, _GRAB_ASYNC
        )
        error = lib.xcb_request_check(self._conn, cookie)
        if not error:
            return True
        code = error.contents.error_code
        self._libc.free(error)
        if code != BAD_ACCESS:
            log.warning("X11 refused a hotkey (error %d)", code)
        return False

    def ungrab(self, keycode: int, modifiers: int) -> None:
        self._lib.xcb_ungrab_key(self._conn, keycode, self._root, modifiers)
        self._lib.xcb_flush(self._conn)

    def fileno(self) -> int:
        return int(self._lib.xcb_get_file_descriptor(self._conn))

    def events(self) -> list[tuple[int, int, int, int]]:
        found: list[tuple[int, int, int, int]] = []
        while True:
            event = self._lib.xcb_poll_for_event(self._conn)
            if not event:
                return found
            key = _KeyEvent.from_address(event)
            kind = key.response_type & 0x7F
            if kind in (KEY_PRESS, KEY_RELEASE):
                found.append((kind, key.detail, key.state, key.time))
            self._libc.free(event)

    def broken(self) -> bool:
        return bool(self._lib.xcb_connection_has_error(self._conn))

    def close(self) -> None:
        if self._conn:
            self._lib.xcb_disconnect(self._conn)
            self._conn = None
