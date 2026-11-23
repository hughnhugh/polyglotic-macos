"""A locked window's corner that keeps taking the mouse (polyglotic-hq 570,
DECISIONS #243 item 6): on a Wayland desktop the app, an X11 program,
can't read the mouse over another app's window, so the lock's corner is a
small window of its own. The mouse is heard arriving there, never leaving
(GNOME's XWayland says nothing when it goes), so Unlock shows as it
arrives and goes a few seconds after it was last heard; where the mouse
was last read doesn't count. The rest of the window still lets every
click through. The real compositor's side is
`tools/app_tour.py`'s unlocking checks on GitHub's runners (570)."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.test_joined_window import SECOND_APP

from polyglotic_desktop.main import follow_unlock_spot, wire_caption_windows
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.unlock_spot import (
    CATCH_AT_LEAST,
    CAUGHT_SHOW_SEC,
    REST_LOOKS,
)
from polyglotic_desktop.ui_next.views.placement import Rect

THROUGH = Qt.WindowType.WindowTransparentForInput


@pytest.fixture
def wired(qapp: QApplication) -> Iterator[tuple[DesktopApp, CaptionWindows]]:
    """The windows as `main` wires them where the OS can't read the mouse over
    another app (`OsAdapters.unlock_spot`)."""
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    follow_unlock_spot(windows, desktop)
    windows.set_captioned([("Web Browser", APP)])
    (window,) = windows.windows.values()
    window.show()
    qapp.processEvents()
    yield desktop, windows
    windows.close()
    desktop.close()


def only(windows: CaptionWindows) -> CaptionWindow:
    (window,) = windows.windows.values()
    return window


def look(window: CaptionWindow, times: int) -> None:
    for _ in range(times):
        window.unlock_spot.look()


def arrive(widget: QWidget) -> None:
    """The mouse arriving on `widget`, as Qt hears it from the X server."""
    QApplication.sendEvent(
        widget, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5))
    )


def move_on(widget: QWidget) -> None:
    QApplication.sendEvent(
        widget,
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(6, 6),
            QPointF(6, 6),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


def test_locked_its_corner_is_a_window_that_takes_the_mouse(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    window = only(windows)
    assert window.unlock_spot.catcher is None  # unlocked: nothing
    desktop.lock_windows.setChecked(True)
    catcher = window.unlock_spot.catcher
    assert catcher is not None and catcher.isWindow() and catcher.isVisible()
    assert not catcher.windowFlags() & THROUGH  # it takes the mouse
    assert window.windowFlags() & THROUGH  # the rest lets clicks through
    corner = window._lock_spot()
    assert corner is not None
    assert catcher.geometry().contains(corner)
    assert catcher.width() >= CATCH_AT_LEAST[0]
    assert catcher.height() >= CATCH_AT_LEAST[1]
    assert window.geometry().contains(catcher.geometry())
    assert catcher.geometry().bottomRight() == window.geometry().bottomRight()
    desktop.lock_windows.setChecked(False)
    assert not catcher.isVisible()


def test_a_mouse_read_where_it_last_was_never_offers_unlock(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    """Over another app's window the X server still says the last place it
    knew - the corner, if the mouse left through it. Not on the corner's own
    window, that place doesn't count: no Unlock left showing over a game."""
    desktop, windows = wired
    window = only(windows)
    desktop.lock_windows.setChecked(True)
    corner = window._lock_spot()
    assert corner is not None
    window.pointer = corner.center
    look(window, 3 * REST_LOOKS)
    assert not window.unlock_spot.shown


def test_the_mouse_arriving_on_the_corner_offers_unlock_for_a_while(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    window = only(windows)
    now = [100.0]
    window.unlock_spot.clock = lambda: now[0]
    desktop.lock_windows.setChecked(True)
    catcher = window.unlock_spot.catcher
    assert catcher is not None
    arrive(catcher)
    button = window.unlock_spot.button
    assert window.unlock_spot.shown and button is not None
    assert window.geometry().contains(button.geometry())  # over its corner
    now[0] += CAUGHT_SHOW_SEC - 0.5
    look(window, 1)
    assert window.unlock_spot.shown
    move_on(button)  # heard on Unlock: it stays
    now[0] += CAUGHT_SHOW_SEC - 0.5
    look(window, 1)
    assert window.unlock_spot.shown
    now[0] += 1.0  # nothing heard since: gone, wherever the mouse was last read
    look(window, 1)
    assert not window.unlock_spot.shown
    assert desktop.lock_windows.isChecked()
    move_on(catcher)  # back on the corner: shown again
    assert window.unlock_spot.shown


def test_a_click_on_the_corner_offers_unlock_at_once(
    wired: tuple[DesktopApp, CaptionWindows], qapp: QApplication
) -> None:
    from PySide6.QtTest import QTest

    desktop, windows = wired
    window = only(windows)
    desktop.lock_windows.setChecked(True)
    catcher = window.unlock_spot.catcher
    assert catcher is not None
    QTest.mouseClick(catcher, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    button = window.unlock_spot.button
    assert window.unlock_spot.shown and button is not None
    button.click()
    assert not desktop.lock_windows.isChecked() and not window.locked
    assert not catcher.isVisible()


def test_the_setting_off_takes_the_corner_back(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    window = only(windows)
    desktop.lock_windows.setChecked(True)
    assert window.unlock_spot.catcher is not None
    desktop.settings.update(unlock_spot=False)
    assert not windows.unlock_spot
    assert not window.unlock_spot.catcher.isVisible()
    corner = window._lock_spot()
    assert corner is not None
    window.pointer = lambda: QPoint(5, 5)
    look(window, 1)
    window.pointer = corner.center  # read anywhere again, as on Windows
    look(window, REST_LOOKS)
    assert window.unlock_spot.shown
    desktop.settings.update(unlock_spot=True)
    assert window.unlock_spot.catcher.isVisible()


def test_where_the_mouse_is_read_anywhere_no_corner_is_kept(
    qapp: QApplication,
) -> None:
    """Windows, a Mac, an Xorg session: `main` doesn't follow the setting,
    and a locked window takes no mouse at all."""
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    windows.set_captioned([("Web Browser", APP)])
    try:
        window = only(windows)
        window.show()
        desktop.lock_windows.setChecked(True)
        assert not windows.unlock_spot
        assert window.unlock_spot.catcher is None
    finally:
        windows.close()
        desktop.close()


def test_a_window_made_later_catches_too(
    wired: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = wired
    desktop.lock_windows.setChecked(True)
    windows.set_captioned([("Web Browser", APP), ("Player", SECOND_APP)])
    assert len(windows.windows) == 2
    for window in windows.windows.values():
        assert window.unlock_spot.catching
