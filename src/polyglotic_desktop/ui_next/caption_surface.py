"""One app's caption lines, painted: the drawing every caption window and
transcript stands on (decision 0031).

A plain widget any container can hold - a caption window, a transcript, or
a joined window with up to three side by side (the user, 2026-11-07) -
each with its own layout cache, keyed by its own width, of no more lines
than its view keeps (polyglotic-hq 239).

The newest line at the bottom, older ones above it - or, scrolled back,
the line the learner left at the top (`views.scroll`). Only the lines that
show are laid out, by the shared engine (`caption_layout`), and a resize
lays them out again at once - nothing waits for a timer, nothing off
screen is touched. The panel, header and controls around it are the
caption window's and the transcript's (the rebuild's part 2, from
polyglotic-hq project 109's structure).
"""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainter, QPaintEvent, QWheelEvent
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.perf import spans
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    Ink,
    LaidLine,
    Marks,
)
from polyglotic_desktop.ui_next.views.captions import CaptionLines, Line

PAD = 14  # px around the lines
GAP = 10  # px between lines, at text size 1.0 (the style's `caption_gap`)
WHEEL_STEP = 48  # px scrolled per notch of the mouse wheel


class CaptionSurface(QWidget):
    """Draws a `CaptionLines` view. Call `changed` after changing the view."""

    def __init__(
        self,
        view: CaptionLines,
        ink: Ink | None = None,
        style: CaptionStyle | None = None,
        marks: Marks | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.view = view
        self.ink = ink or Ink()
        self.engine = CaptionLayout(style, lines_kept=view.keep)
        self.marks = marks
        self.shown = 0  # lines drawn by the last paint
        self._drawn_revision = -1

    def changed(self) -> None:
        """The view changed: repaint, if what it shows did."""
        if self.view.revision != self._drawn_revision:
            self.update()

    # -- measuring --------------------------------------------------------------------

    def _width(self) -> int:
        return max(1, self.width() - 2 * PAD)

    def _gap(self) -> float:
        return self.engine.style.caption_gap * self.view.text_size

    def _laid(self, line: Line) -> LaidLine:
        return self.engine.laid(line, self._width(), self.view.text_size)

    def _height(self, line: Line) -> float:
        return self._laid(line).height

    def _view_height(self) -> float:
        return max(1.0, self.height() - 2.0 * PAD)

    def ink_for(self, line: Line) -> Ink:
        """The ink `line` is drawn in: the surface's (a preview's older
        caption steps back, `caption_preview`)."""
        return self.ink

    # -- events -----------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        with spans.span("caption_surface.paint"):
            self._paint()

    def _paint(self) -> None:
        view = self.view
        placed = view.scroll.placed(
            view.lines, self._height, self._view_height(), self._gap()
        )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setClipRect(QRectF(0, PAD, self.width(), self._view_height()))
        for item in placed:
            self.engine.paint(
                painter,
                item.line,
                self._laid(item.line),
                QPointF(PAD, PAD + item.top),
                self.ink_for(item.line),
                self.marks,
            )
        painter.end()
        self.shown = len(placed)
        self._drawn_revision = view.revision

    def wheelEvent(self, event: QWheelEvent) -> None:
        notches = event.angleDelta().y() / 120
        self.scroll_by(notches * WHEEL_STEP)
        event.accept()

    def scroll_by(self, dy: float) -> None:
        """Back to older lines if `dy` is positive, towards the newest if not."""
        self.view.scroll.scroll_by(
            dy, self.view.lines, self._height, self._view_height(), self._gap()
        )
        self.update()
