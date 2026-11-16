"""The listening mark is a loading bar, easy to see at a glance - the user's
word for it (F33, "a loading bar whilst there is speech being recorded /
processed"), and 260's finding that it was 4 px dots in a corner
(polyglotic-hq 267). Still quiet: thin, in the window's own colour, its
lit part sweeping slowly; with Windows' animations off, it stands still
(`test_caption_window`'s reduced-motion test)."""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_window import (
    MARK_LENGTH,
    CaptionWindow,
    mark_lit,
)
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

GREEN = "#7dff8a"
"""A look's own original colour, unlike the default white."""


@pytest.fixture
def listening(qapp: QApplication) -> Iterator[CaptionWindow]:
    window = window_of(qapp, captions=3, look=CaptionLook(original=GREEN))
    window.always_shown = True
    window.set_listening(True)
    window.canvas.repaint()
    yield window
    window.close()


def test_it_is_a_bar_long_enough_to_see_at_a_glance(listening: CaptionWindow) -> None:
    """At least 56 px long at 100 % text size (the three dots were 25 px
    across), and still thin: no taller than the padding under the text."""
    rect = listening.canvas.mark_rect
    assert rect is not None
    assert rect.width() >= MARK_LENGTH >= 56
    assert rect.height() <= 12
    assert rect.bottom() < listening.canvas.height()


def test_it_grows_with_the_text_size(qapp: QApplication) -> None:
    window = window_of(qapp, captions=3, text_size=1.5)
    try:
        window.always_shown = True
        window.set_listening(True)
        window.canvas.repaint()
        rect = window.canvas.mark_rect
        assert rect is not None and rect.width() >= MARK_LENGTH * 1.5
    finally:
        window.close()


def test_its_lit_part_sweeps_left_to_right_inside_the_bar() -> None:
    lit = [mark_lit(n / 40) for n in range(40)]
    assert all(0.0 <= start <= end <= 1.0 for start, end in lit)
    middles = [(start + end) / 2 for start, end in lit if end > start]
    assert middles == sorted(middles)  # one way, then it starts again
    assert min(middles) < 0.2 and max(middles) > 0.8  # across the whole bar


def test_it_is_drawn_in_the_window_s_own_colour(
    listening: CaptionWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The brightest of the bar's pixels is the look's original colour."""
    monkeypatch.setattr(caption_window_module.time, "monotonic", lambda: 100.7)
    listening.canvas.repaint()
    rect = listening.canvas.mark_rect
    assert rect is not None
    image = listening.canvas.grab().toImage()
    ratio = image.devicePixelRatio()
    pixels = [
        image.pixelColor(round(x * ratio), round(y * ratio))
        for x in range(rect.left(), rect.right())
        for y in range(rect.top(), rect.bottom())
    ]
    brightest = max(pixels, key=QColor.lightness)
    green = QColor(GREEN)
    assert brightest.green() > brightest.red() and brightest.green() > 160
    assert abs(brightest.hue() - green.hue()) <= 12
