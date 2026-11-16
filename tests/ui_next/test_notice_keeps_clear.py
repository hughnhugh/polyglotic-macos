"""A caption window's notice line never covers a caption, and the strip
coming and going doesn't move it (polyglotic-hq 376, 403).

It sat at the top while the strip was away and 26 px lower - over the top
caption - whenever the mouse was on the window: "Click any word to look it
up" covered the line the learner was reaching for.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.ui_next.caption_window import CaptionWindow, band_height


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp)
    yield shown
    shown.close()
    shown.deleteLater()
    qapp.processEvents()


def _captions_start(window: CaptionWindow) -> float:
    """Where the captions start once painted: nothing is drawn above it
    (the canvas clips there, at a whole row or wrapped line)."""
    window.canvas.grab()
    assert window.canvas.placed, "nothing drawn"
    return window.canvas.clear_top


def test_the_strip_showing_doesnt_move_the_notice(window: CaptionWindow) -> None:
    window.show_notice("Click any word to look it up")
    at_rest = window.notice.geometry()
    assert window.notice.isVisible()
    assert at_rest.bottom() < band_height()  # in the strip's own height
    window._show_band(True)
    assert window.notice.geometry() == at_rest
    # ...in the gap between the strip's label and its buttons
    first = min(b.x() for b in window.buttons.values() if not b.isHidden())
    assert at_rest.right() < window.band.x() + first
    assert at_rest.left() > window.band.x() + window.tag.sizeHint().width()
    window._show_band(False)
    assert window.notice.geometry() == at_rest


def test_no_caption_is_drawn_under_the_notice(window: CaptionWindow) -> None:
    window.show_notice("Click any word to look it up")
    foot = window.notice.geometry().bottom()
    start = _captions_start(window)
    assert foot < start < window.height() / 2  # below it, and captions left
    window._show_band(True)  # the strip showing: the same rows
    assert _captions_start(window) == start


def test_where_the_strip_leaves_no_gap_the_notice_goes_under_it(
    window: CaptionWindow,
) -> None:
    """A narrow window: the strip's label and buttons take its width. The
    notice shows under the strip while the strip shows - and the captions
    still start below it."""
    window.resize(260, 300)
    QApplication.processEvents()
    window.show_notice("Can't reach Polyglotic's server - trying again in 8 s")
    at_rest = window.notice.geometry()
    window._show_band(True)
    under = window.notice.geometry()
    assert under.top() >= band_height()
    assert _captions_start(window) > under.bottom()
    window._show_band(False)
    assert window.notice.geometry() == at_rest


def test_the_rows_come_back_when_the_notice_goes(window: CaptionWindow) -> None:
    without = _captions_start(window)
    window.notices.paused = True
    window._tick()
    assert window.notice.isVisible() and window.notice_foot() > 0
    assert _captions_start(window) > window.notice.geometry().bottom()
    window.notices.paused = False
    window._tick()
    assert not window.notice.isVisible() and window.notice_foot() == 0
    assert _captions_start(window) == without
