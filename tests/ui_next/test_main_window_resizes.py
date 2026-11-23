"""Every edge of the main window can make it smaller, and it opens at the
size the learner left it (polyglotic-hq 586; the user, 2026-11-21: "Desktop
client UI can't be resized also, shows the arrows but doesn't let you").

Its minimum was 960 x 680 times the text size, kept to the screen, and it
opened at that minimum from the Normal text size (1.3, decision 0244) up:
on a 2560 x 1440 screen, 1248 x 884 opened and 1248 x 884 was the least
Windows let an edge drag it to (`WM_GETMINMAXINFO`'s track size is Qt's
minimum plus the frame - 586's probe on a private desktop read 1264 x 923
for both). Offscreen: Qt's minimum is what Windows is told."""

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.main_window import (
    FLOOR,
    FRAME,
    SIZE,
    MainWindow,
    minimum_size,
    roomy_size,
)

SCREENS = {
    "2560x1440": QRect(0, 0, 2560, 1392),  # the work area, the taskbar left out
    "1920x1080": QRect(0, 0, 1920, 1032),
    "laptop_150": QRect(0, 0, 1280, 672),  # 1920 x 1080 at 150 %
}


@pytest.mark.parametrize("screen", list(SCREENS))
@pytest.mark.parametrize("app_size", list(style.APP_TEXT_SIZES))
@pytest.mark.parametrize("windows_size", [1.0, 1.5, 2.0])
def test_every_edge_can_make_it_smaller(
    qapp: QApplication, screen: str, app_size: str, windows_size: float
) -> None:
    """At every text size, on a big screen and a laptop's, it opens larger
    than its minimum both ways: no edge shows arrows that move nothing."""
    style.use_text_scale(windows_size)
    style.use_app_text_size(app_size)
    window = MainWindow(QAction("Quit"))
    area = SCREENS[screen]
    window.fit_to(area)
    assert window.minimumWidth() < window.width(), (window.size(), area)
    assert window.minimumHeight() < window.height(), (window.size(), area)
    assert window.width() + FRAME <= area.width()
    assert window.height() + FRAME <= area.height()
    window.keep_in_tray = False
    window.close()


def test_it_opens_as_before_and_can_be_made_as_small_as_the_floor(
    qapp: QApplication,
) -> None:
    """At the default text size on a 2560 x 1440 screen: as large as
    before - a Settings section fits (`roomy_size`) - and as small as
    FLOOR, where every page still fits without a sideways scrollbar."""
    style.use_app_text_size("normal")  # the default
    window = MainWindow(QAction("Quit"))
    window.fit_to(SCREENS["2560x1440"])
    assert (window.width(), window.height()) == roomy_size() == (1248, 884)
    assert (window.minimumWidth(), window.minimumHeight()) == FLOOR
    window.resize(*FLOOR)
    assert (window.width(), window.height()) == FLOOR
    window.resize(400, 300)  # under the minimum: Qt keeps it there
    assert (window.width(), window.height()) == FLOOR
    window.keep_in_tray = False
    window.close()


def test_it_opens_at_the_size_left_kept_to_the_screen(qapp: QApplication) -> None:
    style.use_app_text_size("smaller")
    window = MainWindow(QAction("Quit"))
    area = SCREENS["1920x1080"]
    window.fit_to(area, (1500, 900))
    assert (window.width(), window.height()) == (1500, 900)
    window.fit_to(area, (5000, 3000))  # left on a larger screen
    assert (window.width(), window.height()) == (1880, 992)
    window.fit_to(area, (100, 100))  # never under its minimum
    assert (window.width(), window.height()) == minimum_size()
    window.fit_to(area)  # nothing left: the usual first size
    assert (window.width(), window.height()) == SIZE
    window.keep_in_tray = False
    window.close()


def test_the_size_left_is_kept_for_the_next_start(qapp: QApplication) -> None:
    """Closed to the tray, and at quit (`Interface.close`): saved; the next
    start's first show opens at it."""
    store = MemorySettingsStore()
    built = Built(store)
    try:
        built.hub.show()
        window = built.hub.window
        area = window.screen().availableGeometry()
        wanted = (
            max(window.minimumWidth(), min(window.width(), area.width() - FRAME) - 10),
            max(
                window.minimumHeight(), min(window.height(), area.height() - FRAME) - 10
            ),
        )
        window.resize(*wanted)
        window.keep_in_tray = True  # as `main` has it with a tray
        window.close()  # kept in the tray: hidden, its size saved
        assert built.desktop.settings.value.main_window_size == wanted
    finally:
        built.close()
    again = Built(store)
    try:
        assert again.desktop.settings.value.main_window_size == wanted
        again.hub.show()
        window = again.hub.window
        assert (window.width(), window.height()) == wanted
    finally:
        again.close()
