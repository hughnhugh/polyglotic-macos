"""Copying any text a learner can see (polyglotic-hq 343; the user,
2026-11-15: "drag and select and ctrl c / right click to copy").

- **A label** (`Text`): its words selected with the mouse, then
  Ctrl+C once it's been clicked, or the right-click menu - Copy (what's
  selected, or all of it when nothing is) and Select all, in the interface
  language. It takes the keyboard only from a click, never from Tab, and
  links in it still open. `controls.label` makes every label so; a label
  inside something a click anywhere on works (Home's rows of apps to add)
  isn't.
- **Painted text** (`TextSelection`): text a window paints itself, such as
  the lookup card's, selected by a drag across it - across its lines and
  within them - and given back as the learner reads it, in order.
- **On a window that never takes the keyboard** (`copy_quietly`): a
  right-click copies the selection at once, with "Copied" by the mouse - no
  menu, which would take the mouse from the game under it - and never the
  keyboard. The lookup card's, and for the caption windows' (polyglotic-hq
  340).

Only the clipboard: nothing copied is logged, sent or kept (captions and
words are content).
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from PySide6 import QtGui
from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QContextMenuEvent,
    QEnterEvent,
    QFontMetricsF,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QTextDocumentFragment,
    QTextLayout,
    QTextLine,
)
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.toast import show_toast
from polyglotic_desktop.ui_next.views.card_window_defaults import TOAST_DURATION_SEC

COPIED_MS = round(TOAST_DURATION_SEC.default * 1000)
"""How long "Copied" stays on a strip button after a click (ms)."""


def _tr(text: str) -> str:
    return QApplication.translate("Copying", text)


MEASURE = 64
"""The most characters a wrapped label puts on a line, as its font's average
ones: a note's lines stay readable (about 65-75 characters; the UI lab's
`line_length` allows 80) however wide the column it sits in."""


ONE_LINE = 1.25
"""Words this much wider than the measure still go on one line, if they're
no more than `ONE_LINE_CHARACTERS`: not a second line of one word."""
ONE_LINE_CHARACTERS = 80
_UNBROKEN = re.compile(r"[\s\u2e80-\uffff]+")
"""What a line can break at: spaces, and any Chinese, Japanese or Korean
character (their sentences have no spaces, and a line breaks between any
two of their characters)."""
BANDS = frozenset({"Banner"})
"""The labels (by the stylesheet's name for them) drawn as a box across
their room: a notice's band is as wide as its card, whatever it says."""
_WIDTH_CHANGES = frozenset(
    {
        QEvent.Type.FontChange,
        QEvent.Type.StyleChange,
        QEvent.Type.LanguageChange,
    }
)
"""What changes the width a label's words need, besides new words."""


class Measured(QLabel):
    """A label whose wrapped lines keep to a readable length (`MEASURE`;
    polyglotic-hq 376): in a 720 px column a 12 px note ran to 120
    characters a line. Only a label that wraps, starts at the left and is in
    a layout; at any text size, since the measure is the font's.

    The label itself is no wider than the measure, at the left of the room
    its layout gives it: it prefers the measure's width (`sizeHint`), is as
    tall as its words need within it (`heightForWidth`), and its place in
    the layout is aligned left, set once, when the layout first asks - Qt then
    gives it the lesser of the room and what it prefers. Nothing is set
    when it's resized: a margin kept up to date there laid a page out twice
    whenever it was first shown, and took Settings' first show of a section
    past its budget. And what a layout asks of every label on every pass
    is answered from what's kept here (`_is`, `_widest`), dropped when the
    words, the font, the wrapping, the side or the parent change: the main
    window has hundreds of labels, and each question comes through Python."""

    _is: bool | None = None
    """Its lines keep to the measure (`measured`); None: not looked at since
    its wrapping, its side or its parent last changed."""
    _widest: int | None = None
    """The width its words need in its font (`_needs`), until either changes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._heights: dict[int, int] = {}
        """How tall its words are at the widths it's been asked about: Qt
        lays the words out again for every question, several a pass."""
        super().__init__(*args, **kwargs)

    def measure(self) -> int:
        """The widest its lines run, in px."""
        return round(MEASURE * QFontMetricsF(self.font()).averageCharWidth())

    def measured(self) -> bool:
        """Its lines keep to the measure."""
        if self._is is None:  # asked by its layout, before it's first placed
            self._is = (
                self.wordWrap()
                and bool(self.alignment() & Qt.AlignmentFlag.AlignLeft)
                and self._align_left()
            )
        return self._is

    def changeEvent(self, event: QEvent) -> None:
        kind = event.type()
        if kind == QEvent.Type.ParentChange:
            self._is = None  # another layout: look again
        elif kind in _WIDTH_CHANGES:
            self._changed()
        super().changeEvent(event)

    def setText(self, text: str) -> None:
        self._changed()
        super().setText(text)

    def setWordWrap(self, on: bool) -> None:
        self._is = None
        self._heights.clear()
        super().setWordWrap(on)

    def setAlignment(self, alignment: Qt.AlignmentFlag) -> None:
        self._is = None
        super().setAlignment(alignment)

    def _align_left(self) -> bool:
        """Aligns its place in its parent's layout left, unless whoever
        put it there chose a side or the middle. Whether it's at the left."""
        if self.objectName() in BANDS or self.styleSheet():
            return False  # a box of its own: as wide as its room, as a band is
        parent = self.parentWidget()
        item = _item_of(parent.layout(), self) if parent is not None else None
        if item is None:
            return False
        chosen = item.alignment()
        if not chosen & Qt.AlignmentFlag.AlignHorizontal_Mask:
            item.setAlignment(chosen | Qt.AlignmentFlag.AlignLeft)
            return True
        return bool(chosen & Qt.AlignmentFlag.AlignLeft)

    def _needs(self) -> int:
        """The width it'd take: the measure - less for words that fit on
        one shorter line, more for a word longer than the measure (a path,
        a link), which can't be broken."""
        if self._widest is None:
            metrics = QFontMetricsF(self.font())
            measure = self.measure()
            read = words(self)  # without markup: a link's address isn't a word
            longest = max(_UNBROKEN.split(read), key=len, default="")
            whole = math.ceil(metrics.horizontalAdvance(read)) + 1
            width = max(
                # a word or two over the measure stays on the line: not a
                # second line of one word
                whole
                if whole <= measure * ONE_LINE and len(read) <= ONE_LINE_CHARACTERS
                else measure,
                math.ceil(metrics.horizontalAdvance(longest)) + 1
                if len(longest) > MEASURE // 3
                else 0,
            )
            self._widest = width
        margins = self.contentsMargins()
        return self._widest + margins.left() + margins.right() + 2 * self.margin()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        if not self.measured():
            return hint
        return QSize(self._needs(), hint.height())

    def heightForWidth(self, width: int) -> int:
        if self.measured():
            width = min(width, self._needs(), self.maximumWidth())
        height = self._heights.get(width)
        if height is None:
            if len(self._heights) > 8:  # a window dragged wider and wider
                self._heights.clear()
            height = self._heights[width] = super().heightForWidth(width)
        return height

    def _changed(self) -> None:
        """Its words, its font or its margins changed: measured again."""
        self._widest = None
        self._heights.clear()

    def setTextFormat(self, format: Qt.TextFormat) -> None:
        self._changed()
        super().setTextFormat(format)

    def setMargin(self, margin: int) -> None:
        self._changed()
        super().setMargin(margin)

    def setIndent(self, indent: int) -> None:
        self._changed()
        super().setIndent(indent)

    def setContentsMargins(self, *margins: Any) -> None:
        self._changed()
        super().setContentsMargins(*margins)


def _item_of(layout: QLayout | None, widget: QWidget) -> QLayoutItem | None:
    """`widget`'s place in `layout`, or in a layout inside it. Each layout
    is asked for the widget itself: walking a card's items one by one in
    Python, for each of its labels, was slow enough to show in the first
    showing of a Settings section."""
    if layout is None:
        return None
    for each in (layout, *layout.findChildren(QLayout)):
        index = each.indexOf(widget)
        if index >= 0:
            return each.itemAt(index)
    return None


_LINK = re.compile(r"<a (?:style='color:[^']*' )?")
"""A link's opening tag, with the colour `Text.ink_links` gave it or none."""


class Text(Measured):
    """A label whose words can be selected with the mouse and copied: Ctrl+C
    once it's been clicked, or its right-click menu (`menu_for`). Qt's own
    menu has no words in some of the interface's languages (Vietnamese,
    Thai, Hindi...) and copies nothing when nothing is selected.

    Selectable from when the mouse first comes to it (`ready`), not before:
    a selectable label lays its words out as a document, about 0.2 ms
    each, and the main window starts with over 250 of them - within a
    400 ms budget (DECISIONS.md #53). Then it takes the keyboard from a
    click (Qt's `ClickFocus`), never from Tab."""

    def ink_links(self) -> None:
        """Its links in the theme's text colour, underlined as Qt draws
        them - not Qt's own blue, 2:1 on the dark theme's cards
        (polyglotic-hq 377). In the markup: under a stylesheet a label's
        palette doesn't reach its links. Again whenever the window is
        styled again: a theme change."""
        text = self.text()
        if "<a " not in text:
            return
        ink = style.current()["TEXT"]
        inked = _LINK.sub(f"<a style='color:{ink}' ", text)
        if inked != text:
            self.setText(inked)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() is QEvent.Type.StyleChange:
            self.ink_links()

    def ready(self) -> None:
        """Selectable now, if it wasn't."""
        flags = self.textInteractionFlags()
        if not flags & Qt.TextInteractionFlag.TextSelectableByMouse:
            self.setTextInteractionFlags(
                flags | Qt.TextInteractionFlag.TextSelectableByMouse
            )

    def enterEvent(self, event: QEnterEvent) -> None:
        self.ready()
        super().enterEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.ready()  # a press with no hover before it (a pen, a test)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        event.accept()
        menu = menu_for(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.popup(event.globalPos())


def words(found: QLabel) -> str:
    """All of `found`'s words, as the learner reads them (no markup)."""
    text = found.text()
    if found.textFormat() is Qt.TextFormat.RichText or (
        found.textFormat() is Qt.TextFormat.AutoText and QtGui.Qt.mightBeRichText(text)
    ):
        return QTextDocumentFragment.fromHtml(text).toPlainText()
    return text


def menu_for(found: QLabel) -> QMenu:
    """The right-click menu on `found`: Copy, Select all. Made, not shown."""
    return selection_menu(found, lambda: copy_label(found), lambda: select_all(found))


def selection_menu(
    parent: QWidget, copy: Callable[[], None], select_all: Callable[[], None]
) -> QMenu:
    """A right-click menu on selectable text: Copy and Select all, in the
    interface language - a label's, the transcript's. Made, not shown."""
    menu = QMenu(parent)
    menu.addAction(_tr("Copy"), copy)
    menu.addAction(_tr("Select all"), select_all)
    return menu


def select_all(found: QLabel) -> None:
    if isinstance(found, Text):
        found.ready()
    found.setSelection(0, len(words(found)))


def copy_label(found: QLabel) -> None:
    """What's selected in `found` to the clipboard - all of it when nothing
    is."""
    text = found.selectedText() or words(found)
    if text:
        QGuiApplication.clipboard().setText(text)


def copy_quietly(text: str, at: QPoint | None, over: QWidget) -> None:
    """`text` to the clipboard - nowhere else - and "Copied to clipboard" in
    a themed toast near `at` (or the bottom of `over`'s window when None):
    what a right-click on a selection or Ctrl+C does on a window that never
    takes the keyboard. No menu: a menu would take the mouse until it closed,
    and over a game that's the game's."""
    QGuiApplication.clipboard().setText(text)
    say_copied(at, over)


def copied() -> str:
    """ "Copied", in the interface language: compact button confirmation."""
    return _tr("Copied")


def copied_to_clipboard() -> str:
    """ "Copied to clipboard", in the interface language: toast confirmation."""
    return _tr("Copied to clipboard")


def saved_feedback() -> str:
    """ "Saved", in the interface language: toast confirmation after saving a caption."""
    return _tr("Saved")


def say_copied(at: QPoint | None, over: QWidget) -> None:
    """Show the themed "Copied to clipboard" toast near `at` (or the bottom
    of `over`'s window when `at` is None)."""
    show_toast(copied_to_clipboard(), over, at)


TYPING = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
"""Widgets a key typed into is text."""


def copy_key_is_ours(event: QKeyEvent) -> bool:
    """`event` is Ctrl+C for a window that never has the keyboard (a
    caption window's selection): pressed while one of this app's windows
    has it, but not into a text field, nor where words are selected of
    their own (a label, a transcript: `hasSelectedText`) - Ctrl+C there
    copies those."""
    if not event.matches(QKeySequence.StandardKey.Copy) or event.isAutoRepeat():
        return False
    focus = QApplication.focusWidget()
    if isinstance(focus, TYPING):
        return False
    own = getattr(focus, "hasSelectedText", None)
    return not (callable(own) and own())


def _x(line: QTextLine, at: int) -> float:
    """Where on `line` the place `at` in its text is drawn."""
    return cast(tuple[float, int], line.cursorToX(at))[0]


@dataclass(frozen=True)
class Painted:
    """A piece of text a window paints: `layout` drawn with its top left at
    `at`. Pieces with the same `line` are on one line - joined with a
    space when copied - and others with a new line."""

    text: str
    layout: QTextLayout
    at: QPointF
    line: int


Spot = tuple[int, int]
"""Where in painted text: (the piece's index, a place in its text)."""


class TextSelection:
    """A selection across a window's painted text (`Painted`, in reading
    order): `start` where the mouse is pressed, `extend` as it drags; then
    the words selected (`text`) and where to paint them as selected
    (`highlights`). It holds what's shown: never log it."""

    def __init__(self) -> None:
        self.pieces: list[Painted] = []
        self.anchor: Spot | None = None
        self.head: Spot | None = None

    def use(self, pieces: Sequence[Painted]) -> None:
        """The text painted now; a selection stays only if its text is the
        same as before (laid out again, say, for a speaker's state)."""
        if [(p.text, p.line) for p in pieces] != [
            (p.text, p.line) for p in self.pieces
        ]:
            self.clear()
        self.pieces = list(pieces)

    def clear(self) -> None:
        self.anchor = self.head = None

    @property
    def empty(self) -> bool:
        return self.anchor is None or self.anchor == self.head

    def on_text(self, pos: QPointF) -> bool:
        """`pos` is on painted text (for the mouse's I-beam)."""
        return any(rect.contains(pos) for _, _, rect in self._lines())

    def start(self, pos: QPointF) -> None:
        self.anchor = self.head = self._spot(pos)

    def extend(self, pos: QPointF) -> None:
        if self.anchor is not None:
            self.head = self._spot(pos)

    def ranges(self) -> list[tuple[int, int, int]]:
        """(piece, from, to) for each piece with something selected."""
        if self.anchor is None or self.head is None or self.empty:
            return []
        first, last = sorted((self.anchor, self.head))
        found = []
        for index in range(first[0], last[0] + 1):
            begin = first[1] if index == first[0] else 0
            end = last[1] if index == last[0] else len(self.pieces[index].text)
            if begin < end:
                found.append((index, begin, end))
        return found

    def text(self) -> str:
        """What's selected, as it reads: a space within a line, a new line
        between lines."""
        said = ""
        line: int | None = None
        for index, begin, end in self.ranges():
            piece = self.pieces[index]
            if line is not None:
                said += " " if piece.line == line else "\n"
            said += piece.text[begin:end]
            line = piece.line
        return said

    def highlights(self) -> list[QRectF]:
        """Where the selection is painted, line by line."""
        found = []
        for index, begin, end in self.ranges():
            piece = self.pieces[index]
            for number in range(piece.layout.lineCount()):
                line = piece.layout.lineAt(number)
                low = max(begin, line.textStart())
                high = min(end, line.textStart() + line.textLength())
                if low >= high:
                    continue
                left, right = _x(line, low), _x(line, high)
                found.append(
                    QRectF(
                        piece.at.x() + min(left, right),
                        piece.at.y() + line.y(),
                        abs(right - left),
                        line.height(),
                    )
                )
        return found

    def _lines(self) -> list[tuple[int, int, QRectF]]:
        """(piece, its line's number, where that line is) for every line."""
        found = []
        for index, piece in enumerate(self.pieces):
            for number in range(piece.layout.lineCount()):
                line = piece.layout.lineAt(number)
                rect = QRectF(
                    piece.at.x() + line.x(),
                    piece.at.y() + line.y(),
                    line.naturalTextWidth(),
                    line.height(),
                )
                found.append((index, number, rect))
        return found

    def _spot(self, pos: QPointF) -> Spot | None:
        """The place in the text nearest `pos`: on the nearest line (above
        or below it, the nearest by height; beside it, by width), at the
        character the mouse is at."""
        lines = self._lines()
        if not lines:
            return None

        def distance(entry: tuple[int, int, QRectF]) -> tuple[float, float]:
            rect = entry[2]
            down = max(rect.top() - pos.y(), 0.0, pos.y() - rect.bottom())
            across = max(rect.left() - pos.x(), 0.0, pos.x() - rect.right())
            return down, across

        index, number, _ = min(lines, key=distance)
        piece = self.pieces[index]
        line = piece.layout.lineAt(number)
        return index, line.xToCursor(pos.x() - piece.at.x())
