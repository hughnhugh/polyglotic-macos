"""A caption window's settings popover: everything the hover strip doesn't
hold, beside its settings button (the user, 2026-11-07: a minimal strip
and a settings popover, instead of project 109's chips on the band).

Seven rows (polyglotic-hq 593, 585's section 6; the user, 2026-11-21: "A
lot of these caption window settings don't need to exist now"):
Captioning (the app), its languages on one line - "Detect → English ▾",
which opens They speak (Detect, or the language its app speaks: any the
speech model hears - `spoken_list`, 317), Lyrics for a music player on Detect, Translate into (a language, or
Original only) and "When they already speak ..." (its second language -
only where a line can already be in the window's language: polyglotic-hq
248's IA.md 1.9; 263; named by the window's language, 465) under it - Text
size (A- / A+, moved here from the hover strip for word links: the user's
rehearsal feedback F9, 249; with a slider between them in 5 % steps, 60 to
400 %: polyglotic-hq 305), Open transcript, Join windows, Stop captioning,
and All caption settings... - Settings > Captions in the main window,
where every window's look, word links and timing are (248's F11: it
replaced the small Look window). No Position: a window
is moved by hand, and keeps its place (the user's rehearsal feedback
F8, 249). Changes apply at once - there is
no OK or Cancel. Every row's words start at the same place (`INSET`);
They speak and Translate into show the choice made as a
chip at the row's right, which opens the choices under it (the arrow
turned while they're open), as does "When they already speak ...", its chip on
the line under its words; Show my speech here is an on / off switch.

**The language chip's popover** (polyglotic-hq 465, 449's 3A): the
window's bar has a chip, "Detect → English ▾", that opens the same
popover with only those three rows (`LANGUAGE_ROWS`) and "Start new
windows like this" - a new window takes this one's spoken language too.
The first window's set-up (`caption_set_up`) is these rows again.

**Spoken language, honestly** (248's Q6 A): a server from before
2026-11-09 takes one spoken language for every window, so when the windows
name different ones every app is heard as Detect - and a window naming one
says so under its row (`CaptionWindow.spoken_fallback`), keeping the
choice for when it can be used.

In a joined window (109's 2a) a column's popover holds only what is that
app's own (`COLUMN_ROWS`), and the window's own popover the rest: All
caption settings... and Separate windows (`WINDOW_ROWS`).

**A mouse-opened popover leaves focus with the app underneath** (a
full-screen game can minimise when it loses focus):
- it is a top-level tool window with `Qt.WindowDoesNotAcceptFocus` -
  on Windows, `WS_EX_NOACTIVATE` on its native window, so a click in it
  doesn't activate it (checked on a real window, 2026-11-07: Windows'
  foreground window stayed the same, and Qt had no active window) - and
  `WA_ShowWithoutActivating`; it is never raised (Qt's `raise_()`
  activates a window); the caption window is the same;
- its language lists expand inside it. The caption controls hotkey can
  explicitly open a focusable chooser and dropdowns for keyboard use.

So it never has the keyboard, and Windows doesn't tell it about clicks in
other apps. **On Linux it does take the keyboard** while it's open
(`above_all.POPOVERS_TAKE_THE_KEYBOARD`, polyglotic-hq 570): an ordinary
window, brought forward and given the keyboard as it opens, closed by Esc
or as soon as another window takes the keyboard back - a click anywhere
else. The app can't read keys or clicks meant for other apps there. **Esc or a click elsewhere closes it** from two places: an
event filter on this app (a click on any of its other widgets, or Esc
while one of them has the keyboard), and - while it's open, and only then
- a look every 40 ms at whether Esc or a mouse button is held anywhere
(`keys`, handed over by `main` from `platform`: Windows' key state, read
without taking the key or the click from the app that gets it).

It keeps its window's hover strip shown while it's open, sits beside the
settings button - flipped above it, or moved in, to stay on the work
area - and closes when its window is locked, hidden or closed.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCursor, QPainter, QPaintEvent, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ports.system import KeyState  # theirs: the OS's
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.above_all import ABOVE_ALL, POPOVERS_TAKE_THE_KEYBOARD
from polyglotic_desktop.ui_next.controls import (
    INSET,
    SWITCH,
    TICK,
    SwitchButton,
    TickButton,
)
from polyglotic_desktop.ui_next.languages import (
    in_sentence,
    language_name,
    not_offered_note,
    target_languages,
)
from polyglotic_desktop.ui_next.spoken_list import SpokenLanguageList
from polyglotic_desktop.ui_next.spoken_list import chip_text as spoken_chip_text
from polyglotic_desktop.ui_next.views.app_choices import AppChoice, AppState
from polyglotic_desktop.ui_next.views.caption_window import (
    FINE_STEP,
    ORIGINAL_ONLY,
    TEXT_STEP,
    TRANSLATION_SIZES,
)
from polyglotic_desktop.ui_next.views.captions import CAPTION_TEXT_SIZES
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.word_classes import WordClassLegend

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow
    from polyglotic_desktop.ui_next.joined_window import JoinedWindow


POLL_MS = 40
"""How often an open popover looks at Esc and the mouse buttons."""
WIDTH = 280
"""At 100 % text size: it grows with the text (`style.px`), and is wider
if its rows need it (`_fit`)."""
GAP = 6
"""Pixels between the settings button and the popover."""
LIST_HEIGHT = 180
TEXT, DIM, SURFACE, LINE, ACCENT = "#e9ecf2", "#a0a8b6", "#191d24", "#2a303b", "#7c9cff"
INK = (ACCENT, DIM, SURFACE)
"""The row buttons' tick and switch: the accent, dimmed, and the knob on it."""
RECOMMENDED_TAG_RADIUS = 6
"""Logical px (2, 3, 6, 8, 9, 10, 12 design scale): corner radius of the quiet Recommended tag in popovers (638)."""
RECOMMENDED_TAG_INSET = (1, 6)
"""Logical px (0..10): vertical and horizontal padding of the Recommended tag (638)."""
RECOMMENDED_TAG_BG = "rgba(124, 156, 255, 0.16)"
"""Subtle accent tint behind the Recommended tag on the dark popover surface (638)."""
RECOMMENDED_TAG_BORDER = "rgba(124, 156, 255, 0.34)"
"""Quiet border around the Recommended tag on the dark popover surface (638)."""
RECOMMENDED_TAG_INK = "#c7d6ff"
"""Soft tinted text colour for the Recommended tag (>8:1 contrast on SURFACE; 638)."""

BAR_ROWS = ("bar_timing", "bar_languages", "bar_presets")
"""Chips in their overflow order. The keyboard shortcut also shows the mic toggle."""
KEYBOARD_BAR_ROWS = (*BAR_ROWS, "bar_mic", "bar_word_classes")
"""Every control on the caption bar, reached through the keyboard shortcut."""
ROWS = (
    "app",
    *BAR_ROWS,
    "text_size",
    "translation_size",
    "transcript",
    "join",
    "stop",
    "all_settings",
)
"""The popover's rows, top to bottom (polyglotic-hq 593, 635, 655): its app,
any bar chips folded away at narrow widths (`BAR_ROWS`: timing, languages,
preset - shown only when overflowed or reached by keyboard), independent
Caption size and Translation size (with Match), and its actions. Join windows
shows only with two or more windows."""
COLUMN_ROWS = (
    "app",
    *BAR_ROWS,
    "text_size",
    "translation_size",
    "transcript",
    "stop",
)
"""A joined window's column's popover: what is that app's own (109's 2a)."""
WINDOW_ROWS = ("separate", "all_settings")
"""The joined window's own popover: what is the whole window's."""
LANGUAGE_ROWS = (
    "spoken",
    "lyrics",
    "language",
    "second",
    "start_like_this",
    "ask_set_up",
)
"""What the bar's language chip opens (465): the window's three language
choices, whether new windows start like it, and whether a window that
opens asks them (478: where the set-up comes back) - and, under They
speak, a music player's Lyrics switch (595)."""


def _style() -> str:
    """The popover's look, its text at the text size now."""
    return f"""
QWidget {{ color: {TEXT}; font-size: {style.px(12)}px; }}
QLabel {{ padding-left: {INSET}px; }}
QLabel[note="true"] {{ color: {DIM}; font-size: {style.px(12)}px; }}
QLabel[recommended="true"] {{
  color: {RECOMMENDED_TAG_INK};
  background: {RECOMMENDED_TAG_BG};
  border: 1px solid {RECOMMENDED_TAG_BORDER};
  border-radius: {RECOMMENDED_TAG_RADIUS}px;
  padding: {RECOMMENDED_TAG_INSET[0]}px {RECOMMENDED_TAG_INSET[1]}px;
  font-size: {style.px(12)}px;
}}
QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
  padding: 4px 8px; text-align: left; }}
QPushButton[tick="true"] {{ padding-left: {INSET - 1 + style.px(TICK)}px; }}
QPushButton[switch="true"] {{ padding-right: {SWITCH[0] + 14}px; }}
QPushButton:hover {{ background: rgba(255,255,255,0.10); }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #6c7484; }}
QPushButton[segment="true"] {{ border: 1px solid {LINE}; padding: 3px 10px; text-align: center; }}
QPushButton[segment="true"]:checked {{ background: rgba(124,156,255,0.28); }}
QListWidget {{ background: #20252e; border: 1px solid {LINE}; border-radius: 6px; }}
QListWidget::item {{ padding: 3px 6px; }}
QListWidget::item:selected {{ background: rgba(124,156,255,0.28); color: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.30); border-radius: 3px;
  min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.50); }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
  background: none; height: 0; }}
QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: rgba(124,156,255,0.55); border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 12px; margin: -5px 0;
  border-radius: 6px; }}
"""


def _tr(text: str) -> str:
    return QApplication.translate("SettingsPopover", text)


def _chip_text(value: str, open_: bool) -> str:
    """A value chip's words: the choice made, and an arrow - down to open
    its choices, up while they're open (as the lookup card's Save to)."""
    return f"{style.button_text(value)} {'▴' if open_ else '▾'}"


def size_badge(size: float) -> str:
    return _tr("{percent}%").format(percent=round(size * 100))


def second_title(language: str) -> str:
    """The second language's row, named by the window's language (465)."""
    #: A caption window's row: what to do with lines already spoken in
    #: {language}, the language this window translates into
    return in_sentence(_tr("When they already speak {language}"), language=language)


def second_tip(language: str) -> str:
    """What the second language's row does, for its tooltip."""
    return in_sentence(
        _tr(
            "{language} is this window's language, so those lines get no "
            "translation. Translate them into a second language too, or leave "
            "them as they are."
        ),
        language=language,
    )


def second_text(code: str | None) -> str:
    """The second language chosen, as its chip says it."""
    if not code:
        return _tr("Leave as they are")
    return in_sentence(
        _tr("Also translate into {language}"), language=language_name(code)
    )


def app_choice_text(choice: AppChoice) -> str:
    """An app as the Captioning list shows it: its name, and whether it's
    playing - or, for one not playing yet, that it's captioned when it
    does (F12)."""
    if choice.state is AppState.PLAYING:
        return _tr("{app} - playing").format(app=choice.title)
    if choice.state is AppState.NOT_PLAYING_YET:
        return _tr("{app} - starts when it plays").format(app=choice.title)
    return choice.title


def app_choice_tip(choice: AppChoice) -> str:
    if choice.state is AppState.NOT_PLAYING_YET:
        return _tr(
            "Captioning starts when {app} plays sound - its first seconds can be missed"
        ).format(app=choice.title)
    return ""


def beside(
    anchor: QRect,
    size: tuple[int, int],
    area: Rect,
    from_left: bool = False,
    clear_of: QRect | None = None,
) -> QPoint:
    """Where a popover of `size` goes beside the button at `anchor`: under
    it, its right edge with the button's (`from_left`: its left edge with
    the button's - the language chip's, 465) - or above it when there's no
    room below; moved in to stay on the work area. `clear_of`: a window it
    mustn't cover where there's room elsewhere - its own caption window, on
    Linux, which is drawn above it there (570) - so below or above that
    window, else beside it."""
    width, height = size
    x = anchor.left() if from_left else anchor.right() + 1 - width
    y = anchor.bottom() + 1 + GAP
    if y + height > area.bottom:
        y = anchor.top() - GAP - height
    x = min(max(x, area.x), area.right - width)
    y = min(max(y, area.y), area.bottom - height)
    if clear_of is None or not QRect(x, y, width, height).intersects(clear_of):
        return QPoint(x, y)
    side_y = min(max(anchor.top(), area.y), area.bottom - height)
    for at in (
        QPoint(x, clear_of.bottom() + 1 + GAP),  # below the window
        QPoint(x, clear_of.top() - GAP - height),  # above it
        QPoint(clear_of.right() + 1 + GAP, side_y),  # right of it
        QPoint(clear_of.left() - GAP - width, side_y),  # left of it
    ):
        inside = (
            area.x <= at.x() <= area.right - width
            and area.y <= at.y() <= area.bottom - height
        )
        if inside:
            return at
    return QPoint(x, y)  # no room clear of it: over it, as before


class _Follows(QObject):
    """Keeps a row's button showing its action - its words, tip, check and
    whether it can be used - and goes with the button. The popover is
    deleted, and made again, when its window joins or separates; a plain
    function connected to the action outlived it, and every later change
    of the action (A+, Panel or Strip) raised an error on the
    deleted button (polyglotic-hq 141)."""

    def __init__(self, button: QPushButton, action: QAction) -> None:
        super().__init__(button)
        self.button, self.action = button, action
        action.changed.connect(self.follow)  # a method of this: let go with it
        self.follow()

    def follow(self) -> None:
        button, action = self.button, self.action
        button.setText(action.text())
        button.setToolTip(action.toolTip())
        button.setEnabled(action.isEnabled())
        button.setCheckable(action.isCheckable())
        button.setChecked(action.isChecked())


class SizeSlider(QSlider):
    """A text size's slider: moved by a drag, a click on its track, or its
    A- and A+ - never by the wheel, which passes over it (polyglotic-hq
    304's rule: the wheel never changes a setting it passes over)."""

    def __init__(self, low: float, high: float, step: float, parent: QWidget) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.low, self.step = low, step
        self.setRange(0, round((high - low) / step))
        self.setPageStep(round(TEXT_STEP / step))
        self.setMinimumWidth(style.px(110))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def chosen(self) -> float:
        """The size where it is now."""
        return round(self.low + self.value() * self.step, 2)

    def show_size(self, size: float) -> None:
        """Shows `size` without saying it changed."""
        blocked = self.blockSignals(True)
        self.setValue(round((size - self.low) / self.step))
        self.blockSignals(blocked)

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


FLAGS = (
    Qt.WindowType.Tool
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.WindowDoesNotAcceptFocus
    | ABOVE_ALL
)
"""A popover that never takes the keyboard (Windows, a Mac)."""
KEYBOARD_FLAGS = (
    Qt.WindowType.Dialog
    | Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
)
"""A popover that takes the keyboard while it's open (Linux, 570): a window
the window manager manages, so it can be given the keyboard."""


class SettingsPopover(QWidget):
    """The settings of one caption window, beside its settings button - or
    of a joined window's column, or of the joined window (`rows`)."""

    def __init__(
        self,
        window: "CaptionWindow | JoinedWindow",
        keys: KeyState | None = None,
        rows: tuple[str, ...] = ROWS,
    ) -> None:
        super().__init__(
            window,  # its own window, owned by the caption window: goes with it
            KEYBOARD_FLAGS if POPOVERS_TAKE_THE_KEYBOARD else FLAGS,
        )
        self.takes_the_keyboard = POPOVERS_TAKE_THE_KEYBOARD
        """It takes the keyboard while it's open (Linux, 570)."""
        self._had_the_keyboard = False
        if not self.takes_the_keyboard:
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # on a Mac a tool window hides while the app isn't active - and the
        # app is never active while the learner is in another (polyglotic-hq 429)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("settings_popover")
        self.setFont(style.ui_font())  # a window: it doesn't take its owner's
        self._styled_at = style.text_scale()
        self.setStyleSheet(_style())
        self.width_at_100 = WIDTH
        """Its width at 100 % text size (`WIDTH`; the set-up's is wider)."""
        self.from_left = rows == LANGUAGE_ROWS
        """Under its button from the button's left edge: the language
        chip's, at the strip's left (465); the settings button's is at its
        right."""
        self.setFixedWidth(style.px(self.width_at_100))
        self.owner = window
        self.keys = keys
        self.keyboard = False
        self._anchor = QRect()
        self._poll = QTimer(self, interval=POLL_MS)
        self._poll.timeout.connect(self._look_at_keys)
        self.rows: dict[str, QWidget] = {}
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(6)
        for name in rows:
            row = getattr(self, f"_{name}_row")()
            row.setObjectName(f"settings_popover.{name}")
            self.rows[name] = row
            column.addWidget(row)

    # -- the rows ----------------------------------------------------------------------

    def _button(
        self,
        action: QAction,
        parent: QWidget | None = None,
        segment: bool = False,
        switch: bool = False,
    ) -> QPushButton:
        """A button for `action` showing its words (the strip's buttons show
        its glyph), its check and whether it can be used, as they change. A
        segment shows its check as its colour; a `switch`, as an on / off
        switch at its right; any other checkable row, as a tick before its
        words."""
        button: QPushButton = (
            SwitchButton(parent or self, INK)
            if switch
            else TickButton(parent or self, INK[:2])
        )
        button.setProperty("segment", segment)
        button.setProperty("tick", action.isCheckable() and not segment and not switch)
        button.setProperty("switch", switch)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setObjectName(f"settings_popover.{action.objectName()}")
        _Follows(button, action)
        button.clicked.connect(lambda: action.trigger())
        return button

    def _wide(self, action: QAction, switch: bool = False) -> QPushButton:
        return self._button(action, switch=switch)

    def _segments(self, title: str, names: tuple[str, ...], note: str = "") -> QWidget:
        row = QWidget(self)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        heading = QLabel(
            f"{title}  <span style='color:{DIM}'>{note}</span>" if note else title
        )
        column.addWidget(heading)
        segments = QHBoxLayout()
        segments.setContentsMargins(INSET - 1, 0, 0, 0)
        segments.setSpacing(4)
        for name in names:
            segments.addWidget(self._button(self.owner.controls[name], row, True))
        segments.addStretch(1)
        column.addLayout(segments)
        return row

    def _value_row(
        self, title: str, name: str, toggle: Callable[[], None]
    ) -> tuple[QWidget, QVBoxLayout, QPushButton]:
        """A row with a title and, at its right, a chip showing the choice
        made (`name`: the chip's object name) - a click on the chip opens
        the choices under it (`toggle`): Translate into shows its value
        without being opened."""
        row = QWidget(self)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        line = QHBoxLayout()
        line.addWidget(QLabel(title))
        line.addStretch(1)
        chip = QPushButton(row)
        chip.setObjectName(f"settings_popover.{name}")
        chip.setCursor(Qt.CursorShape.PointingHandCursor)
        chip.setProperty("segment", True)
        chip.clicked.connect(toggle)
        line.addWidget(chip)
        column.addLayout(line)
        return row, column, chip

    def _bar_chip(self, open_chip: Callable[..., None]) -> QPushButton:
        button = QPushButton(self)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: open_chip(keyboard=self.keyboard))
        return button

    def _bar_timing_row(self) -> QPushButton:
        return self._bar_chip(self._window.toggle_timings)

    def _bar_languages_row(self) -> QPushButton:
        return self._bar_chip(self._window.toggle_languages)

    def _bar_presets_row(self) -> QPushButton:
        return self._bar_chip(self._window.toggle_presets)

    def _bar_word_classes_row(self) -> WordClassLegend:
        legend = WordClassLegend(self, copyable=False)
        legend.expanded.connect(self._fit)
        return legend

    def _bar_mic_row(self) -> QPushButton:
        button = SwitchButton(self, INK)
        button.setProperty("switch", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setCheckable(True)
        button.clicked.connect(lambda on: self._window.set_show_mic(bool(on)))
        return button

    def _language_row(self) -> QWidget:
        row, column, self.language = self._value_row(
            _tr("Translate into"), "language_button", self._toggle_languages
        )
        self.language.setToolTip(
            _tr("The language this window's captions are translated into")
        )
        self.languages = QListWidget(row)
        self.languages.setAccessibleName(_tr("Translate into"))
        self.languages.setMaximumHeight(style.px(LIST_HEIGHT))
        self.languages.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        choices = [(ORIGINAL_ONLY, _tr("Original only (no translation)"))]
        choices += [
            (str(code), language_name(str(code))) for code in target_languages()
        ]
        for code, name in choices:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.languages.addItem(item)
        self.languages.itemClicked.connect(self._language_chosen)
        self.languages.itemActivated.connect(self._language_chosen)
        self.languages.hide()
        column.addWidget(self.languages)
        # under the list while it's open, as the rail says it (DECISIONS.md #40)
        self.not_offered = QLabel(not_offered_note(), row)
        self.not_offered.setProperty("note", True)
        self.not_offered.setWordWrap(True)
        self.not_offered.setContentsMargins(0, 4, 0, 2)
        self.not_offered.hide()
        column.addWidget(self.not_offered)
        return row

    def _list(
        self, parent: QWidget, name: str, chosen: Callable[[QListWidgetItem], None]
    ) -> QListWidget:
        """The choices a chip opens, under it (hidden until it does)."""
        found = QListWidget(parent)
        found.setAccessibleName(name)
        found.setMaximumHeight(style.px(LIST_HEIGHT))
        found.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        found.itemClicked.connect(chosen)
        found.itemActivated.connect(chosen)
        found.hide()
        return found

    def _note(self, text: str, parent: QWidget) -> QLabel:
        note = QLabel(text, parent)
        note.setProperty("note", True)
        note.setWordWrap(True)
        note.setContentsMargins(0, 4, 0, 2)
        return note

    def _spoken_row(self) -> QWidget:
        """Spoken language: Detect, or the language this window's app
        speaks (263) - and, under it, when that can't be used as it is.
        Its list is every language the speech model hears, the recent ones
        first (`spoken_list`; 317), made when first opened."""
        row, column, self.spoken = self._value_row(
            _tr("They speak"), "spoken_button", self._toggle_spoken
        )
        self.spoken.setToolTip(
            _tr(
                "What this app's speech is in. Detect finds the language each "
                "time someone speaks, and handles mixed talk. Name it and every "
                "caption is heard as that language: short or mumbled speech is "
                "never taken for another."
            )
        )
        self.spoken_choices = SpokenLanguageList(
            row,
            searchable=False,
            recent=lambda: self._window.recent_spoken(),
            dim=DIM,
        )
        self.spoken_choices.chosen.connect(self._spoken_chosen)
        column.addWidget(self.spoken_choices)
        self.spoken_fallback = self._note(
            _tr("Heard as Detect for now: another window hears a different language"),
            row,
        )
        self.spoken_fallback.setObjectName("settings_popover.spoken_fallback")
        self.spoken_fallback.setToolTip(
            _tr(
                "This server takes one spoken language for every window, so "
                "while the windows name different ones, every app is detected. "
                "Your choice is kept."
            )
        )
        self.spoken_fallback.hide()
        column.addWidget(self.spoken_fallback)
        return row

    def _lyrics_row(self) -> QWidget:
        """Lyrics: songs mode for music players heard on Detect, on or off -
        the learner's one setting, as in Settings > Captions > Speech
        (polyglotic-hq 595, decision 0287). Shown only in a music player's
        window while it hears Detect (`CaptionWindow.offers_lyrics`)."""
        row = QWidget(self)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._wide(self.owner.controls["lyrics"], switch=True))
        note = QLabel(_tr("Captions singing too: the music is sent while it plays"))
        note.setProperty("note", True)
        note.setWordWrap(True)
        note.setContentsMargins(0, 0, 0, 2)
        column.addWidget(note)
        return row

    def _second_row(self) -> QWidget:
        """When they already speak the window's language: those lines
        translated into another language too, or left as they are - only
        where a line can already be in it: the spoken language Detect, or
        the window's own (IA.md 1.9). Named by the window's language (465:
        "Why english? what if you're targetting chinese translation?" -
        the user, 2026-11-17)."""
        row = QWidget(self)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        self.second_title = QLabel(row)
        self.second_title.setWordWrap(True)
        column.addWidget(self.second_title)
        line = QHBoxLayout()
        line.setContentsMargins(INSET - 1, 0, 0, 0)
        self.second = QPushButton(row)
        self.second.setObjectName("settings_popover.second_button")
        self.second.setCursor(Qt.CursorShape.PointingHandCursor)
        self.second.setProperty("segment", True)
        self.second.clicked.connect(self._toggle_second)
        line.addWidget(self.second)
        line.addStretch(1)
        column.addLayout(line)
        self.second_line = line
        self.second_choices = self._list(
            row,
            _tr("When they already speak this window's language"),
            self._second_chosen,
        )
        column.addWidget(self.second_choices)
        return row

    def _app_row(self) -> QWidget:
        """Captioning: the app this window captions, and the apps it can
        caption instead - found ones, then browsers and the main apps
        before they play (F12, 249) - opened under it; and what to do when
        an app isn't there."""
        row, column, self.app = self._value_row(
            _tr("Captioning"), "app_button", self._toggle_apps
        )
        self.app.setToolTip(_tr("The app this window captions - pick another here"))
        self.apps = QListWidget(row)
        self.apps.setAccessibleName(_tr("Captioning"))
        self.apps.setMaximumHeight(style.px(LIST_HEIGHT))
        self.apps.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.apps.itemClicked.connect(self._app_chosen)
        self.apps.hide()
        column.addWidget(self.apps)
        self.no_app = QLabel(
            _tr("Don't see your app here? Make sure it's playing audio."), row
        )
        self.no_app.setProperty("note", True)
        self.no_app.setWordWrap(True)
        self.no_app.setContentsMargins(0, 4, 0, 2)
        self.no_app.hide()
        column.addWidget(self.no_app)
        return row

    def _toggle_apps(self) -> None:
        if self.apps.isHidden():
            self._list_apps()
        self.apps.setVisible(self.apps.isHidden())
        self.refresh()

    def _list_apps(self) -> None:
        self.apps.clear()
        current = self._window.key
        for choice in self._window.app_choices():
            item = QListWidgetItem(app_choice_text(choice))
            item.setData(Qt.ItemDataRole.UserRole, choice.name)
            item.setToolTip(app_choice_tip(choice))
            self.apps.addItem(item)
            item.setSelected(choice.name == current)

    def _app_chosen(self, item: QListWidgetItem) -> None:
        self.apps.hide()
        name = str(item.data(Qt.ItemDataRole.UserRole))
        if name != self._window.key:
            self._window.app_wanted.emit(name)
        self.refresh()

    def _start_like_this_row(self) -> QWidget:
        """Start new windows like this: a new window takes this one's
        spoken language too, not Detect (465)."""
        return self._wide(self.owner.controls["start_like_this"], switch=True)

    def _ask_set_up_row(self) -> QWidget:
        """Ask when a window opens: the set-up on every window that opens,
        until Use as my default is chosen there - this brings it back
        (478)."""
        return self._wide(self.owner.controls["ask_set_up"], switch=True)

    def _sized(
        self,
        title: str,
        names: tuple[str, str],
        said: tuple[str, str],
        slider: QSlider,
        trailing: QWidget | None = None,
    ) -> tuple[QWidget, QLabel]:
        """A size's row: its title and language/size readout (with an optional
        compact trailing button such as Match), then A-, a slider and A+."""
        row = QWidget(self)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(3)
        heading = QLabel(title, row)
        if trailing is not None:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(6)  # constant: matches popover row spacing
            header.addWidget(heading)
            header.addStretch(1)
            header.addWidget(trailing)
            column.addLayout(header)
        else:
            column.addWidget(heading)
        line = QHBoxLayout()
        line.setContentsMargins(INSET - 1, 0, 0, 0)
        line.setSpacing(6)  # constant: matches popover row spacing
        smaller = self._button(self.owner.controls[names[0]], row, True)
        bigger = self._button(self.owner.controls[names[1]], row, True)
        smaller.setAccessibleName(said[0])  # not "A-"
        bigger.setAccessibleName(said[1])
        slider.setParent(row)
        slider.setAccessibleName(title)
        line.addWidget(smaller)
        line.addWidget(slider, 1)
        line.addWidget(bigger)
        column.addLayout(line)
        return row, heading

    def _text_size_row(self) -> QWidget:
        """Caption size: A-, a slider and A+, with a percentage readout."""
        self.text_slider = SizeSlider(*CAPTION_TEXT_SIZES, FINE_STEP, self)
        self.text_slider.setObjectName("settings_popover.text_size_slider")
        self.text_slider.valueChanged.connect(
            lambda _: self._window.set_text_size(self.text_slider.chosen())
        )
        row, self.text_size = self._sized(
            _tr("Caption size"),
            ("smaller", "bigger"),
            (_tr("Smaller caption size"), _tr("Bigger caption size")),
            self.text_slider,
        )
        return row

    def _translation_size_row(self) -> QWidget:
        """Translation size: independent of caption size (60 to 400 %, slider
        in 5 % steps), with a small Match button to match caption size (655)."""
        self.translation_slider = SizeSlider(*TRANSLATION_SIZES, FINE_STEP, self)
        self.translation_slider.setObjectName(
            "settings_popover.translation_size_slider"
        )
        self.translation_slider.valueChanged.connect(
            lambda _: self._window.set_translation_size(
                self.translation_slider.chosen()
            )
        )
        self.translation_match = self._button(
            self.owner.controls["translation_same"], self, True
        )
        self.translation_match.setAccessibleName(
            _tr("Match translation size to caption size")
        )
        row, self.translation_size = self._sized(
            _tr("Translation size"),
            ("translation_smaller", "translation_bigger"),
            (_tr("Smaller translation size"), _tr("Bigger translation size")),
            self.translation_slider,
            trailing=self.translation_match,
        )
        return row

    def _all_settings_row(self) -> QWidget:
        return self._wide(self.owner.controls["all_settings"])

    def _transcript_row(self) -> QWidget:
        return self._wide(self.owner.controls["transcript"])

    def _join_row(self) -> QWidget:
        return self._wide(self.owner.controls["join"])

    def _stop_row(self) -> QWidget:
        return self._wide(self.owner.controls["stop"])

    def _separate_row(self) -> QWidget:
        return self._wide(self.owner.controls["separate"])

    # -- what it shows -------------------------------------------------------------------

    @property
    def _window(self) -> "CaptionWindow":
        """The caption window whose own rows these are (its language, Join
        windows) - never the joined window, whose rows are WINDOW_ROWS."""
        return cast("CaptionWindow", self.owner)

    def refresh(self) -> None:
        """Shows the window's choices (the actions follow by themselves): each
        chip its value, with the arrow turned while its choices are open."""
        legend = self.rows.get("bar_word_classes")
        if isinstance(legend, WordClassLegend):
            legend.set_look(self._window.look)
        if "spoken" in self.rows:
            self._show_spoken()
        if "lyrics" in self.rows:
            self.rows["lyrics"].setVisible(self._window.offers_lyrics)
        if "second" in self.rows:
            self._show_second()
        if "language" in self.rows:
            target = self._window.choices.target
            value = language_name(str(target)) if target else _tr("Original only")
            self.language.setText(_chip_text(value, self.languages.isVisible()))
            chosen = self._window.choices.translate_into
            for index in range(self.languages.count()):
                item = self.languages.item(index)
                item.setSelected(item.data(Qt.ItemDataRole.UserRole) == chosen)
            self.not_offered.setHidden(self.languages.isHidden())
        if "text_size" in self.rows:
            self.text_slider.show_size(self._window.view.text_size)
            badge = size_badge(self._window.view.text_size)
            self.text_size.setText(
                f"{_tr('Caption size')}  <span style='color:{DIM}'>{badge}</span>"
            )
        if "translation_size" in self.rows:
            has_target = self._window.choices.target is not None
            self.rows["translation_size"].setVisible(has_target)
            if has_target:
                trans = self._window.choices.translation_size
                self.translation_slider.show_size(trans)
                badge = size_badge(trans)
                self.translation_size.setText(
                    f"{_tr('Translation size')}  <span style='color:{DIM}'>{badge}</span>"
                )
        if "app" in self.rows:
            self.rows["app"].setVisible(bool(self._window.app_choices()))
            self.app.setText(_chip_text(self._window.label.name, self.apps.isVisible()))
            self.no_app.setHidden(self.apps.isHidden())
        if "join" in self.rows:
            self.rows["join"].setVisible(self._window.windows > 1)
        if "bar_timing" in self.rows:
            for name, chip in zip(
                BAR_ROWS,
                (self._window.timing_chip, self._window.chip, self._window.preset_chip),
                strict=True,
            ):
                row = cast(QPushButton, self.rows[name])
                value = chip.accessibleName()
                row.setText(style.button_text(value))
                row.setAccessibleName(value)
                row.setVisible(self.keyboard or chip.isHidden())
        if "bar_mic" in self.rows:
            mic_row = cast(QPushButton, self.rows["bar_mic"])
            on = self._window.choices.show_mic
            mic_row.setText(style.button_text(_tr("Caption what I say")))
            mic_row.setChecked(on)
            mic_row.setAccessibleName(_tr("Caption what I say"))
            tip = self._window.mic_button.toolTip()
            mic_row.setToolTip(tip)
            mic_row.setAccessibleDescription(tip)
            mic_row.setVisible(self._window.mic_offered())
        self._fit()

    def _show_spoken(self) -> None:
        spoken = self._window.choices.spoken_language
        value = spoken_chip_text(spoken)
        self.spoken.setText(_chip_text(value, self.spoken_choices.isVisible()))
        self.spoken_choices.set_current(spoken)
        self.spoken_fallback.setVisible(self._window.spoken_fallback)

    def _show_second(self) -> None:
        target = self._window.choices.target
        spoken = self._window.choices.spoken
        shown = target is not None and spoken in (None, target)
        self.rows["second"].setVisible(shown)
        if target is None:
            self.second_choices.hide()
            return
        name = language_name(target)
        self.second_title.setText(second_title(name))
        self.second.setToolTip(second_tip(name))
        second = self._window.second_languages.get(target)
        value = second_text(second)
        self.second.setText(_chip_text(value, self.second_choices.isVisible()))
        for index in range(self.second_choices.count()):
            item = self.second_choices.item(index)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) == (second or ""))

    def _toggle_spoken(self) -> None:
        if self.spoken_choices.isHidden():
            self.spoken_choices.open(self._window.choices.spoken_language)
        else:
            self.spoken_choices.close_list()
        self.refresh()

    def _spoken_chosen(self, code: str | None) -> None:
        self.spoken_choices.close_list()
        self._window.choose_bar_language("spoken_language", code or "")
        self.refresh()

    def _toggle_second(self) -> None:
        if self.second_choices.isHidden():
            self._list_seconds()
        self.second_choices.setVisible(self.second_choices.isHidden())
        if self.second_choices.isVisible():
            selected = self.second_choices.selectedItems()
            if selected:
                self.second_choices.scrollToItem(selected[0])
        self.refresh()

    def _list_seconds(self) -> None:
        """Leave as they are, then every language but the window's own."""
        self.second_choices.clear()
        target = self._window.choices.target
        choices = [("", _tr("Leave as they are"))]
        choices += [
            (str(code), language_name(str(code)))
            for code in target_languages()
            if code != target
        ]
        for code, name in choices:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, code)
            self.second_choices.addItem(item)

    def _second_chosen(self, item: QListWidgetItem) -> None:
        self.second_choices.hide()
        self._window.set_second(str(item.data(Qt.ItemDataRole.UserRole)))
        self.refresh()

    def _toggle_languages(self) -> None:
        self.languages.setVisible(not self.languages.isVisible())
        if self.languages.isVisible():
            selected = self.languages.selectedItems()
            if selected:
                self.languages.scrollToItem(selected[0])
        self.refresh()

    def _language_chosen(self, item: QListWidgetItem) -> None:
        self.languages.hide()
        self._window.choose_bar_language(
            "translate_into", str(item.data(Qt.ItemDataRole.UserRole))
        )
        self.refresh()

    # -- opening, placing, closing ---------------------------------------------------------

    def open_beside(self, anchor: QRect, *, keyboard: bool = False) -> None:
        """Show beside `anchor`. A shortcut can explicitly request focus."""
        if keyboard != self.keyboard:
            self.keyboard = keyboard
            takes_focus = keyboard or self.takes_the_keyboard
            self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, not takes_focus)
            self.setAttribute(
                Qt.WidgetAttribute.WA_ShowWithoutActivating, not takes_focus
            )
        self._anchor = QRect(anchor)
        if self._styled_at != style.text_scale():  # Windows' changed since
            self._styled_at = style.text_scale()
            self.setStyleSheet(_style())
            self.setFixedWidth(style.px(self.width_at_100))
        # the lists inside it: shut at each open
        for opened in (
            "languages",
            "apps",
            "spoken_choices",
            "second_choices",
        ):
            if hasattr(self, opened):
                getattr(self, opened).hide()
        self.refresh()
        self.show()  # always on top, and above its window: no raise_(), which activates
        if self.takes_the_keyboard:  # Linux: Esc and clicks elsewhere reach it (570)
            self._had_the_keyboard = False
            self.raise_()
            self.activateWindow()
        if keyboard:
            if not self.takes_the_keyboard:
                self.activateWindow()
            for child in self.findChildren(QWidget):
                if (
                    child.isVisibleTo(self)
                    and child.focusPolicy() == Qt.FocusPolicy.StrongFocus
                ):
                    child.setFocus(Qt.FocusReason.ShortcutFocusReason)
                    break
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        if self.keys is not None:
            self.keys("escape")  # forget a press from before it opened
            self.keys("mouse")
            self._poll.start()

    def follow_anchor(self, anchor: QRect) -> None:
        if self._anchor != anchor:
            self._anchor = anchor
            self._put()

    def _fit(self) -> None:
        """Its size to what shows - `WIDTH`, or what its rows need if more
        (in Segoe UI, Timing's three choices: 2 px more), and the height
        they need at that width - beside the button, on the work area.
        Not `adjustSize`, which holds a window to two thirds of the screen:
        at 200 % text size, with Position open, that squashed the rows and
        cut their words (polyglotic-hq 176, 198).

        Every layout in it is asked afresh first: a list shut while the
        popover was closed (`open_beside`) is only told to its row's layout
        once the popover shows, so the height measured was the one with the
        list open, and the rows spread out into it (246, 269)."""
        layout = self.layout()
        assert layout is not None
        for each in self.findChildren(QWidget):
            each.updateGeometry()  # its size afresh, in the layout it's in
            if isinstance(each, (QAbstractButton, QAbstractItemView, QAbstractSlider)):
                each.setFocusPolicy(
                    Qt.FocusPolicy.StrongFocus
                    if self.keyboard
                    else Qt.FocusPolicy.NoFocus
                )
        for laid in self.findChildren(QLayout):
            laid.invalidate()
        layout.activate()  # and the least height it allows, from them
        width = max(style.px(self.width_at_100), layout.minimumSize().width())
        self.setFixedWidth(width)
        height = self.heightForWidth(width)
        self.resize(width, height if height > 0 else self.sizeHint().height())
        self._put()

    def _put(self) -> None:
        """Where it goes, at its size now: beside its button."""
        if self._anchor.isNull():
            return
        area = self.owner.area_at(self._anchor)
        size = (self.width(), self.height())
        clear_of = None
        if self.takes_the_keyboard:  # Linux: its window is drawn above it (570)
            window = self.owner.window()
            clear_of = QRect(window.mapToGlobal(QPoint(0, 0)), window.size())
        self.move(beside(self._anchor, size, area, self.from_left, clear_of))

    def hideEvent(self, event: object) -> None:
        self._poll.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def _outside(self, pos: QPoint) -> bool:
        """A press at `pos` (global) is somewhere else: not in the popover,
        nor on the settings button (which opens and closes it itself)."""
        return not self.frameGeometry().contains(pos) and not self._anchor.contains(pos)

    def _look_at_keys(self) -> None:
        keys = self.keys
        if keys is None or not self.isVisible():
            return
        if keys("escape") or (keys("mouse") and self._outside(QCursor.pos())):
            self.close()

    def event(self, event: QEvent) -> bool:
        """Taking the keyboard (Linux): closed once another window has it."""
        kind = event.type()
        if self.takes_the_keyboard and kind == QEvent.Type.WindowActivate:
            self._had_the_keyboard = True
        elif (
            self.takes_the_keyboard
            and kind == QEvent.Type.WindowDeactivate
            and self._had_the_keyboard
            and self.isVisible()
        ):
            self._had_the_keyboard = False
            self.close()
        return super().event(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress:
            key = getattr(event, "key", lambda: None)()
            if key == Qt.Key.Key_Escape:
                self.close()
                return (
                    self.keyboard
                    and isinstance(watched, QWidget)
                    and (watched is self or self.isAncestorOf(watched))
                )
            if (
                self.keyboard
                and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and isinstance(watched, (QAbstractButton, QListWidget))
                and self.isAncestorOf(watched)
            ):
                if isinstance(watched, QAbstractButton):
                    watched.click()
                elif (item := watched.currentItem()) is not None:
                    # Cocoa uses Return to edit a list item. These lists offer
                    # read-only choices, so Return confirms the highlighted one.
                    watched.itemActivated.emit(item)
                return True
        elif kind == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget):
            inside = watched is self or self.isAncestorOf(watched)
            position = getattr(event, "globalPosition", None)
            at = position().toPoint() if position is not None else QCursor.pos()
            if not inside and self._outside(at):
                self.close()
        return False

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(LINE))
        painter.setBrush(QColor(SURFACE))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10
        )
        painter.end()
