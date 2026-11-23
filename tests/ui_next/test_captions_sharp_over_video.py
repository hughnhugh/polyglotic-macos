"""Captions sharp over a video (polyglotic-hq 584; the user, 2026-11-21:
"Big fonts are blurry during video mode, especially when greyed").

Video's subtitles have no panel: the letters are outlined, and the window
is see-through around them. The outline was the text drawn again eight
times round it, each copy at 85 % of the text's ink and moved by a
fraction of a pixel at Video's size (3.1 px at 63 px text): wherever one
copy reached and its neighbour didn't, a grey fringe; under faint text
(the words still to come, an older caption stepped back) every copy was
as faint, and the video showed through the letters and their outline -
smeared. Now each copy is moved by whole pixels of the screen and drawn
solid, one under the letters themselves, so faint text is a solid grey on
solid black. Offscreen, a made-up caption drawn as Video's window draws
it: onto nothing, at the screen's scale."""

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import EN, finished_updates

from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, CaptionStyle, Ink
from polyglotic_desktop.ui_next.views.caption_window import TextEdge
from polyglotic_desktop.ui_next.views.captions import CaptionLines

VIDEO_TEXT = 3.0
"""Video's subtitles' text size: 63 px (4.5 % of a 1440p screen) over
the 21 px a caption's text is at 100 %."""


def _drawn(ink: float, ratio: float) -> QImage:
    """A finished caption at Video's size, outlined, at `ink`, drawn onto a
    see-through window's pixels at the screen's scale `ratio`."""
    view = CaptionLines((APP,), EN, keep=10, yours=(MIC,))
    view.apply(finished_updates(1, APP)[0])
    line = view.lines[0]
    engine = CaptionLayout(CaptionStyle())
    laid = engine.laid(line, 1400, VIDEO_TEXT)
    width, height = 1460, int(laid.height) + 40
    image = QImage(
        round(width * ratio), round(height * ratio), QImage.Format.Format_ARGB32
    )
    image.setDevicePixelRatio(ratio)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    white, yellow = QColor("#ffffff"), QColor("#ffd76e")
    drawn = Ink(white, yellow, alpha=ink, edge=TextEdge.OUTLINE)
    engine.paint(painter, line, laid, QPointF(20.3, 20.4), drawn)
    painter.end()
    return image


def _solid_share(image: QImage) -> float:
    """Of the pixels drawn on, the share drawn solid: the video can't be
    seen through them. A sharp outline is solid but for its own edge."""
    drawn = solid = 0
    for y in range(image.height()):
        for x in range(0, image.width(), 2):
            alpha = image.pixelColor(x, y).alpha()
            if alpha > 5:
                drawn += 1
                solid += alpha >= 250
    return solid / max(1, drawn)


@pytest.mark.parametrize("ratio", [1.0, 1.5])
@pytest.mark.parametrize("ink", [1.0, 0.72, 0.5])
def test_outlined_text_is_solid_however_faint(
    qapp: QApplication, ink: float, ratio: float
) -> None:
    """At full ink, an older caption's (0.72) and the words still to come
    (0.5): most of what's drawn is solid - only the outline's own edge
    isn't. On preview 2 (before 584) this failed at every ink, at 100 %
    and at 150 %."""
    share = _solid_share(_drawn(ink, ratio))
    assert share >= 0.75, share


def test_faint_text_is_its_own_grey_on_black(qapp: QApplication) -> None:
    """Faint text is drawn in a grey of its own over solid black: the
    brightest of its pixels is the grey, as solid as the white's (what
    the words still to come look like; it held before 584 too, where the
    copies under a letter's middle happened to cover it)."""
    full, faint = _drawn(1.0, 1.0), _drawn(0.5, 1.0)

    def brightest(image: QImage) -> QColor:
        best = QColor(0, 0, 0, 0)
        for y in range(image.height()):
            for x in range(0, image.width(), 2):
                found = image.pixelColor(x, y)
                if found.alpha() >= 250 and found.lightness() > best.lightness():
                    best = found
        return best

    white, grey = brightest(full), brightest(faint)
    assert white.lightness() >= 250
    assert 110 <= grey.lightness() <= 150, grey.name()
    assert grey.alpha() >= 250
