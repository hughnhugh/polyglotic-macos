"""Dictation's sign: a small pill at the bottom of the screen while the dictation key is held, and just after (polyglotic-hq 283, decision 0073).

"Listening", with the mic's level, while the key is held; "Working..."
from letting go to the text; then, if nothing was typed, why - for two
seconds ("Didn't catch that", "Cancelled", "No answer from the server -
nothing typed"...); five for "Not allowed to type", a Mac without the
Accessibility permission, which Settings > Dictation explains with a way
to System Settings (polyglotic-hq 438). Typed text needs no word: the sign just goes. Turned
on, it says which key to hold for four seconds ("Hold Right Ctrl and
speak"; polyglotic-hq 289).

It never takes the focus and lets clicks through (the window being typed
into must keep the keyboard, and a full-screen game mustn't minimise). It
sits above the taskbar of the screen the mouse is on, in the caption
windows' dark colours whatever the window theme. `main` hands it
`ui.dictation.Dictating`'s `sign_changed`.
"""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPaintEvent
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.ui_next.above_all import ABOVE_ALL
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.style import at_app_text_size, px, ui_font
from polyglotic_desktop.ui_next.views.respeaking import SIGN_GAP

SAID_MS = 2000
"""How long the sign says why nothing was typed."""
LONGER_SAID_MS = 5000
"""How long it says what the learner has to do something about: the
OS not letting the app type (polyglotic-hq 438)."""
LONGER = frozenset({"not_allowed"})
HINT_MS = 4000
"""How long it says which key to hold, once dictation is turned on."""
_ABOVE_TASKBAR = 28
_HEIGHT = 40
_LISTENING_DOT = QColor("#ff5c5c")
_WORKING_DOT = QColor("#7c9cff")
_PANEL = QColor(20, 22, 28, 235)
_TEXT = QColor("#e9ecf2")
_BARS = 8


def _tr(text: str) -> str:
    return QApplication.translate("DictationSign", text)


def said_text(said: str, key: str = "") -> str:
    """What the sign says for a `Said` value; "" for nothing (typed, or
    idle). `key`: dictation's key, in words ("Right Ctrl")."""
    texts = {
        "nothing_heard": _tr("Didn't catch that"),
        "no_mic": _tr("No microphone found"),
        "too_short": (
            _tr("Hold {key} while you speak").format(key=key)
            if key
            else _tr("Hold the key while you speak")
        ),
        "cancelled": _tr("Cancelled"),
        "no_answer": _tr("No answer from the server - nothing typed"),
        "no_server": _tr("Not connected to the server - nothing typed"),
        "window_changed": _tr("Another window has the keyboard - nothing typed"),
        "not_typed": _tr("Couldn't type it here"),
        # a Mac without the Accessibility permission (polyglotic-hq 438)
        "not_allowed": _tr("Not allowed to type - see Settings > Dictation"),
        "sign_in": _tr("Sign in to dictate"),
    }
    return texts.get(said, "")


def respeaking_said(said: str) -> str:
    """What the sign says once a re-speaking hold is over and nothing was
    captioned (a `core.listening.respeaking.Said` value); "" for nothing
    to say - captioned, or idle."""
    texts = {
        "nothing_heard": _tr("Didn't catch that"),
        "no_mic": _tr("No microphone found"),
        "too_short": _tr("Hold the key while you speak"),
        "cancelled": _tr("Cancelled"),
        "no_answer": _tr("No answer from the server"),
        "no_server": _tr("Not connected to the server"),
        "no_source": _tr("Nothing else is being captioned to re-speak for"),
    }
    return texts.get(said, "")


class DictationSign(QWidget):
    """The pill: shown without activating, click-through, on top."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
            | ABOVE_ALL,
        )
        self.setObjectName("DictationSign")
        self.setWindowTitle(_tr("Dictation"))  # never shown; tools name it
        self.setAccessibleName(_tr("Dictation"))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # on a Mac a tool window hides while the app isn't active - and the
        # app is never active while the learner is in another (polyglotic-hq 429)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.text = self._display = ""
        self.listening = False
        self.level = 0.0
        self.key = ""
        """Dictation's key, in words ("Right Ctrl"), as the sign names it."""
        self._anchor: QRect | None = None
        self._hide_later = QTimer(self, singleShot=True, interval=SAID_MS)
        self._hide_later.timeout.connect(self.hide)

    def show_state(
        self,
        state: str,
        level: float = 0.0,
        *,
        speakers: bool = False,
        window: QWidget | None = None,
    ) -> None:
        """A `Stage` value ("listening", "working", "idle") or a `Said`
        value, as `Dictating.sign_changed` gives them."""
        anchor = QRect(window.mapToGlobal(QPoint()), window.size()) if window else None
        moved = anchor != self._anchor
        self._anchor = anchor
        self._hide_later.stop()
        self.listening = state == "listening"
        self.level = level
        if self.listening:
            text = (
                pc_or_mac(
                    _tr("Listening to the PC - let go to type it"),
                    _tr("Listening to the Mac - let go to type it"),
                )
                if speakers
                else _tr("Listening")
            )
        elif state == "working":
            text = _tr("Working…")
        else:
            text = (
                {
                    "nothing_heard": _tr("Didn't hear anyone"),
                    "no_mic": _tr("Couldn't capture speaker audio"),
                    "too_short": _tr("Hold the key while they speak"),
                    "own_window": _tr("Choose a text field in another app"),
                    "sign_in": _tr("Sign in to type what they said"),
                    "copied": _tr("Copied to the clipboard. Paste it where you want."),
                }.get(state, said_text(state))
                if speakers
                else said_text(state, self.key)
            )
            if not text:
                self.hide()
                return
            self._hide_later.start(LONGER_SAID_MS if state in LONGER else SAID_MS)
        self._show_text(text, moved)

    def show_respeaking(
        self,
        state: str,
        level: float = 0.0,
        whose: str = "",
        window: QWidget | None = None,
    ) -> None:
        """Re-speaking's state (polyglotic-hq 567), as
        `Respeaking.sign_changed` gives it: whose it's for while held -
        "Re-speaking for Discord" - then nothing once it's captioned (the
        caption shows), or why not."""
        anchor = (
            QRect(window.mapToGlobal(QPoint()), window.size())
            if window is not None
            else None
        )
        moved = self._anchor != anchor
        self._anchor = anchor
        self._hide_later.stop()
        self.listening = state == "listening"
        self.level = level
        if self.listening:
            text = (
                _tr("Re-speaking for {name} - let go to caption").format(name=whose)
                if whose
                else _tr("Re-speaking")
            )
        elif state == "working":
            text = _tr("Working…")
        else:
            text = respeaking_said(state)
            if not text:
                self.hide()
                return
            self._hide_later.start(SAID_MS)
        self._show_text(text, moved)

    def show_hint(self) -> None:
        """Dictation was just turned on: which key to hold, for
        `HINT_MS` (polyglotic-hq 289)."""
        if not self.key or self.isVisible():
            return
        self._anchor = None
        self.listening = False
        self._show_text(_tr("Hold {key} and speak").format(key=self.key))
        self._hide_later.start(HINT_MS)

    def _show_text(self, text: str, moved: bool = False) -> None:
        if moved or text != self.text or not self.isVisible():
            self.setAccessibleName(text)
            self.text = text
            self._place()
        self.show()
        self.update()

    def _place(self) -> None:
        self.setFont(at_app_text_size(ui_font()))
        metrics = self.fontMetrics()
        meter = px(_BARS * 8 + 12) if self.listening else 0
        width = px(40) + metrics.horizontalAdvance(self.text) + meter + px(18)
        screen = (
            QGuiApplication.screenAt(
                self._anchor.center() if self._anchor else QCursor.pos()
            )
            or QGuiApplication.primaryScreen()
        )
        area = screen.availableGeometry()
        self.resize(min(area.width(), width), px(_HEIGHT))
        self._display = metrics.elidedText(
            self.text,
            Qt.TextElideMode.ElideMiddle,
            self.width() - px(40) - px(18) - meter,
        )
        if self._anchor is not None:
            anchor = self._anchor
            gap = px(SIGN_GAP.value)
            x = anchor.center().x() - self.width() // 2
            y = anchor.top() - self.height() - gap
            if y < area.top():
                y = anchor.bottom() + gap
            self.move(
                max(area.left(), min(x, area.right() - self.width() + 1)),
                max(area.top(), min(y, area.bottom() - self.height() + 1)),
            )
            return
        self.move(
            area.center().x() - self.width() // 2,
            area.bottom() - self.height() - px(_ABOVE_TASKBAR),
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_PANEL)
        radius = self.height() / 2
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(1, 1, -1, -1), radius, radius
        )
        dot = px(12)
        painter.setBrush(_LISTENING_DOT if self.listening else _WORKING_DOT)
        painter.drawEllipse(QRectF(px(16), (self.height() - dot) / 2, dot, dot))
        painter.setPen(_TEXT)
        text_left = px(40)
        advance = self.fontMetrics().horizontalAdvance(self._display)
        painter.drawText(
            QRectF(text_left, 0, advance + 2, self.height()),
            Qt.AlignmentFlag.AlignVCenter,
            self._display,
        )
        if self.listening:  # the meter
            painter.setPen(Qt.PenStyle.NoPen)
            left = text_left + advance + px(12)
            for i in range(_BARS):
                lit = self.level * _BARS > i
                painter.setBrush(QColor(255, 92, 92, 230 if lit else 60))
                height = px(6 + i * 2)
                painter.drawRoundedRect(
                    QRectF(
                        left + i * px(8), (self.height() - height) / 2, px(5), height
                    ),
                    2,
                    2,
                )
        painter.end()
