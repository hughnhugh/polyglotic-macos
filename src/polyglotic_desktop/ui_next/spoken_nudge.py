"""A caption window's question once Detect has heard its app speak one
language steadily: "This sounds like Russian. Always hear it as Russian?"
with **Yes** and **Not now** (polyglotic-hq 317: naming the language is
the path the app suggests; Detect still works).

At the top of the window, where its notice line is - under the notices
while one shows - with the captions below it, never under it (350): Yes
names the language for this window (`CaptionWindow.set_spoken_language`,
so it's first in every list after); Not now leaves Detect, and the window
never asks about that language again (`StoredWindows.declined_spoken`).
Unanswered, it goes by itself once it has shown for SHOWN_MS, and isn't
asked again until the app starts again (`SteadyLanguage.unanswered`).
Hidden while the window is locked (clicks pass through it then) and back
when it's unlocked, its while starting again.

Like the rest of a caption window it never takes the keyboard: its
buttons take no focus, and the window doesn't activate on a click.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.languages import named_question

TEXT, LINE, ACCENT, ACCENT_TEXT = "#e9ecf2", "#262b34", "#7c9cff", "#0b0e14"
WIDTH = 440
"""Its widest at 100 % text size (it grows with the text): the question
wraps under it, the buttons stay on one line."""

SHOWN_MS = 60_000
"""How long it shows, unanswered, before it goes by itself: long enough to
be seen between captions, short enough that it doesn't sit over a whole
lecture (350; counted while it shows - a locked window's hidden question
starts its minute again when unlocked)."""


def _tr(text: str) -> str:
    return QApplication.translate("SpokenNudge", text)


def nudge_style() -> str:
    """Its look, at the text size now: the notice line's panel, Yes in the
    accent as Back to live is."""
    return f"""
QWidget#spoken_nudge {{ background: rgba(25,29,36,0.94); border: 1px solid {LINE};
  border-radius: 9px; }}
QLabel {{ color: {TEXT}; font-size: {style.px(12)}px; background: transparent; }}
QPushButton {{ border-radius: 8px; padding: 3px 12px; font-size: {style.px(12)}px;
  color: {TEXT}; background: rgba(255,255,255,0.10); border: none; }}
QPushButton:hover {{ background: rgba(255,255,255,0.18); }}
QPushButton#spoken_nudge\\.yes {{ background: {ACCENT}; color: {ACCENT_TEXT};
  font-weight: 600; }}
"""


class SpokenNudge(QWidget):
    """The question and its two answers; `answered` with True for Yes,
    `went` when it has shown SHOWN_MS unanswered."""

    answered = Signal(bool)
    went = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("spoken_nudge")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.code: str | None = None
        """The language asked about; None while nothing is."""
        line = QHBoxLayout(self)
        line.setContentsMargins(12, 6, 8, 6)
        line.setSpacing(8)
        self.question = QLabel(self)
        self.question.setObjectName("spoken_nudge.question")
        self.question.setWordWrap(True)
        line.addWidget(self.question, 1)
        self.yes = self._button("spoken_nudge.yes", _tr("Yes"), True)
        self.no = self._button("spoken_nudge.not_now", _tr("Not now"), False)
        line.addWidget(self.yes)
        line.addWidget(self.no)
        self._while = QTimer(self, singleShot=True, interval=SHOWN_MS)
        self._while.timeout.connect(self.went)
        self.restyle()
        self.hide()

    def _button(self, name: str, text: str, answer: bool) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(name)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # never the keyboard
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: self._answer(answer))
        return button

    def restyle(self) -> None:
        self.setStyleSheet(nudge_style())
        self.setMaximumWidth(style.px(WIDTH))

    def ask(self, code: str) -> None:
        """Asks about `code` (shown by its window: `CaptionWindow`)."""
        self.code = code
        self.question.setText(named_question(code))
        self.adjustSize()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._while.start()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._while.stop()

    def _answer(self, yes: bool) -> None:
        self.answered.emit(yes)
