"""Learning's card for the learning load (polyglotic-hq 324), shown while
the Lab's "Learning load" is on, for the language in use:

- **the load in one bar**: how many of its words are red, orange, yellow
  and green, how many are ready to check, and how many graduated in the
  last 7 days;
- **its words**, one list at a time: ready to check (each with "I know
  this" and "Not yet" - the one-click check, here and never over the
  captions), in the load (each with what it has been heard and needs, "I
  know this" and "Not now"), next to enter (each with "Add to my load"),
  and graduated;
- **several words at once** (polyglotic-hq 342): Shift-click picks every
  word between, Ctrl-click one more, the keyboard both (`views.picking`);
  then "I know these" and the list's other actions for them all;
- **feeding it**: "Add the next" 10, 25 or 50 words now;
- **its rules**: its size, the times heard that change a colour, what
  counts as hearing a word, and the most words in one colour.

It shows what it is given (`views.load.LoadView`) and says what the
learner asked; `main` does it.
"""

from dataclasses import replace

from PySide6.QtCore import QCoreApplication, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from polyglotic_desktop.core.learning.load import (
    ADD_SIZES,
    SIZES,
    STEPS,
    WEEK,
    Counting,
    LoadRules,
    Stage,
)
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import CJK_FAMILIES, LATIN_FAMILIES
from polyglotic_desktop.ui_next.caption_marks import STAGE_COLOURS, STAGE_COLOURS_LIGHT
from polyglotic_desktop.ui_next.controls import Card, Combo, Row, Segmented, label
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.load import (
    LIMITS,
    ROWS,
    Listed,
    LoadRow,
    LoadView,
)
from polyglotic_desktop.ui_next.views.picking import Picking
from polyglotic_desktop.ui_next.word_table import SelectionBar

PICKED_ACTIONS = {
    Listed.READY: ("check_known", "not_yet"),
    Listed.IN_LOAD: ("known", "not_now"),
    Listed.NEXT: ("known", "add"),
    Listed.GRADUATED: (),
}
"""What each list offers for several words picked at once (342): its own
actions for one word, and "I know these" for the words next to enter."""


def _tr(text: str) -> str:
    return QCoreApplication.translate("LearningLoad", text)


def _trn(text: str, n: int) -> str:
    return QCoreApplication.translate("LearningLoad", text, None, n)


def stage_name(stage: Stage) -> str:
    """A stage in words: its colour is never the only thing that says it."""
    return {
        Stage.RED: _tr("Red"),
        Stage.ORANGE: _tr("Orange"),
        Stage.YELLOW: _tr("Yellow"),
        Stage.GREEN: _tr("Green"),
        Stage.READY: _tr("Ready to check"),
    }[stage]


def stage_colours() -> tuple[str, ...]:
    """The four stages' colours on the window's theme: the captions' ramp
    for a dark panel, or for a light one."""
    return STAGE_COLOURS if style.current().dark else STAGE_COLOURS_LIGHT


def progress_text(row: LoadRow) -> str:
    """What a word in the load has been heard and needs, in words."""
    if row.stage is None:
        return ""
    return stage_text(row.stage, row.heard, row.step)


def stage_text(stage: Stage, heard: int, step: int) -> str:
    """A word in the load: its stage, and its meetings of those it needs
    - on Learning's card and on the word's own (the lookup card)."""
    if stage is Stage.READY:
        return stage_name(Stage.READY)
    if heard >= step > 0:
        return _tr("{colour}: waiting for room in the next colour").format(
            colour=stage_name(stage)
        )
    return _tr("{colour}: heard {heard} of {needed}").format(
        colour=stage_name(stage), heard=heard, needed=step
    )


def check_texts() -> tuple[str, str]:
    """The check's two answers, as every place that asks words them."""
    return _tr("I know this"), _tr("Not yet")


def add_text() -> str:
    return _tr("Add to my load")


class StageBar(QWidget):
    """The load as one bar: a part for each colour and one for the words
    ready to check, as wide as its share of the load's size; what is left
    is the room the load still has."""

    def __init__(self) -> None:
        super().__init__()
        self.counts: tuple[int, ...] = (0, 0, 0, 0, 0)
        self.size_of_load = 1
        self.setFixedHeight(style.px(12))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def show_counts(self, stages: tuple[int, ...], ready: int, size: int) -> None:
        self.counts = (*stages, ready)
        self.size_of_load = max(size, sum(self.counts), 1)
        self.update()

    def parts(self) -> list[tuple[float, float, str]]:
        """Each part's start and width as shares of the bar, and its colour."""
        theme = style.current()
        colours = (*stage_colours(), theme["TEXT"])
        found, at = [], 0.0
        for count, colour in zip(self.counts, colours, strict=True):
            share = count / self.size_of_load
            if share:
                found.append((at, share, colour))
            at += share
        return found

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        width, height = float(self.width()), float(self.height())
        painter.setBrush(QColor(style.current()["SURFACE_2"]))
        painter.drawRoundedRect(QRectF(0, 0, width, height), 3, 3)
        for at, share, colour in self.parts():
            painter.setBrush(QColor(colour))
            painter.drawRect(QRectF(at * width, 0, max(1.0, share * width), height))
        painter.end()


class LoadRows(QWidget):
    """The load's words, a row each, in a grid (`grid`); rows picked
    together by mouse and keyboard (`picking`, 342), shaded from two."""

    picked_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.grid = QGridLayout(self)
        self.picking = Picking()
        self.order: list[str] = []
        """The entries listed, top to bottom."""
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def show_order(self, order: list[str]) -> None:
        """The list shown again: what's picked stays where still listed."""
        self.order = order
        self.picking.keep(order)
        self.update()
        self.picked_changed.emit()

    def picked(self) -> list[str]:
        return self.picking.in_order(self.order)

    def let_go(self) -> None:
        self.picking.clear()
        self.update()
        self.picked_changed.emit()

    def row_rect(self, row: int) -> QRect:
        """Row `row` across the list's width, with half the gap either side."""
        cells = QRect()
        for column in range(self.grid.columnCount()):
            item = self.grid.itemAtPosition(row, column)
            if item is not None and (widget := item.widget()) is not None:
                cells = cells.united(widget.geometry())
        gap = self.grid.verticalSpacing() // 2
        return QRect(0, cells.top() - gap, self.width(), cells.height() + 2 * gap)

    def _row_at(self, at: QPoint) -> int | None:
        for row in range(len(self.order)):
            if self.row_rect(row).contains(at):
                return row
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        row = self._row_at(event.position().toPoint())
        if row is None or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        held = event.modifiers()
        self.picking.click(
            self.order[row],
            self.order,
            shift=bool(held & Qt.KeyboardModifier.ShiftModifier),
            ctrl=bool(held & Qt.KeyboardModifier.ControlModifier),
        )
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.update()
        self.picked_changed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key, held = event.key(), event.modifiers()
        shift = bool(held & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(held & Qt.KeyboardModifier.ControlModifier)
        picking = self.picking
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and self.order:
            picking.move(-1 if key == Qt.Key.Key_Up else 1, self.order, shift)
        elif key == Qt.Key.Key_A and ctrl:
            picking.all(self.order)
        elif key == Qt.Key.Key_Space and picking.current is not None:
            picking.toggle()
        elif key == Qt.Key.Key_Escape and picking.picked:
            picking.clear()
        else:
            super().keyPressEvent(event)
            return
        self.update()
        self.picked_changed.emit()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = style.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        shade = QColor(theme["ACCENT"])
        shade.setAlphaF(0.18)
        picked = self.picking.picked
        for row, key in enumerate(self.order):
            if len(picked) > 1 and key in picked:
                painter.fillRect(self.row_rect(row), shade)
            if self.hasFocus() and key == self.picking.current:
                painter.setPen(QColor(theme["FOCUS"]))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(self.row_rect(row).adjusted(0, 0, -1, -1), 4, 4)
        painter.end()


class LoadCard(Card):
    """The learning load on Learning."""

    rules_chosen = Signal(object)
    """The load's rules, changed (`LoadRules`)."""
    checked = Signal(str, bool)
    """The check's answer for a word: its entry and whether it is known."""
    known = Signal(str)
    """ "I know this" for a word in the load that isn't ready to check."""
    not_now = Signal(str)
    add_wanted = Signal(str)
    """ "Add to my load" for a word next to enter."""
    add_next_wanted = Signal(int)
    many_wanted = Signal(str, list)
    """An action for several words picked at once (342): `check_known`,
    `not_yet`, `known`, `not_now` or `add`, and their entries."""
    listed_chosen = Signal()
    """Another list, or more of this one, was asked for: show it again."""
    lab_wanted = Signal()
    """ "Settings > Lab", where the mode is turned on and off (342)."""

    def __init__(self) -> None:
        super().__init__(_tr("Learning load"))
        self.view: LoadView | None = None
        self.chinese = True
        self.rows = ROWS
        # where it's turned on, and off (342): it's experimental, and the
        # learner may not remember where they found it
        self.where = label(
            _tr("An experiment, turned on in {lab}, where you can turn it off.").format(
                lab=f"<a href='lab'>{_tr('Settings > Lab')}</a>"
            ),
            "Faint",
            wrap=True,
        )
        self.where.linkActivated.connect(lambda _: self.lab_wanted.emit())
        self.add(self.where)
        self.summary = label("", "Dim", wrap=True)
        self.summary.setObjectName("load.summary")
        self.add(self.summary)
        self.bar = StageBar()
        self.bar.setObjectName("load.bar")
        self.add(self.bar)
        self.by_stage = label("", "Faint", wrap=True)
        self.by_stage.setObjectName("load.by_stage")
        self.add(self.by_stage)

        self.lists = Segmented(
            [
                (Listed.READY, _tr("Ready to check")),
                (Listed.IN_LOAD, _tr("In the load")),
                (Listed.NEXT, _tr("Next to enter")),
                (Listed.GRADUATED, _tr("Graduated")),
            ],
            Listed.READY,
        )
        self.lists.setObjectName("load.lists")
        self.lists.setAccessibleName(_tr("Learning load"))
        self.lists.changed.connect(self._list_chosen)
        self.add(_left(self.lists))
        self.picked_bar = SelectionBar("load.picked")
        know = _tr("I know these")
        for key, text in (
            ("check_known", know),
            ("not_yet", check_texts()[1]),
            ("known", know),
            ("not_now", _tr("Not now")),
            ("add", add_text()),
        ):
            self.picked_bar.add(key, text)
        self.picked_bar.chosen.connect(self._for_picked)
        self.add(self.picked_bar)
        self.words = LoadRows()
        self.words.setObjectName("load.words")
        self.words.picked_changed.connect(self._picked_changed)
        self.grid = self.words.grid
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        self.add(self.words)
        self.none = label("", "Faint", wrap=True)
        self.none.setObjectName("load.none")
        self.add(self.none)
        self.more = _button(_tr("Show more"), "load.more", "ghost")
        self.more.clicked.connect(self._more)
        self.add(_left(self.more))

        adding = QWidget()
        buttons = QHBoxLayout(adding)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(6)
        self.add_next: list[QPushButton] = []
        for count in ADD_SIZES:
            button = _button(f"+{count}", f"load.add_next.{count}", "small")
            button.clicked.connect(
                lambda _=False, c=count: self.add_next_wanted.emit(c)
            )
            buttons.addWidget(button)
            self.add_next.append(button)
        self.add(
            Row(
                _tr("Add the next words now"),
                _tr("They come in ahead of graduations, and the load grows by them."),
                adding,
                beside=True,
            )
        )

        self.size_box = _combo("load.size", _tr("Words in the load"))
        self.size_box.activated.connect(self._rules_chosen)
        self.add(
            Row(
                _tr("Words in the load"),
                _tr(
                    "Raise it and the next words come in at once. Lower it and the "
                    "words heard least leave first; they keep their counts and "
                    "come back when there is room."
                ),
                self.size_box,
                beside=True,
            )
        )
        self.step = Segmented([(n, str(n)) for n in STEPS], 3)
        self.step.setObjectName("load.step")
        self.step.setAccessibleName(_tr("Times heard to change colour"))
        self.step.changed.connect(self._rules_chosen)
        self.add(
            Row(
                _tr("Times heard to change colour"),
                _tr(
                    "Red, orange, yellow, green: a word moves on each time it has "
                    "been heard this often, then is ready to check."
                ),
                self.step,
                beside=True,
            )
        )
        self.counting = _combo("load.counting", _tr("What counts as hearing a word"))
        for counting, text in (
            (Counting.EVERY, _tr("Every time it is said")),
            (Counting.CAPTION, _tr("Once a caption")),
            (Counting.SESSION, _tr("Once a session")),
            (Counting.DAY, _tr("Once a day")),
        ):
            self.counting.addItem(text, counting)
        self.counting.activated.connect(self._rules_chosen)
        self.add(
            Row(
                _tr("What counts as hearing a word"),
                pc_or_mac(
                    _tr(
                        "Only what your PC plays counts, in finished captions - not "
                        "what you say."
                    ),
                    _tr(
                        "Only what your Mac plays counts, in finished captions - not "
                        "what you say."
                    ),
                ),
                self.counting,
                beside=True,
            )
        )
        self.limit = _combo("load.limit", _tr("Most words in one colour"))
        for limit in LIMITS:
            self.limit.addItem(str(limit) if limit else _tr("No limit"), limit)
        self.limit.activated.connect(self._rules_chosen)
        self.add(
            Row(
                _tr("Most words in one colour"),
                _tr(
                    "For orange, yellow and green. When a colour is full, a word "
                    "waits in the one before it, the most heard first."
                ),
                self.limit,
                beside=True,
            )
        )

    # -- what it shows -------------------------------------------------------------

    @property
    def listed(self) -> Listed:
        value = self.lists.value()
        return value if isinstance(value, Listed) else Listed.READY

    def show_load(self, view: LoadView | None, chinese: bool = True) -> None:
        """The load now; None: the mode is off - the card hides."""
        self.view, self.chinese = view, chinese
        self.setVisible(view is not None)
        if view is None:
            return
        progress, rules = view.progress, view.rules
        self.summary.setText(
            _trn(
                "In your load: {words} of {size}. Ready to check: {ready}. Graduated in the last %Ln day(s): {week}.",
                WEEK.days,
            ).format(
                words=progress.words,
                size=progress.size,
                ready=progress.ready,
                week=progress.graduated_week,
            )
            if view.available
            else _tr(
                "This language's dictionary has no word frequencies yet, so it "
                "has no learning load."
            )
        )
        self.bar.show_counts(progress.stages, progress.ready, progress.size)
        self.by_stage.setText(
            "  ·  ".join(
                f"{stage_name(Stage(n))} {count}"
                for n, count in enumerate(progress.stages)
            )
        )
        for widget in (self.bar, self.by_stage, self.lists, self.words):
            widget.setVisible(view.available)
        self._show_rows(view)
        self._show_rules(rules)

    def _show_rows(self, view: LoadView) -> None:
        while (item := self.grid.takeAt(0)) is not None:
            if (old := item.widget()) is not None:
                old.hide()
                old.deleteLater()
        self.buttons: dict[tuple[str, str], QPushButton] = {}
        listed = self.listed
        for at, row in enumerate(view.rows):
            self._add_row(at, row, listed)
        self.none.setVisible(view.available and not view.rows)
        self.none.setText(_nothing(listed))
        self.more.setVisible(view.available and view.more > 0)
        offered = PICKED_ACTIONS[listed]
        for key, button in self.picked_bar.buttons.items():
            button.setVisible(not key or key in offered)
        self.words.show_order([row.entry_id for row in view.rows] if offered else [])

    def _add_row(self, at: int, row: LoadRow, listed: Listed) -> None:
        # not copyable: a press anywhere on a row picks it (342), and a
        # selectable label would take the press (343)
        word = label(
            row.word if not row.reading else f"{row.word}  {row.reading}",
            copyable=False,
        )
        word.setParent(self.words)
        word.setFont(self._word_font())
        if row.stage is not None and row.stage < Stage.READY:
            word.setStyleSheet(f"color: {stage_colours()[row.stage]};")
        word.setObjectName(f"load.word.{row.entry_id}")
        self.grid.addWidget(word, at, 0)
        needs = "" if listed is Listed.READY else progress_text(row)  # said by the list
        said = " - ".join(t for t in (row.meaning, needs) if t)
        about = label(said, "Faint", wrap=True, copyable=False)
        about.setParent(self.words)
        self.grid.addWidget(about, at, 1)
        offered: list[tuple[str, str]] = []
        if listed is Listed.READY:
            know, not_yet = check_texts()
            offered = [("know", know), ("not_yet", not_yet)]
        elif listed is Listed.IN_LOAD:
            offered = [("know", check_texts()[0]), ("not_now", _tr("Not now"))]
        elif listed is Listed.NEXT:
            offered = [("add", add_text())]
        for column, (what, text) in enumerate(offered, start=2):
            button = _button(text, f"load.{what}.{row.entry_id}", "small")
            button.setParent(self.words)
            button.setAccessibleName(f"{text}: {row.word}")
            button.clicked.connect(
                lambda _=False, w=what, e=row.entry_id, ready=listed is Listed.READY: (
                    self._asked(w, e, ready)
                )
            )
            self.buttons[(what, row.entry_id)] = button
            self.grid.addWidget(button, at, column)

    def _asked(self, what: str, entry_id: str, ready: bool) -> None:
        if what == "know" and ready:
            self.checked.emit(entry_id, True)
        elif what == "know":
            self.known.emit(entry_id)
        elif what == "not_yet":
            self.checked.emit(entry_id, False)
        elif what == "not_now":
            self.not_now.emit(entry_id)
        else:
            self.add_wanted.emit(entry_id)

    def _picked_changed(self) -> None:
        self.picked_bar.show_count(len(self.words.picked()))

    def _for_picked(self, key: str) -> None:
        picked = self.words.picked()
        self.words.let_go()
        if key and picked:
            self.many_wanted.emit(key, picked)

    def _word_font(self) -> QFont:
        font = QFont(self.font())
        font.setFamilies(list(CJK_FAMILIES["zh"] if self.chinese else LATIN_FAMILIES))
        font.setPixelSize(style.px(15))
        return font

    def _show_rules(self, rules: LoadRules) -> None:
        self.size_box.clear()
        for size in sorted({*SIZES, rules.size}):
            self.size_box.addItem(str(size), size)
        self.size_box.setCurrentIndex(self.size_box.findData(rules.size))
        self.step.set_value(rules.step)
        self.counting.setCurrentIndex(self.counting.findData(rules.counting))
        if self.limit.findData(rules.stage_limit) < 0:
            self.limit.addItem(str(rules.stage_limit), rules.stage_limit)
        self.limit.setCurrentIndex(self.limit.findData(rules.stage_limit))

    # -- what it asks --------------------------------------------------------------

    def _rules_chosen(self, _value: object = None) -> None:
        if self.view is None:
            return
        size, counting, limit = (
            self.size_box.currentData(),
            self.counting.currentData(),
            self.limit.currentData(),
        )
        step = self.step.value()
        rules = replace(
            self.view.rules,
            size=size if isinstance(size, int) else self.view.rules.size,
            step=step if isinstance(step, int) else self.view.rules.step,
            counting=Counting(counting) if counting else self.view.rules.counting,
            stage_limit=limit if isinstance(limit, int) else 0,
        )
        if rules != self.view.rules:
            self.rules_chosen.emit(rules)

    def _list_chosen(self, _value: object) -> None:
        self.rows = ROWS
        self.listed_chosen.emit()

    def _more(self) -> None:
        self.rows += ROWS
        self.listed_chosen.emit()


def _nothing(listed: Listed) -> str:
    """What a list says when it has no words."""
    if listed is Listed.READY:
        return _tr(
            "None yet. A word is ready to check once it has passed green; then "
            "one click here says whether you know it."
        )
    return _tr("No words here now.")


def _button(text: str, name: str, kind: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    if kind:
        button.setProperty("kind", kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _combo(name: str, said: str) -> QComboBox:
    combo = Combo()
    combo.setObjectName(name)
    combo.setAccessibleName(said)
    return combo


def _left(widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(widget)
    row.addStretch(1)
    return row
