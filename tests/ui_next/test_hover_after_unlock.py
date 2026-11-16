"""The hover band comes with the mouse even when Windows loses its arrival
(the user's live testing, polyglotic-hq 272: "Sometimes when locking and
unlocking screens it leads to bugs where hovering the screen doesn't reveal
top settings bar in captioning window").

Locking Windows switches to another desktop; Qt's windows plugin can be
left believing the mouse is still over the window it was over, so no
enter (and no leave) reaches it again. A mouse move still does: a move
over a window not hovered counts as the mouse coming over it, and a
hovered window checks the mouse is still there. Offscreen: the events are
sent by hand, as Windows would after an unlock - no enter event first."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import _mouse, window_of
from tests.ui_next.test_joined_window import THREE, areas, joined, mouse

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import STILL_OVER_MS, CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp)
    yield shown
    shown.close()


def test_a_move_without_an_enter_shows_the_band(window: CaptionWindow) -> None:
    assert not window.hovered and not window.band_shown
    _mouse(window, "move", QPointF(window.width() / 2, window.height() / 2))
    assert window.hovered and window._band_in.isActive()
    window._band_in.timeout.emit()
    assert window.band_shown


def test_a_lost_leave_is_found_and_the_band_goes(window: CaptionWindow) -> None:
    _mouse(window, "move", QPointF(60, 60))
    window._band_in.timeout.emit()
    assert window._still_over.isActive()
    assert window._still_over.interval() == STILL_OVER_MS == 250
    window.pointer = lambda: window.geometry().center()
    window._still_over.timeout.emit()
    assert window.hovered  # still over it: nothing changes
    window.pointer = lambda: window.geometry().bottomRight() + QPoint(40, 40)
    window._still_over.timeout.emit()  # gone, and Qt never said so
    assert not window._still_over.isActive() and window._band_out.isActive()
    window._band_out.timeout.emit()
    assert not window.band_shown and not window.hovered


def test_a_locked_window_never_shows_its_band_on_a_move(window: CaptionWindow) -> None:
    window.set_locked(True)
    _mouse(window, "move", QPointF(60, 60))
    assert not window.hovered and not window._band_in.isActive()


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, areas)
    found.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
    found.set_captioned(THREE)
    found.join()
    qapp.processEvents()
    yield found
    found.close()


def test_a_joined_window_shows_its_bands_on_a_move_over_a_column(
    windows: CaptionWindows,
) -> None:
    window = joined(windows)
    column = window.columns[1]
    assert not column.hovered
    mouse(column, "move", QPointF(40, 60))
    assert all(c.hovered for c in window.columns)
    window._band_in.timeout.emit()
    assert window.band_shown and all(c.band_shown for c in window.columns)
    window.pointer = lambda: window.geometry().topLeft() - QPoint(50, 50)
    window._still_over.timeout.emit()  # left, unheard
    window._band_out.timeout.emit()
    assert not window.band_shown and not any(c.hovered for c in window.columns)
