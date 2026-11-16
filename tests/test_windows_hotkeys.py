"""System-wide hotkeys (platform.windows.hotkeys), without pressing a key.

The hotkeys' thread is sent `WM_HOTKEY` the way Windows sends it when a
combination is pressed, so nothing is typed into whatever has the
keyboard. Registration is tried with Ctrl+Alt+Shift+Q - a combination
nothing should be using - held for a moment only."""

import sys
import threading
import time

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.platform.windows.hotkeys import (
    CTRL_ALT,
    MOD_SHIFT,
    GlobalHotkeys,
    combination,
)

UNUSUAL = CTRL_ALT | MOD_SHIFT


def wait_for(event: threading.Event) -> bool:
    return event.wait(timeout=5)


def test_a_hotkey_calls_its_binding_on_the_hotkeys_thread() -> None:
    pressed: list[tuple[str, str]] = []
    done = threading.Event()

    def on(key: str) -> None:
        pressed.append((key, threading.current_thread().name))
        done.set()

    hotkeys = GlobalHotkeys(
        {"Q": lambda: on("Q"), "7": lambda: on("7")}, modifiers=UNUSUAL
    )
    hotkeys.start()
    try:
        hotkeys.post("7")
        assert wait_for(done)
        assert pressed == [("7", "hotkeys")]
    finally:
        hotkeys.stop()


def test_a_failing_action_doesnt_end_the_hotkeys() -> None:
    done = threading.Event()

    def fails() -> None:
        raise RuntimeError("made up")

    hotkeys = GlobalHotkeys({"Q": fails, "W": done.set}, modifiers=UNUSUAL)
    hotkeys.start()
    try:
        hotkeys.post("Q")
        hotkeys.post("W")
        assert wait_for(done)
    finally:
        hotkeys.stop()


def test_stop_ends_the_thread() -> None:
    hotkeys = GlobalHotkeys({"Q": lambda: None}, modifiers=UNUSUAL)
    hotkeys.start()
    hotkeys.stop()
    assert not any(t.name == "hotkeys" and t.is_alive() for t in threading.enumerate())
    hotkeys.stop()  # twice is fine


def test_a_combination_another_app_has_is_reported_as_taken(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = GlobalHotkeys({"Q": lambda: None}, modifiers=UNUSUAL)
    if first.start():
        first.stop()
        pytest.skip("Ctrl+Alt+Shift+Q can't be registered here")
    try:
        second = GlobalHotkeys({"Q": lambda: None, "W": lambda: None}, UNUSUAL)
        with caplog.at_level("WARNING"):
            assert second.start() == ["Q"]  # W still registered
        second.stop()
        # the log names which of ours (polyglotic-hq 291: it said "1 hotkey(s)")
        assert "already taken by another app: Ctrl+Alt+Shift+Q" in caplog.text
    finally:
        first.stop()
    time.sleep(0.05)
    again = GlobalHotkeys({"Q": lambda: None}, modifiers=UNUSUAL)
    assert again.start() == []  # free again once the first stopped
    again.stop()


def test_a_combination_is_named_as_windows_writes_it() -> None:
    assert combination(CTRL_ALT, "L") == "Ctrl+Alt+L"
    assert combination(UNUSUAL, "Q") == "Ctrl+Alt+Shift+Q"


def test_keys_are_one_letter_or_digit() -> None:
    for bad in ("q", "F1", "", "Ä"):
        with pytest.raises(ValueError):
            GlobalHotkeys({bad: lambda: None})
