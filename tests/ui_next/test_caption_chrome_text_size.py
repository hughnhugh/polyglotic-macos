"""A caption window's chrome follows Windows' text size (polyglotic-hq 138,
135's proposal A): the hover band, its buttons and label, the notice, Back
to live and the settings popover grow with `style.text_scale()`, and so
does the width a window needs for its band; its captions keep the window's
own text size (A- / A+). Offscreen, made-up captions."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import (
    BAND_HEIGHT,
    MIN_PANEL,
    CaptionWindow,
    band_height,
    least_size,
)
from polyglotic_desktop.ui_next.settings_popover import WIDTH
from polyglotic_desktop.ui_next.views import placement


@pytest.fixture
def at_100(qapp: QApplication) -> Iterator[QApplication]:
    style.use_text_scale(1.0)
    yield qapp
    style.use_text_scale(1.0)


def band_shown(window: CaptionWindow) -> None:
    window.hovered = True
    window._show_band(True)


def test_the_chrome_grows_with_the_text_and_the_captions_keep_their_size(
    at_100: QApplication,
) -> None:
    before = window_of(at_100)
    caption_font = before.canvas.engine.style.text_px
    style.use_text_scale(2.0)
    window = window_of(at_100)
    band_shown(window)
    assert band_height() == 2 * BAND_HEIGHT
    assert window.band.height() == band_height() - placement.EDGE_ZONE
    assert "font-size: 24px" in window.band.styleSheet()
    assert "font-size: 24px" in window.notice.styleSheet()
    assert window.tag.sizeHint().height() == 44
    assert least_size(MIN_PANEL).width == 2 * MIN_PANEL.width  # room for the band
    assert least_size(MIN_PANEL).height == MIN_PANEL.height  # captions: their own
    assert window.canvas.engine.style.text_px == caption_font
    assert window.choices.text_size == before.choices.text_size
    before.close()
    window.close()


def test_open_windows_follow_a_change_while_running(at_100: QApplication) -> None:
    window = window_of(at_100)
    band_shown(window)
    assert "font-size: 12px" in window.band.styleSheet()
    style.use_text_scale(1.5)
    window.restyle()
    assert "font-size: 18px" in window.band.styleSheet()
    assert window.band.height() == style.px(BAND_HEIGHT) - placement.EDGE_ZONE
    window.toggle_settings()  # made at 1.5
    popover = window.popover
    assert popover is not None and popover.width() >= style.px(WIDTH)
    window.close_settings()
    style.use_text_scale(2.0)
    popover.open_beside(QRect(100, 100, 20, 20))  # restyled as it opens
    assert popover.width() >= 2 * WIDTH  # or what its rows need (`_fit`)
    popover.close()
    window.close()


def test_the_popover_is_as_big_as_its_rows_need(at_100: QApplication) -> None:
    """198: in Segoe UI its rows needed 2 px more than `WIDTH`, and at 200 %,
    with Position open, more height than `adjustSize` gives a window (two
    thirds of the screen): Position's choices were squashed and cut. (No
    Position since 249: the language list is what opens inside it.)"""
    for scale in (1.0, 2.0):
        style.use_text_scale(scale)
        window = window_of(at_100)
        window.toggle_languages()
        popover = window.languages
        assert popover is not None
        popover.language.click()  # the languages open inside it
        at_100.processEvents()
        layout = popover.layout()
        assert layout is not None
        assert popover.width() >= max(style.px(WIDTH), layout.minimumSize().width())
        assert popover.height() == popover.heightForWidth(popover.width())
        for row in popover.rows.values():
            if row.isVisible():
                assert row.height() >= row.minimumSizeHint().height(), row.objectName()
        window.close()


def test_its_notice_is_measured_again_at_a_new_text_size(
    at_100: QApplication,
) -> None:
    """A text size change while it's open (Windows', or the app's own:
    polyglotic-hq 292): the notice restyled and measured again - at its old
    width the larger text was cut."""
    window = window_of(at_100)
    window.set_paused(True)
    window._tick()
    assert window.notice.isVisible()
    style.use_text_scale(2.0)
    window.restyle()
    assert window.notice.width() >= window.notice.sizeHint().width()
    window.close()


def test_a_place_kept_from_a_smaller_text_size_widens_to_its_least_width(
    at_100: QApplication,
) -> None:
    """polyglotic-hq 999: a window kept at 320 px, then Windows' Text size
    raised to 200 %, stayed at 320 and squashed its hover band's buttons
    over each other (its layout needed 394 px of 300). Open, it widens as
    the text size changes; placed again at 320, it takes its least width."""
    window = window_of(at_100)
    preset, size = window.choices.preset, window.choices.text_size
    window.take_place(preset, placement.Rect(100, 100, 320, 200), size)
    assert window.width() == max(320, window._minimum().width)
    style.use_text_scale(2.0)
    window.restyle()
    band_shown(window)
    least = window._minimum().width
    assert least >= 2 * MIN_PANEL.width
    assert window.width() == least
    assert window.band.width() >= window.band.minimumSizeHint().width()
    window.take_place(preset, placement.Rect(100, 100, 320, 200), size)
    assert window.width() == least
    window.close()
