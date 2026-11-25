"""Window-level Home/End shortcuts and auto-hiding overlay scroll bar (951)."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSlider
from tests.ui_next.made_up import finished_updates
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.core.listening.display import LongLines
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next import help_page, hotkeys_card
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.joined_window import JoinedWindow
from polyglotic_desktop.ui_next.views.caption_window import JoinedChoices
from polyglotic_desktop.ui_next.views.card_window_defaults import (
    SCROLL_BAR_EDGE_PX,
    SCROLL_BAR_FADE_SEC,
    SCROLL_BAR_IDLE_SEC,
)
from polyglotic_desktop.ui_next.views.placement import Rect


class _Clock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _wheel(widget: CaptionWindow, delta: int) -> None:
    pos = QPointF(widget.width() / 2, widget.height() / 2)
    event = QWheelEvent(
        pos,
        pos,
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)


def _handle_rect(window: CaptionWindow):
    bar = window.scroll_bar
    opt = QStyleOptionSlider()
    bar.initStyleOption(opt)
    return bar.style().subControlRect(
        QStyle.ComplexControl.CC_ScrollBar,
        opt,
        QStyle.SubControl.SC_ScrollBarSlider,
        bar,
    )


def _paint(window: CaptionWindow) -> None:
    window.grab()
    QApplication.processEvents()


@pytest.mark.parametrize(
    "modifier",
    [Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier],
)
def test_home_goes_to_first_caption_and_end_returns_to_live(
    qapp: QApplication, modifier: Qt.KeyboardModifier
) -> None:
    window = window_of(qapp, captions=25)
    try:
        _paint(window)
        first_key = window.view.lines[0].key
        last_key = window.view.lines[-1].key
        assert window.view.scroll.following
        assert first_key not in {line.key for line, _, _ in window.canvas.placed}

        QTest.keyClick(window, Qt.Key.Key_Home, modifier)
        _paint(window)
        assert not window.view.scroll.following
        assert window.view.scroll.anchor is not None
        assert window.view.scroll.anchor.key == first_key
        assert window.canvas.placed and window.canvas.placed[0][0].key == first_key
        assert window.pill.isVisible()

        QTest.keyClick(window, Qt.Key.Key_End, modifier)
        _paint(window)
        assert window.view.scroll.following
        assert window.canvas.placed and window.canvas.placed[-1][0].key == last_key
        assert window.pill.isHidden()
    finally:
        window.close()


def test_locked_window_ignores_home_and_end(qapp: QApplication) -> None:
    window = window_of(qapp, captions=25)
    try:
        window.set_locked(True)
        QTest.keyClick(window, Qt.Key.Key_Home)
        assert window.view.scroll.following
        assert window.scroll_bar.isHidden()
    finally:
        window.close()


def test_joined_window_forwards_home_and_end(qapp: QApplication) -> None:
    left = window_of(qapp, captions=25)
    right = window_of(qapp, captions=25)
    joined = JoinedWindow(JoinedChoices())
    try:
        joined.set_columns([left, right])
        joined.place_at(Rect(0, 0, 900, 260))
        joined.show()
        joined.pointer = lambda: QPoint(-1000, -1000)
        QTest.keyClick(joined, Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)
        assert not left.view.scroll.following and not right.view.scroll.following
        assert left.view.scroll.anchor is not None
        assert left.view.scroll.anchor.key == left.view.lines[0].key
        QTest.keyClick(joined, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
        assert left.view.scroll.following and right.view.scroll.following
    finally:
        joined.close()
        left.close()
        right.close()


def test_bar_shows_on_wheel_no_layout_shift_and_hides_after_idle(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: False)
    window = window_of(qapp, captions=25)
    clock = _Clock(100.0)
    window.clock = clock
    try:
        _paint(window)
        width_before = window.canvas._width()
        assert window.scroll_bar.isHidden()

        _wheel(window, 240)
        _paint(window)
        assert not window.view.scroll.following
        assert window.scroll_bar.isVisible()
        assert window.scroll_bar.opacity == 1.0
        assert window.scroll_bar.maximum() > 0
        # Over the right padding: no layout shift of the caption canvas.
        assert window.canvas._width() == width_before
        assert window.scroll_bar.geometry().left() >= PAD + window.canvas._width()

        # Still visible before idle expires.
        clock.now += SCROLL_BAR_IDLE_SEC.value * 0.5
        window._tick()
        assert window.scroll_bar.isVisible() and window.scroll_bar.opacity == 1.0

        # Mid-fade after idle expires.
        clock.now += SCROLL_BAR_IDLE_SEC.value * 0.5 + SCROLL_BAR_FADE_SEC.value * 0.5
        window._tick()
        assert window.scroll_bar.isVisible()
        assert 0.0 < window.scroll_bar.opacity < 1.0

        # Hidden once fade finishes.
        clock.now += SCROLL_BAR_FADE_SEC.value
        window._tick()
        assert window.scroll_bar.isHidden()
        assert window.scroll_bar.opacity == 0.0
    finally:
        window.close()


def test_bar_shows_on_right_edge_hover_and_hides_after_leaving(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: True)
    window = window_of(qapp, captions=25)
    clock = _Clock(50.0)
    window.clock = clock
    try:
        _paint(window)
        assert window.scroll_bar.isHidden()

        edge_pos = QPointF(window.width() - SCROLL_BAR_EDGE_PX.value / 2, 100.0)
        QApplication.sendEvent(
            window,
            QMouseEvent(
                QEvent.Type.MouseMove,
                edge_pos,
                edge_pos,
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        assert window.scroll_bar.isVisible()
        # Stays visible while hovered on the right edge, even past idle time.
        clock.now += SCROLL_BAR_IDLE_SEC.value * 3
        window._tick()
        assert window.scroll_bar.isVisible()

        # Moving away from the right edge starts the idle countdown.
        away = QPointF(40.0, 100.0)
        QApplication.sendEvent(
            window,
            QMouseEvent(
                QEvent.Type.MouseMove,
                away,
                away,
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )
        clock.now += SCROLL_BAR_IDLE_SEC.value + 0.05
        window._tick()
        assert window.scroll_bar.isHidden()

        # Entering directly on the right edge also reveals it.
        QApplication.sendEvent(window, QEnterEvent(edge_pos, edge_pos, edge_pos))
        assert window.scroll_bar.isVisible()
    finally:
        window.close()


def test_dragging_bar_to_top_shows_first_caption_and_track_click_pages(
    qapp: QApplication,
) -> None:
    window = window_of(qapp, captions=40)
    try:
        _paint(window)
        _wheel(window, 120)
        _paint(window)
        bar = window.scroll_bar
        assert bar.isVisible() and bar.maximum() > 5
        bar.setValue(bar.maximum())
        _paint(window)
        assert window.view.scroll.following

        # Click the track above the handle to page up.
        handle = _handle_rect(window)
        assert handle.top() > 4
        before = bar.value()
        QTest.mouseClick(
            bar, Qt.MouseButton.LeftButton, pos=QPoint(bar.width() // 2, 2)
        )
        QApplication.processEvents()
        assert bar.value() < before
        assert not window.view.scroll.following

        # Drag the handle all the way to the top -> first caption shows.
        handle = _handle_rect(window)
        start = handle.center()
        top = QPoint(bar.width() // 2, 0)
        QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(bar, pos=top)
        QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=top)
        _paint(window)
        first_key = window.view.lines[0].key
        assert bar.value() == 0
        assert not window.view.scroll.following
        assert window.canvas.placed and window.canvas.placed[0][0].key == first_key
    finally:
        window.close()


@pytest.mark.parametrize("choice", [LongLines.GROUPED, LongLines.DISPLAY_NEW_LINES])
def test_shortcuts_and_scrollbar_work_with_long_lines_modes(
    qapp: QApplication, choice: LongLines
) -> None:
    window = window_of(qapp, captions=25)
    try:
        window.set_presets(replace(window.preset_menu, long_lines=choice))
        _paint(window)
        first_key = window.view.lines[0].key

        _wheel(window, 120)
        assert window.scroll_bar.isVisible() and window.scroll_bar.maximum() > 0

        window.scroll_bar.setValue(0)
        _paint(window)
        assert not window.view.scroll.following
        assert window.canvas.placed and window.canvas.placed[0][0].key == first_key

        QTest.keyClick(window, Qt.Key.Key_End)
        _paint(window)
        assert window.view.scroll.following

        QTest.keyClick(window, Qt.Key.Key_Home)
        _paint(window)
        assert not window.view.scroll.following
        assert window.canvas.placed and window.canvas.placed[0][0].key == first_key
    finally:
        window.close()


def test_shortcuts_and_scrollbar_work_in_video_mode(qapp: QApplication) -> None:
    window = window_of(qapp, captions=0)
    clock = _Clock(10.0)
    window.clock = clock
    try:
        window.set_video(True)
        for update in finished_updates(20):
            window.receive(update)
            clock.now += 2.0
            window.grab()
        for _ in range(40):
            clock.now += 1.0
            window.grab()
        _paint(window)
        first_key = window.canvas._lines()[0].key
        assert first_key not in {line.key for line, _, _ in window.canvas.placed}

        _wheel(window, 120)
        _paint(window)
        assert not window.view.scroll.following
        assert window.scroll_bar.isVisible() and window.scroll_bar.maximum() > 0

        window.scroll_bar.setValue(0)
        _paint(window)
        assert window.canvas.placed and window.canvas.placed[0][0].key == first_key

        QTest.keyClick(window, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
        _paint(window)
        assert window.view.scroll.following

        QTest.keyClick(window, Qt.Key.Key_Home, Qt.KeyboardModifier.ControlModifier)
        _paint(window)
        assert not window.view.scroll.following
        assert window.canvas.placed and window.canvas.placed[0][0].key == first_key
    finally:
        window.close()


def test_scrollbar_follows_panel_theme_colours(qapp: QApplication) -> None:
    window = window_of(qapp, captions=20)
    try:
        assert window.scroll_bar._ink.shade == "255,255,255"
        window.set_look(replace(window.look, background="#f5f6f7"))
        assert window.scroll_bar._ink.shade == "0,0,0"
    finally:
        window.close()


def test_shortcuts_are_listed_in_help_and_hotkeys_settings(qapp: QApplication) -> None:
    keys_list = hotkeys_card.window_keys()
    labels = {what: key for what, key in keys_list}
    assert "Jump to the first caption" in labels
    assert "Home" in labels["Jump to the first caption"]
    assert "Back to live in a caption or transcript window" in labels
    assert "End" in labels["Back to live in a caption or transcript window"]

    # Listed in Help even when global hotkeys are disabled (preview builds).
    topics = dict(help_page.set_up(()))
    caption_help = topics["Move, lock and resize caption windows"]
    assert "Home" in caption_help and "End" in caption_help
