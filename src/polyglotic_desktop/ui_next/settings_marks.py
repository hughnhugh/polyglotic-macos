"""Settings you can scan (polyglotic-hq 470; 449's design 4A, the user's
"try to make each setting category very obvious as you scroll the page"):
each card's title a size up, with its mark at its left;
and, pinned under the page's title and sections while the page scrolls,
the name of the card the learner is in.

A mark is drawn as the caption windows' icons are (`glyphs`), in the
theme's colours at paint time, so a theme change needs no re-inking - and
it always sits beside its words, never alone (Nielsen Norman Group's
"Icon Usability": "a text label must be present alongside an icon").
"""

from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QWidget

from polyglotic_desktop.ui_next import glyphs, style
from polyglotic_desktop.ui_next.controls import Card, label

TILE = 30
"""Space reserved for a card's mark at 100 % text size."""
MARK = 18
"""...and the mark in it."""
PINNED_MARK = 16
"""The mark beside the pinned card's name: a row's size."""


class GlyphTile(QWidget):
    """Draw the glyph in the theme's text colour, with space around card marks."""

    def __init__(
        self,
        glyph: glyphs.Glyph,
        tile: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.glyph, self.tile = glyph, tile
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def show_glyph(self, glyph: glyphs.Glyph) -> None:
        if glyph is not self.glyph:
            self.glyph = glyph
            self.update()

    def sizeHint(self) -> QSize:
        side = style.px(TILE if self.tile else PINNED_MARK)
        return QSize(side, side)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:  # perhaps another text size
            self.updateGeometry()

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = style.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # U1 keeps the landmark glyph and its alignment but removes its
        # decorative square: the mark no longer adds another nested container.
        side = style.px(MARK if self.tile else PINNED_MARK)
        box = QRectF(0, 0, side, side)
        box.moveCenter(QRectF(self.rect()).center())
        glyphs.paint(painter, self.glyph, box, QColor(theme["TEXT"]))
        painter.end()


def mark_card(card: Card, glyph: glyphs.Glyph) -> GlyphTile:
    """`card`'s title beside `glyph`, a size up from a
    row's title (16 px: `#CardTitle[heading="true"]`), wrapping where the
    room runs out - a long title at the Largest text size (449's finding
    8). The card's `title` stays the same label."""
    title = card.title
    assert title is not None, "a card marked has a title"
    index = card.column.indexOf(title)
    card.column.removeWidget(title)
    line = QHBoxLayout()
    line.setSpacing(10)
    tile = GlyphTile(glyph)
    tile.setObjectName("CardMark")
    line.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
    title.setProperty("heading", True)
    title.setWordWrap(True)
    title.setMinimumHeight(0)
    line.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
    card.column.insertLayout(index, line)
    return tile


class PinnedCard(QFrame):
    """The name of the card the learner is in, with its mark, pinned under
    the page's sections while that card's own title is scrolled away."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PinnedCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        line = QHBoxLayout(self)
        line.setContentsMargins(14, 6, 14, 6)
        line.setSpacing(8)
        self.mark = GlyphTile(glyphs.Glyph.LOOK, tile=False)
        line.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = label("", "RowTitle", copyable=False)
        line.addWidget(self.title, 1)

    def show_card(self, glyph: glyphs.Glyph, title: str) -> None:
        self.mark.show_glyph(glyph)
        if self.title.text() != title:
            self.title.setText(title)
        self.setAccessibleName(title)
