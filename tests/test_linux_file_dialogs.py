"""The desktop's own file dialogs on Linux, through its portal
(`platform/linux/file_dialogs`, polyglotic-hq 574, decision 0280). The
dialogs themselves open on GitHub's runners, from the packed AppImage
(`.github/workflows/linux-release.yml`)."""

import os

import pytest

from polyglotic_desktop.main import use_file_dialogs
from polyglotic_desktop.platform.linux import file_dialogs


def test_the_portals_theme_unless_one_is_asked_for() -> None:
    assert file_dialogs.theme_to_use({}) == {"QT_QPA_PLATFORMTHEME": "xdgdesktopportal"}
    assert file_dialogs.theme_to_use({"QT_QPA_PLATFORMTHEME": " "}) == {
        "QT_QPA_PLATFORMTHEME": "xdgdesktopportal"
    }
    for asked in ("gtk3", "kde", "xdgdesktopportal", "qt6ct"):  # the learner's own
        assert file_dialogs.theme_to_use({"QT_QPA_PLATFORMTHEME": asked}) == {}


def test_it_is_put_in_the_environment_before_qt_starts() -> None:
    env = {"XDG_CURRENT_DESKTOP": "KDE"}
    assert file_dialogs.use_portal_dialogs(env) == {
        "QT_QPA_PLATFORMTHEME": "xdgdesktopportal"
    }
    assert env == {
        "XDG_CURRENT_DESKTOP": "KDE",
        "QT_QPA_PLATFORMTHEME": "xdgdesktopportal",
    }
    assert file_dialogs.use_portal_dialogs(env) == {}  # asked for now: as it is


def test_the_start_asks_for_it_on_x11_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Linux's `xcb` (decision 0258); Windows and the Mac (None) keep Qt's
    own theme and its native dialogs."""
    # A later native Windows start inherits the process environment. Keep
    # the simulated X11 session's portal theme in this test's mapping.
    env: dict[str, str] = {}
    monkeypatch.setattr(os, "environ", env)
    for platform in (None, "cocoa", "windows"):
        use_file_dialogs(platform)
        assert "QT_QPA_PLATFORMTHEME" not in env
    use_file_dialogs("xcb")
    assert env["QT_QPA_PLATFORMTHEME"] == "xdgdesktopportal"
