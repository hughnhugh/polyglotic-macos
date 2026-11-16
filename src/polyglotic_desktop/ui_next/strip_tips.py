"""What a caption window's strip buttons do, said on hover (polyglotic-hq
395: "hovering caption nav bar icons should say what they do").

Qt shows a widget's tooltip only while its window, or a window above it,
is the active one (`QApplication`'s tooltip timer asks `isActiveWindow`),
and a caption window never is: it never takes the focus
(`Qt.WindowDoesNotAcceptFocus`), so a full-screen game keeps it. Its
buttons' tooltips were never shown. So the strip has a hover label of its
own (`HoverLabel`): shown `REST_MS` after the mouse comes to rest on a
button - at once when it moves from one button to the next - with the
button's own tooltip (in the interface language, at the app's text
size), and gone when the mouse leaves or presses.

It never takes the focus and lets clicks through, like the window. It
sits just above the window, clear of the captions; only when the window
is at the top of its screen does it go under the strip, over the
captions, and then for `OVER_CAPTIONS_MS` at most.
"""

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QEnterEvent, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QLabel, QToolButton, QWidget

from polyglotic_desktop.ui_next import style

REST_MS = 500
"""How long the mouse rests on a button before its label shows (Qt's own
tooltips wait 700 ms)."""
SHOWN_MS = 10000
"""The longest a label stays above the window - long enough to read the
longest (Fill the width's)."""
OVER_CAPTIONS_MS = 3000
"""The longest a label stays over the captions (a window at the top of
its screen has no room above it)."""
TEXT = "#e9ecf2"
"""The caption windows' words (`caption_window.TEXT`): on its own dark panel."""
GAP = 4
WIDEST = 360
"""A label wider than this, in pixels at 100 % text size, wraps."""
"""Pixels between the label and the window (or the strip)."""
TipText = Callable[[QPoint], str]
"""A widget's label at a point in it (a button's is the same everywhere)."""


def tip_place(
    size: tuple[int, int], button: QRect, window: QRect, area: QRect
) -> tuple[QRect, bool]:
    """Where a label of `size` (width, height) goes for `button` (on the
    screen) on `window` (its window's frame, on the screen) inside `area`
    (the screen's work area): centred over the button, just above the
    window - or, with no room there, just under the button, over the
    captions (the second value, True). Never off the screen."""
    width, height = size
    x = button.center().x() - width // 2
    x = max(area.left(), min(x, area.right() + 1 - width))
    above = window.top() - GAP - height
    if above >= area.top():
        return QRect(x, above, width, height), False
    below = min(button.bottom() + 1 + GAP, area.bottom() + 1 - height)
    return QRect(x, below, width, height), True


def label_style() -> str:
    """The label's look, at the text size now: the caption windows' notice
    colours, opaque, so it reads over any game or video."""
    return (
        f"background: rgb(25,29,36); color: {TEXT}; border: 1px solid #3a4150;"
        f" border-radius: 6px; padding: 4px 8px; font-size: {style.px(12)}px;"
    )


class HoverLabel(QLabel):
    """The label itself: on top of everything, never active, never in the
    mouse's way."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(
            parent,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setObjectName("strip_tip")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWordWrap(True)
        self.over_captions = False
        """Whether it's shown under the strip, over the captions."""


class StripTips(QObject):
    """Hover labels for the buttons of one window's strip (`watch`)."""

    def __init__(self, owner: QWidget) -> None:
        super().__init__(owner)
        self.label = HoverLabel(owner)
        self.texts: dict[QWidget, TipText] = {}
        self.over: QWidget | None = None
        """The watched widget the mouse is on, or None."""
        self.at = QPoint()
        """Where the mouse is on it."""
        self._rest = QTimer(self, singleShot=True, interval=REST_MS)
        self._rest.timeout.connect(self._show)
        self._gone = QTimer(self, singleShot=True)
        self._gone.timeout.connect(self.hide)

    def watch(self, widget: QWidget, text: TipText | None = None) -> None:
        """Say `widget`'s `text` on hover - by default its action's tooltip
        (a strip button's) or its own, read each time, so a changed tip
        (Stop captioning's app, word links turned off) is the one said."""
        self.texts[widget] = text or partial(_tooltip_at, widget)
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(watched, QWidget) or watched not in self.texts:
            return False
        kind = event.type()
        if kind is QEvent.Type.ToolTip:
            return True  # Qt's own, should the window ever be active: ours instead
        if isinstance(event, (QEnterEvent, QMouseEvent)):
            self.at = event.position().toPoint()
        if kind is QEvent.Type.Enter:
            self.over = watched
            if self.label.isVisible():
                self._show()  # from one button to the next: at once
            else:
                self._rest.start()
        elif kind is QEvent.Type.MouseMove and watched is self.over:
            if self.label.isVisible():
                self._show()  # a widget whose tip depends on the place (the label's mic)
        elif kind in (QEvent.Type.Leave, QEvent.Type.Hide) and watched is self.over:
            self.over = None
            self.hide()
        elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            self.hide()
        return False

    def _show(self) -> None:
        widget = self.over
        if widget is None or not widget.isVisible():
            return
        text = self.texts[widget](self.at)
        if not text:
            self.hide()
            return
        label = self.label
        label.setStyleSheet(label_style())
        label.setText(text)
        fit(label, style.px(WIDEST))
        button = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
        window = widget.window().frameGeometry()
        screen = widget.screen() or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else window
        place, over = tip_place((label.width(), label.height()), button, window, area)
        label.over_captions = over
        label.setGeometry(place)
        label.show()
        label.raise_()
        self._gone.start(OVER_CAPTIONS_MS if over else SHOWN_MS)

    def hide(self) -> None:
        self._rest.stop()
        self._gone.stop()
        self.label.hide()


def fit(label: QLabel, widest: int) -> None:
    """`label` on one line, or wrapped at `widest` pixels if that's wider."""
    label.setWordWrap(False)
    label.ensurePolished()
    hint = label.sizeHint()
    if hint.width() <= widest:
        label.resize(hint)
        return
    label.setWordWrap(True)
    label.resize(widest, label.heightForWidth(widest))


def _tooltip_at(widget: QWidget, _at: QPoint) -> str:
    return tooltip_of(widget)


def tooltip_of(widget: QWidget) -> str:
    """A strip button's tooltip: its action's, or its own."""
    if isinstance(widget, QToolButton) and widget.defaultAction() is not None:
        return widget.defaultAction().toolTip()
    return widget.toolTip()
