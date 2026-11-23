"""The first caption window sets itself up (polyglotic-hq 465, 449's design
3A; DECISIONS.md #195 item 5): the first caption window on a PC opens with
its three language choices asked in it - They speak, Translate into, and
what to do when they already speak the window's language - each already
filled in, and Start captions.

The user, 2026-11-17: "make detect, translation selection and secondary
language selection more noticeable / easier to reach. Maybe introduce a
set up screen on first caption window opening which sets it as a default,
existing behaviour remains where last behaviour remains as default on
open."

- **The same rows as the settings popover** (`settings_popover`): it is
  one, with a heading, a line under two of its rows and a foot (Start
  captions). A choice applies at once, as in the popover; the answers are
  how new windows start (`StoredWindows.start_like_this`).
- **Inside its window**, over the captions under the hover band, and
  following it when it moves; at the work area's edge it moves in. In a
  joined window, inside its column, as narrow as the column if it must
  be: windows start joined, and joining (a second app's window opening)
  or separating keeps the question (polyglotic-hq 554). **Never over
  its window's resize edges:** in a window too short for it - a new one
  at its usual 300 px - it shows just above the window (below, if the
  screen has no room above); hanging past the window's foot, it took the
  presses meant for the bottom edge and corners (polyglotic-hq 586).
- **It never blocks:** captions are heard and kept while it shows, and the
  first one closes it (`CaptionWindow.set_up_heard`) - not while the mouse
  is on it or one of its lists is open: the next caption after does.
  Neither a click elsewhere nor Esc closes it (a click in a game, or Esc
  for its menu, isn't an answer).
- Like the popover it never takes the keyboard or the focus.

**On every window that opens, until "Use as my default"** (polyglotic-hq
478; the user, 2026-11-18: "need a caption open quick configuration
screen, select translate language (selecting as default on start up gets
rid of the screen for future opens), select secondary language, default to
detect language"). Closed without it - Start captions, or a caption came -
its answers are that window's, and the next window that opens asks again.
With it, they're how new windows start and it never shows again
(`StoredWindows.set_up`); a window's language chip brings it back ("Ask
when a window opens"). A learner with windows from before it came (0.1.7)
is never asked.

- **My speech too** (polyglotic-hq 478; the user, 2026-11-18: "record user
  mic in first window is the default"): a new learner's first window starts
  showing it, and the set-up shows its switch - on there - with a line
  saying what that sends: the popover's own switch, so turning it off here
  turns it off in the window.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.settings_popover import (
    ACCENT,
    SettingsPopover,
)
from polyglotic_desktop.ui_next.views import placement
from polyglotic_desktop.ui_next.views.placement import Rect

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow

ROWS = ("set_up_head", "spoken", "language", "second", "set_up_mic", "set_up_foot")
"""Its rows, top to bottom: the popover's three language rows and my
speech between a heading and the foot."""
WIDTH = 440
"""At 100 % text size: wider than the popover, so a row's words and its
choice sit on one line (449's picture)."""
MARGIN = 12
"""Pixels between it and its window's sides, at least."""
ACCENT_TEXT = "#0b0e14"


def _tr(text: str) -> str:
    return QApplication.translate("CaptionSetUp", text)


class CaptionSetUp(SettingsPopover):
    """The first window's set-up: its language rows, Start captions."""

    done = Signal()
    """Start captions: the answers stand (or a caption came: the window
    closes it the same way)."""

    def __init__(self, window: "CaptionWindow") -> None:
        super().__init__(window, None, ROWS)
        self.setObjectName("caption_set_up")
        self.width_at_100 = WIDTH
        self.setFixedWidth(style.px(WIDTH))
        spoken = self.rows["spoken"].layout()
        assert isinstance(spoken, QVBoxLayout)
        spoken.insertWidget(
            1,
            self._note(
                _tr("Detect works out the language each time someone speaks."),
                self.rows["spoken"],
            ),
        )
        # its choice at the right of its words, as the other two rows'
        second = self.rows["second"].layout()
        assert isinstance(second, QVBoxLayout)
        second.removeWidget(self.second_title)
        second.removeItem(self.second_line)
        line = QHBoxLayout()
        line.addWidget(self.second_title, 1)
        line.addWidget(self.second)
        second.insertLayout(0, line)
        second.insertWidget(
            1,
            self._note(
                _tr("Translate those lines into a second language too, or leave them."),
                self.rows["second"],
            ),
        )

    def _set_up_head_row(self) -> QWidget:
        heading = QLabel(_tr("Set up your captions"), self)
        heading.setStyleSheet(f"font-size: {style.px(16)}px; font-weight: 600;")
        return heading

    def _set_up_mic_row(self) -> QWidget:
        """Show my speech here - on in a new learner's first window (478) -
        and what it sends."""
        row = QWidget(self)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._wide(self.owner.controls["show_mic"], switch=True))
        column.addWidget(
            self._note(
                _tr(
                    'Shown as "You". Your mic is sent for your captions only while '
                    "it's on."
                ),
                row,
            )
        )
        return row

    def _set_up_foot_row(self) -> QWidget:
        """Use as my default - off until chosen (478) - and Start captions
        beside it, with a line saying what the choice does."""
        row = QWidget(self)
        column = QVBoxLayout(row)
        column.setContentsMargins(0, 6, 0, 0)
        column.setSpacing(0)
        line = QHBoxLayout()
        line.setSpacing(12)
        column.addLayout(line)
        self.as_default = QAction(_tr("Use as my default"), self)
        self.as_default.setObjectName("caption_set_up.as_default")
        self.as_default.setCheckable(True)
        self.as_default.setToolTip(
            _tr("New caption windows start like this, and this stops showing")
        )
        line.addWidget(self._button(self.as_default, row, switch=True), 1)
        self.start = QPushButton(_tr("Start captions"), row)
        self.start.setObjectName("caption_set_up.start")
        self.start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: {ACCENT_TEXT}; border: none;"
            f" border-radius: 6px; padding: 5px 14px; font-weight: 600;"
            f" text-align: center; }}"
        )
        self.start.clicked.connect(self.done)
        line.addWidget(self.start, 0, Qt.AlignmentFlag.AlignVCenter)
        column.addWidget(
            self._note(
                _tr(
                    "On: new windows start like this and this stops showing. The "
                    "languages on a window's bar change them, or bring it back."
                ),
                row,
            )
        )
        return row

    # -- where it shows -------------------------------------------------------------------

    def open_over(self) -> None:
        """Shown over its window's captions, without taking the keyboard or
        the focus - and with no watch on Esc or clicks elsewhere."""
        for opened in ("languages", "spoken_choices", "second_choices"):
            getattr(self, opened).hide()
        self._anchor = QRect()  # not beside a button
        self.refresh()
        self.show()

    def busy(self) -> bool:
        """The learner is at it: the mouse on it, or one of its lists open."""
        if any(
            getattr(self, opened).isVisible()
            for opened in ("languages", "spoken_choices", "second_choices")
        ):
            return True
        return self.isVisible() and self.frameGeometry().contains(
            self._window.pointer()
        )

    def _put(self) -> None:
        """Inside its window under the band, as wide as it fits; moved in
        to stay on the work area. In a window too short for it, above the
        window - else below it - never over its resize edges: it hung
        past a 300 px window's foot and took the presses meant for the
        bottom edge and corners (polyglotic-hq 586)."""
        owner = self._window
        if not owner.isVisible() and not self.isVisible():
            return
        top_left = owner.mapToGlobal(QPoint(0, 0))
        width = min(self.width(), max(1, owner.width() - 2 * MARGIN))
        if width != self.width():
            self.setFixedWidth(width)
            height = self.heightForWidth(width)
            self.resize(width, height if height > 0 else self.sizeHint().height())
        x = top_left.x() + (owner.width() - self.width()) // 2
        area = owner.area_at(QRect(top_left, owner.size()))
        y = beside_if_short(
            top_left.y(), owner.height(), owner.band_bottom(), self.height(), area
        )
        self.move(*placed_in(Rect(x, y, self.width(), self.height()), area))

    def follow(self) -> None:
        """Its window moved or changed size: it goes with it."""
        if self.isVisible():
            self._fit()


def beside_if_short(top: int, height: int, band: int, tall: int, area: Rect) -> int:
    """Where a set-up `tall` px high goes for a window at `top`, `height`
    high, its band `band` px: under the band if it fits there clear of the
    window's foot and its corners (`placement.CORNER_ZONE`); else just
    above the window, or below it, where the work area `area` has room;
    else under the band as before."""
    under = top + band
    if under + tall <= top + height - placement.CORNER_ZONE:
        return under
    above = top - MARGIN - tall
    if above >= area.y:
        return above
    below = top + height + MARGIN
    if below + tall <= area.bottom:
        return below
    return under


def placed_in(rect: Rect, area: Rect) -> tuple[int, int]:
    """`rect`'s top left, moved up or in as little as keeps it on `area`."""
    x = min(max(rect.x, area.x), area.x + area.width - rect.width)
    y = min(max(rect.y, area.y), area.y + area.height - rect.height)
    return max(x, area.x), max(y, area.y)
