"""A lock or an unlock never changes the input shape of a mapped window
(polyglotic-hq 547, 550): GNOME's window manager ignores a live change to
it - over a Wayland window the click then went to nobody (547's runs, 0/2
and 0/5 on mutter 46 and 51) - so clicks passing through are changed only
while the window is hidden, and it's shown again after. And on Linux the
floating windows are override-redirect: the window manager stacks them
above a focused full-screen window (547: the only arrangement that never
failed on GNOME 46, 51 and KDE 6.8)."""

import sys
from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_joined_window import joined, store, windows  # noqa: F401 - fixtures

from polyglotic_desktop.ui_next.above_all import ABOVE_ALL, set_click_through
from polyglotic_desktop.ui_next.caption_window import WINDOW_FLAGS, CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows

THROUGH = Qt.WindowType.WindowTransparentForInput
BYPASS = Qt.WindowType.X11BypassWindowManagerHint


def mapped_when_changed(widget: QWidget) -> list[bool]:
    """Whether `widget` showed each time its clicks-pass-through flag was
    changed: a spy on its own `setWindowFlag`."""
    seen: list[bool] = []
    original = widget.setWindowFlag

    def recording(flag: Qt.WindowType, on: bool = True) -> None:
        if flag == THROUGH:
            seen.append(widget.isVisible())
        original(flag, on)

    widget.setWindowFlag = recording  # type: ignore[method-assign]
    return seen


@pytest.fixture
def caption(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp)
    yield shown
    shown.close()
    shiboken6.delete(shown)


def test_a_caption_window_locks_and_unlocks_while_hidden(
    qapp: QApplication, caption: CaptionWindow
) -> None:
    seen = mapped_when_changed(caption)
    caption.set_locked(True)
    qapp.processEvents()
    assert seen == [False]
    assert caption.isVisible() and caption.windowFlags() & THROUGH
    caption.set_locked(False)
    qapp.processEvents()
    assert seen == [False, False]
    assert caption.isVisible() and not caption.windowFlags() & THROUGH


def test_a_joined_window_locks_while_hidden(
    qapp: QApplication,
    windows: CaptionWindows,  # noqa: F811 - the fixture
) -> None:
    windows.join()
    window = joined(windows)
    seen = mapped_when_changed(window)
    windows.set_locked(True)
    qapp.processEvents()
    assert seen and not any(seen)
    assert window.isVisible() and window.windowFlags() & THROUGH
    windows.set_locked(False)
    assert not any(seen) and window.isVisible()


def test_click_through_is_changed_only_while_hidden(qapp: QApplication) -> None:
    widget = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
    try:
        widget.show()
        seen = mapped_when_changed(widget)
        set_click_through(widget, True)
        assert seen == [False] and widget.isVisible()
        set_click_through(widget, True)  # already so: nothing touched
        assert seen == [False]
        set_click_through(widget, False, show=False)  # the caller shows it
        assert seen == [False, False] and not widget.isVisible()
        set_click_through(widget, True)  # hidden: stays hidden
        assert not widget.isVisible() and widget.windowFlags() & THROUGH
    finally:
        widget.close()
        shiboken6.delete(widget)


def test_the_floating_windows_are_override_redirect_on_linux_only() -> None:
    on_linux = sys.platform.startswith("linux")
    assert bool(ABOVE_ALL & BYPASS) == on_linux
    assert bool(WINDOW_FLAGS & BYPASS) == on_linux
    assert WINDOW_FLAGS & Qt.WindowType.WindowStaysOnTopHint  # every OS
