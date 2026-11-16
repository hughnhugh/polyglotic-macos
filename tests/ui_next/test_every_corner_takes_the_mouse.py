"""Every pixel of an unlocked caption window takes the mouse - its very
corners too (the user, 2026-11-16, polyglotic-hq 398: "sometimes I can't
modify caption window size").

Windows passes the mouse through a translucent window's pixels that have
no alpha at all. The panel's rounded corners left the outer third of each
corner's resize zone bare, so a press on a window's very corner reached
the app underneath (measured on a private desktop: 68 of each corner's
100 pixels reached the window, 100 after the fix). Here, offscreen, what
the window paints at its corners stands in for Windows' hit test."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_joined_window import THREE, joined

from polyglotic_desktop.ui.recorded_captions import MIC
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import CORNER_ZONE, Rect


def corner_alphas(window: QWidget) -> list[int]:
    """The alpha of each pixel in each corner's resize zone, as painted."""
    image = window.grab().toImage()
    w, h = image.width(), image.height()
    return [
        image.pixelColor(cx - x if cx else x, cy - y if cy else y).alpha()
        for cx in (0, w - 1)
        for cy in (0, h - 1)
        for x in range(CORNER_ZONE)
        for y in range(CORNER_ZONE)
    ]


def test_an_unlocked_window_s_corners_take_the_mouse_and_a_locked_one_s_dont(
    qapp: QApplication,
) -> None:
    window = window_of(qapp)
    try:
        assert min(corner_alphas(window)) > 0  # nothing bare in a corner
        window.set_locked(True)
        qapp.processEvents()
        assert min(corner_alphas(window)) == 0  # as it was: clicks pass anyway
        window.set_locked(False)
        qapp.processEvents()
        assert min(corner_alphas(window)) > 0
    finally:
        window.close()


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    store = {"apps": [name for name, _ in THREE], "targets": ["en"]}
    from tests.ui.fakes import MemorySettingsStore

    made = CaptionWindows(
        MemorySettingsStore(store), MIC, lambda: [Rect(0, 0, 1920, 1040)]
    )
    made.set_captioned(THREE)
    yield made
    made.close()


def test_a_joined_window_s_corners_take_the_mouse(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.join()
    window = joined(windows)
    qapp.processEvents()
    assert min(corner_alphas(window)) > 0
