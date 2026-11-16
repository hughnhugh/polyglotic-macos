"""The caption surface and its layout engine lay out only what shows, keep
what they laid out, and repaint marks without laying anything out."""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget
from tests.ui_next.made_up import EN, finished_updates

from polyglotic_desktop.ui.recorded_captions import APP
from polyglotic_desktop.ui_next.caption_layout import Mark
from polyglotic_desktop.ui_next.caption_surface import CaptionSurface
from polyglotic_desktop.ui_next.views.captions import (
    TRANSCRIPT_LINES,
    CaptionLines,
    Line,
)

ROWS_PER_LINE = 4  # the made-up lines: two clauses, each with its translation


@pytest.fixture
def surface(qapp: QApplication) -> Iterator[CaptionSurface]:
    view = CaptionLines((APP,), EN, keep=TRANSCRIPT_LINES)
    for update in finished_updates(TRANSCRIPT_LINES):
        view.apply(update)
    shown = CaptionSurface(view)
    shown.resize(800, 260)
    shown.show()
    qapp.processEvents()
    shown.repaint()
    yield shown
    shown.close()


def test_a_thousand_lines_lay_out_only_what_shows(surface: CaptionSurface) -> None:
    assert 1 <= surface.shown < 10
    assert surface.engine.laid_out <= surface.shown * ROWS_PER_LINE


def test_a_resize_lays_out_what_shows_once_per_width(
    surface: CaptionSurface, qapp: QApplication
) -> None:
    before = surface.engine.laid_out
    surface.resize(600, 260)
    qapp.processEvents()
    surface.repaint()
    narrower = surface.engine.laid_out - before
    assert 0 < narrower <= surface.shown * ROWS_PER_LINE
    surface.resize(800, 260)  # back to a width laid out before: kept
    qapp.processEvents()
    surface.repaint()
    surface.resize(600, 260)
    qapp.processEvents()
    surface.repaint()
    assert surface.engine.laid_out == before + narrower


def test_a_new_caption_lays_out_only_itself(
    surface: CaptionSurface, qapp: QApplication
) -> None:
    before = surface.engine.laid_out
    surface.view.apply(finished_updates(1, start=TRANSCRIPT_LINES)[0])
    surface.changed()
    surface.repaint()
    assert surface.engine.laid_out - before == ROWS_PER_LINE


def test_the_text_size_lays_out_only_what_shows(surface: CaptionSurface) -> None:
    before = surface.engine.laid_out
    surface.view.set_text_size(1.5)
    surface.changed()
    surface.repaint()
    assert 0 < surface.engine.laid_out - before <= surface.shown * ROWS_PER_LINE


def test_marks_repaint_without_laying_out(surface: CaptionSurface) -> None:
    marked = QTextCharFormat()
    marked.setForeground(QColor("#ff6e9c"))
    seen: list[int] = []

    def marks(line: Line, row: int) -> list[Mark]:
        seen.append(line.key)
        return [(0, 2, marked)] if row == 0 else []

    before = surface.engine.laid_out
    surface.marks = marks
    surface.repaint()
    assert seen
    assert surface.engine.laid_out == before


def test_scrolled_back_it_stays_put_as_captions_arrive(
    surface: CaptionSurface,
) -> None:
    surface.scroll_by(300)
    surface.repaint()
    top = surface.view.scroll.anchor
    assert top is not None
    surface.view.apply(finished_updates(1, start=TRANSCRIPT_LINES)[0])
    surface.changed()
    surface.repaint()
    assert surface.view.scroll.anchor == top


def test_surfaces_side_by_side_in_one_window(qapp: QApplication) -> None:
    """A joined window: up to three caption windows' lines in one, each
    surface laid out at its own column's width."""
    joined = QWidget()
    row = QHBoxLayout(joined)
    surfaces = []
    for n in range(3):
        view = CaptionLines((APP,), EN, keep=TRANSCRIPT_LINES)
        for update in finished_updates(20, start=n):
            view.apply(update)
        surface = CaptionSurface(view)
        row.addWidget(surface, stretch=n + 1)
        surfaces.append(surface)
    joined.resize(1200, 260)
    joined.show()
    qapp.processEvents()
    joined.repaint()
    widths = {surface.width() for surface in surfaces}
    assert len(widths) == 3 and max(widths) < 1200
    assert all(surface.shown > 0 for surface in surfaces)
    joined.close()


def test_a_word_linked_and_in_the_deck_shows_both_marks(qapp: QApplication) -> None:
    """A link's underline and the deck's dots on the same word: both drawn
    (112 found the underline hid the dots). The underline stays a format
    Qt draws with the text; the dots are drawn below it."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter

    from polyglotic_desktop.ui_next.caption_layout import (
        CaptionLayout,
        Ink,
        split_marks,
    )

    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished_updates(1)[0])
    line = view.lines[0]
    link, deck = "#ff9f43", "#7ee0a8"
    underline = QTextCharFormat()
    underline.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
    underline.setUnderlineColor(QColor(link))
    dotted = QTextCharFormat()
    dotted.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DotLine)
    dotted.setUnderlineColor(QColor(deck))
    both: list[Mark] = [(0, 4, underline), (0, 4, dotted)]

    selections, dots, _ = split_marks(both)
    assert [s.format.underlineColor().name() for s in selections] == [link]
    assert [(a, b, c.name(), dashed) for a, b, c, dashed in dots] == [
        (0, 4, deck, False)
    ]

    engine = CaptionLayout()
    laid = engine.laid(line, 600, 1.0)
    image = QImage(640, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    engine.paint(
        painter, line, laid, QPointF(10, 10), Ink(), lambda _, r: both if r == 0 else []
    )
    painter.end()
    drawn = {
        image.pixelColor(x, y).name()
        for x in range(10, 300)
        for y in range(image.height())
    }
    assert deck in drawn  # the dots


def test_a_row_out_of_view_leaves_no_marks_behind(qapp: QApplication) -> None:
    """A row hidden under the hover band (clipped out) is not painted at
    all - its dots and dashes included. They sit a little below the row's
    box, so a row under the band used to leak its marks into the gap
    beneath it (151, seen on a real window 2026-11-07)."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter

    from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, Ink

    view = CaptionLines((APP,), EN, keep=10)
    view.apply(finished_updates(1)[0])
    line = view.lines[0]
    deck = "#7ee0a8"
    dashed = QTextCharFormat()
    dashed.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)
    dashed.setUnderlineColor(QColor(deck))
    marks: list[Mark] = [(0, 4, dashed)]
    engine = CaptionLayout()
    laid = engine.laid(line, 600, 1.0)
    first = laid.rows[0]
    below_first = 10 + first.top + first.layout.boundingRect().height()
    image = QImage(640, int(laid.height) + 20, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    painter.setClipRect(QRectF(0, below_first, 640, image.height() - below_first))
    engine.paint(
        painter,
        line,
        laid,
        QPointF(10, 10),
        Ink(),
        lambda _, r: marks if r == 0 else [],
    )
    painter.end()
    drawn = {
        image.pixelColor(x, y).name()
        for x in range(10, 300)
        for y in range(image.height())
    }
    assert deck not in drawn
