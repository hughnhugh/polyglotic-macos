"""Dictation's key and typing on Windows (platform.windows.hotkeys.HoldKey,
platform.windows.text_input), without pressing or typing anything.

A registered key's thread is sent `WM_HOTKEY` as Windows sends it when the
key goes down, and every key's state is read from a stand-in keyboard, so
nothing is pressed and nothing reaches whatever has the keyboard;
registration is tried with Ctrl+Alt+Shift+Pause - a combination nothing
should be using - held for a moment only. A key held alone (Right Ctrl,
Ctrl+Win; polyglotic-hq 289) is read from the stand-in alone. Typing's
events are built and checked, never sent."""

import ctypes
import sys
import threading
import time
from collections.abc import Callable, Sized

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.core.listening.dictation_keys import KEYS, LONE_MODIFIERS
from polyglotic_desktop.platform.windows.hotkeys import (
    LONE_VKS,
    VK_KEYS,
    HoldKey,
)
from polyglotic_desktop.platform.windows.text_input import (
    INPUT,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    keyboard_window,
    type_text,
    unicode_events,
)

UNUSUAL = "ctrl+alt+shift+pause"
"""A combination nothing should be using, registered for a moment only."""
CTRL, ALT, SHIFT, PAUSE = 0x11, 0x12, 0x10, 0x13
RIGHT_CTRL, LEFT_CTRL, LWIN, C = 0xA3, 0xA2, 0x5B, 0x43


class Keys:
    """A stand-in keyboard: the keys down, as `GetAsyncKeyState` would say."""

    def __init__(self) -> None:
        self.down: set[int] = set()
        self.read: set[int] = set()

    def __call__(self, vk: int) -> bool:
        self.read.add(vk)
        return vk in self.down


class Calls:
    def __init__(self) -> None:
        self.said: list[str] = []
        self.event = threading.Event()

    def __call__(self, what: str) -> Callable[[], None]:
        def call() -> None:
            self.said.append(what)
            self.event.set()

        return call

    def wait_for(self, *said: str) -> None:
        deadline = time.monotonic() + 5
        while self.said != list(said) and time.monotonic() < deadline:
            time.sleep(0.005)
        assert self.said == list(said)


def held_alone(key: str, keys: Keys, calls: Calls) -> HoldKey:
    hold = HoldKey(
        key, calls("down"), calls("up"), calls("other"), key_down=keys, poll=0.002
    )
    assert hold.held_alone and hold.start()  # never another program's
    return hold


def test_a_combination_says_when_it_goes_down_and_when_any_of_its_keys_comes_up() -> (
    None
):
    keys, calls = Keys(), Calls()
    key = HoldKey(UNUSUAL, calls("down"), calls("up"), key_down=keys)
    if not key.start():
        pytest.skip("Ctrl+Alt+Shift+Pause can't be registered here")
    try:
        keys.down = {CTRL, ALT, SHIFT, PAUSE}
        key.post()  # Windows' word that the whole combination went down
        calls.wait_for("down")
        time.sleep(0.1)
        assert calls.said == ["down"]  # still held
        keys.down.discard(SHIFT)  # one of its keys let go: the hold ends
        calls.wait_for("down", "up")
        assert keys.read == {CTRL, ALT, SHIFT, PAUSE}  # its own keys, nothing else
    finally:
        key.stop()


def test_repeated_wm_hotkey_while_held_stays_one_hold() -> None:
    """Real keyboards send repeated WM_HOTKEY notifications while a key is held
    (651): they must not queue extra down/up pairs after release."""
    keys, calls = Keys(), Calls()
    key = HoldKey(
        UNUSUAL, calls("down"), calls("up"), key_down=keys, poll=0.005, release_polls=3
    )
    if not key.start():
        pytest.skip("Ctrl+Alt+Shift+Pause can't be registered here")
    try:
        keys.down = {CTRL, ALT, SHIFT, PAUSE}
        key.post()
        calls.wait_for("down")
        for _ in range(6):
            key.post()
            time.sleep(0.01)
        assert calls.said == ["down"]
        keys.down.clear()
        calls.wait_for("down", "up")
        time.sleep(0.06)
        assert calls.said == ["down", "up"]
    finally:
        key.stop()


def test_a_brief_async_key_state_drop_does_not_split_a_hold() -> None:
    """A single false poll from GetAsyncKeyState mid-hold must not end the hold
    early (651); release requires consecutive up polls."""
    calls = Calls()
    polls = 0
    released = threading.Event()

    def flaky_key_down(vk: int) -> bool:
        nonlocal polls
        if released.is_set():
            return False
        if vk == PAUSE:
            polls += 1
            # Drop one poll every 4 polls while still held
            return polls % 4 != 0
        return True

    key = HoldKey(
        UNUSUAL,
        calls("down"),
        calls("up"),
        key_down=flaky_key_down,
        poll=0.005,
        release_polls=3,
    )
    if not key.start():
        pytest.skip("Ctrl+Alt+Shift+Pause can't be registered here")
    try:
        key.post()
        calls.wait_for("down")
        time.sleep(0.08)
        assert calls.said == ["down"]
        released.set()
        calls.wait_for("down", "up")
    finally:
        key.stop()


def test_stop_ends_the_key_even_while_held() -> None:
    down = threading.Event()
    key = HoldKey(UNUSUAL, down.set, lambda: None, key_down=lambda _vk: True)
    if not key.start():
        pytest.skip("Ctrl+Alt+Shift+Pause can't be registered here")
    key.post()
    assert down.wait(5)
    key.stop()  # the stand-in key never comes up
    assert not any(t.name == "hold-key" and t.is_alive() for t in threading.enumerate())


def test_a_key_another_program_has_is_not_ours() -> None:
    first = HoldKey(UNUSUAL, lambda: None, lambda: None)
    if not first.start():
        first.stop()
        pytest.skip("Ctrl+Alt+Shift+Pause can't be registered here")
    try:
        second = HoldKey(UNUSUAL, lambda: None, lambda: None)
        assert not second.start()
        second.stop()
    finally:
        first.stop()


def test_right_ctrl_held_alone_starts_and_ends_dictation() -> None:
    keys, calls = Keys(), Calls()
    key = held_alone("right_ctrl", keys, calls)
    try:
        time.sleep(0.03)
        assert calls.said == []
        keys.down = {RIGHT_CTRL, CTRL}  # Windows says either Ctrl is down too
        calls.wait_for("down")
        keys.down = set()
        calls.wait_for("down", "up")
    finally:
        key.stop()
    assert not any(t.name == "hold-key" and t.is_alive() for t in threading.enumerate())


def test_another_key_with_right_ctrl_is_a_shortcut_not_dictation() -> None:
    keys, calls = Keys(), Calls()
    key = held_alone("right_ctrl", keys, calls)
    try:
        keys.down = {RIGHT_CTRL, CTRL}
        calls.wait_for("down")
        keys.down.add(C)  # Right Ctrl + C: copy
        calls.wait_for("down", "other")
        keys.down.discard(C)
        time.sleep(0.03)  # C let go, Right Ctrl still held: it doesn't start again
        assert calls.said == ["down", "other"]
        keys.down = set()
        calls.wait_for("down", "other", "up")
    finally:
        key.stop()


def test_a_shortcut_begun_before_right_ctrl_never_starts_it() -> None:
    keys, calls = Keys(), Calls()
    key = held_alone("right_ctrl", keys, calls)
    try:
        keys.down = {LEFT_CTRL, CTRL}  # Left Ctrl held...
        time.sleep(0.02)
        keys.down |= {RIGHT_CTRL}  # ...then Right Ctrl: both Ctrls
        time.sleep(0.03)
        keys.down = {RIGHT_CTRL, CTRL}  # Left let go, Right still held
        time.sleep(0.03)
        assert calls.said == []
        keys.down = set()
        time.sleep(0.02)
        keys.down = {RIGHT_CTRL, CTRL}  # a fresh press is dictation
        calls.wait_for("down")
    finally:
        key.stop()
    calls.wait_for("down", "up")  # stopped while held: it ends


def test_modifiers_alone_held_together() -> None:
    keys, calls = Keys(), Calls()
    key = held_alone("ctrl+win", keys, calls)
    try:
        keys.down = {CTRL, LEFT_CTRL}  # Ctrl alone isn't it
        time.sleep(0.03)
        assert calls.said == []
        keys.down.add(LWIN)
        calls.wait_for("down")
        keys.down.discard(CTRL)
        keys.down.discard(LEFT_CTRL)
        calls.wait_for("down", "up")
    finally:
        key.stop()


def test_every_key_a_learner_can_choose_has_its_code() -> None:
    assert set(VK_KEYS) == KEYS
    assert set(LONE_VKS) == set(LONE_MODIFIERS)


def test_a_key_held_alone_costs_little_while_dictation_waits() -> None:
    """Reading one key's state every 15 ms: well under 1% of one core
    (measured with Windows' own call, on a key nobody presses - F24)."""
    key = HoldKey(
        "right_ctrl",
        lambda: None,
        lambda: None,
        key_down=lambda _vk: bool(ctypes.windll.user32.GetAsyncKeyState(0x87) & 0x8000),
    )
    before = time.process_time()
    key.start()
    time.sleep(1.0)
    key.stop()
    assert time.process_time() - before < 0.05  # under 5% at the very worst


def test_text_is_typed_as_unicode_characters_whatever_the_layout() -> None:
    events = unicode_events("a你😀\n")
    units = [0x61, 0x4F60, 0xD83D, 0xDE00, 0x20]  # the emoji's two halves; \n a space
    assert len(events) == 2 * len(units)
    for i, unit in enumerate(units):
        down, up = events[2 * i].u.ki, events[2 * i + 1].u.ki
        assert (down.wVk, down.wScan, down.dwFlags) == (0, unit, KEYEVENTF_UNICODE)
        assert (up.wScan, up.dwFlags) == (unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
    assert len(unicode_events("")) == 0


def test_the_keyboard_window_is_a_handle() -> None:
    assert isinstance(keyboard_window(), int)


def test_the_text_is_sent_in_one_call_and_typed_only_if_all_of_it_was_taken() -> None:
    # Windows' call is stood in for: a test must never type into whatever
    # has the keyboard on the PC.
    calls: list[tuple[int, int, int]] = []

    def all_taken(count: int, events: Sized, size: int) -> int:
        calls.append((count, len(events), size))
        return count

    assert type_text("你好 a", send=all_taken) is True
    assert calls == [(8, 8, ctypes.sizeof(INPUT))]  # four characters, down and up
    assert type_text("abc", send=lambda count, events, size: 0) is False  # blocked
    assert type_text("abc", send=lambda count, events, size: 4) is False  # cut short
    calls.clear()
    assert type_text("", send=all_taken) is True  # nothing to type is no failure
    assert calls == []


def test_inside_a_test_run_nothing_is_typed_without_a_stand_in() -> None:
    assert type_text("this must never reach the keyboard") is False
