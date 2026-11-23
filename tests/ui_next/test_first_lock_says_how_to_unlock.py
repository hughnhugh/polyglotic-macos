"""The first lock on Linux says at length how to unlock again (polyglotic-hq
546, 570): some Linux desktops have no tray, and GNOME's Wayland session
gives the app no hotkey - so the corner's lock, the hotkey where it works,
and Home. Once: kept in the settings."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.main import tell_how_to_unlock, wire_caption_windows
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import (
    FIRST_LOCKED_SEC,
    LOCKED_SEC,
    first_locked_text,
    locked_text,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect


def made(qapp: QApplication, told: bool = False) -> tuple[DesktopApp, CaptionWindows]:
    store = MemorySettingsStore(
        {"apps": ["Web Browser"], "targets": ["en"], "unlock_told": told}
    )
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    tell_how_to_unlock(windows, desktop)
    windows.set_captioned([("Web Browser", APP)])
    return desktop, windows


@pytest.fixture
def wired(qapp: QApplication) -> Iterator[tuple[DesktopApp, CaptionWindows]]:
    desktop, windows = made(qapp)
    yield desktop, windows
    windows.close()
    desktop.close()


def test_the_first_lock_says_at_length_then_never_again(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    (window,) = windows.windows.values()
    desktop.lock_windows.setChecked(True)
    assert window.notice.text() == first_locked_text(window.unlock_keys)
    assert desktop.settings.value.unlock_told  # kept: never at length again
    assert not windows.tell_how_to_unlock
    desktop.lock_windows.setChecked(False)
    desktop.lock_windows.setChecked(True)
    assert window.notice.text() == locked_text(window.unlock_keys)


def test_it_names_the_hotkey_only_where_it_works(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    (window,) = windows.windows.values()
    desktop.hotkeys_not_working(["lock"])  # GNOME's Wayland session: none
    desktop.lock_windows.setChecked(True)
    said = window.notice.text()
    assert said == first_locked_text("")
    assert "corner" in said and "Home" in said and "tray" not in said
    assert "Ctrl" not in said


def test_told_once_is_told_for_good(qapp: QApplication) -> None:
    desktop, windows = made(qapp, told=True)
    try:
        (window,) = windows.windows.values()
        desktop.lock_windows.setChecked(True)
        assert window.notice.text() == locked_text(window.unlock_keys)
    finally:
        windows.close()
        desktop.close()


def test_it_stays_longer_than_the_lock_s_own_notice() -> None:
    assert FIRST_LOCKED_SEC > 2 * LOCKED_SEC
    assert "{keys}" not in first_locked_text("Ctrl+Alt+Shift+L")
    assert "Ctrl+Alt+Shift+L" in first_locked_text("Ctrl+Alt+Shift+L")
