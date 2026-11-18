"""The mouse over a caption window while the app is in the background, on a
Mac (polyglotic-hq 515): Qt's view on a Mac drops the mouse's moves, arrival
and leaving while the app isn't active, so with a video in front the strip
never showed (GitHub's Mac, 515's run 1). `PointerWatch` tells the window
where the mouse is instead. Offscreen: the mouse's place and the app's
state stand in."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.pointer_watch import POLL_MS, PointerWatch


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp)
    yield shown
    shown.close()


class Mouse:
    def __init__(self) -> None:
        self.at = QPoint(-500, -500)
        self.held = False
        self.active = False


def watch_of(window: CaptionWindow, mouse: Mouse) -> PointerWatch:
    return PointerWatch(
        lambda: [window],
        window,
        pointer=lambda: mouse.at,
        held=lambda: mouse.held,
        active=lambda: mouse.active,
    )


def test_the_mouse_over_a_window_of_a_background_app_shows_its_strip(
    window: CaptionWindow,
) -> None:
    mouse = Mouse()
    watch = watch_of(window, mouse)
    watch.look()
    assert not window.hovered  # not over it yet
    mouse.at = window.geometry().center()
    watch.look()
    assert window.hovered and window._band_in.isActive()
    window._band_in.timeout.emit()
    assert window.band_shown


def test_the_mouse_gone_takes_the_strip_away(window: CaptionWindow) -> None:
    mouse = Mouse()
    watch = watch_of(window, mouse)
    mouse.at = window.geometry().center()
    watch.look()
    window._band_in.timeout.emit()
    mouse.at = window.geometry().bottomRight() + QPoint(60, 60)
    watch.look()
    assert window._band_out.isActive()
    window._band_out.timeout.emit()
    assert not window.band_shown and not window.hovered


def test_it_keeps_out_of_a_press_and_out_of_an_active_app(
    window: CaptionWindow,
) -> None:
    """A press or a drag comes from macOS itself; an active app's mouse
    from Qt."""
    mouse = Mouse()
    watch = watch_of(window, mouse)
    mouse.at, mouse.held = window.geometry().center(), True
    watch.look()
    assert not window.hovered
    mouse.held, mouse.active = False, True
    watch.timer.start()
    watch.look()
    assert not window.hovered and not watch.timer.isActive()


def test_a_locked_window_lets_the_mouse_through(window: CaptionWindow) -> None:
    window.set_locked(True)
    mouse = Mouse()
    watch = watch_of(window, mouse)
    mouse.at = window.geometry().center()
    watch.look()
    assert not window.hovered


def test_it_looks_every_50_ms_only_while_the_app_is_in_the_background(
    window: CaptionWindow,
) -> None:
    mouse = Mouse()
    watch = watch_of(window, mouse)
    assert POLL_MS == 50 and watch.timer.interval() == POLL_MS
    mouse.active = True
    watch.start()
    assert not watch.timer.isActive()
    watch._state_changed(Qt.ApplicationState.ApplicationInactive)
    assert watch.timer.isActive()
    watch._state_changed(Qt.ApplicationState.ApplicationActive)
    assert not watch.timer.isActive()


def test_the_caption_windows_watch_the_mouse_only_when_asked(
    qapp: QApplication,
) -> None:
    """`main` asks on a Mac; on Windows a background app's window hears the
    mouse itself."""
    asked = CaptionWindows(None, watch_pointer=True)
    plain = CaptionWindows(None)
    try:
        assert asked.pointer_watch is not None and plain.pointer_watch is None
        assert asked.under_the_mouse() == []
    finally:
        asked.close()
        plain.close()
