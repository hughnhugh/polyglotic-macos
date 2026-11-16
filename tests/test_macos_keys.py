"""Esc and clicks elsewhere on a Mac (polyglotic-hq 438;
`platform.macos.keys`): the global monitor's presses read once each, the
mouse held now, nothing kept but Esc, Backspace and the mouse, and the
monitor gone once nobody asks - on any OS with a stand-in for AppKit;
what touches macOS itself is `macos_only`. GitHub's Mac proves it whole
(`tools.macos_full_screen_checks`: escape_cancels, click_elsewhere)."""

import sys
from collections.abc import Callable

import pytest

from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.macos import keys
from polyglotic_desktop.platform.macos.keys import (
    IDLE_SEC,
    KEY_CODES,
    KEY_DOWN,
    LEFT_DOWN,
    OTHER_DOWN,
    RIGHT_DOWN,
    MacKeys,
    pressed_name,
)

A_KEY = 0x00  # kVK_ANSI_A


class StandInAppKit:
    def __init__(self, gives: bool = True) -> None:
        self.heard: Callable[[int, int], None] | None = None
        self.added = 0
        self.removed: list[object] = []
        self.held = False
        self.gives = gives

    def add(self, heard: Callable[[int, int], None]) -> object | None:
        if not self.gives:
            raise OSError("no monitor")
        self.heard = heard
        self.added += 1
        return f"monitor {self.added}"

    def remove(self, monitor: object) -> None:
        self.removed.append(monitor)

    def button_held(self) -> bool:
        return self.held

    def press(self, kind: int, code: int = 0) -> None:
        assert self.heard is not None
        self.heard(kind, code)


class Clock:
    def __init__(self) -> None:
        self.now = 50.0

    def __call__(self) -> float:
        return self.now


def rig() -> tuple[MacKeys, StandInAppKit, Clock]:
    mac, clock = StandInAppKit(), Clock()
    return MacKeys(mac, clock), mac, clock


def test_the_mac_record_reads_esc_and_clicks_elsewhere() -> None:
    """Before 438 the Mac's `keys` was `not_yet.held`: always False."""
    assert isinstance(os_adapters("darwin").keys, MacKeys)


def test_each_press_reads_once_and_the_first_ask_starts_listening() -> None:
    held, mac, _ = rig()
    assert held("escape") is False
    assert mac.added == 1 and held.listening
    mac.press(KEY_DOWN, KEY_CODES["escape"])
    assert held("escape") is True
    assert held("escape") is False  # read: gone, as Windows' "since" bit
    mac.press(LEFT_DOWN)
    mac.press(KEY_DOWN, KEY_CODES["backspace"])
    assert held("mouse") is True
    assert held("backspace") is True
    assert held("mouse") is False
    assert mac.added == 1  # one monitor while it's asked about


@pytest.mark.parametrize("kind", [LEFT_DOWN, RIGHT_DOWN, OTHER_DOWN])
def test_every_button_is_the_mouse(kind: int) -> None:
    assert pressed_name(kind, 0) == "mouse"


def test_no_other_key_is_kept() -> None:
    held, mac, _ = rig()
    held("escape")
    mac.press(KEY_DOWN, A_KEY)
    assert pressed_name(KEY_DOWN, A_KEY) is None
    assert held._pressed == set()
    assert not any(held(name) for name in ("escape", "backspace", "mouse"))


def test_a_button_held_now_is_the_mouse_without_a_press_heard() -> None:
    """A press in the app's own windows never reaches the global monitor."""
    held, mac, _ = rig()
    mac.held = True
    assert held("mouse") is True
    assert held("escape") is False


def test_the_monitor_goes_once_nobody_asks() -> None:
    held, mac, clock = rig()
    held("mouse")
    clock.now += IDLE_SEC + 0.1
    mac.press(KEY_DOWN, KEY_CODES["escape"])  # heard after the asking stopped
    assert mac.removed == ["monitor 1"] and not held.listening
    clock.now += 5
    assert held("escape") is False  # not kept, and listening again
    assert mac.added == 2


def test_a_press_while_asked_about_regularly_is_kept() -> None:
    held, mac, clock = rig()
    for _ in range(100):
        clock.now += 0.04
        held("escape")
    mac.press(KEY_DOWN, KEY_CODES["escape"])
    assert held("escape") is True
    assert mac.removed == []


def test_a_mac_that_gives_no_monitor_reads_nothing_and_stops_asking() -> None:
    mac = StandInAppKit(gives=False)
    held = MacKeys(mac, Clock())
    assert held("escape") is False
    assert held("mouse") is False


def test_an_unknown_name_is_a_mistake() -> None:
    held, _, _ = rig()
    with pytest.raises(KeyError):
        held("space")


@pytest.mark.macos_only
def test_appkits_monitor_comes_and_goes() -> None:
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(["keys"])
    assert sys.platform == "darwin"
    held = MacKeys()
    held("escape")
    assert held.listening
    assert held("mouse") in (True, False)
    held.stop()
    assert not held.listening
    keys._quartz()  # loads
