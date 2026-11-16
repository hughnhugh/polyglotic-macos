"""A list of words as a table (Words, polyglotic-hq project 109's section
7): one painted row per word - the headword over its reading, the short
meaning over the row's details, and the row's actions as buttons -
as tall as its rows, so the page scrolls and never the table. A row's
text is looked up when it first shows (`views.words.WordRows`), so a long
list costs no more to open than a short one. Painted at paint time in the
window's theme (`style.current()`), the text elided to its cell.

Click a word (or its meaning) to look it up, an action to do it; with the
keyboard, the arrows move between cells and Enter or Space does what a
click would. What's clicked is said (`acted`); the page does it.

**Several words at once** (polyglotic-hq 342; the user, 2026-11-15:
"should be a faster way to multiselect known words"): Shift-click a second
row to pick every row between it and the last one clicked, Ctrl-click to
add or take away one - neither does the cell's action; with the keyboard,
Shift and the arrows, Ctrl+Space and Ctrl+A; Esc lets them go. The rows
picked are shaded, and with two or more the page shows a `SelectionBar`
with what can be done to them all.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QItemSelection,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QPainter,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QWidget,
)

from polyglotic_desktop.core.learning.saved_words import Category
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ui_next import fonts, style
from polyglotic_desktop.ui_next.controls import wrapped
from polyglotic_desktop.ui_next.views.words import WordRows, WordText

ROW = 46
"""A word's row: the headword over its reading. This and the widths below
are at 100 % text size: each grows with the text (`style.px`)."""
WORD_WIDTH = 150
NARROW_WORD_WIDTH = 116
WIDE_TABLE = 600
"""A table narrower than this has the narrower word column."""
LEAST_MEANING = 56
LEAST_WORD = 72
LEAST_CATEGORY = 72
"""Where a table is too narrow for its columns - a large text size at the
main window's narrowest - the word column, then the category's, narrow to
these (their words elided), then Add to deck's and Known's to their
longest word (the button's words on two lines), so the meaning keeps at
least LEAST_MEANING and nothing goes past the table's edge (polyglotic-hq
354)."""
HEADWORD_PX = 17
CJK_FAMILIES = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    *fonts.also("zh"),
    *style.UI_FAMILIES,
]
PAD = 10
BUTTON_PAD = 24
"""An action's button: its words and the padding either side."""
ARROW = "▾"
"""A menu's mark, at a status's or a category's right."""


def _tr(text: str) -> str:
    return QApplication.translate("Words", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("Words", text, None, n)


def _known_button() -> str:
    """The Known column's button - not the status "Known": in Chinese one
    is "认识" (mark it), the other "已认识" (it is)."""
    return QApplication.translate("Words", "Known", "a button: mark the word known")


class Column(StrEnum):
    """What a column of a word table shows - or does, when clicked."""

    WORD = "word"  # the headword (in its category's colour dot) over its reading
    MEANING = "meaning"  # the short meaning over the row's details
    ADD = "add"  # Add to deck
    KNOWN = "known"  # Known
    STATUS = "status"  # the word's status: a menu of the others
    CATEGORY = "category"  # a saved word's category: a menu of the others
    REMOVE = "remove"  # remove from the saved words


ROOT = QModelIndex()
"""A table's rows have no parent: the model's root."""

ACTIONS = (Column.ADD, Column.KNOWN, Column.STATUS, Column.CATEGORY, Column.REMOVE)


def status_name(status: WordStatus) -> str:
    return {
        WordStatus.NEW: _tr("New"),
        WordStatus.LEARNING: _tr("In your deck"),
        WordStatus.KNOWN: _tr("Known"),
        WordStatus.IGNORED: _tr("Ignored"),
    }[status]


@dataclass(frozen=True, slots=True)
class Item:
    """One row of a word table: the word, the row's details, and what its
    action columns show. `own`: the status was set by the learner (not
    estimated from the level); `sentence`: the line it was saved from (the
    lookup's context)."""

    entry_id: EntryId
    details: str
    status: WordStatus | None = None
    own: bool = True
    category: Category | None = None
    sentence: str = ""


class WordModel(QAbstractTableModel):
    """A word table's rows. The text of each is the dictionary's, looked up
    when the row is first painted (`WordRows`)."""

    def __init__(self, columns: Sequence[Column], rows: WordRows) -> None:
        super().__init__()
        self.columns = tuple(columns)
        self.words = rows
        self.items: list[Item] = []

    def set_items(self, items: list[Item]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = ROOT) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = ROOT) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def column(self, index: QModelIndex | QPersistentModelIndex) -> Column:
        return self.columns[index.column()]

    def text(self, index: QModelIndex | QPersistentModelIndex) -> WordText | None:
        return self.words.text(self.items[index.row()].entry_id)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> object:
        if not index.isValid():
            return None
        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.AccessibleTextRole,
        ):
            return self.shown(index)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.tip(index)
        return None

    def shown(self, index: QModelIndex | QPersistentModelIndex) -> str:
        """What a cell says: its words, or its action's."""
        item = self.items[index.row()]
        column = self.column(index)
        text = self.text(index)
        if column is Column.WORD:
            return text.headword if text else ""
        if column is Column.MEANING:
            return text.meaning if text else ""
        if column is Column.ADD:
            return _tr("Add to deck")
        if column is Column.KNOWN:
            return _known_button()
        if column is Column.STATUS and item.status is not None:
            return status_name(item.status)
        if column is Column.CATEGORY:
            return item.category.name if item.category else ""
        if column is Column.REMOVE:
            return _tr("Remove")
        return ""

    def tip(self, index: QModelIndex | QPersistentModelIndex) -> str:
        item = self.items[index.row()]
        column = self.column(index)
        if column is Column.WORD:
            return _tr("Look it up")
        if column is Column.MEANING:
            text = self.text(index)
            return text.meaning if text else ""
        if column is Column.STATUS:
            return (
                _tr("Change its status")
                if item.own
                else _tr("Estimated from your level - pick one to set it yourself")
            )
        if column is Column.CATEGORY:
            return _tr("Move it to another category")
        if column is Column.REMOVE:
            return _tr("Remove from your saved words")
        return ""


def _font(base: QFont, px: int, families: list[str] | None = None) -> QFont:
    font = QFont(base)
    font.setPixelSize(style.px(px))  # at Windows' text size
    if families:
        font.setFamilies(families)
    return font


class WordDelegate(QStyledItemDelegate):
    """Paints a word table's cells in the window's theme, at paint time:
    text elided to its cell, an action as a quiet button."""

    def __init__(self, table: "WordTable") -> None:
        super().__init__(table)
        self.table = table

    def sizeHint(
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(style.px(WORD_WIDTH), style.px(ROW))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        model = self.table.words
        rect = QRect(option.rect)
        column = model.column(index)
        item = model.items[index.row()]
        state = option.state
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        focused = self.table.hasFocus() and self.table.currentIndex() == index
        base = QFont(self.table.font())
        painter.save()
        if self.table.picked(index.row()):  # one of several picked (342)
            shade = QColor(style.current()["ACCENT"])
            shade.setAlphaF(0.18)
            painter.fillRect(rect, shade)
        if column in ACTIONS:
            self._button(painter, rect, model.shown(index), column, hovered, focused)
        elif column is Column.WORD:
            self._word(painter, rect, model.text(index), item, base, hovered, focused)
        else:
            text = model.text(index)
            meaning = text.meaning if text else ""
            self._two_lines(painter, rect, meaning, item.details, base)
        painter.restore()

    def _word(
        self,
        painter: QPainter,
        rect: QRect,
        text: WordText | None,
        item: Item,
        base: QFont,
        hovered: bool,
        focused: bool,
    ) -> None:
        theme = style.current()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inner = rect.adjusted(2, 3, -4, -3)
        if hovered or focused:
            painter.setPen(QColor(theme["FOCUS"]) if focused else Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme["SURFACE_2"]))
            painter.drawRoundedRect(inner, 6, 6)
        left = inner.left() + 6
        if item.category is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(item.category.color))
            painter.drawEllipse(left, inner.top() + 10, 8, 8)
            left += 14
        if text is None:
            return
        families = CJK_FAMILIES if self.table.chinese else None
        headword = _font(base, HEADWORD_PX, families)
        width = inner.right() - left - 4
        painter.setFont(headword)
        painter.setPen(QColor(theme["TEXT"]))
        metrics = QFontMetrics(headword)
        top = QRect(left, inner.top() + 1, width, metrics.height())
        painter.drawText(
            top,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(text.headword, Qt.TextElideMode.ElideRight, width),
        )
        reading = _font(base, 12)
        painter.setFont(reading)
        painter.setPen(QColor(theme["TEXT_DIM"]))
        small = QFontMetrics(reading)
        below = QRect(left, top.bottom() + 1, width, small.height())
        painter.drawText(
            below,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            small.elidedText(text.reading, Qt.TextElideMode.ElideRight, width),
        )

    def _two_lines(
        self,
        painter: QPainter,
        rect: QRect,
        first: str,
        second: str,
        base: QFont,
    ) -> None:
        """`first` in the text's colour over `second`, smaller and fainter,
        centred in the row."""
        theme = style.current()
        inner = rect.adjusted(PAD, 4, -PAD, -4)
        width = inner.width()
        lines = [(first, _font(base, 13), theme["TEXT"])]
        if second:
            lines.append((second, _font(base, 12), theme["TEXT_FAINT"]))
        height = sum(QFontMetrics(f).height() for _, f, _c in lines)
        y = inner.top() + max(0, (inner.height() - height) // 2)
        for text, font, ink in lines:
            metrics = QFontMetrics(font)
            painter.setFont(font)
            painter.setPen(QColor(ink))
            painter.drawText(
                QRect(inner.left(), y, width, metrics.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(text, Qt.TextElideMode.ElideRight, width),
            )
            y += metrics.height()

    def _button(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        column: Column,
        hovered: bool,
        focused: bool,
    ) -> None:
        if not text:
            return
        theme = style.current()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = _font(self.table.font(), 13)
        metrics = QFontMetrics(font)
        menu = column in (Column.STATUS, Column.CATEGORY)
        shown = "✕" if column is Column.REMOVE else text
        if menu:  # as wide as its column, so the menus line up
            width = rect.width() - 8
        else:
            width = min(rect.width() - 8, metrics.horizontalAdvance(shown) + BUTTON_PAD)
        high = style.px(28)
        two = not menu and metrics.horizontalAdvance(shown) > width - BUTTON_PAD
        if two:  # a narrow column (`fitted`): its words on two lines, not cut
            shown = wrapped(shown, font, width - BUTTON_PAD)
            lines = shown.count("\n") + 1
            high = min(rect.height() - 2, max(high, lines * metrics.height() + 8))
        button = QRect(
            rect.right() - width - 4, rect.center().y() - high // 2, width, high
        )
        painter.setPen(QColor(theme["FOCUS"] if focused else theme["BORDER"]))
        painter.setBrush(QColor(theme["SURFACE_3" if hovered else "SURFACE_2"]))
        painter.drawRoundedRect(button, 7, 7)
        painter.setFont(font)
        painter.setPen(QColor(theme["TEXT"]))
        inside = button.adjusted(BUTTON_PAD // 2, 0, -(BUTTON_PAD // 2), 0)
        if menu:
            arrow = metrics.horizontalAdvance(ARROW)
            painter.drawText(
                inside,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                ARROW,
            )
            inside.setRight(inside.right() - arrow - 6)
        painter.drawText(
            inside,
            Qt.AlignmentFlag.AlignVCenter
            | (Qt.AlignmentFlag.AlignLeft if menu else Qt.AlignmentFlag.AlignHCenter),
            shown
            if two
            else metrics.elidedText(shown, Qt.TextElideMode.ElideRight, inside.width()),
        )


def _action_width(texts: Sequence[str], font: QFont, more: str = "") -> int:
    """An action column: its widest words, the button's padding, a gap."""
    metrics = QFontMetrics(_font(font, 13))
    return max(metrics.horizontalAdvance(t + more) for t in texts) + BUTTON_PAD + 12


TWO_LINES = {Column.ADD: lambda: _tr("Add to deck"), Column.KNOWN: _known_button}
"""The actions whose button's words go onto two lines in a narrow column."""


def fitted(
    widths: dict[Column, int], least: dict[Column, int], room: int
) -> dict[Column, int]:
    """`widths` (every column but the meaning's) narrowed to leave the
    meaning at least LEAST_MEANING of `room`: the word column first, then
    the category's, then the two-line actions' - each down to its `least`.
    Where there's room, as given."""
    fitted = dict(widths)
    over = sum(fitted.values()) + style.px(LEAST_MEANING) - room
    for column in (Column.WORD, Column.CATEGORY, *TWO_LINES):
        if over <= 0 or column not in fitted:
            continue
        cut = min(over, max(0, fitted[column] - least.get(column, fitted[column])))
        fitted[column] -= cut
        over -= cut
    return fitted


class WordTable(QTableView):
    """A list of words, one painted row each, as tall as its rows (the page
    scrolls, not the table). Click a word to look it up, an action to do
    it; with the keyboard, the arrows move between cells and Enter or
    Space does what a click would."""

    acted = Signal(str, str, QRect)
    """(the column, the entry ID, the cell on the screen)."""
    picked_changed = Signal(int)
    """How many rows are picked now (342): a bar shows from two."""

    def __init__(
        self, name: str, columns: Sequence[Column], rows: WordRows, chinese: bool
    ) -> None:
        super().__init__()
        self.setObjectName(name)
        self.chinese = chinese
        self.words = WordModel(columns, rows)
        self.setModel(self.words)
        self.setItemDelegate(WordDelegate(self))
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setDefaultSectionSize(style.px(ROW))
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setFrameShape(QTableView.Shape.NoFrame)
        # rows picked together (342): Shift and Ctrl, by mouse or keyboard
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setTabKeyNavigation(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # rows picked are shaded by the delegate, not Qt's own highlight
        self.setStyleSheet(
            "QTableView { background: transparent; border: none;"
            " selection-background-color: transparent; }"
        )
        header = self.horizontalHeader()
        header.setMinimumSectionSize(36)
        for i, column in enumerate(self.words.columns):
            header.setSectionResizeMode(
                i,
                QHeaderView.ResizeMode.Stretch
                if column is Column.MEANING
                else QHeaderView.ResizeMode.Fixed,
            )
        self._size_columns()
        self.clicked.connect(self._clicked)
        self.selectionModel().selectionChanged.connect(self._picking)
        self.fit()

    def _size_columns(self) -> None:
        """Each action column as wide as its words in the font the window's
        stylesheet gives the table (known once it's polished) - the word
        and category columns narrower where the table has no room for
        them all (`fitted`)."""
        header = self.horizontalHeader()
        widths: dict[Column, int] = {
            column: self._width(column)
            for column in self.words.columns
            if column is not Column.MEANING
        }
        if Column.MEANING in self.words.columns:
            widths = fitted(widths, self._least(), self.width())
        for i, column in enumerate(self.words.columns):
            if column in widths:
                header.resizeSection(i, widths[column])

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            # the window restyled - at another text size, perhaps
            self.verticalHeader().setDefaultSectionSize(style.px(ROW))
            self.setFixedHeight(max(1, len(self.words.items)) * style.px(ROW))
            self._size_columns()

    def showEvent(self, event: QShowEvent) -> None:
        self._size_columns()
        super().showEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        if event.size().width() != event.oldSize().width():
            self._size_columns()  # the word column's width follows the table's
        super().resizeEvent(event)

    def _width(self, column: Column) -> int:
        font = self.font()
        if column is Column.WORD:  # narrower at the window's minimum
            wide = self.width() >= style.px(WIDE_TABLE)
            return style.px(WORD_WIDTH if wide else NARROW_WORD_WIDTH)
        if column is Column.ADD:
            return _action_width([_tr("Add to deck")], font)
        if column is Column.KNOWN:
            return _action_width([_known_button()], font)
        if column is Column.STATUS:
            return _action_width([status_name(s) for s in WordStatus], font, "  ▾ ")
        if column is Column.CATEGORY:
            return style.px(150)
        return style.px(48)  # Remove: ✕

    def set_items(self, items: list[Item]) -> None:
        """The rows. Words picked stay picked where they're still listed:
        the list is shown again as captions come in, and a learner picking
        words shouldn't lose them to it (342)."""
        picked = set(self.picked_entries())
        self.words.set_items(items)
        self.fit()
        if picked:
            model, flags = self.selectionModel(), self.selectionModel().SelectionFlag
            for row, item in enumerate(items):
                if item.entry_id in picked:
                    model.select(self.words.index(row, 0), flags.Select | flags.Rows)
        self.picked_changed.emit(len(self.selectionModel().selectedRows()))

    def fit(self) -> None:
        """As tall as its rows: the page scrolls, never the table."""
        self.setFixedHeight(max(1, len(self.words.items)) * style.px(ROW))
        self.setVisible(bool(self.words.items))

    def sizeHint(self) -> QSize:
        return QSize(style.px(320), self.height())

    def _least(self) -> dict[Column, int]:
        """Each column but the meaning's at its narrowest (`fitted`)."""
        least: dict[Column, int] = {}
        for column in self.words.columns:
            width = self._width(column)
            if column is Column.WORD:
                width = min(width, style.px(LEAST_WORD))
            elif column is Column.CATEGORY:
                width = min(width, style.px(LEAST_CATEGORY))
            elif column in TWO_LINES:
                words = TWO_LINES[column]().split()
                width = min(width, _action_width(words, self.font()))
            if column is not Column.MEANING:
                least[column] = width
        return least

    def minimumSizeHint(self) -> QSize:
        """Its columns at their narrowest (`fitted`), and never under 240."""
        width = sum(self._least().values()) + style.px(LEAST_MEANING)
        return QSize(max(style.px(240), width), self.height())

    def _clicked(self, index: QModelIndex) -> None:
        held = QApplication.keyboardModifiers()
        if held & (
            Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
        ):
            return  # picking rows, not doing the cell's action (342)
        self.act(index)

    # -- rows picked together (342) ---------------------------------------------------

    def picked(self, row: int) -> bool:
        """Whether row `row` is one of two or more picked: one alone is
        only the row last clicked, and isn't shaded."""
        model = self.selectionModel()
        return model.isRowSelected(row) and len(model.selectedRows()) > 1

    def picked_entries(self) -> list[EntryId]:
        """The entries of the rows picked, top to bottom."""
        rows = sorted(i.row() for i in self.selectionModel().selectedRows())
        return [self.words.items[r].entry_id for r in rows if r < len(self.words.items)]

    def let_go(self) -> None:
        """No row picked any more."""
        self.clearSelection()

    def _picking(self, _new: QItemSelection, _old: QItemSelection) -> None:
        self.viewport().update()
        self.picked_changed.emit(len(self.selectionModel().selectedRows()))

    def act(self, index: QModelIndex) -> None:
        """What a click on cell `index` does: said by `acted`."""
        if not index.isValid():
            return
        column = self.words.column(index)
        if column is Column.MEANING:
            column = Column.WORD  # the whole word is the lookup's
            index = index.siblingAtColumn(self.words.columns.index(Column.WORD))
        cell = self.visualRect(index)
        on_screen = QRect(self.viewport().mapToGlobal(cell.topLeft()), cell.size())
        entry = self.words.items[index.row()].entry_id
        self.acted.emit(column.value, str(entry), on_screen)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        held = event.modifiers()
        ctrl = bool(held & Qt.KeyboardModifier.ControlModifier)
        if event.key() == Qt.Key.Key_Space and ctrl:  # pick or let go of a row
            current = self.currentIndex()
            if current.isValid():
                flags = (
                    self.selectionModel().SelectionFlag.Toggle
                    | self.selectionModel().SelectionFlag.Rows
                )
                self.selectionModel().select(current, flags)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.act(self.currentIndex())
            return
        if event.key() == Qt.Key.Key_Escape and self.selectionModel().hasSelection():
            self.let_go()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        if not self.currentIndex().isValid() and self.words.items:
            self.setCurrentIndex(self.words.index(0, 0))
        super().focusInEvent(event)

    def item(self, entry_id: str) -> Item | None:
        for item in self.words.items:
            if item.entry_id == entry_id:
                return item
        return None


class SelectionBar(QWidget):
    """What can be done to several words picked in a list at once (342):
    how many, a button for each action, and "Clear". Hidden until two or
    more are picked; the page gives it the actions that make sense for its
    list and does them (`chosen`)."""

    chosen = Signal(str)
    """An action's key, as given to `add`."""

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(8)
        self.count = QLabel(self)
        self.count.setObjectName("Dim")
        self.row.addWidget(self.count)
        self.row.addStretch(1)
        self.buttons: dict[str, QPushButton] = {}
        self.clear = self._button("", _tr("Clear"), "ghost")
        self.row.addWidget(self.clear)
        self.hide()

    def add(self, key: str, text: str, kind: str = "") -> QPushButton:
        """An action, before "Clear"."""
        button = self._button(key, text, kind)
        self.row.insertWidget(self.row.count() - 1, button)
        return button

    def _button(self, key: str, text: str, kind: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(f"{self.objectName()}.{key or 'clear'}")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if kind:
            button.setProperty("kind", kind)
        button.clicked.connect(lambda _=False, k=key: self.chosen.emit(k))
        self.buttons[key] = button
        return button

    def show_count(self, count: int) -> None:
        """`count` words picked: said, and the bar shown from two."""
        self.count.setText(_trn("%Ln word(s) picked", count))
        self.setVisible(count > 1)
