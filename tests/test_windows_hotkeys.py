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
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    GlobalHotkeys,
    combination,
    registered,
)

Q, W, SEVEN = "ctrl+alt+shift+q", "ctrl+alt+shift+w", "ctrl+alt+shift+7"
"""Combinations nothing should be using."""


def wait_for(event: threading.Event) -> bool:
    return event.wait(timeout=5)


def test_a_hotkey_calls_its_binding_on_the_hotkeys_thread() -> None:
    pressed: list[tuple[str, str]] = []
    done = threading.Event()

    def on(key: str) -> None:
        pressed.append((key, threading.current_thread().name))
        done.set()

    hotkeys = GlobalHotkeys({Q: lambda: on("Q"), SEVEN: lambda: on("7")})
    hotkeys.start()
    try:
        hotkeys.post(SEVEN)
        assert wait_for(done)
        assert pressed == [("7", "hotkeys")]
    finally:
        hotkeys.stop()


def test_a_failing_action_doesnt_end_the_hotkeys() -> None:
    done = threading.Event()

    def fails() -> None:
        raise RuntimeError("made up")

    hotkeys = GlobalHotkeys({Q: fails, W: done.set})
    hotkeys.start()
    try:
        hotkeys.post(Q)
        hotkeys.post(W)
        assert wait_for(done)
    finally:
        hotkeys.stop()


def test_stop_ends_the_thread() -> None:
    hotkeys = GlobalHotkeys({Q: lambda: None})
    hotkeys.start()
    hotkeys.stop()
    assert not any(t.name == "hotkeys" and t.is_alive() for t in threading.enumerate())
    hotkeys.stop()  # twice is fine


def test_a_combination_another_app_has_is_reported_as_taken(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = GlobalHotkeys({Q: lambda: None})
    if first.start():
        first.stop()
        pytest.skip("Ctrl+Alt+Shift+Q can't be registered here")
    try:
        second = GlobalHotkeys({Q: lambda: None, W: lambda: None})
        with caplog.at_level("WARNING"):
            assert second.start() == [Q]  # W still registered
        second.stop()
        # the log names which of ours (polyglotic-hq 291: it said "1 hotkey(s)")
        assert "already taken by another app: Ctrl+Alt+Shift+Q" in caplog.text
    finally:
        first.stop()
    time.sleep(0.05)
    again = GlobalHotkeys({Q: lambda: None})
    assert again.start() == []  # free again once the first stopped
    again.stop()


def test_a_combination_is_named_as_windows_writes_it() -> None:
    assert combination("ctrl+alt+l") == "Ctrl+Alt+L"
    assert combination(Q) == "Ctrl+Alt+Shift+Q"
    assert combination("shift+win+page_up") == "Shift+Win+Page Up"
    assert combination("f9") == "F9"


def test_any_key_with_any_modifiers_is_registered_as_windows_takes_it() -> None:
    """polyglotic-hq 567: the learner's own keys, not only Ctrl+Alt with a
    letter."""
    assert registered("ctrl+alt+l") == (MOD_CONTROL | MOD_ALT, 0x4C)
    assert registered("f9") == (0, 0x78)
    assert registered("shift+win+insert") == (MOD_SHIFT | MOD_WIN, 0x2D)


def test_a_modifier_alone_or_a_key_not_kept_isnt_a_hotkey() -> None:
    for bad in ("right_ctrl", "ctrl+win", "Q", "", "ctrl+alt+ä"):
        with pytest.raises(ValueError):
            GlobalHotkeys({bad: lambda: None})
