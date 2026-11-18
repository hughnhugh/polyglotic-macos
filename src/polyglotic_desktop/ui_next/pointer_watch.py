"""The mouse over a caption window while the app is in the background, on a
Mac (polyglotic-hq 515).

macOS tells the windows of an app that isn't active nothing of the mouse
passing over them: Qt's tracking area hears it, but its view drops the
moves, the arrival and the leaving while the app isn't active (Qt 6's
QNSView: `if (!NSApp.active) return;`). The app is an accessory that never
activates when a caption window is clicked (`platform/macos/on_top.py`), so
while the learner watches a video in another app - nearly always - the
mouse over a caption window showed nothing: no strip, no word marked under
it, no settings button to press, no card from resting on a word. Presses
and drags still came (GitHub's Mac, polyglotic-hq 515's run 1: the strip
never showed with TextEdit in front; every corner still resized). On
Windows a background app's window hears the mouse as any other.

`PointerWatch` stands in for macOS while the app isn't active: every
`POLL_MS` it looks at where the mouse is (`QCursor.pos`: macOS's own
reading, which needs no permission and takes nothing from the app in
front) and tells the window under it as macOS would have - its arrival, its
moves, its leaving - through the window's own `QWindow`, so Qt hands each
to the widget under the mouse as it does a real one (the strip's buttons
light up too). It stays out of the way while a button is held (a press, a
drag: those still come from macOS) and while the app is active (Qt has the
mouse then); its timer runs only while the app isn't. A locked window lets
the mouse through, as it does a real one.
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QCursor, QEnterEvent, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

POLL_MS = 50
"""How often it looks: a strip shown within 50 ms of the mouse's arrival
(its own BAND_IN_MS is 80), and a word marked as the mouse moves."""


class PointerWatch(QObject):
    """Tells the windows `windows` gives (top-most first) of the mouse while
    the app is in the background. `pointer`: where the mouse is, on the
    screen; `held`: whether a mouse button is down; `active`: whether the
    app is active."""

    def __init__(
        self,
        windows: Callable[[], Sequence[QWidget]],
        parent: QObject | None = None,
        pointer: Callable[[], QPoint] = QCursor.pos,
        held: Callable[[], bool] = lambda: bool(QGuiApplication.mouseButtons()),
        active: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._windows = windows
        self._pointer = pointer
        self._held = held
        self._active = active or _app_active
        self._over: QWidget | None = None
        self._at: QPoint | None = None
        self.timer = QTimer(self, interval=POLL_MS)
        self.timer.timeout.connect(self.look)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._state_changed)

    def start(self) -> None:
        """Looks from now on while the app isn't active."""
        if not self._active():
            self.timer.start()

    def _state_changed(self, state: Qt.ApplicationState) -> None:
        if state == Qt.ApplicationState.ApplicationActive:
            self.timer.stop()  # Qt has the mouse; a window hovered keeps its own watch
            self._over, self._at = None, None
        else:
            self.timer.start()

    def look(self) -> None:
        """Where the mouse is now, told to the window under it."""
        if self._active():
            self.timer.stop()
            return
        shown = [w for w in self._windows() if _showing(w)]
        if not shown and self._over is None:
            return
        if self._held():
            return  # a press or a drag: macOS sends those itself
        at = self._pointer()
        under = next((w for w in shown if w.frameGeometry().contains(at)), None)
        over = self._over
        if under is not over:
            if over is not None and _alive(over):
                _send(over, QEvent(QEvent.Type.Leave))
            if under is not None:
                local = QPointF(under.mapFromGlobal(at))
                _send(under, QEnterEvent(local, local, QPointF(at)))
            self._over, self._at = under, None
        if under is not None and at != self._at:
            local = QPointF(under.mapFromGlobal(at))
            _send(
                under,
                QMouseEvent(
                    QEvent.Type.MouseMove,
                    local,
                    QPointF(at),
                    Qt.MouseButton.NoButton,
                    Qt.MouseButton.NoButton,
                    Qt.KeyboardModifier.NoModifier,
                ),
            )
            self._at = at


def _app_active() -> bool:
    return QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive


def _alive(widget: QWidget) -> bool:
    try:
        widget.objectName()
    except RuntimeError:  # deleted
        return False
    return True


def _showing(widget: QWidget | None) -> bool:
    """Shown and taking the mouse: a locked window and the card while it's
    only hovered let the mouse through to what's under them."""
    return (
        widget is not None
        and _alive(widget)
        and widget.isVisible()
        and not widget.windowFlags() & Qt.WindowType.WindowTransparentForInput
    )


def _send(widget: QWidget, event: QEvent) -> None:
    """To the widget's own window, which hands it on as Qt does a real
    one: to the widget under the mouse."""
    handle = widget.windowHandle()
    QApplication.sendEvent(handle if handle is not None else widget, event)
