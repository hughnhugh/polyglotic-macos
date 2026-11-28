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
    LLKHF_INJECTED,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    VK_KEYS,
    WM_KEYDOWN,
    WM_KEYUP,
    GlobalHotkeys,
    HookEntry,
    LowLevelMatcher,
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


def test_refused_registration_falls_back_to_low_level_hook_and_swallows_only_our_chord() -> (
    None
):
    """966: when RegisterHotKey is refused for one chord, GlobalHotkeys falls
    back to WH_KEYBOARD_LL, fires our action, swallows ONLY that chord, and
    passes every other key on."""
    fired: list[str] = []
    done = threading.Event()
    hooks_installed: list[object] = []
    hooks_removed: list[int] = []
    held_vks: set[int] = set()

    def register(hid: int, mods: int, vk: int) -> bool:
        del hid, mods
        return vk != VK_KEYS["p"]  # pretend another program holds Ctrl+Alt+P

    def on_pause() -> None:
        fired.append("pause")
        done.set()

    def install_hook(proc: object) -> int:
        hooks_installed.append(proc)
        return 42

    hotkeys = GlobalHotkeys(
        {"ctrl+alt+l": lambda: fired.append("lock"), "ctrl+alt+p": on_pause},
        register_hotkey=register,
        unregister_hotkey=lambda _hid: None,
        install_hook=install_hook,
        remove_hook=hooks_removed.append,
        key_down=lambda vk: vk in held_vks,
    )
    taken = hotkeys.start()
    try:
        assert taken == ["ctrl+alt+p"]
        assert hotkeys.hooked == ["ctrl+alt+p"]
        assert len(hooks_installed) == 1

        # Unrelated keys and bare P pass straight through without firing.
        assert not hotkeys.simulate_hook(WM_KEYDOWN, VK_KEYS["a"])
        assert not hotkeys.simulate_hook(WM_KEYDOWN, VK_KEYS["p"])
        held_vks.update({0x11, 0x12})  # Ctrl + Alt held
        assert not hotkeys.simulate_hook(WM_KEYDOWN, VK_KEYS["x"])
        # Injected Ctrl+Alt+P passes through without firing.
        assert not hotkeys.simulate_hook(WM_KEYDOWN, VK_KEYS["p"], LLKHF_INJECTED)
        assert fired == []

        # Real Ctrl+Alt+P fires our action AND swallows ONLY our chord.
        assert hotkeys.simulate_hook(WM_KEYDOWN, VK_KEYS["p"]) is True
        assert wait_for(done)
        assert fired == ["pause"]
        # Key auto-repeat while held stays swallowed and does not double-fire.
        assert hotkeys.simulate_hook(WM_KEYDOWN, VK_KEYS["p"]) is True
        time.sleep(0.03)
        assert fired == ["pause"]
        # Releasing P swallows the paired keyup and re-arms the chord.
        assert hotkeys.simulate_hook(WM_KEYUP, VK_KEYS["p"]) is True
        # Releasing modifiers is never swallowed.
        assert hotkeys.simulate_hook(WM_KEYUP, 0x11) is False
    finally:
        hotkeys.stop()
    assert hooks_removed == [42]


def test_everywhere_typing_key_uses_passthrough_hook_and_never_swallows() -> None:
    """966: a typing key set to Everywhere runs our action via WH_KEYBOARD_LL
    and ALWAYS passes the key on to the foreground app (never registers with
    RegisterHotKey, never swallows)."""
    registered_vks: list[int] = []
    fired = threading.Event()

    def record_register(_hid: int, _mods: int, vk: int) -> bool:
        registered_vks.append(vk)
        return True

    hotkeys = GlobalHotkeys(
        {"space": fired.set},
        passthrough={"space"},
        register_hotkey=record_register,
        unregister_hotkey=lambda _hid: None,
        install_hook=lambda _proc: 99,
        remove_hook=lambda _h: None,
        key_down=lambda _vk: False,
    )
    taken = hotkeys.start()
    try:
        assert taken == []
        assert hotkeys.hooked == []  # not a refused fallback
        assert registered_vks == []  # RegisterHotKey was NEVER called for Space
        assert hotkeys.simulate_hook(WM_KEYDOWN, VK_KEYS["space"]) is False
        assert wait_for(fired)
        assert hotkeys.simulate_hook(WM_KEYUP, VK_KEYS["space"]) is False
    finally:
        hotkeys.stop()


def test_low_level_matcher_and_probe_handle_punctuation_and_media_keys() -> None:
    for name in ("comma", "minus", "slash", "media_play", "volume_up"):
        mods, vk = registered(name)
        assert mods == 0 and vk == VK_KEYS[name]
    matcher = LowLevelMatcher(
        [HookEntry(7, "media_play", 0, VK_KEYS["media_play"], True)],
        key_down=lambda _vk: False,
    )
    assert matcher.handle(WM_KEYDOWN, VK_KEYS["media_play"]) == (7, True)
    assert matcher.handle(WM_KEYUP, VK_KEYS["media_play"]) == (None, True)
    busy_vks = {VK_KEYS["f9"]}
    unregistered: list[int] = []
    hotkeys = GlobalHotkeys(
        {"ctrl+alt+l": lambda: None},
        register_hotkey=lambda _hid, _mods, vk: vk not in busy_vks,
        unregister_hotkey=unregistered.append,
    )
    assert hotkeys.probe(["f9", "f10", "ctrl+alt+shift+l"]) == ["f9"]
    assert len(unregistered) == 2
