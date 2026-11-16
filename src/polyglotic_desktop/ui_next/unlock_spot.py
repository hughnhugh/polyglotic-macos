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
"""

from collections.abc import Callable

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer
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

    def look(self) -> None:
        """One look for the mouse (the timer's; a test's own)."""
        spot = self._spot()
        if spot is None:
            self._looks = 0
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

    def _clicked(self) -> None:
        self._hide()
        self._looks = 0
        self._unlock()
