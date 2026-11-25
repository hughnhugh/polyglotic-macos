"""The new interface's small standard controls: a card, a setting's row, a
row of choices, a switch, a colour choice, a status dot and a button that
opens one of our web pages in the browser.

Like today's `ui.widgets` (which this package can't import - decision
0031), with the same object names, so a window's stylesheet
(`style.stylesheet`) dresses them; nothing has a fixed width, so a card
fits a 320 px popover and a 720 px column alike (109's 10.5). The switch
and the dot paint themselves in the theme's colours at paint time.
"""

import math
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QFontMetricsF,
    QIcon,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
    QResizeEvent,
    QShowEvent,
    QTextLayout,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLayout,
    QLayoutItem,
    QMenu,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpacerItem,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui_next import glyphs, style
from polyglotic_desktop.ui_next.copying import Measured, Text


def page_button(text: str, url: str, name: str) -> QPushButton:
    """A button that opens `url` - a page of our website, such as the privacy
    notice - in the learner's browser; never shown inside the app, so the
    app and the site can't say different things (polyglotic-hq 185). Today's
    dialogs have the same, `ui.widgets.page_button`."""
    button = QPushButton(text)
    button.setObjectName(name)
    button.setProperty("url", url)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(QApplication.translate("Pages", "Opens in your browser"))
    button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
    return button


class Flow(QLayout):
    """A row that wraps (polyglotic-hq 354): its items left to right, and
    what doesn't fit on the next line - so a row of buttons, or a title and
    the choices beside it, fits the main window at its narrowest in every
    language and text size instead of making the page scroll sideways.

    Each line is as tall as its tallest item, the others centred in it. An
    item that wraps its own words (a label with word wrap, a `WrapButton`)
    is as wide as its words if they fit on a line, else the line's width.
    `add_stretch` is the room a line has to spare, given out as a
    QHBoxLayout's stretch is: on the line it falls on, it pushes what
    follows to the right (a stretch at the start of a line is nothing);
    a line with no stretch gives it to its items added with a stretch, if
    any. The least width is the widest item's least. `right`: each line's
    spare room on its left (a row of buttons at a card's right)."""

    def __init__(
        self,
        parent: QWidget | None = None,
        spacing: int = 8,
        line_spacing: int = 6,
        right: bool = False,
    ) -> None:
        super().__init__(parent)
        self._right = right
        self._items: list[QLayoutItem] = []
        self._stretch: dict[int, int] = {}  # id(item) -> its stretch
        self._spacing = spacing
        self._line_spacing = line_spacing
        self._heights: dict[int, int] = {}  # by width, until it's invalidated
        self._least: QSize | None = None
        self._placed = 0  # the width it was last laid out at
        self._height_placed = 0
        self.setContentsMargins(0, 0, 0, 0)

    # -- QLayout -------------------------------------------------------------

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)
        self.invalidate()

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        """`widget` at the line's end; with `stretch`, it takes a share of a
        line's spare room when the line has no `add_stretch`."""
        self.addWidget(widget)
        if stretch:
            self._stretch[id(self._items[-1])] = stretch

    def add_stretch(self, stretch: int = 1) -> None:
        spacer = QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self.addItem(spacer)
        self._stretch[id(spacer)] = stretch

    def add_layout(self, layout: QLayout, stretch: int = 0) -> QWidget:
        """`layout` as one item, in a widget of its own (returned), its
        margins none: a layout held straight in a layout written in Python
        was deleted twice as its window closed (a crash, 354)."""
        holder = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(layout)
        self.add_widget(holder, stretch)
        return holder

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if not 0 <= index < len(self._items):
            return None
        item = self._items.pop(index)
        self._stretch.pop(id(item), None)
        self.invalidate()
        return item

    def setSpacing(self, spacing: int) -> None:
        self._spacing = spacing
        self.invalidate()

    def spacing(self) -> int:
        return self._spacing

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if width not in self._heights:  # asked thousands of times a restyle
            self._heights[width] = self._lay_out(QRect(0, 0, width, 0), place=False)
        return self._heights[width]

    def invalidate(self) -> None:
        self._heights.clear()
        self._least = None
        super().invalidate()

    def sizeHint(self) -> QSize:
        """All on one line - as tall as its lines are at its width now, so
        a widget of fixed height holding it is as tall as they are."""
        shown = self._shown()
        width = sum(item.sizeHint().width() for item in shown)
        width += self._spacing * max(0, len(shown) - 1)
        height = max((item.sizeHint().height() for item in shown), default=0)
        hint = QSize(width, height) + self._margins()
        if 0 < self._placed < hint.width():
            hint.setHeight(self.heightForWidth(self._placed))
        return hint

    def minimumSize(self) -> QSize:
        if self._least is None:
            shown = self._shown()
            width = max((item.minimumSize().width() for item in shown), default=0)
            height = max((item.minimumSize().height() for item in shown), default=0)
            self._least = QSize(width, height) + self._margins()
        return QSize(self._least)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        height = self._lay_out(rect, place=True)
        if rect.width() != self._placed and height != self._height_placed:
            self._placed, self._height_placed = rect.width(), height
            self.invalidate()  # its size hint's height follows its lines
        self._placed = rect.width()

    # -- the lines -----------------------------------------------------------

    def _margins(self) -> QSize:
        m = self.contentsMargins()
        return QSize(m.left() + m.right(), m.top() + m.bottom())

    def _shown(self) -> list[QLayoutItem]:
        """The items that take room: shown widgets, layouts (stretches
        take none until a line has room to spare)."""
        return [
            item
            for item in self._items
            if not item.isEmpty() and item.spacerItem() is None
        ]

    def _width(self, item: QLayoutItem, room: int) -> int:
        least = item.minimumSize().width()
        return max(least, min(item.sizeHint().width(), room))

    def _height(self, item: QLayoutItem, width: int) -> int:
        if item.hasHeightForWidth():
            height = item.heightForWidth(width)
        else:
            height = item.sizeHint().height()
        return max(height, item.minimumSize().height())

    def _lines(self, room: int) -> list[list[QLayoutItem]]:
        """The items (stretches among them) on each line, at `room` wide."""
        lines: list[list[QLayoutItem]] = [[]]
        used = 0
        for item in self._items:
            if item.spacerItem() is not None:
                lines[-1].append(item)
                continue
            if item.isEmpty():
                continue
            width = self._width(item, room)
            taken = [i for i in lines[-1] if i.spacerItem() is None]
            if taken and used + self._spacing + width > room:
                lines.append([])
                used = 0
                taken = []
            used += width + (self._spacing if taken else 0)
            lines[-1].append(item)
        return lines

    def _lay_out(self, rect: QRect, place: bool) -> int:
        """Places the items in `rect` (if `place`); its height either way."""
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        room = max(0, area.width())
        y = area.y()
        first = True
        for line in self._lines(room):
            items = [i for i in line if i.spacerItem() is None]
            if not items:
                continue
            # a stretch counts only between two of the line's items
            start = line.index(items[0])
            end = line.index(items[-1])
            spacers = [i for i in line[start : end + 1] if i.spacerItem() is not None]
            widths = {id(i): self._width(i, room) for i in items}
            spare = room - sum(widths.values()) - self._spacing * (len(items) - 1)
            stretched = [i for i in items if self._stretch.get(id(i))]
            extra = self._share(spare, spacers + stretched, line)
            for item in items:
                widths[id(item)] += extra[id(item)]
            heights = {id(i): self._height(i, widths[id(i)]) for i in items}
            tall = max(heights.values())
            if not first:
                y += self._line_spacing
            first = False
            if place:
                x = area.x()
                if self._right and not any(extra.values()):
                    x += max(0, spare)
                for item in line[start : end + 1]:
                    if item.spacerItem() is not None:
                        x += extra[id(item)]
                        continue
                    if item.isEmpty():
                        continue
                    width, height = widths[id(item)], heights[id(item)]
                    top = y + (tall - height) // 2
                    if item.alignment() & Qt.AlignmentFlag.AlignTop:
                        top = y
                    item.setGeometry(QRect(x, top, width, height))
                    x += width + self._spacing
            y += tall
        return y - area.y() + m.top() + m.bottom()

    def _share(
        self, spare: int, takers: list[QLayoutItem], line: list[QLayoutItem]
    ) -> dict[int, int]:
        """A line's `spare` room, given out to `takers` by their stretch, as
        a QHBoxLayout does: an item no wider than its maximum, what it
        can't take going to the stretches."""
        extra = {id(i): 0 for i in line}
        left = [i for i in takers if self._stretch.get(id(i))]
        while spare > 0 and left:
            total = sum(self._stretch[id(i)] for i in left)
            given, full = 0, []
            for item in left:
                part = spare * self._stretch[id(item)] // total
                if item.spacerItem() is None:
                    most = item.maximumSize().width() - item.sizeHint().width()
                    room = max(0, most - extra[id(item)])
                    if part >= room:
                        part = room
                        full.append(item)
                extra[id(item)] += part
                given += part
            spare -= given
            left = [i for i in left if i not in full]
            if not full:  # all given but the rounding's few px: to the last
                if left:
                    extra[id(left[-1])] += spare
                break
        return extra


def least_width(text: str, font: QFont) -> int:
    """The widest piece of `text` a line can't break inside, in `font`: a
    word - or, in Chinese or Japanese, a character (Unicode's line breaking,
    as Qt does it)."""
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    layout.setTextOption(option)
    widest = 0.0
    layout.beginLayout()
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(0)  # one piece a line
        widest = max(widest, line.naturalTextWidth())
    layout.endLayout()
    return math.ceil(widest)


def wrapped(text: str, font: QFont, width: int) -> str:
    """`text` broken into lines `width` px wide in `font`: at spaces, and
    inside a word only when it's wider than a line (Chinese and Japanese
    break between any characters)."""
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    lines = []
    layout.beginLayout()
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1, width))
        lines.append(text[line.textStart() : line.textStart() + line.textLength()])
    layout.endLayout()
    return "\n".join(each.rstrip() for each in lines)


class _Wraps:
    """Wrap a button's words onto more lines when the button narrows.
    The least width is the longest word's. `text()` stays the words as given
    (a screen reader, the tests); only the painting breaks them. Its height
    follows its lines (`sizeHint` at its width now), so a layout gives it
    the lines' height and no more."""

    _element = QStyle.ControlElement.CE_PushButton
    _lines = 1

    def _one_line(self) -> QSize:
        raise NotImplementedError

    def _button(self) -> QAbstractButton:
        assert isinstance(self, QAbstractButton)
        return self

    def _room(self, width: int) -> int:
        """The words' width in a button `width` px wide: less its padding
        (and a check box's box), as its one-line size has them."""
        button = self._button()
        words = QFontMetrics(button.font()).horizontalAdvance(button.text())
        return max(1, width - (self._one_line().width() - words))

    def _wrapped(self, width: int) -> str:
        button = self._button()
        return wrapped(button.text(), button.font(), self._room(width))

    def _setup(self) -> None:
        button = self._button()
        policy = button.sizePolicy()
        if policy.horizontalPolicy() == QSizePolicy.Policy.Minimum:  # Qt's own
            policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)  # may narrow
        policy.setHeightForWidth(True)
        button.setSizePolicy(policy)

    def sizeHint(self) -> QSize:
        one = self._one_line()
        button = self._button()
        width = button.width()
        # laid out yet? A child's width is Qt's 100 px until it is
        if width >= one.width() or not button.isVisible():
            return one
        return QSize(one.width(), self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        button = self._button()
        one = self._one_line()
        metrics = QFontMetrics(button.font())
        padding = one.width() - metrics.horizontalAdvance(button.text())
        word = least_width(button.text(), button.font())
        return QSize(min(one.width(), word + padding), one.height())

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        one = self._one_line()
        if width >= one.width():
            return one.height()
        button = self._button()
        key = (button.text(), button.font().key(), one.toTuple(), width)
        heights: dict[object, int] = button.__dict__.setdefault("_wrap_heights", {})
        if key not in heights:  # a restyle asks thousands of times
            if len(heights) > 32:
                heights.clear()
            lines = self._wrapped(width).count("\n") + 1
            spacing = QFontMetrics(button.font()).lineSpacing()
            heights[key] = one.height() + (lines - 1) * spacing
        return heights[key]

    def resizeEvent(self, event: QResizeEvent) -> None:
        button = self._button()
        super().resizeEvent(event)  # type: ignore[misc]  # the Qt class's
        lines = self.heightForWidth(button.width())
        if lines != self._lines:  # taller or shorter: the layout asks again
            self._lines = lines
            button.updateGeometry()

    def paintEvent(self, event: QPaintEvent) -> None:
        button = self._button()
        if button.width() >= self._one_line().width():
            super().paintEvent(event)  # type: ignore[misc]
            return
        option = QStyleOptionButton()
        button.initStyleOption(option)  # type: ignore[attr-defined]
        option.text = self._wrapped(button.width())
        painter = QStylePainter(button)
        painter.drawControl(self._element, option)
        painter.end()


class WrapButton(_Wraps, QPushButton):
    """A push button whose words wrap onto more lines when it's narrower
    than them (polyglotic-hq 354): a whole sentence on a switch, a help
    topic - never cut, never pushing the page wider than the window."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._setup()

    def _one_line(self) -> QSize:
        return QPushButton.sizeHint(self)


class WrapCheckBox(_Wraps, QCheckBox):
    """A check box whose words wrap, as `WrapButton`'s do."""

    _element = QStyle.ControlElement.CE_CheckBox

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._setup()

    def _one_line(self) -> QSize:
        return QCheckBox.sizeHint(self)


class WrapRadioButton(_Wraps, QRadioButton):
    """A radio button whose label wraps at narrow widths."""

    _element = QStyle.ControlElement.CE_RadioButton

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._setup()

    def _one_line(self) -> QSize:
        return QRadioButton.sizeHint(self)

    def hitButton(self, pos: QPoint) -> bool:
        if self.width() < self._one_line().width():
            # Qt's native hit area can cover only the unwrapped line.
            return self.rect().contains(pos)
        return super().hitButton(pos)


def right_row(*buttons: QWidget) -> Flow:
    """`buttons` at a row's right - and onto more lines, still at the
    right, where the room runs out (polyglotic-hq 354)."""
    row = Flow(right=True)
    for button in buttons:
        row.addWidget(button)
    return row


def label(
    text: str = "", role: str | None = None, wrap: bool = False, copyable: bool = True
) -> Measured:
    """A label; `role` is its object name for the stylesheet (`Dim`,
    `Faint`, `CardTitle`, ...) - and its `role` property, which the
    stylesheet reads too for the quieter roles (`style.QUIET_ROLES`), so a
    note given a name of its own afterwards (`setObjectName`, for a test or
    the lab) stays the note it was: eleven such notes drew at the full
    text colour and size (polyglotic-hq 403). Its words can be selected and copied
    (`copying.Text`) - `copyable=False` only for a label inside
    something a click anywhere on works, such as Home's rows of apps to
    add, where a selectable label would take the click; and not for a
    window that never takes the keyboard (a caption window's settings),
    where its menu would take the mouse from the game under it. Wrapped,
    its lines keep to a readable length (`copying.Measured`)."""
    found = Text(text) if copyable else Measured(text)
    if isinstance(found, Text):
        found.ink_links()  # a link in the text: readable on the theme (377)
    if role:
        found.setObjectName(role)
        found.setProperty("role", role)
    found.setWordWrap(wrap)
    return found


@contextmanager
def focus_kept(within: QWidget) -> Iterator[None]:
    """Rows inside `within` made again - a language's card on Learning, a
    category's row on Words - with the keyboard where it was: on the same
    control of the row made again (or the same one, not made again), found
    by its object name and which of its parts had the keyboard (a
    `Segmented`'s choice); with none, on nothing. Wrap the making again in
    it; each old row is hidden as it goes.

    Qt hands the keyboard of a widget that hides to the next control along,
    and a page scrolls that one into view: as each old card hid in turn,
    Learning ran down to about its middle at every setting changed
    (polyglotic-hq 480). Taken from the old control before its row hides,
    the keyboard is handed to nothing; given to the new one, nothing
    scrolls - the page stays where it was. The window's keyboard, active or
    not: one made again behind a dialog (Change your level's) has it back
    on the same control when the dialog closes."""
    focused = within.window().focusWidget()
    place = _place(focused, within) if focused is not None else None
    if focused is None or place is None:
        yield
        return
    name, part = place
    focused.clearFocus()
    yield
    again = _named(within, name)
    if len(again) != 1:
        return  # gone with its row, or not one to be sure of
    found: QWidget | None = again[0]
    if part >= 0:
        parts = again[0].findChildren(QWidget)
        found = parts[part] if part < len(parts) else None
    if found is not None and type(found) is type(focused):
        found.setFocus(Qt.FocusReason.OtherFocusReason)


def _place(focused: QWidget, within: QWidget) -> tuple[str, int] | None:
    """Where `focused` is inside `within`: the object name of the nearest
    widget at or above it that no other in `within` has, and which of that
    one's widgets it is (-1: that one). None: not inside `within`, or under
    no such name (a label's role, a card's "Card")."""
    if not within.isAncestorOf(focused):
        return None
    named = focused
    while not named.objectName():
        parent = named.parentWidget()
        if parent is None or parent is within:
            return None
        named = parent
    same = _named(within, named.objectName())
    if len(same) != 1 or same[0] is not named:
        return None
    part = -1 if named is focused else named.findChildren(QWidget).index(focused)
    return named.objectName(), part


def _named(within: QWidget, name: str) -> list[QWidget]:
    """The widgets called `name` in `within` that show, or will once they're
    shown - not one in a row hidden as it goes (it's deleted later), nor
    one hidden on purpose. A row just made isn't shown until the event loop
    comes round, and a second making again can come first: "Mark known"
    shows the page twice in one click."""
    found = []
    for each in within.findChildren(QWidget, name):
        widget: QWidget | None = each
        while widget is not None and widget is not within:
            if widget.isHidden() and widget.testAttribute(
                Qt.WidgetAttribute.WA_WState_ExplicitShowHide
            ):
                break
            widget = widget.parentWidget()
        else:
            found.append(each)
    return found


class Card(QFrame):
    """A titled card: a column of rows."""

    def __init__(
        self, title: str = "", subtitle: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.column = QVBoxLayout(self)
        self.column.setContentsMargins(14, 14, 14, 14)
        self.column.setSpacing(10)
        self.title = label(title, "CardTitle") if title else None
        if self.title is not None:
            self.column.addWidget(self.title)
        self.subtitle = label(subtitle, "Dim", wrap=True) if subtitle else None
        if self.subtitle is not None:
            self.column.addWidget(self.subtitle)

    def add(self, item: QWidget | QLayout) -> None:
        if isinstance(item, QWidget):
            self.column.addWidget(item)
        else:
            self.column.addLayout(item)


class Row(QWidget):
    """One setting: its title and what it does, with its control under them
    (`beside`: at their right), so the row fits any width. Its words start
    at INSET, as a `SwitchRow`'s do. `tip`: what it does when the title
    says enough to use it - on hover and to a screen reader, not under it
    (151's P2, 176: one sentence at most under a control)."""

    def __init__(
        self,
        title: str,
        detail: str,
        control: QWidget,
        beside: bool = False,
        tip: str = "",
    ) -> None:
        super().__init__()
        self.control = control
        if tip:
            tipped(self, control, tip)
        words = QVBoxLayout()
        words.setContentsMargins(1, 0, 0, 0)  # with the control's border: INSET
        words.setSpacing(2)
        self.title = label(title, "RowTitle", wrap=True)
        words.addWidget(self.title)
        self.detail = label(detail, "Faint", wrap=True)
        if not detail:  # hidden, never shown: shown before it has a parent, a
            self.detail.hide()  # label is a window of its own for a moment
        words.addWidget(self.detail)
        if beside:
            line = QHBoxLayout(self)
            line.setContentsMargins(INSET - 1, 0, 0, 0)
            line.setSpacing(12)
            line.addLayout(words, 1)
            line.addWidget(control, 0, Qt.AlignmentFlag.AlignTop)
        else:
            column = QVBoxLayout(self)
            column.setContentsMargins(INSET - 1, 0, 0, 0)
            column.setSpacing(6)
            column.addLayout(words)
            column.addWidget(control)


class Segmented(QFrame):
    """A row of choices, one at a time - a handful that should all stay in
    view rather than in a dropdown. Each choice is a Tab stop: the one-at-a-
    time rule is kept here, not by an exclusive button group (which Qt
    makes a single Tab stop, reached only at its checked choice). Its
    choices wrap onto a second line where the room runs out (`Flow`), as
    in a long language at the main window's narrowest (polyglotic-hq 354)."""

    changed = Signal(object)

    def __init__(
        self, options: Sequence[tuple[object, str]], value: object = None
    ) -> None:
        super().__init__()
        self.setProperty("segmented", True)  # its name is free for tests
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        # as wide as its choices on one line at most; narrower, they wrap
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._values = [v for v, _ in options]
        row = Flow(self, spacing=2, line_spacing=2)
        row.setContentsMargins(3, 3, 3, 3)
        self.buttons: list[QPushButton] = []
        for index, (_, text) in enumerate(options):
            button = self._make_button(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._clicked(i))
            self.buttons.append(button)
            row.addWidget(button)
        self.set_value(value)

    def showEvent(self, event: QShowEvent) -> None:
        """Measure polished buttons before the first visible layout settles."""
        super().showEvent(event)
        self._remeasure_buttons()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Keep a wrapped row tall enough after each width reflow."""
        super().resizeEvent(event)
        self._remeasure_buttons()

    def _make_button(self, text: str) -> QPushButton:
        return QPushButton(text)

    def changeEvent(self, event: QEvent) -> None:
        """Remeasure the fixed-height frame after its buttons are restyled."""
        super().changeEvent(event)
        if event.type() is QEvent.Type.StyleChange:
            # A parent's style reaches this frame before it reaches the buttons.
            # Measure on the next event-loop turn, once their new hints are known.
            QTimer.singleShot(0, self._remeasure_after_style)

    def _remeasure_after_style(self) -> None:
        self._remeasure_buttons()

    def _remeasure_buttons(self) -> None:
        if (row := self.layout()) is None:
            return
        # A platform style can change a button's hint when it is polished,
        # without sending this already-measured parent a StyleChange.  Ask the
        # real buttons after polish, rather than trusting Flow's construction-
        # time cache.  Include the frame around the layout's contents.
        for button in self.buttons:
            button.ensurePolished()
        row.invalidate()
        width = max(0, self.contentsRect().width())
        required = (
            max(
                row.minimumSize().height(),
                row.sizeHint().height(),
                row.heightForWidth(width),
            )
            + 2 * self.frameWidth()
        )
        if self.minimumHeight() != required:
            self.setMinimumHeight(required)
            self.updateGeometry()

    def _clicked(self, index: int) -> None:
        self.set_value(self._values[index])  # a click on the chosen one keeps it
        self.changed.emit(self._values[index])

    def set_value(self, value: object) -> None:
        if value not in self._values:
            return
        chosen = self._values.index(value)
        for index, button in enumerate(self.buttons):
            button.setChecked(index == chosen)

    def value(self) -> object:
        for index, button in enumerate(self.buttons):
            if button.isChecked():
                return self._values[index]
        return None

    def choose(self, value: object) -> None:
        """Picks `value` as a click would."""
        self.buttons[self._values.index(value)].click()


INSET = 9
"""Where every row's words start inside its card or popover: a button's
border and padding - so titles, notes, buttons and ticked choices line up."""
TICK = 16
"""The column a ticked choice's tick sits in, before its words (at 100 %
text size: it grows with the tick, `style.px`)."""
SWITCH = (28, 16)
"""The on / off switch's size: on, it's filled with the accent."""
DROP = "▾"
"""What marks a control that opens a list: a chip's ("EN ▾") and a
`Combo`'s alike."""
DROP_ROOM = 22
"""The room a `Combo` keeps at its right for `DROP` (at 100 % text size)."""
DROP_INSET = 10
"""...and how far in from the box's right edge the mark ends: a field's
own padding, so it sits where a chip's does."""


def _ink(given: tuple[str, ...] | None, tokens: tuple[str, ...]) -> list[QColor]:
    """The colours given, or the theme's now."""
    if given is not None:
        return [QColor(c) for c in given]
    theme = style.current()
    return [QColor(theme[t]) for t in tokens]


class TickButton(QPushButton):
    """A row button: a checked, checkable one with the property `tick` has
    a tick in the column before its words (`TICK`), so ticked and unticked
    rows line up. `ink`: (accent, dim) - the theme's if not given."""

    def __init__(
        self, parent: QWidget | None = None, ink: tuple[str, str] | None = None
    ) -> None:
        super().__init__(parent)
        self.ink = ink

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if not (self.property("tick") and self.isCheckable() and self.isChecked()):
            return
        accent, dim = _ink(self.ink, ("ACCENT", "TEXT_DIM"))
        painter = QPainter(self)
        painter.setPen(accent if self.isEnabled() else dim)
        painter.drawText(
            QRectF(INSET, 0, style.px(TICK), self.height()),
            Qt.AlignmentFlag.AlignVCenter,
            "✓",
        )
        painter.end()


class Combo(QComboBox):
    """A box that opens a list of choices, marked as the chips are - `DROP`
    at its right, in its text's colour - where Qt's own style draws a
    bevelled arrow box that pokes past the field's rounded border
    (polyglotic-hq 376, 403). The stylesheet leaves the arrow's room empty
    (`QComboBox[drop="own"]`); this draws the mark in it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("drop", "own")

    def drop_rect(self) -> QRectF:
        """Where the mark is drawn: the arrow's room, its right edge the
        field's padding in from the box's."""
        room = style.px(DROP_ROOM)
        return QRectF(self.width() - room, 0, room - DROP_INSET, self.height())

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        group = (
            QPalette.ColorGroup.Normal
            if self.isEnabled()
            else QPalette.ColorGroup.Disabled
        )
        painter = QPainter(self)
        painter.setPen(self.palette().color(group, QPalette.ColorRole.Text))
        painter.drawText(
            self.drop_rect(),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            DROP,
        )
        painter.end()


LABEL_GAP = 6
"""Between a choice's icon and its name, as Qt's stylesheet style draws a
`Combo`'s label (CE_ComboBoxLabel: its rule's `spacing`, 6 when none is
set) - where Qt's own measure of the box allows 4."""


class FittingCombo(Combo):
    """A `Combo` whose width is its own (a fixed size policy): its widest
    choice fits as it's drawn, at the text size now. Qt's measure
    (`QComboBox.sizeHint`) takes a name's ink, a pixel or two inside its
    advance in Chinese, and 4 px beside an icon where the label is drawn
    6 px from it: at the largest text size Settings' sections dropdown cut
    "應用程式" (App, Traditional Chinese) 2 px short (polyglotic-hq 500).
    Measured again whenever a choice changes (`AdjustToContents`)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        drawn, measured = QFontMetricsF(self.font()), self.fontMetrics()
        icon = self.iconSize().width()
        needed = held = 0
        for index in range(self.count()):
            name = self.itemText(index)
            beside = not self.itemIcon(index).isNull()
            advance = math.ceil(drawn.horizontalAdvance(name))
            needed = max(needed, advance + (icon + LABEL_GAP if beside else 0))
            ink = measured.boundingRect(name).width()
            held = max(held, ink + (icon + 4 if beside else 0))  # Qt's own
        return QSize(hint.width() + max(0, needed - held), hint.height())


class GlyphButton(QToolButton):
    """A small button whose face is one of the interface's own drawn icons
    (`glyphs`), in the theme's colours at paint time: dim, the accent while
    checked, faint while off to clicks. Home's "show my speech in this
    window" was the 🎤 emoji as the button's text - Windows' colour emoji
    font in one place, a drawn mic on the caption window in another
    (polyglotic-hq 403). `ink`: (dim, accent, faint) - the theme's if not
    given."""

    GLYPH = 14
    """The icon's square (at 100 % text size)."""
    TARGET = 24
    """Its least height, a target WCAG 2.5.8 accepts: a Mac's smaller font
    made it 23 px (polyglotic-hq 421)."""

    def __init__(
        self,
        glyph: glyphs.Glyph,
        parent: QWidget | None = None,
        ink: tuple[str, str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.glyph, self.ink = glyph, ink

    def sizeHint(self) -> QSize:
        """As wide as the icon font's glyph made a button (`glyphs.text_width`)
        with the stylesheet's padding either side; as tall as a chip beside
        it, and never under a target's least height (`TARGET`)."""
        side = style.px(self.GLYPH)
        height = max(max(self.fontMetrics().height(), side) + 2 * 3 + 2, self.TARGET)
        return QSize(glyphs.text_width(side) + 2 * 6 + 2, height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)  # the frame; there is no text
        dim, accent, faint = _ink(self.ink, ("TEXT_DIM", "ACCENT", "TEXT_FAINT"))
        color = faint if not self.isEnabled() else accent if self.isChecked() else dim
        side = style.px(self.GLYPH)
        box = QRectF(0, 0, side, side)
        box.moveCenter(QRectF(self.rect()).center())
        painter = QPainter(self)
        glyphs.paint(painter, self.glyph, box, color)
        painter.end()


class SwitchButton(WrapButton):
    """A row button with an on / off switch at its right: on, filled with
    the accent and the knob at the right. The whole row is the switch; its
    words wrap when the row is narrower than them (`WrapButton`).
    `ink`: (accent, dim, the knob on the accent) - the theme's if not given."""

    def __init__(
        self, parent: QWidget | None = None, ink: tuple[str, str, str] | None = None
    ) -> None:
        super().__init__("", parent)
        self.ink = ink
        self.setCheckable(True)
        self.setProperty("switch", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_quietly(self, on: bool) -> None:
        """Shows `on` without saying it changed (it was changed elsewhere)."""
        blocked = self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(blocked)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        accent, dim, knob_on = _ink(self.ink, ("ACCENT", "TEXT_DIM", "SURFACE"))
        if not self.isEnabled():
            accent.setAlphaF(0.4)
        width, height = SWITCH
        track = QRectF(
            self.width() - width - INSET, (self.height() - height) / 2, width, height
        )
        on = self.isChecked()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(accent if on else dim)
        painter.setBrush(accent if on else QColor(0, 0, 0, 0))
        painter.drawRoundedRect(track.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        knob = height - 6
        x = track.right() - 3 - knob if on else track.left() + 3
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_on if on else dim)
        painter.drawEllipse(QRectF(x, track.top() + 3, knob, knob))
        painter.end()


def tipped(row: QWidget, control: QWidget, tip: str) -> None:
    """`tip` on `row` and its control - or, when the control holds others
    (a slider and its value), each of them that takes the focus: on hover,
    and to a screen reader."""
    row.setToolTip(tip)
    held = [  # a selectable label takes it from a click only: not one of them
        w
        for w in control.findChildren(QWidget)
        if w.focusPolicy() & Qt.FocusPolicy.TabFocus
    ]
    for each in [control, *held]:
        if not each.toolTip():
            each.setToolTip(tip)
        if not each.accessibleDescription():
            each.setAccessibleDescription(tip)


class SwitchRow(QWidget):
    """A setting that is on or off: its title on a row-wide switch
    (`SwitchButton`), and what it does under it - or, with `tip`, on hover
    (as `Row`'s)."""

    def __init__(self, title: str, detail: str, name: str, tip: str = "") -> None:
        super().__init__()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)
        self.switch = SwitchButton(self)
        self.switch.setObjectName(name)
        self.switch.setText(title)
        if tip:
            tipped(self, self.switch, tip)
        column.addWidget(self.switch)
        self.detail = label(detail, "Faint", wrap=True)
        self.detail.setContentsMargins(INSET, 0, SWITCH[0] + INSET, 0)
        if not detail:  # hidden, never shown: shown before it has a parent, a
            self.detail.hide()  # label is a window of its own for a moment
        column.addWidget(self.detail)


def swatch(colour: str, size: int = 16) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(128, 128, 128, 160))
    painter.setBrush(QColor(colour))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pixmap)


class ColourChoice(QToolButton):
    """A colour, chosen from a few that read well: its swatch, and a menu of
    the others."""

    chosen = Signal(str)

    def __init__(self, choices: Sequence[str], colour: str, name: str) -> None:
        super().__init__()
        self.setObjectName(name)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.colour = ""
        menu = QMenu(self)
        for each in choices:
            action = menu.addAction(swatch(each), "")
            action.setObjectName(f"{name}.{each}")
            action.triggered.connect(lambda _=False, c=each: self.chosen.emit(c))
        self.setMenu(menu)
        self.show_colour(colour)

    def show_colour(self, colour: str) -> None:
        if colour != self.colour:
            self.colour = colour
            self.setIcon(swatch(colour))


PULSE_SEC = 1.2
"""One breath of a pulsing dot: from full to faint and back."""
PULSE_MS = 50
"""How often a pulsing dot repaints (20 a second: a 14 px dot, cheap)."""


def pulse_opacity(seconds: float) -> float:
    """A pulsing dot's opacity `seconds` into its pulse: 1.0 down to 0.35
    and back, smoothly, once every PULSE_SEC."""
    return 0.675 + 0.325 * math.cos(2 * math.pi * seconds / PULSE_SEC)


class StatusDot(QWidget):
    """A small dot in one of the theme's colours (`SUCCESS`, `WARNING`, ...)
    - or a colour of its own. Pulsing (`set_pulsing`), it breathes: the
    app is doing something (connecting)."""

    def __init__(self, token: str = "TEXT_FAINT", size: int = 10) -> None:
        super().__init__()
        self.token = token
        self.setFixedSize(size, size)
        self.opacity = 1.0
        self._pulse_started = 0.0
        self._pulse = QTimer(self, interval=PULSE_MS)
        self._pulse.timeout.connect(self._breathe)

    def set_pulsing(self, on: bool) -> None:
        if on == self._pulse.isActive():
            return
        if on:
            self._pulse_started = time.monotonic()
            self._pulse.start()
        else:
            self._pulse.stop()
            self.opacity = 1.0
            self.update()

    @property
    def pulsing(self) -> bool:
        return self._pulse.isActive()

    def _breathe(self) -> None:
        self.opacity = pulse_opacity(time.monotonic() - self._pulse_started)
        self.update()

    def set_token(self, token: str) -> None:
        if token != self.token:
            self.token = token
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        token = self.token
        colour = token if token.startswith("#") else style.current()[token]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colour))
        painter.setOpacity(self.opacity)  # alpha only: nothing moves
        painter.drawEllipse(self.rect())
        painter.end()
