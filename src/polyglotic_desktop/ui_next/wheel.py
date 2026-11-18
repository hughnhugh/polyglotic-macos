"""The mouse wheel scrolls the page: it never changes a setting it passes
over (the user, 2026-11-13: "scrolling settings will inadvertently change
many settings as you navigate the page"; polyglotic-hq 304, decision 0092).

**The rule,** for every list (a dropdown), slider and number box on a page
that scrolls - every page of the main window (Settings and its Lab,
Learning, Words...) and a transcript's settings rail:

- the wheel over one scrolls the page, as if it weren't there;
- a list takes the wheel only while it's open: its own choices scroll;
- a slider or number box takes it once it's been clicked, while the
  pointer stays on it: moving off it, the keyboard moving on or the
  control going out of sight lets it go;
- the wheel never gives one the keyboard (Qt's `WheelFocus`), so the arrow
  keys never change a list the page scrolled past.

Keyboard use is unchanged: Tab and a click give a control the keyboard, and
its keys work as they did. Scrolling a caption window, a transcript or a
list of choices is unchanged too: none of them is a setting.

**One guard, put on each page by the page itself** (`guard`: `home.Page`,
the base of every main-window page, and `transcript_window.SettingsRail`).
When the page shows, and whenever its content's layout changes (a row
added later), it finds the page's lists, sliders and number boxes and
watches only them. Nothing else's events reach Python: watching every
event of the application instead cost a theme change 50-60 ms and the
start 25-40 ms (measured 2026-11-14), and the UI lab's budgets failed.
"""

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QScrollBar,
    QWidget,
)

HELD = (QComboBox, QAbstractSlider, QAbstractSpinBox)
"""What the wheel would change: a list (closed), a slider, a number box. A
scroll bar is a slider too, but it's the page's own: never held."""
CLICKED_INTO = (QAbstractSlider, QAbstractSpinBox)
"""What takes the wheel once clicked. A list doesn't: a click opens it, and
its open choices take the wheel themselves."""

_WHEEL = QEvent.Type.Wheel
_PRESS = QEvent.Type.MouseButtonPress
_LET_GO = frozenset({QEvent.Type.Leave, QEvent.Type.FocusOut, QEvent.Type.Hide})
_LOOK = frozenset({QEvent.Type.Show, QEvent.Type.LayoutRequest})


def held_in(root: QWidget) -> list[QWidget]:
    """The lists, sliders and number boxes in `root`, not scroll bars."""
    found: list[QWidget] = []
    for kind in HELD:
        found += [w for w in root.findChildren(kind) if not isinstance(w, QScrollBar)]
    return found


def page_of(control: QWidget) -> QAbstractScrollArea | None:
    """The scrolling page `control` is on: the nearest scroll area it's
    inside - in its viewport, or pinned above it, as Settings' sections
    dropdown is (polyglotic-hq 470) - or None."""
    found = control.parentWidget()
    while found is not None:
        if isinstance(found, QAbstractScrollArea):
            return found
        if found.isWindow():  # a page may be a window of its own
            return None
        found = found.parentWidget()
    return None


class WheelGuard(QObject):
    """The rule above, as an event filter on each page (and its content)
    and on the controls it finds there."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.clicked: QWidget | None = None
        """The slider or number box clicked into, while it holds the wheel."""

    def watch(self, page: QAbstractScrollArea) -> None:
        """`page`'s controls from now on, as they come."""
        page.installEventFilter(self)
        content = page.widget() if hasattr(page, "widget") else None
        if isinstance(content, QWidget):
            content.installEventFilter(self)

    def look(self, root: QWidget) -> None:
        """Each list, slider and number box in `root` watched, and given
        the keyboard by a click or Tab only."""
        for control in held_in(root):
            control.installEventFilter(self)  # again: Qt keeps it once
            if control.focusPolicy() == Qt.FocusPolicy.WheelFocus:
                control.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if not isinstance(watched, QWidget):
            return False
        if not isinstance(watched, HELD):  # a page or its content
            if kind in _LOOK:
                self.look(watched)
            return False
        if kind == _WHEEL:
            if watched is self.clicked and isinstance(watched, CLICKED_INTO):
                return False  # clicked into: it takes the wheel
            self._scroll_page(watched, event)  # type: ignore[arg-type]
            return True
        if kind == _PRESS:
            self.clicked = watched if isinstance(watched, CLICKED_INTO) else None
        elif kind in _LET_GO and watched is self.clicked:
            self.clicked = None
        return False

    @staticmethod
    def _scroll_page(control: QWidget, event: QWheelEvent) -> None:
        """The wheel to the page `control` is on, not to it."""
        event.accept()  # no further: the page has it, or nothing does
        page = page_of(control)
        if page is None:
            return
        viewport = page.viewport()
        moved = QWheelEvent(
            viewport.mapFromGlobal(event.globalPosition()),
            event.globalPosition(),
            event.pixelDelta(),
            event.angleDelta(),
            event.buttons(),
            event.modifiers(),
            event.phase(),
            event.inverted(),
            event.source(),
            event.pointingDevice(),
        )
        QApplication.sendEvent(viewport, moved)


_GUARD: WheelGuard | None = None


def guard(page: QAbstractScrollArea) -> None:
    """The rule on `page`, a page that scrolls: its lists, sliders and
    number boxes, now and as they come, by the one guard."""
    global _GUARD
    if _GUARD is None or not shiboken6.isValid(_GUARD):
        _GUARD = WheelGuard(QCoreApplication.instance())
    _GUARD.watch(page)
