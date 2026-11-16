"""Dictation's key as the learner chooses it (core.listening.dictation_keys;
polyglotic-hq 289, decision 0081): kept as text, read back, and refused
with why when it can't be dictation's."""

import pytest

from polyglotic_desktop.core.listening.dictation_keys import (
    DEFAULT_KEY,
    DictationKey,
    Modifier,
    Refusal,
    refusal,
)

OWN = [DictationKey.parse(f"ctrl+alt+{k}") for k in "lphw"]
APP_HOTKEYS = [k for k in OWN if k is not None]


@pytest.mark.parametrize("kept", ["insert", "f8", "f9", "f10", "scroll_lock", "pause"])
def test_the_keys_283_offered_still_read_as_themselves(kept: str) -> None:
    key = DictationKey.parse(kept)
    assert key == DictationKey(key=kept)
    assert str(key) == kept and not key.held_alone
    assert refusal(key, APP_HOTKEYS) is None


@pytest.mark.parametrize(
    ("kept", "modifiers", "name"),
    [
        ("ctrl+alt+d", {Modifier.CTRL, Modifier.ALT}, "d"),
        ("ctrl+shift+win+f9", {Modifier.CTRL, Modifier.SHIFT, Modifier.WIN}, "f9"),
        ("right_ctrl", set(), "right_ctrl"),
        ("ctrl+win", {Modifier.CTRL, Modifier.WIN}, None),
    ],
)
def test_a_key_is_kept_as_text_and_read_back(
    kept: str, modifiers: set[Modifier], name: str | None
) -> None:
    key = DictationKey(frozenset(modifiers), name)
    assert str(key) == kept
    assert DictationKey.parse(kept) == key


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "ctrl",  # one modifier on its own has a side
        "alt+ctrl+d",  # out of order
        "ctrl+ctrl+d",
        "ctrl+right_ctrl",  # a side only on its own
        "d+ctrl",
        "ctrl+numpad_0",
        "space bar",
        "f25",
    ],
)
def test_anything_else_is_not_a_key(bad: str) -> None:
    assert DictationKey.parse(bad) is None


def test_right_ctrl_alone_is_the_default_and_held_alone() -> None:
    assert str(DEFAULT_KEY) == "right_ctrl"
    assert DEFAULT_KEY.held_alone
    assert DictationKey.parse("ctrl+win").held_alone  # type: ignore[union-attr]
    assert not DictationKey.parse("ctrl+alt+d").held_alone  # type: ignore[union-attr]
    assert refusal(DEFAULT_KEY, APP_HOTKEYS) is None


@pytest.mark.parametrize(
    ("kept", "why"),
    [
        # keys that type or edit, alone or with Shift
        ("a", Refusal.TYPES),
        ("7", Refusal.TYPES),
        ("space", Refusal.TYPES),
        ("enter", Refusal.TYPES),
        ("backspace", Refusal.TYPES),
        ("left", Refusal.TYPES),
        ("delete", Refusal.TYPES),
        ("shift+a", Refusal.TYPES),
        ("shift+space", Refusal.TYPES),
        # Esc is dictation's own cancel
        ("escape", Refusal.ESCAPE),
        ("shift+escape", Refusal.ESCAPE),
        # Windows keeps them
        ("win+l", Refusal.WINDOWS),
        ("win+h", Refusal.WINDOWS),
        ("ctrl+alt+delete", Refusal.WINDOWS),
        ("ctrl+escape", Refusal.WINDOWS),
        ("ctrl+shift+escape", Refusal.WINDOWS),
        ("left_win", Refusal.WINDOWS),
        ("ctrl+shift", Refusal.WINDOWS),
        ("ctrl+space", Refusal.WINDOWS),
        ("f12", Refusal.WINDOWS),  # the debugger's
        # Alt without Ctrl: Alt+Tab, Alt+F4, and a menu opened on letting go
        ("alt+tab", Refusal.ALT),
        ("alt+f4", Refusal.ALT),
        ("alt+d", Refusal.ALT),
        ("alt+shift", Refusal.ALT),
        ("alt+win", Refusal.ALT),
        # every program's
        ("ctrl+c", Refusal.EVERY_PROGRAM),
        ("ctrl+v", Refusal.EVERY_PROGRAM),
        ("ctrl+1", Refusal.EVERY_PROGRAM),
        ("shift+insert", Refusal.EVERY_PROGRAM),
        # a modifier alone, other than Right Ctrl
        ("left_ctrl", Refusal.MODIFIER),
        ("ctrl+alt", Refusal.MODIFIER),  # AltGr, and every Ctrl+Alt hotkey
        ("right_shift", Refusal.MODIFIER),
        ("right_alt", Refusal.MODIFIER),
        # the app's own hotkeys
        ("ctrl+alt+l", Refusal.APP_HOTKEY),
        ("ctrl+alt+h", Refusal.APP_HOTKEY),
    ],
)
def test_a_key_that_cant_be_dictations_says_why(kept: str, why: Refusal) -> None:
    key = DictationKey.parse(kept)
    assert key is not None
    assert refusal(key, APP_HOTKEYS) is why


@pytest.mark.parametrize(
    "kept",
    [
        "ctrl+alt+d",
        "ctrl+shift+d",
        "ctrl+win",
        "ctrl+shift+win",
        "shift+f9",
        "ctrl+f9",
        "win+f9",
        "menu",
        "f1",
        "ctrl+alt+space",
    ],
)
def test_keys_that_can_be_dictations(kept: str) -> None:
    key = DictationKey.parse(kept)
    assert key is not None
    assert refusal(key, APP_HOTKEYS) is None
