"""The list a spoken language is chosen from - one list, one wording,
wherever the choice is: a caption window's settings, Settings > Speech, a
transcript's rail (polyglotic-hq 317, decision 0108).

At the top, **Detect automatically**, saying what it covers ("Any of the
30 languages below"); under **Always hear as**,
every language the speech model can be told (`core.listening.spoken`):
the ones named last first, then the learner's own (Windows' languages),
then the rest by name - each by the interface's name and its own,
"Russian · Русский" (`languages.spoken_choice_text`).

`searchable`: a box over the list finds a language by any of its names or
its code, as it's typed ("russ", "рус", "espanol"). A caption window's
settings never take the keyboard - a full-screen game behind them could
minimise - so theirs has no box; its list is short enough to scroll, the
recent ones on top.

**Made when first opened, not before** (`open`): the main window's pages
are all built at start, and the start is measured (polyglotic-hq 314).
Each opening puts the recent languages first again.

`SpokenPicker` is the list behind a chip that shows the choice made, for
Settings and a transcript's rail: the caption window's settings popover
has its own chip (`settings_popover`), in its row's style.
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.spoken import SPOKEN_LANGUAGES
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.languages import (
    detect_covers,
    detect_name,
    detect_short,
    find_placeholder,
    named_heading,
    named_short,
    none_found,
    spoken_choice_text,
    spoken_matches,
    spoken_order,
)

LIST_HEIGHT = 220
"""The list's height at 100 % text size: it grows with the text."""
DETECT = ""
"""Detect's item's data (a language's is its code)."""
HEADING = "heading"
"""What a heading item is, in its `Qt.UserRole + 1`."""


def _tr(text: str) -> str:
    return QApplication.translate("SpokenList", text)


def chip_text(code: str | None) -> str:
    """The choice made, as a chip shows it: "Detect · 30 languages", or
    "Always Russian"."""
    return named_short(code) if code else detect_short(len(SPOKEN_LANGUAGES))


class SpokenLanguageList(QWidget):
    """Detect and every spoken language, the choice made ticked; `chosen`
    with a language's code, or None for Detect. Hidden, and empty, until
    `open`."""

    chosen = Signal(object)

    def __init__(
        self,
        parent: QWidget,
        searchable: bool,
        recent: Callable[[], Sequence[str]] = tuple,
        own: Sequence[str] | None = None,
        dim: str | None = None,
    ) -> None:
        """`recent`: the languages named last, newest first; `own`: the
        learner's languages (None: Windows'); `dim`: the headings' colour
        (None: the palette's placeholder text's)."""
        super().__init__(parent)
        self.setObjectName("spoken_list")
        self.searchable = searchable
        self.recent = recent
        self.own = own
        self.dim = dim
        self.current: str | None = None
        self.search: QLineEdit | None = None
        self.items: QListWidget | None = None
        self.nothing: QLabel | None = None
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.hide()

    @property
    def built(self) -> bool:
        return self.items is not None

    def _build(self) -> None:
        column = self.layout()
        assert isinstance(column, QVBoxLayout)
        if self.searchable:
            self.search = QLineEdit(self)
            self.search.setObjectName("spoken_list.find")
            self.search.setPlaceholderText(find_placeholder())
            self.search.setAccessibleName(find_placeholder())
            self.search.setClearButtonEnabled(True)
            self.search.textChanged.connect(self._filter)
            self.search.returnPressed.connect(self._first_found)
            column.addWidget(self.search)
        self.items = QListWidget(self)
        self.items.setObjectName("spoken_list.items")
        self.items.setAccessibleName(_tr("Spoken language"))
        self.items.setMaximumHeight(style.px(LIST_HEIGHT))
        self.items.setMinimumHeight(style.px(LIST_HEIGHT) // 2)
        self.items.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.items.setWordWrap(True)  # a long name wraps: never a sideways scroll
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.itemClicked.connect(self._clicked)
        self.items.itemActivated.connect(self._clicked)  # Enter, in Settings
        if not self.searchable:  # a caption window's: never the keyboard
            self.items.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        column.addWidget(self.items)
        self.nothing = QLabel(none_found(), self)
        self.nothing.setObjectName("spoken_list.nothing")
        self.nothing.setProperty("note", True)
        self.nothing.hide()
        column.addWidget(self.nothing)

    def _heading(self, text: str) -> QListWidgetItem:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # not a choice
        item.setData(Qt.ItemDataRole.UserRole + 1, HEADING)
        if self.dim:
            item.setForeground(QColor(self.dim))
        return item

    def _fill(self) -> None:
        """The items, in today's order (the recent ones may have changed)."""
        assert self.items is not None
        self.items.clear()
        count = len(SPOKEN_LANGUAGES)
        detect = QListWidgetItem(f"{detect_name()}\n{detect_covers(count)}")
        detect.setData(Qt.ItemDataRole.UserRole, DETECT)
        self.items.addItem(detect)
        self.items.addItem(self._heading(named_heading()))
        order = spoken_order(SPOKEN_LANGUAGES, tuple(self.recent()), self.own)
        for code in order:
            item = QListWidgetItem(spoken_choice_text(code))
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.items.addItem(item)

    def open(self, current: str | None) -> None:
        """Shown, made if it wasn't, with `current` (None: Detect) ticked
        and in view; the box (if any) empty and given the keyboard."""
        if not self.built:
            self._build()
        self._fill()
        self.show()
        if self.search is not None:
            self.search.clear()
            self.search.setFocus(Qt.FocusReason.OtherFocusReason)
        self.set_current(current)

    def close_list(self) -> None:
        self.hide()

    def set_current(self, code: str | None) -> None:
        """`code` ticked (None: Detect), and scrolled to."""
        self.current = code
        if self.items is None:
            return
        wanted = code or DETECT
        for index in range(self.items.count()):
            item = self.items.item(index)
            if item.data(Qt.ItemDataRole.UserRole + 1) == HEADING:
                continue
            if item.data(Qt.ItemDataRole.UserRole) == wanted:
                self.items.setCurrentItem(item)
                self.items.scrollToItem(item)
                return

    def codes_shown(self) -> list[str]:
        """The choices showing now, in order ("" for Detect)."""
        if self.items is None:
            return []
        return [
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in (self.items.item(i) for i in range(self.items.count()))
            if item.data(Qt.ItemDataRole.UserRole + 1) != HEADING
            and not item.isHidden()
        ]

    def _filter(self, typed: str) -> None:
        """Only the languages `typed` finds (Detect too while nothing is)."""
        assert self.items is not None and self.nothing is not None
        searching = bool(typed.strip())
        found = 0
        for index in range(self.items.count()):
            item = self.items.item(index)
            code = item.data(Qt.ItemDataRole.UserRole)
            if item.data(Qt.ItemDataRole.UserRole + 1) == HEADING or code == DETECT:
                item.setHidden(searching)
            else:
                hidden = not spoken_matches(str(code), typed)
                item.setHidden(hidden)
                found += not hidden
        self.nothing.setVisible(searching and not found)

    def _first_found(self) -> None:
        """Enter in the box: the first language found."""
        shown = self.codes_shown()
        if self.search is not None and self.search.text().strip() and shown:
            self.chosen.emit(shown[0] or None)

    def _clicked(self, item: QListWidgetItem) -> None:
        if item.data(Qt.ItemDataRole.UserRole + 1) == HEADING:
            return
        code = str(item.data(Qt.ItemDataRole.UserRole))
        self.chosen.emit(code or None)


class SpokenPicker(QWidget):
    """The spoken language for Settings and a transcript's rail: a chip
    showing the choice made, the searchable list under it while it's
    open. `changed` with a language's code, or None for Detect."""

    changed = Signal(object)

    def __init__(
        self,
        value: str | None,
        recent: Callable[[], Sequence[str]] = tuple,
        own: Sequence[str] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("languages.spoken")
        self._value = value
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        self.chip = QPushButton(self)
        self.chip.setObjectName("languages.spoken_button")
        self.chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chip.setAccessibleName(_tr("Spoken language"))
        self.chip.clicked.connect(self.toggle)
        line.addWidget(self.chip)
        line.addStretch(1)
        column.addLayout(line)
        self.list = SpokenLanguageList(self, searchable=True, recent=recent, own=own)
        self.list.setMaximumWidth(style.px(420))
        self.list.chosen.connect(self._chosen)
        column.addWidget(self.list)
        self._show_value()

    def value(self) -> str | None:
        """The choice made: a language's code, or None for Detect."""
        return self._value

    def _show_value(self) -> None:
        arrow = "▾" if self.list.isHidden() else "▴"
        self.chip.setText(f"{chip_text(self._value)} {arrow}")

    def set_value(self, value: str | None) -> None:
        """The choice as it is now (a change elsewhere): shown, not said."""
        self._value = value
        self.list.set_current(value)
        self._show_value()

    def toggle(self) -> None:
        if not self.list.isHidden():
            self.list.close_list()
        else:
            self.list.open(self._value)
        self._show_value()

    def choose(self, code: str | None) -> None:
        """`code` chosen (None: Detect), as a click on it in the list."""
        self._chosen(code)

    def _chosen(self, code: str | None) -> None:
        self.list.close_list()
        changed = code != self._value
        self._value = code
        self._show_value()
        if self.isVisible():
            self.chip.setFocus(Qt.FocusReason.OtherFocusReason)
        if changed:
            self.changed.emit(code)
