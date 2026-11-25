"""Caption windows support native minimise on Windows. When a window
is hidden, shown, minimised or faded out with fading off the log says so
and why - content-free (the user's live testing, polyglotic-hq 272: "the
caption window will minimize when the fade off feature is off. Perhaps
when it is on for a long time").

A caption window has no taskbar button and no system menu, so a window
Windows minimised ("show desktop", another app's ShowWindow) had no way
back but Ctrl+Alt+H twice - and the app still thought it showed. On a
private desktop, `ShowWindow(SW_MINIMIZE)` minimised one and it stayed so
(272's report)."""

import logging
import sys
from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import SEPARATE
from tests.ui_next.test_caption_window import Clock, _settle, window_of
from tests.ui_next.test_joined_window import THREE, areas, joined

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp)
    yield shown
    shown.close()


def test_a_window_windows_minimised_is_back_at_once(
    qapp: QApplication, window: CaptionWindow, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        window.setWindowState(Qt.WindowState.WindowMinimized)
        qapp.processEvents()
    if sys.platform == "win32":
        assert window.isMinimized()
        window.showNormal()
    else:
        assert "caption window 0 minimised by Windows: restored" in caplog.messages
    assert not window.isMinimized() and window.isVisible()


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, areas)
    found.stored.joined = SEPARATE  # on their own: windows start joined (554)
    found.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
    found.set_captioned(THREE)
    yield found
    found.close()


def test_a_joined_window_windows_minimised_is_back_at_once(
    qapp: QApplication, windows: CaptionWindows
) -> None:
    windows.join()
    window = joined(windows)
    window.setWindowState(Qt.WindowState.WindowMinimized)
    qapp.processEvents()
    if sys.platform == "win32":
        assert window.isMinimized()
        window.showNormal()
    assert not window.isMinimized() and window.isVisible()


def test_hiding_showing_and_closing_are_logged_with_why_never_the_app(
    windows: CaptionWindows, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        windows.set_hidden(True)
        windows.set_hidden(False)
        windows.join()
        windows.set_captioned(THREE[:2])
    said = caplog.messages
    assert "caption windows hidden (Ctrl+Alt+H)" in said
    assert "caption windows shown again" in said
    assert "caption windows joined, 3 columns: shown" in said
    assert "caption window 2 closed: its app no longer captioned" in said
    assert not any("Discord" in line or "app-" in line for line in said)


def test_fading_out_with_fading_off_is_logged(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A window with captions never fades with fading off; if one ever
    does, the log says so - as "unexpected" - once (the rule made to fail
    here, as whatever made the user's go would)."""
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    shown = window_of(qapp, captions=3, look=CaptionLook(fade_after=None))
    try:
        monkeypatch.setattr(caption_window_module, "shows", lambda **_: False)
        with caplog.at_level(logging.INFO):
            _settle(shown, clock)
        assert shown.alpha == 0.0
        said = "caption window 0 faded out with fading off: unexpected"
        assert caplog.messages.count(said) == 1
    finally:
        shown.close()
