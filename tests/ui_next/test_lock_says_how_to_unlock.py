"""A locked caption window says how to unlock it - with the hotkey as it is
now - for a few seconds on locking, then faintly in its corner (the user's
rehearsal feedback F10, polyglotic-hq 249, 2026-11-08: "if you press the
lock button there should be directive to know how to unlock")."""

import sys
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.test_caption_window import Clock, window_of
from tests.ui_next.test_joined_window import THREE

from polyglotic_desktop.main import not_working, shortcut_text, wire_caption_windows
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_window import LOCKED_SEC, lock_tip, locked_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.os_words import hotkeys_here as keys
from polyglotic_desktop.ui_next.os_words import pc_mac_or_linux
from polyglotic_desktop.ui_next.unlock_spot import REST_LOOKS, UnlockSpot
from polyglotic_desktop.ui_next.views.placement import Rect

LOCK_KEYS = "⌥⌘L" if sys.platform == "darwin" else "Ctrl+Alt+L"
"""Qt's Ctrl+Alt+L as the OS writes it: on a Mac Qt's Ctrl is Command,
written ⌥⌘L there (polyglotic-hq 420: the first Mac run of the suite)."""
APP_LOCK_KEYS = "⌃⌘L" if sys.platform == "darwin" else "Ctrl+Alt+L"
"""The app's own lock hotkey as the OS writes it: on a Mac Control+Command
(`DesktopApp`, polyglotic-hq 428)."""
APP_HOTKEYS = (
    "Meta+Ctrl+L, Meta+Ctrl+P, Meta+Ctrl+H, Space"
    if sys.platform == "darwin"
    else "Ctrl+Alt+L, Ctrl+Alt+P, Ctrl+Alt+H, Space"
)
"""The app's hotkeys as the log names them (Qt's portable text): those
with a key - Back to live's too (polyglotic-hq 567)."""
if sys.platform.startswith("linux"):  # Ctrl+Alt+Shift there (570)
    APP_LOCK_KEYS = "Ctrl+Alt+Shift+L"
    APP_HOTKEYS = ", ".join(f"Ctrl+Alt+Shift+{key}" for key in "LPH") + ", Space"
LOCKED_SAID = pc_mac_or_linux(
    "Locked - unlock on Home or from the tray",
    "Locked - unlock on Home or from the menu bar",
    "Locked - unlock on Home",  # GNOME has no tray without an extension (571)
)
"""Where else a locked window unlocks: where the app's icon is, on each OS."""


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
    assert locked_text("") == LOCKED_SAID


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
    assert window.unlock_keys == APP_LOCK_KEYS
    desktop.hotkeys_not_working(["lock"])  # another app has it
    assert window.unlock_keys == ""
    desktop.lock_windows.setChecked(True)
    assert window.notice.text() == LOCKED_SAID


def test_a_shortcut_as_the_os_writes_it(qapp: QApplication) -> None:
    action = QAction()
    assert shortcut_text(action) == ""
    action.setShortcut(QKeySequence("Ctrl+Alt+L"))
    assert shortcut_text(action) == LOCK_KEYS


# -- with no hotkey at all, and from the window itself (polyglotic-hq 398) -------------


def test_hotkeys_never_registered_don_t_work_and_taken_ones_don_t_either() -> None:
    """A preview build registers none (its installed copy has them): before
    398 a locked window still said "Ctrl+Alt+L to unlock", which did
    nothing (the user, 2026-11-16: "ctrl alt l doesn't seem to work on my
    current instance and i can't unlock the caption window")."""
    assert not_working(["L", "P", "H"], {}, []) == ["L", "P", "H"]
    assert not_working(["L", "P", "H"], {"L": 1, "P": 2, "H": 3}, ["P"]) == ["P"]
    assert not_working(["L", "P", "H"], {"L": 1, "P": 2, "H": 3}, []) == []


def test_with_no_hotkey_the_windows_say_where_to_unlock_and_the_log_says_why(
    wired: tuple[DesktopApp, CaptionWindows], caplog: pytest.LogCaptureFixture
) -> None:
    desktop, windows = wired
    (window,) = windows.windows.values()
    with caplog.at_level("WARNING"):
        desktop.hotkeys_not_working(not_working(desktop.hotkeys, {}, []))
    assert f"not working, not shown: {APP_HOTKEYS}" in caplog.text
    assert window.unlock_keys == ""
    assert "rest the mouse on the lock" in window.controls["lock"].toolTip()
    desktop.lock_windows.setChecked(True)
    assert window.notice.text() == LOCKED_SAID


def test_the_lock_button_s_tip_names_the_hotkey_while_it_works(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    _, windows = wired
    (window,) = windows.windows.values()
    assert window.controls["lock"].toolTip().endswith(keys("Ctrl+Alt+L"))
    assert lock_tip("") != lock_tip(keys("Ctrl+Alt+L"))


def rest_on(spot: UnlockSpot, looks: int) -> None:
    for _ in range(looks):
        spot.look()


def test_resting_the_mouse_on_a_locked_window_s_lock_offers_unlock(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    (window,) = windows.windows.values()
    where = [QPoint(5, 5)]
    window.pointer = lambda: where[0]
    desktop.lock_windows.setChecked(True)
    spot = window.unlock_spot
    assert spot.watching
    corner = window._lock_spot()
    assert corner is not None
    assert window.geometry().contains(corner)
    assert corner.bottomRight() == window.geometry().bottomRight()
    rest_on(spot, 1)  # away from it
    where[0] = corner.center()
    rest_on(spot, REST_LOOKS - 1)
    assert not spot.shown  # passing over it isn't enough
    rest_on(spot, 1)
    assert spot.shown and spot.button is not None
    assert spot.button.text() == "Unlock"
    assert window.geometry().contains(spot.button.geometry())  # over its corner
    assert spot.button.isWindow()  # takes clicks: the locked window doesn't
    spot.button.click()
    assert not desktop.lock_windows.isChecked()  # every window unlocked
    assert not window.locked and not spot.shown and not spot.watching


def test_a_mouse_already_on_the_lock_when_it_locks_never_offers_it(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    """A game holding the cursor still where the lock is: never unlocked."""
    desktop, windows = wired
    (window,) = windows.windows.values()
    desktop.lock_windows.setChecked(True)
    corner = window._lock_spot()
    assert corner is not None
    window.pointer = corner.center
    rest_on(window.unlock_spot, 3 * REST_LOOKS)
    assert not window.unlock_spot.shown


def test_leaving_the_lock_hides_unlock_and_hiding_the_window_stops_looking(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    (window,) = windows.windows.values()
    where = [QPoint(5, 5)]
    window.pointer = lambda: where[0]
    desktop.lock_windows.setChecked(True)
    spot = window.unlock_spot
    rest_on(spot, 1)
    corner = window._lock_spot()
    assert corner is not None
    where[0] = corner.center()
    rest_on(spot, REST_LOOKS)
    assert spot.shown
    where[0] = QPoint(5, 5)
    rest_on(spot, 1)
    assert not spot.shown and desktop.lock_windows.isChecked()
    desktop.hide_windows.setChecked(True)
    assert not spot.watching
    desktop.hide_windows.setChecked(False)
    assert spot.watching
    desktop.lock_windows.setChecked(False)
    assert not spot.watching


def test_a_joined_window_offers_unlock_at_its_last_column_s_lock(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({"apps": ["a", "b"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    windows.set_captioned(THREE[:2])
    windows.join()
    joined = windows.joined_window
    try:
        assert joined is not None
        joined.show()
        qapp.processEvents()
        first, last = joined.columns
        desktop.lock_windows.setChecked(True)
        assert first._lock_spot() is None
        corner = last._lock_spot()
        assert corner is not None
        assert corner.bottomRight() == joined.geometry().bottomRight()
        where = [QPoint(5, 5)]
        last.pointer = lambda: where[0]
        rest_on(last.unlock_spot, 1)
        where[0] = corner.center()
        rest_on(last.unlock_spot, REST_LOOKS)
        button = last.unlock_spot.button
        assert button is not None and button.isVisible()
        button.click()
        assert not joined.locked
    finally:
        windows.close()
        desktop.close()
