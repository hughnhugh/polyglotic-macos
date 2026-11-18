"""The card that saves a caption window's selection as a sentence
(polyglotic-hq 459; the user's design, 2026-11-14).

When the learner lets go of a drag across more than a word - across lines,
clauses, captions and speakers (`views.sentences.worth_saving`) - this card
shows under the caption the selection ends in, never over its translation
(above it with no room below):
"Save sentence to" and a button per category, in its colour - the saved
words' categories, shared. A click saves it in the learning data of the
language it was spoken in and says "Saved to Tricky"; the card goes a
moment later, the selection stays (a right-click still copies it). It goes
with the selection: Esc, a click elsewhere, another drag.

Like the settings popover and the lookup card it **never takes focus** -
a tool window with `Qt.WindowDoesNotAcceptFocus`, shown without
activating, never raised - so a full-screen game keeps the keyboard; its
clicks don't let go of the selection (`HeldSelection.keeps`).

Holds caption text only to save it: never logs it.
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

from polyglotic_desktop.core.learning.saved_words import Category, CategoryId
from polyglotic_desktop.ui_next import style

TEXT, DIM, SURFACE, LINE = "#e9ecf2", "#a0a8b6", "#191d24", "#2a303b"
"""The settings popover's colours: the caption windows' cards share them."""
SAVED_MS = 1400
"""How long "Saved to ..." shows before the card goes."""
GAP = 6
"""Between the selection and the card."""


def _tr(text: str) -> str:
    return QApplication.translate("SentenceCard", text)


def save_to_text() -> str:
    """ "Save sentence to", before the categories: the card's, and the
    transcript's menu's."""
    return _tr("Save sentence to")


def saved_to_text(category: str) -> str:
    """What saving a sentence says: "Saved to Tricky"."""
    return _tr("Saved to {category}").format(category=category)


def _style() -> str:
    return f"""
QWidget {{ color: {TEXT}; font-size: {style.px(12)}px; }}
QLabel {{ color: {DIM}; padding: 0 2px; }}
QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 6px;
  padding: 3px 9px; }}
QPushButton:hover {{ background: rgba(255,255,255,0.10); }}
"""


def placed(anchor: QRect, size: tuple[int, int], area: QRect) -> QPoint:
    """Where the card goes: under `anchor` (the selection's last line, on
    the screen), its left edge with the line's - above it when there's no
    room below; moved in to stay on `area` (the work area)."""
    width, height = size
    x = anchor.left()
    y = anchor.bottom() + 1 + GAP
    if y + height > area.bottom() + 1:
        y = anchor.top() - GAP - height
    x = max(area.left(), min(x, area.right() + 1 - width))
    y = max(area.top(), min(y, area.bottom() + 1 - height))
    return QPoint(x, y)


class SentenceCard(QWidget):
    """A caption window's "Save sentence to" card. `owner`: the caption
    window (it goes with it)."""

    def __init__(self, owner: QWidget) -> None:
        super().__init__(
            owner,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("sentence_card")
        self.setFont(style.ui_font())
        self.setStyleSheet(_style())
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(10, 8, 10, 8)
        self._row.setSpacing(6)
        self.said = QLabel(self)
        self._row.addWidget(self.said)
        self.buttons: list[QPushButton] = []
        self._save: Callable[[CategoryId], str] | None = None
        self._gone = QTimer(self, singleShot=True, interval=SAVED_MS)
        self._gone.timeout.connect(self.hide)

    def offer(
        self,
        categories: Sequence[Category],
        save: Callable[[CategoryId], str],
        anchor: QRect,
        area: QRect,
    ) -> None:
        """Shows the card by `anchor` (on the screen): a button per
        category; a click calls `save` with its ID, which returns the
        category's name it went into ("" if it couldn't be saved)."""
        self._gone.stop()
        self._save = save
        for button in self.buttons:
            self._row.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        self.said.setText(save_to_text())
        for category in categories:
            button = QPushButton(f"● {category.name}", self)
            button.setObjectName(f"sentence_card.{category.id}")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(f"QPushButton {{ color: {category.color}; }}")
            button.clicked.connect(lambda _=False, c=category.id: self._chosen(c))
            self._row.addWidget(button)
            self.buttons.append(button)
        self.adjustSize()
        self.move(placed(anchor, (self.width(), self.height()), area))
        self.show()

    def _chosen(self, category_id: CategoryId) -> None:
        if self._save is None:
            return
        name = self._save(category_id)
        for button in self.buttons:
            button.hide()
        if name:
            self.said.setText(saved_to_text(name))
        else:
            self.said.setText(_tr("Couldn't save it"))
        self.adjustSize()
        self._save = None
        self._gone.start()

    def withdraw(self) -> None:
        """The selection went: the card goes, unless it's saying "Saved"."""
        if not self._gone.isActive():
            self.hide()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(LINE))
        painter.setBrush(QColor(SURFACE))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10
        )
        painter.end()
