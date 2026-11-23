"""The card that saves a caption window's selection as a sentence
(polyglotic-hq 459; the user's design, 2026-11-14).

When the learner lets go of a drag across more than a word - across lines,
clauses, captions and speakers (`views.sentences.worth_saving`) - this card
shows at the mouse, where the drag let go (the user, 2026-11-18: "should
appear on mouse"; under the caption the selection ended in until 522), and
alone: no lookup card opens for the selection beside it (522: the two
overlapped, and covered Say it):
"Save sentence to" and a button per category, in its colour - the saved
words' categories, shared. A click saves it in the learning data of the
language it was spoken in and says "Saved to Tricky"; the card goes a
moment later, the selection stays (a right-click still copies it). It goes
with the selection: Esc, a click elsewhere, another drag.

A second row reads it aloud (polyglotic-hq 495, 488's design): "Say it"
and a button a language - what was said and its translation, by the
language's own name, the side used last first (`SelectionReading`). The
one reading turns into "Stop"; with no voice for a language its button
says to add one, and opens the OS's speech settings. Read in a basic voice
(a Mac's compact one), a third part says how to add a better one, with
"Don't show again" for the language and Dismiss (polyglotic-hq 518). The
card going stops the reading - after "Saved", it waits for the reading to
end.

A selection within one clause - a set phrase like 一石二鳥, too long to
open a lookup card by itself (522) - has a third row, "Look it up": the
card goes and the lookup card opens on the phrase, as a click on a word
opens it (polyglotic-hq 533). Across clauses or captions there's no
phrase to look up, and no such row.

Like the settings popover and the lookup card it **never takes focus** -
a tool window with `Qt.WindowDoesNotAcceptFocus`, shown without
activating, never raised - so a full-screen game keeps the keyboard; its
clicks don't let go of the selection (`HeldSelection.keeps`).

Holds caption text only to save it or read it aloud: never logs it.
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.learning.saved_words import Category, CategoryId
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.above_all import ABOVE_ALL
from polyglotic_desktop.ui_next.languages import (
    an_before,
    in_sentence,
    learned_name,
    own_name,
)
from polyglotic_desktop.ui_next.lookup_card import (
    better_voice_steps,
    dismiss_text,
    never_again_text,
    no_voice_steps,
)
from polyglotic_desktop.ui_next.selection_reading import SelectionReading
from polyglotic_desktop.ui_next.views.sentences import SideAloud
from polyglotic_desktop.ui_next.views.speech import Say

TEXT, DIM, SURFACE, LINE = "#e9ecf2", "#a0a8b6", "#191d24", "#2a303b"
"""The settings popover's colours: the caption windows' cards share them."""
SAVED_MS = 1400
"""How long "Saved to ..." shows before the card goes."""
GAP = 6
"""Between the mouse and the card."""


def _tr(text: str) -> str:
    return QApplication.translate("SentenceCard", text)


def save_to_text() -> str:
    """ "Save sentence to", before the categories: the card's, and the
    transcript's menu's."""
    return _tr("Save sentence to")


def saved_to_text(category: str) -> str:
    """What saving a sentence says: "Saved to Tricky"."""
    return _tr("Saved to {category}").format(category=category)


def look_up_text() -> str:
    """The card's button that looks the selected phrase up (polyglotic-hq
    533)."""
    return _tr("Look it up")


def say_it_text() -> str:
    """ "Say it", before the languages: the card's, and the transcript's
    menu's (polyglotic-hq 495)."""
    return _tr("Say it")


def stop_text() -> str:
    """What the button reading aloud says: "Stop"."""
    return _tr("Stop")


def say_in_text(language: str) -> str:
    """A side's button in words, for its tooltip and a screen reader."""
    name = learned_name(_learned(language))
    return in_sentence(_tr("Say it in {language}"), language=name)


def add_voice_text(language: str) -> str:
    """A side's button when the PC has no voice for its language."""
    name = learned_name(_learned(language))
    if an_before(name):
        #: "an" before a language name said with a vowel first: "Add an English voice". Translate as "Add a {language} voice"
        said = _tr("Add an {language} voice")
    else:
        said = _tr("Add a {language} voice")
    return in_sentence(said, language=name)


def _learned(language: str) -> str:
    return "zh" if language.split("-")[0].lower() == "zh" else language


def side_name(language: str) -> str:
    """A side's button names its language as its speakers write it
    ("中文", "English", "Español"), whatever the interface's language."""
    primary = language.split("-")[0].lower()
    if primary == "zh":
        return "中文"
    return own_name(primary) or language


def side_text(state: Say, language: str) -> str:
    """What a side's button says: "▶ 中文", "■ Stop", or to add a voice."""
    if state is Say.SPEAKING:
        return f"■ {stop_text()}"
    if state is Say.NO_VOICE:
        return f"+ {add_voice_text(language)}"
    return f"▶ {side_name(language)}"


def _style() -> str:
    return f"""
QWidget {{ color: {TEXT}; font-size: {style.px(12)}px; }}
QLabel {{ color: {DIM}; padding: 0 2px; }}
QPushButton {{ background: transparent; border: 1px solid {LINE}; border-radius: 6px;
  padding: 3px 9px; }}
QPushButton:hover {{ background: rgba(255,255,255,0.10); }}
QCheckBox {{ spacing: 6px; padding-right: 4px; }}
QCheckBox::indicator {{ width: 12px; height: 12px; border: 1px solid {DIM};
  border-radius: 3px; background: transparent; }}
QCheckBox::indicator:checked {{ background: {DIM}; }}
"""


def placed(at: QPoint, size: tuple[int, int], area: QRect) -> QPoint:
    """Where the card goes: just under `at` (the mouse, on the screen),
    its left edge there - above it when there's no room below; moved in
    to stay on `area` (the work area)."""
    width, height = size
    x = at.x()
    y = at.y() + GAP
    if y + height > area.bottom() + 1:
        y = at.y() - GAP - height
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
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | ABOVE_ALL,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("sentence_card")
        self.setFont(style.ui_font())
        self.setStyleSheet(_style())
        rows = QVBoxLayout(self)
        # the card always its rows' size: buttons hidden after "Saved", or
        # renamed while reading, shrink or grow it at once
        rows.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        rows.setContentsMargins(10, 8, 10, 8)
        rows.setSpacing(6)
        self._row = QHBoxLayout()
        self._row.setSpacing(6)
        rows.addLayout(self._row)
        self.said = QLabel(self)
        self._row.addWidget(self.said)
        self._row.addStretch(1)
        self.buttons: list[QPushButton] = []
        self._save: Callable[[CategoryId], str] | None = None
        self._gone = QTimer(self, singleShot=True, interval=SAVED_MS)
        self._gone.timeout.connect(self._go)
        self._say_row = QHBoxLayout()
        self._say_row.setSpacing(6)
        rows.addLayout(self._say_row)
        self.say_label = QLabel(self)
        self.say_label.hide()
        self._say_row.addWidget(self.say_label)
        self._say_row.addStretch(1)
        self.sides: list[tuple[QPushButton, SideAloud]] = []
        """The Say it row's buttons, a side each (polyglotic-hq 495)."""
        self.look_up = QPushButton(self)
        """Looks the selected phrase up (533): shown when `offer` has one."""
        self.look_up.setObjectName("sentence_card.look_up")
        self.look_up.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.look_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.look_up.clicked.connect(self._looked_up)
        self.look_up.hide()
        self._look: Callable[[], None] | None = None
        look_row = QHBoxLayout()
        look_row.addWidget(self.look_up)
        look_row.addStretch(1)
        rows.addLayout(look_row)
        self.reading: SelectionReading | None = None
        self._owner: object = owner
        self.better = QLabel(self)
        """How to add a better voice, after a reading in a basic one (518)."""
        self.better.setObjectName("sentence_card.better")
        self.better.setWordWrap(True)
        self.never_again = QCheckBox(self)
        self.never_again.setObjectName("sentence_card.never_again")
        self.never_again.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dismiss = QPushButton(self)
        self.dismiss.setObjectName("sentence_card.dismiss")
        self.dismiss.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dismiss.clicked.connect(self._dismiss)
        self._better_row = QHBoxLayout()
        self._better_row.setSpacing(6)
        self._better_row.addWidget(self.never_again)
        self._better_row.addStretch(1)
        self._better_row.addWidget(self.dismiss)
        rows.addWidget(self.better)
        rows.addLayout(self._better_row)
        self._show_better(None)

    def use_reading(self, reading: SelectionReading | None) -> None:
        """Say it reads through `reading` (`main`'s, app-wide)."""
        if reading is self.reading:
            return
        if self.reading is not None:
            self.reading.changed.disconnect(self._show_sides)
        self.reading = reading
        if reading is not None:
            reading.changed.connect(self._show_sides)

    def offer(
        self,
        categories: Sequence[Category],
        save: Callable[[CategoryId], str],
        at: QPoint,
        area: QRect,
        sides: Sequence[SideAloud] = (),
        look_up: Callable[[], None] | None = None,
    ) -> None:
        """Shows the card at `at` (the mouse, on the screen): a button per
        category; a click calls `save` with its ID, which returns the
        category's name it went into ("" if it couldn't be saved). `sides`:
        what can be read aloud (with `reading`); none, no Say it row.
        `look_up`: opens the lookup card on the selected phrase, after the
        card goes; None, no Look it up row (a selection across clauses)."""
        self._gone.stop()
        self._save = save
        self._look = look_up
        self.look_up.setText(look_up_text())
        self.look_up.setVisible(look_up is not None)
        for button in self.buttons:
            self._row.removeWidget(button)
            button.deleteLater()
        self.buttons = []
        self.said.setText(save_to_text())
        self.said.setMinimumWidth(0)
        for category in categories:
            button = QPushButton(f"● {category.name}", self)
            button.setObjectName(f"sentence_card.{category.id}")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(f"QPushButton {{ color: {category.color}; }}")
            button.clicked.connect(lambda _=False, c=category.id: self._chosen(c))
            self._row.insertWidget(self._row.count() - 1, button)
            self.buttons.append(button)
        self._offer_sides(sides)
        self.adjustSize()
        self.move(placed(at, (self.width(), self.height()), area))
        self.show()

    def _offer_sides(self, sides: Sequence[SideAloud]) -> None:
        for button, _ in self.sides:
            self._say_row.removeWidget(button)
            button.deleteLater()
        self.sides = []
        reading = self.reading
        self.say_label.setVisible(reading is not None and bool(sides))
        if reading is None or not sides:
            return
        self.say_label.setText(say_it_text())
        # the two rows' buttons start in one column
        width = max(self.said.sizeHint().width(), self.say_label.sizeHint().width())
        for label in (self.said, self.say_label):
            label.setMinimumWidth(width)
        for side in reading.ordered(tuple(sides)):
            button = QPushButton(self)
            button.setObjectName(f"sentence_card.say.{side.kind.value}")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, s=side: self._say(s))
            self._say_row.insertWidget(self._say_row.count() - 1, button)
            self.sides.append((button, side))
        self._show_sides()

    def _show_sides(self) -> None:
        """Each side's button as it is now: ready, reading, or no voice."""
        reading = self.reading
        if reading is None or not self.sides:
            return
        for button, side in self.sides:
            state = reading.state(self._owner, side)
            button.setText(side_text(state, side.language))
            if state is Say.NO_VOICE:
                tip = no_voice_steps(side.language, reading.system_voice())
            elif state is Say.SPEAKING:
                tip = f"{stop_text()} (Esc)"
            else:
                tip = say_in_text(side.language)
            button.setToolTip(tip)
            button.setAccessibleName(button.text().lstrip("▶■+ "))
            button.setAccessibleDescription(tip)
        self._show_better(reading.notice_for(self._owner))
        if self.isVisible():
            self._fit()

    def _show_better(self, language: str | None) -> None:
        """The better-voice part (518): shown while `language`'s reading's
        notice is on, none hides it."""
        for widget in (self.better, self.never_again, self.dismiss):
            widget.setVisible(language is not None)
        if language is None:
            self.never_again.setChecked(False)
            return
        self.better.setText(better_voice_steps(language))
        self.never_again.setText(never_again_text(language))
        self.dismiss.setText(dismiss_text())
        # the steps wrap to the rows above, or a readable measure if narrower
        rows = (self._row.sizeHint().width(), self._say_row.sizeHint().width())
        self.better.setFixedWidth(max(*rows, style.px(300)))

    def _dismiss(self) -> None:
        if self.reading is not None:
            self.reading.dismiss(self.never_again.isChecked())

    def _fit(self) -> None:
        """The card to its rows as they are now (buttons hidden or renamed)."""
        layout = self.layout()
        if layout is not None:
            layout.activate()

    def _say(self, side: SideAloud) -> None:
        if self.reading is not None:
            self.reading.toggle(self._owner, side)

    def _looked_up(self) -> None:
        """Look it up: the card goes (its reading too), and the phrase's
        lookup card opens in its place - never both at once (522)."""
        look, self._look = self._look, None
        self._gone.stop()
        self.hide()
        if look is not None:
            look()

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
        self._fit()
        self._save = None
        self._gone.start()

    def _go(self) -> None:
        """After "Saved": the card goes - once its reading has ended."""
        reading = self.reading
        if (
            reading is not None
            and reading.reading is not None
            and (reading.reading[0] is self._owner)
        ):
            self._gone.start()
            return
        self.hide()

    def withdraw(self) -> None:
        """The selection went: its reading stops, and the card goes -
        unless it's saying "Saved"."""
        if self.reading is not None:
            self.reading.stop_for(self._owner)
        if not self._gone.isActive():
            self.hide()

    def hideEvent(self, event: QHideEvent) -> None:
        if self.reading is not None:  # the card gone: its reading too
            self.reading.stop_for(self._owner)
        super().hideEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(LINE))
        painter.setBrush(QColor(SURFACE))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10
        )
        painter.end()
