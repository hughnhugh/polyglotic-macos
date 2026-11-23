"""Linux's hotkeys (polyglotic-hq 546's slice 3, 570): X11's key grab where
the session hands it every key, through a fake X server here; the real
grab and a key pressed through the X server are `linux_desktop`
(`.github/workflows/linux.yml`, `tools/linux_hotkey_checks.py`)."""

import os
import sys
import threading
import time
from collections.abc import Callable

import pytest

from polyglotic_desktop.platform.linux import hotkeys
from polyglotic_desktop.platform.linux.hotkeys import (
    CONTROL,
    CTRL_ALT_SHIFT,
    KEY_PRESS,
    KEY_RELEASE,
    LOCK,
    MOD1,
    MOD2,
    MOD4,
    SHIFT,
    HoldCombination,
    NoHotkeys,
    X11Hotkeys,
    combination,
    for_this_session,
    keycode_for,
)
from polyglotic_desktop.platform.linux.shortcut_portal import preferred_trigger

L_CODE, P_CODE, H_CODE = 46, 33, 43
"""Where a US keyboard has L, P and H (X key codes)."""


def us_mapping() -> tuple[int, list[list[int]]]:
    """A US keyboard's map from key code 8: each code's lower and upper case."""
    mapping = [[0, 0] for _ in range(8, 256)]
    for key, code in hotkeys.US_KEYCODES.items():
        mapping[code - 8] = [ord(key.lower()), ord(key.upper())]
    return 8, mapping


class FakeX:
    """`Xcb`: grabs kept, some held by another program, events handed in."""

    def __init__(self, held: set[tuple[int, int]] = frozenset()) -> None:  # type: ignore[assignment]
        self.held = set(held)
        self.grabbed: set[tuple[int, int]] = set()
        self.read_fd, self.write_fd = os.pipe()
        self.waiting: list[tuple[int, int, int, int]] = []
        self.lock = threading.Lock()
        self.closed = False
        self.mapping = us_mapping()

    def keyboard(self) -> tuple[int, list[list[int]]]:
        return self.mapping

    def grab(self, keycode: int, modifiers: int) -> bool:
        if (keycode, modifiers) in self.held:
            return False
        self.grabbed.add((keycode, modifiers))
        return True

    def ungrab(self, keycode: int, modifiers: int) -> None:
        self.grabbed.discard((keycode, modifiers))

    def fileno(self) -> int:
        return self.read_fd

    def press(self, *events: tuple[int, int, int, int]) -> None:
        with self.lock:
            self.waiting.extend(events)
        os.write(self.write_fd, b".")

    def events(self) -> list[tuple[int, int, int, int]]:
        os.read(self.read_fd, 64)
        with self.lock:
            found, self.waiting = self.waiting, []
        return found

    def broken(self) -> bool:
        return False

    def close(self) -> None:
        self.closed = True
        os.close(self.read_fd)
        os.close(self.write_fd)


LPH = {"ctrl+alt+shift+l": "L", "ctrl+alt+shift+p": "P", "ctrl+alt+shift+h": "H"}
"""Linux's own Lock, Pause and Hide (decision 0293), as the settings keep them."""


def started(x: FakeX, calls: list[str]) -> tuple[X11Hotkeys, list[str]]:
    keys = X11Hotkeys(
        {kept: (lambda k=k: calls.append(k)) for kept, k in LPH.items()},  # type: ignore[misc]
        connect=lambda: x,
    )
    return keys, keys.start()


def wait_for(done: Callable[[], bool]) -> None:
    end = time.monotonic() + 5
    while not done() and time.monotonic() < end:
        time.sleep(0.01)


needs_select = pytest.mark.skipif(
    sys.platform == "win32", reason="the hotkeys' thread waits with select() on a pipe"
)


@needs_select
def test_each_key_is_grabbed_with_caps_lock_and_numlock_either_way() -> None:
    x = FakeX()
    keys, taken = started(x, [])
    try:
        assert taken == []
        for code in (L_CODE, P_CODE, H_CODE):
            for extra in (0, LOCK, MOD2, LOCK | MOD2):
                assert (code, CTRL_ALT_SHIFT | extra) in x.grabbed
    finally:
        keys.stop()
    assert x.grabbed == set() and x.closed


@needs_select
def test_a_key_another_program_holds_is_taken_and_none_of_it_kept() -> None:
    """Ctrl+Alt+Shift+P with NumLock on held elsewhere: P isn't ours at all
    (half a combination would work only with NumLock off), L and H are."""
    x = FakeX(held={(P_CODE, CTRL_ALT_SHIFT | MOD2)})
    keys, taken = started(x, [])
    try:
        assert taken == ["ctrl+alt+shift+p"]
        assert not any(code == P_CODE for code, _ in x.grabbed)
        assert (L_CODE, CTRL_ALT_SHIFT) in x.grabbed
    finally:
        keys.stop()


@needs_select
def test_a_press_calls_its_binding_once_however_long_its_held() -> None:
    x = FakeX()
    calls: list[str] = []
    keys, _ = started(x, calls)
    try:
        x.press((KEY_PRESS, L_CODE, CTRL_ALT_SHIFT, 100))
        wait_for(lambda: calls == ["L"])
        # held: X repeats a release and a press at the same moment
        x.press(
            (KEY_RELEASE, L_CODE, CTRL_ALT_SHIFT, 600),
            (KEY_PRESS, L_CODE, CTRL_ALT_SHIFT, 600),
            (KEY_PRESS, L_CODE, CTRL_ALT_SHIFT, 650),  # a repeat with no release
            (KEY_RELEASE, L_CODE, CTRL_ALT_SHIFT, 700),  # let go
            (KEY_PRESS, H_CODE, CTRL_ALT_SHIFT | LOCK | MOD2, 900),  # Caps, NumLock on
            (KEY_PRESS, L_CODE, CTRL_ALT_SHIFT, 1000),  # pressed again
        )
        wait_for(lambda: len(calls) >= 3)
        time.sleep(0.05)
        assert calls == ["L", "H", "L"]
    finally:
        keys.stop()


def test_a_combination_with_other_modifiers_isnt_ours() -> None:
    keys = X11Hotkeys({"ctrl+alt+shift+l": lambda: calls.append("L")}, connect=FakeX)
    calls: list[str] = []
    keys._grabbed[L_CODE, CTRL_ALT_SHIFT] = "ctrl+alt+shift+l"  # as `start` grabs it
    keys.handle(KEY_PRESS, L_CODE, CONTROL | MOD1, 1)  # Ctrl+Alt+L, no Shift
    keys.handle(KEY_PRESS, P_CODE, CTRL_ALT_SHIFT, 2)  # a key not grabbed
    assert calls == []
    keys.handle(KEY_PRESS, L_CODE, CTRL_ALT_SHIFT | MOD2, 3)
    assert calls == ["L"]


@needs_select
def test_speaker_hold_reports_one_press_and_one_release_across_x11_repeats() -> None:
    x = FakeX()
    first, mapping = x.mapping
    f8 = 74
    mapping[f8 - first] = [hotkeys.NAMED_KEYSYMS["f8"]]
    calls: list[str] = []
    held = HoldCombination(
        "f8",
        lambda: calls.append("down"),
        lambda: calls.append("up"),
        lambda: calls.append("other"),
        connect=lambda: x,
    )
    assert held.start()
    try:
        x.press(
            (KEY_PRESS, f8, 0, 100),
            (KEY_RELEASE, f8, 0, 200),
            (KEY_PRESS, f8, 0, 200),
            (KEY_PRESS, f8, 0, 250),
            (KEY_RELEASE, f8, 0, 300),
        )
        wait_for(lambda: calls == ["down", "up"])
        assert calls == ["down", "up"]
    finally:
        held.stop()


def test_wayland_portal_shortcut_is_the_configured_hold_key() -> None:
    assert preferred_trigger("f8") == "F8"
    assert preferred_trigger("ctrl+alt+d") == "CTRL+ALT+d"
    assert preferred_trigger("right_ctrl") is None


def test_a_failing_action_doesnt_end_the_hotkeys() -> None:
    def fails() -> None:
        raise RuntimeError("an action's own bug")

    calls: list[str] = []
    keys = X11Hotkeys(
        {"ctrl+alt+shift+l": fails, "ctrl+alt+shift+p": lambda: calls.append("P")},
        connect=FakeX,
    )
    keys._grabbed.update(
        {
            (L_CODE, CTRL_ALT_SHIFT): "ctrl+alt+shift+l",
            (P_CODE, CTRL_ALT_SHIFT): "ctrl+alt+shift+p",
        }
    )
    keys.handle(KEY_PRESS, L_CODE, CTRL_ALT_SHIFT, 1)
    keys.handle(KEY_PRESS, P_CODE, CTRL_ALT_SHIFT, 2)
    assert calls == ["P"]


def test_no_x_server_is_every_key_not_working_here() -> None:
    def refuse() -> FakeX:
        raise OSError("no X server")

    keys = X11Hotkeys({"ctrl+alt+shift+l": print, "f9": print}, connect=refuse)
    assert keys.start() == ["ctrl+alt+shift+l", "f9"]
    keys.stop()  # nothing to give back


def test_keys_must_be_kept_combinations() -> None:
    for wrong in (
        "L",
        "l",
        "ctrl",
        "ctrl+alt",
        "right_ctrl",
        "alt+ctrl+l",
        "ctrl+alt+lock",
    ):
        with pytest.raises(ValueError):
            X11Hotkeys({wrong: print})


@needs_select
def test_a_kept_combination_is_grabbed_as_it_says() -> None:
    """The hotkeys the learner sets (polyglotic-hq 567): "ctrl+alt+j", "f9",
    "shift+win+p" - each its own modifiers, beside Linux's own."""
    x = FakeX()
    f9_code = 8 + 67  # the kernel's KEY_F9
    x.mapping[1][f9_code - 8] = [hotkeys.NAMED_KEYSYMS["f9"], 0]
    calls: list[str] = []
    keys = X11Hotkeys(
        {
            "ctrl+alt+j": lambda: calls.append("live"),
            "f9": lambda: calls.append("f9"),
            "shift+win+p": lambda: calls.append("win"),
            "ctrl+alt+shift+l": lambda: calls.append("L"),
        },
        connect=lambda: x,
    )
    try:
        assert keys.start() == []
        j_code = hotkeys.US_KEYCODES["J"]
        assert (j_code, CONTROL | MOD1) in x.grabbed
        assert (f9_code, 0) in x.grabbed
        assert (P_CODE, SHIFT | MOD4) in x.grabbed
        assert (L_CODE, CTRL_ALT_SHIFT) in x.grabbed
        x.press(
            (KEY_PRESS, j_code, CONTROL | MOD1 | MOD2, 1),
            (KEY_PRESS, P_CODE, SHIFT | MOD4, 2),
            (KEY_PRESS, j_code, CTRL_ALT_SHIFT, 3),  # Shift too: not its combination
        )
        wait_for(lambda: len(calls) >= 2)
        time.sleep(0.05)
        assert calls == ["live", "win"]
    finally:
        keys.stop()


def test_a_function_key_is_found_by_its_keysym() -> None:
    first, mapping = us_mapping()
    mapping[67] = [hotkeys.NAMED_KEYSYMS["f9"], 0]  # X key code 75
    assert keycode_for("f9", mapping, first) == 75
    assert keycode_for("f10", mapping, first) is None  # not on this keyboard


def test_keys_are_found_by_what_they_type() -> None:
    first, mapping = us_mapping()
    assert keycode_for("L", mapping, first) == L_CODE
    # AZERTY: A and Q swap places; the code that types "a" is found
    azerty = [list(m) for m in mapping]
    q, a = hotkeys.US_KEYCODES["Q"] - 8, hotkeys.US_KEYCODES["A"] - 8
    azerty[q], azerty[a] = azerty[a], azerty[q]
    assert keycode_for("A", azerty, first) == q + 8
    # Russian first, US second: the Latin letter on the second layout
    cyrillic = [[0x6CB, 0x6EB, *m] for m in mapping]
    assert keycode_for("L", cyrillic, first) == L_CODE
    # no Latin letters anywhere: where a US keyboard has it
    assert keycode_for("L", [[0x6CB, 0x6EB]] * 248, first) == L_CODE


def test_combinations_are_written_as_linuxs_desktops_write_them() -> None:
    assert combination(CTRL_ALT_SHIFT, "L") == "Ctrl+Alt+Shift+L"
    assert combination(CONTROL | MOD1, "P") == "Ctrl+Alt+P"
    assert CTRL_ALT_SHIFT == CONTROL | MOD1 | SHIFT


@pytest.mark.parametrize(
    ("environ", "grabbed"),
    [
        ({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, True),
        ({"DISPLAY": ":0"}, True),  # a bare X server
        ({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "XFCE"}, True),
        (
            {
                "XDG_SESSION_TYPE": "wayland",
                "XDG_CURRENT_DESKTOP": "KDE",
                "KDE_SESSION_VERSION": "6",
            },
            True,
        ),
        # Plasma 5.27 hands X11 apps no keys by default (its kwin.kcfg)
        (
            {
                "XDG_SESSION_TYPE": "wayland",
                "XDG_CURRENT_DESKTOP": "KDE",
                "KDE_SESSION_VERSION": "5",
            },
            False,
        ),
        ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, False),
        ({"WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "GNOME"}, False),
    ],
)
def test_the_grab_is_used_where_it_hears_every_app(
    environ: dict[str, str], grabbed: bool
) -> None:
    keys = for_this_session({"ctrl+alt+shift+l": print}, environ)
    assert isinstance(keys, X11Hotkeys) is grabbed
    if not grabbed:
        assert isinstance(keys, NoHotkeys)
        assert keys.start() == ["ctrl+alt+shift+l"]  # not working here: Help says so
