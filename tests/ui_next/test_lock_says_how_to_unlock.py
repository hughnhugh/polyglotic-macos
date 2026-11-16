"""A locked caption window says how to unlock it - with the hotkey as it is
now - for a few seconds on locking, then faintly in its corner (the user's
rehearsal feedback F10, polyglotic-hq 249, 2026-11-08: "if you press the
lock button there should be directive to know how to unlock")."""

import sys
from collections.abc import Iterator

import pytest
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.test_caption_window import Clock, window_of

from polyglotic_desktop.main import shortcut_text, wire_caption_windows
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_window import LOCKED_SEC, locked_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect

LOCK_KEYS = "⌥⌘L" if sys.platform == "darwin" else "Ctrl+Alt+L"
"""Qt's Ctrl+Alt+L as the OS writes it: on a Mac Qt's Ctrl is Command,
written ⌥⌘L there (polyglotic-hq 420: the first Mac run of the suite)."""


def test_on_locking_it_says_the_hotkey_then_stops(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    window = window_of(qapp)
    try:
        window.set_locked(True)
        assert window.notice.isVisible()
        assert window.notice.text() == "Locked - Ctrl+Alt+L to unlock"
        clock.now += LOCKED_SEC + 0.1
        window._tick()
        assert not window.notice.isVisible()
        window.set_unlock_keys("Ctrl+Shift+K")
        window.set_locked(False)
        window.set_locked(True)
        assert window.notice.text() == "Locked - Ctrl+Shift+K to unlock"
    finally:
        window.close()


def test_without_the_hotkey_it_says_where_else_to_unlock() -> None:
    assert locked_text("") == "Locked - unlock on Home or from the tray"


def test_while_locked_its_corner_shows_the_hotkey(qapp: QApplication) -> None:
    window = window_of(qapp)
    try:
        corner = window.canvas.rect().adjusted(
            window.canvas.width() - 120, window.canvas.height() - 14, 0, 0
        )
        unlocked = window.canvas.grab(corner).toImage()
        window.set_locked(True)
        locked = window.canvas.grab(corner).toImage()
        assert locked != unlocked  # the lock and "Ctrl+Alt+L", faintly
        window.set_locked(False)
        assert window.canvas.grab(corner).toImage() == unlocked
    finally:
        window.close()


@pytest.fixture
def wired(qapp: QApplication) -> Iterator[tuple[DesktopApp, CaptionWindows]]:
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    windows.set_captioned([("Web Browser", APP)])
    yield desktop, windows
    windows.close()
    desktop.close()


def test_the_windows_say_the_app_s_hotkey_and_none_once_taken(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    (window,) = windows.windows.values()
    assert window.unlock_keys == LOCK_KEYS
    desktop.hotkeys_taken(["L"])  # another app has it
    assert window.unlock_keys == ""
    desktop.lock_windows.setChecked(True)
    assert window.notice.text() == "Locked - unlock on Home or from the tray"


def test_a_shortcut_as_the_os_writes_it(qapp: QApplication) -> None:
    action = QAction()
    assert shortcut_text(action) == ""
    action.setShortcut(QKeySequence("Ctrl+Alt+L"))
    assert shortcut_text(action) == LOCK_KEYS
