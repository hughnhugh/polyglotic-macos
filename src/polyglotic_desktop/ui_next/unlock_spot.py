"""Unlocking a locked caption window from the window itself, with no
hotkey (polyglotic-hq 398; the user, 2026-11-16: "ctrl alt l doesn't seem
to work on my current instance and i can't unlock the caption window").

A locked window passes every click through, so nothing on it can be
clicked - but where the mouse is can still be read. While a window is
locked, `UnlockSpot` looks for the mouse every `LOOK_MS`: when it has
come to the lock in the window's corner (the faint lock the window draws
there) and rested on it for `REST_LOOKS` looks, about a second, an Unlock
button shows over it, a small window of its own that takes clicks; a
click on it unlocks every window. Leaving the lock and the button hides
it again.

Why the lock, and why a rest: a game shouldn't unlock its captions by
accident. The lock is a small spot in a corner; a mouse that was already
there when the window locked (a game holding the cursor still) never
"comes" to it; and nothing unlocks without a click on the button that
then shows. Home's Lock all and the tray's menu unlock too, and the
hotkey where it works.

**Where the OS can't say where the mouse is** (Linux on a Wayland desktop,
polyglotic-hq 547, 570; DECISIONS #243 item 6): the app is an X11 program
there, and the X server knows nothing of the mouse while it is over another
app's window - and a locked window lets it through to that window. So the
lock's corner, at least `CATCH_AT_LEAST`, keeps taking the mouse itself
(`catch`): a small window of its own over the corner, drawn as nothing; the
rest of the window still lets every click through. Behind a setting
(`AppSettings.unlock_spot`, on), so it can go.

There the mouse can be seen arriving - the corner hears it come, and move -
but not leaving: on GNOME 46's XWayland the corner was still "under the
mouse", at the place it last had, with the mouse over the app beneath
(570's run on GitHub's runner). So a rest can't be timed and a leaving
can't be seen: Unlock shows as the mouse arrives on the corner (or clicks
it), and goes `CAUGHT_SHOW_SEC` after the corner or Unlock last heard it,
unless clicked - never left showing over a game.
"""

import time
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

LOOK_MS = 200
"""How often a locked window looks for the mouse."""
REST_LOOKS = 5
"""Looks in a row the mouse rests on the lock before Unlock shows: about a
second."""
AROUND = 8
"""How far around the button the mouse can stray before it hides."""
INSET = 5
"""The button's gap from the window's corner: inside its rounded corner."""
CATCH_AT_LEAST = (60, 40)
"""The least of a locked window's corner that keeps taking the mouse
(`catch`): wide and tall enough to find with a mouse."""
CAUGHT_SHOW_SEC = 3.0
"""How long Unlock stays, while the corner catches, after the corner or
Unlock last heard the mouse (it can't hear it leave)."""


def _tr(text: str) -> str:
    return QApplication.translate("UnlockSpot", text)


class UnlockSpot(QObject):
    """A locked window's Unlock button, shown when the mouse rests on its
    lock (`spot`, on the screen; None while it shows no lock). `pointer`
    is where the mouse is; `unlock` unlocks; `look` is the button's style
    sheet, at the text size now; `flags` its window's (the caption
    windows' own: on top, never taking the focus)."""

    def __init__(
        self,
        window: QWidget,
        spot: Callable[[], QRect | None],
        pointer: Callable[[], QPoint],
        unlock: Callable[[], None],
        look: Callable[[], str],
        flags: Qt.WindowType,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._spot = spot
        self._pointer = pointer
        self._unlock = unlock
        self._look = look
        self._flags = flags
        self.button: QPushButton | None = None
        """Made the first time it shows."""
        self._timer = QTimer(self, interval=LOOK_MS)
        self._timer.timeout.connect(self.look)
        self._came = False
        """The mouse was seen off the lock since watching began: it can
        come to it."""
        self._looks = 0
        self.catching = False
        """The lock's corner takes the mouse itself while it watches
        (`catch`)."""
        self.catcher: QWidget | None = None
        """The corner's own window while it catches: made the first time."""
        self._heard = 0.0
        """When the corner or Unlock last heard the mouse (monotonic)."""
        self.clock: Callable[[], float] = time.monotonic
        """The time (a test's own)."""

    @property
    def watching(self) -> bool:
        return self._timer.isActive()

    @property
    def shown(self) -> bool:
        return self.button is not None and self.button.isVisible()

    def watch(self, on: bool) -> None:
        """Looks for the mouse (locked and shown) or stops, the button
        hidden."""
        if on and not self._timer.isActive():
            self._came = False
            self._looks = 0
            self._timer.start()
        elif not on:
            self._timer.stop()
            self._looks = 0
            self._hide()
        self._place_catcher(self._spot() if on else None)

    def catch(self, on: bool) -> None:
        """Whether the lock's corner takes the mouse itself while it
        watches: where the OS can't say where the mouse is over another
        app (Linux on a Wayland desktop)."""
        self.catching = on
        self._place_catcher(self._spot() if self.watching else None)

    def look(self) -> None:
        """One look for the mouse (the timer's; a test's own)."""
        spot = self._spot()
        self._place_catcher(spot)
        if spot is None:
            self._looks = 0
            self._hide()
            return
        if self.catching:  # the mouse is heard arriving, never leaving
            if self.shown and self.clock() - self._heard > CAUGHT_SHOW_SEC:
                self._hide()
            return
        at = self._pointer()
        if self.shown:
            assert self.button is not None
            near = self.button.geometry().adjusted(-AROUND, -AROUND, AROUND, AROUND)
            if not near.contains(at) and not spot.contains(at):
                self._hide()
                self._came = True
            return
        if not spot.contains(at):
            self._came = True
            self._looks = 0
            return
        if not self._came:  # there since it locked: a game's still cursor
            return
        self._looks += 1
        if self._looks >= REST_LOOKS:
            self._show(spot)

    def _show(self, spot: QRect) -> None:
        button = self.button
        if button is None:
            button = self.button = QPushButton(_tr("Unlock"), self._window)
            button.setWindowFlags(self._flags)  # a window of its own: it takes clicks
            button.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            button.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # a pill
            button.setObjectName("caption_window.unlock")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(_tr("Unlock every caption window"))
            button.clicked.connect(self._clicked)
            button.installEventFilter(self)  # the mouse on it, while catching
            button.setMouseTracking(True)  # its moves too, no button held
        button.setStyleSheet(self._look())
        button.adjustSize()
        # over the lock, inside the window's corner
        button.move(
            spot.right() + 1 - INSET - button.width(),
            spot.bottom() + 1 - INSET - button.height(),
        )
        button.show()
        button.raise_()

    def _hide(self) -> None:
        if self.button is not None:
            self.button.hide()

    def _place_catcher(self, spot: QRect | None) -> None:
        """The corner's own window over `spot`'s corner while it catches,
        at least `CATCH_AT_LEAST`; hidden otherwise."""
        if not self.catching or spot is None:
            if self.catcher is not None:
                self.catcher.hide()
            return
        catcher = self.catcher
        if catcher is None:
            catcher = self.catcher = _Catcher(self._window, self._flags)
            catcher.heard.connect(self._arrived)
        width, height = CATCH_AT_LEAST
        corner = QRect(spot)
        corner.setLeft(min(spot.left(), spot.right() + 1 - width))
        corner.setTop(min(spot.top(), spot.bottom() + 1 - height))
        window = self._window.window()
        on_screen = QRect(window.mapToGlobal(QPoint(0, 0)), window.size())
        corner &= on_screen
        if catcher.geometry() != corner:
            catcher.setGeometry(corner)
        if not catcher.isVisible():
            catcher.show()

    def _arrived(self) -> None:
        """The corner heard the mouse - arriving, moving or clicking: Unlock
        shows, or stays."""
        spot = self._spot()
        if spot is None or not self.catching:
            return
        self._heard = self.clock()
        if not self.shown:
            self._show(spot)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            watched is self.button
            and self.catching
            and event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove)
        ):
            self._heard = self.clock()
        return False

    def _clicked(self) -> None:
        self._hide()
        self._looks = 0
        self._unlock()


class _Catcher(QWidget):
    """A locked window's corner that takes the mouse (`UnlockSpot.catch`):
    a window of its own, drawn as nothing, never taking the focus."""

    heard = Signal()
    """The mouse arrived on it, moved on it or clicked it."""

    def __init__(self, window: QWidget, flags: Qt.WindowType) -> None:
        super().__init__(window)
        self.setWindowFlags(flags)  # a window of its own: it takes the mouse
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)  # moves without a button held
        self.setObjectName("caption_window.unlock_spot")

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Enter:
            self.heard.emit()
        return super().event(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        event.accept()
        self.heard.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        event.accept()
        self.heard.emit()
