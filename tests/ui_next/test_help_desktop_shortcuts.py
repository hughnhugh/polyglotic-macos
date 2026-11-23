"""Help on Linux says how to make a shortcut of the desktop's own that locks,
pauses or hides (polyglotic-hq 546, 570): GNOME's Wayland session gives the
app no hotkey, so a custom shortcut runs the app with --lock and the like,
and the copy that runs does it."""

import sys

import pytest

from polyglotic_desktop.main import shortcut_command
from polyglotic_desktop.ui_next.help_page import desktop_shortcuts, set_up


def test_on_linux_set_up_has_the_desktop_s_own_shortcuts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    topics = set_up(frozenset(), "/home/me/Polyglotic.AppImage")
    title, text = topics[-1]
    assert (title, text) == desktop_shortcuts("/home/me/Polyglotic.AppImage")
    assert "/home/me/Polyglotic.AppImage --lock" in text
    assert "--pause" in text and "--hide" in text
    monkeypatch.setattr(sys, "platform", "win32")
    assert len(set_up(frozenset())) == len(topics) - 1  # Windows has hotkeys


def test_the_command_is_the_appimage_s_own_path() -> None:
    assert shortcut_command({"APPIMAGE": "/home/me/Polyglotic.AppImage"}) == (
        "/home/me/Polyglotic.AppImage"
    )
    spaced = shortcut_command({"APPIMAGE": "/home/me/My Apps/Polyglotic.AppImage"})
    assert spaced == '"/home/me/My Apps/Polyglotic.AppImage"'
    assert shortcut_command({}) == f"{sys.executable} -m polyglotic_desktop.main"
