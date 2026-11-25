"""A small, themed toast for brief copy and save confirmations (polyglotic-hq
950): rounded, in the popover's own dark colours, with a gentle fade-out.

Replaces Qt's default grey `QToolTip` flash for "Copied to clipboard" and
"Saved". Never takes keyboard focus and lets mouse clicks pass straight
through, so a game or video underneath is never disturbed. Holds only short
UI labels, never caption text.
"""

from __future__ import annotations

import time
import weakref
from collections.abc import Callable

import shiboken6
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.above_all import ABOVE_ALL
from polyglotic_desktop.ui_next.views.arrivals import ease_out
from polyglotic_desktop.ui_next.views.card_window_defaults import (
    TOAST_DURATION_SEC,
    TOAST_FADE_SEC,
)

SURFACE = "#191d24"
BORDER = "#2a303b"
TEXT = "#e9ecf2"
"""The settings popover and sentence card's colours."""
RADIUS = 9
PAD_X = 12
PAD_Y = 6
GAP = 8
BOTTOM_MARGIN = 12
FRAME_MS = 16


def _reduced_motion() -> bool:
    hints = QGuiApplication.styleHints()
    return hints.accessibility().motionPreference() is Qt.MotionPreference.ReducedMotion


def place_toast(
    size: QSize,
    owner: QRect,
    area: QRect,
    at: QPoint | None = None,
) -> QPoint:
    """Where a toast of `size` goes inside `area`: centred just above `at`
    when a screen point is given (or below it if there is no room above),
    otherwise centred near the bottom of `owner`. Clamped inside `area` when
    `owner` sits within it (offscreen tests may place windows on a wider
    virtual work area than Qt's offscreen screen)."""
    width, height = size.width(), size.height()
    bounds = area if area.contains(owner) else owner
    if at is not None:
        x = at.x() - width // 2
        y = at.y() - height - GAP
        if y < bounds.top():
            y = at.y() + GAP
    else:
        x = owner.center().x() - width // 2
        y = owner.bottom() + 1 - height - BOTTOM_MARGIN
    x = max(bounds.left(), min(x, bounds.right() + 1 - width))
    y = max(bounds.top(), min(y, bounds.bottom() + 1 - height))
    return QPoint(x, y)


class Toast(QWidget):
    """A floating, non-activating toast pill with a smooth fade-out."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
            | ABOVE_ALL,
        )
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._clock = clock
        self._text = ""
        self._opacity = 1.0
        self._fade_started = 0.0
        self._fade_sec = TOAST_FADE_SEC.value
        self._hold = QTimer(self, singleShot=True)
        self._hold.timeout.connect(self._begin_fade)
        self._fade = QTimer(self, interval=FRAME_MS)
        self._fade.timeout.connect(self._step_fade)

    def text(self) -> str:
        return self._text

    def opacity(self) -> float:
        return self._opacity

    def _font(self) -> QFont:
        font = style.ui_font()
        font.setPixelSize(style.px(12))
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self._font())
        width = metrics.horizontalAdvance(self._text) + 2 * PAD_X
        height = metrics.height() + 2 * PAD_Y
        return QSize(max(width, 2 * PAD_X), max(height, 2 * PAD_Y))

    def show_message(
        self,
        text: str,
        over: QWidget,
        at: QPoint | None = None,
        *,
        duration: float | None = None,
        fade: float | None = None,
    ) -> None:
        """Show `text` near `at` (global) or near the bottom of `over`'s window."""
        if not text:
            return
        total = TOAST_DURATION_SEC.value if duration is None else max(0.05, duration)
        fade_sec = TOAST_FADE_SEC.value if fade is None else max(0.0, fade)
        fade_sec = min(fade_sec, total)
        self._hold.stop()
        self._fade.stop()
        self._text = text
        self._opacity = 1.0
        self._fade_sec = fade_sec
        self.setAccessibleName(text)
        size = self.sizeHint()
        self.resize(size)
        window = over.window()
        owner_rect = window.frameGeometry()
        screen = window.screen() or QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else owner_rect
        self.move(place_toast(size, owner_rect, area, at))
        self.show()
        self.update()
        hold_sec = total if _reduced_motion() or fade_sec <= 0.0 else total - fade_sec
        self._hold.start(max(1, round(hold_sec * 1000)))

    def dismiss(self) -> None:
        """Hide immediately and stop timers."""
        self._hold.stop()
        self._fade.stop()
        self._opacity = 0.0
        self.hide()

    def _begin_fade(self) -> None:
        if _reduced_motion() or self._fade_sec <= 0.0:
            self.dismiss()
            return
        self._fade_started = self._clock()
        self._fade.start()

    def _step_fade(self) -> None:
        elapsed = self._clock() - self._fade_started
        if elapsed >= self._fade_sec:
            self.dismiss()
            return
        progress = max(0.0, min(1.0, elapsed / self._fade_sec))
        self._opacity = max(0.0, 1.0 - ease_out(progress))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._opacity <= 0.001 or not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setOpacity(self._opacity)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(QColor(SURFACE))
        painter.setPen(QPen(QColor(BORDER), 1.0))
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        painter.setPen(QColor(TEXT))
        painter.setFont(self._font())
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)
        painter.end()


_by_window: weakref.WeakKeyDictionary[QWidget, Toast] = weakref.WeakKeyDictionary()
_last: weakref.ref[Toast] | None = None


def current_toast() -> Toast | None:
    """The most recently shown toast if it is still alive and visible."""
    if _last is None:
        return None
    toast = _last()
    if toast is None or not shiboken6.isValid(toast) or not toast.isVisible():
        return None
    return toast


def toast_text() -> str:
    """The visible toast's message, or "" when none is showing."""
    toast = current_toast()
    return toast.text() if toast is not None else ""


def hide_toast() -> None:
    """Hide the active toast if one is visible."""
    toast = current_toast()
    if toast is not None:
        toast.dismiss()


def show_toast(
    text: str,
    over: QWidget,
    at: QPoint | None = None,
    *,
    duration: float | None = None,
    fade: float | None = None,
) -> Toast:
    """Show a themed toast over `over`'s window (one reusable toast per window)."""
    global _last
    owner = over.window()
    existing = _by_window.get(owner)
    if existing is None or not shiboken6.isValid(existing):
        existing = Toast(owner)
        _by_window[owner] = existing
    previous = current_toast()
    if previous is not None and previous is not existing:
        previous.dismiss()
    existing.show_message(text, over, at, duration=duration, fade=fade)
    _last = weakref.ref(existing)
    return existing
