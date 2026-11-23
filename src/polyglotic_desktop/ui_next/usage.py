"""The usage meter of a capped plan (polyglotic-hq 684; PLAN-OPEN-BETA v17):
its words, and the small ring a caption window's bar draws beside the mic.

Capped plans (Free, Lite, a Standard pass) always show how much is left, as
the server's percentage and reset time - never a caption or hour count.
Unlimited plans show nothing. The same words are the ring's tip, its
screen-reader text and (shorter) the tray's line.

A reset time is said on this PC's clock: the server sends an instant, and
the account's midnight is this PC's midnight unless the learner is
travelling, when the time itself is said instead.
"""

from datetime import datetime

from PySide6.QtCore import QDateTime, QLocale, QRectF, QSize, Qt, QTimeZone
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from polyglotic_desktop.core.shared.open_beta import (
    USAGE_WARNING_PERCENTS,
    UsageMeter,
)
from polyglotic_desktop.core.shared.tunables import tunable
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.maintenance import clock_time, pc_zone

RING_STROKE = tunable(
    "usage_ring.stroke",
    2.0,
    "logical pixels",
    (1.0, 4.0),
    source="684: the bar's usage ring's line, as heavy as the bar's glyphs' strokes",
)
RING_PAD = tunable(
    "usage_ring.pad",
    4,
    "logical pixels",
    (0, 12),
    source="684: space each side of the usage ring, the mic button's own padding",
)
RING_TRACK_OPACITY = tunable(
    "usage_ring.track_opacity",
    0.45,
    "opacity, 0 to 1",
    (0.1, 1.0),
    source="684: the used part of the ring, dim enough that the part left reads first",
)
LOW_COLOUR = "#f2c14e"
"""The ring's part left once it is low: the interface's warning colour
(`style`'s WARNING), made readable on the panel by the caption window."""

_FULL_TURN = 360 * 16  # Qt's arcs are in sixteenths of a degree
_TOP = 90 * 16  # 12 o'clock


def _tr(text: str) -> str:
    return QApplication.translate("Usage", text)


def _on_clock(at: datetime, zone: QTimeZone | None) -> QDateTime:
    """`at` on `zone`'s clock (None: this PC's)."""
    return QDateTime.fromMSecsSinceEpoch(
        round(at.timestamp() * 1000), pc_zone() if zone is None else zone
    )


def reset_day(at: datetime, zone: QTimeZone | None = None) -> str:
    """The day `at` falls on by this PC's clock, as its region writes dates."""
    return QLocale().toString(_on_clock(at, zone).date(), QLocale.FormatType.LongFormat)


def _plan_word(plan: str) -> str | None:
    """A monthly capped plan's name in the meter's words; None for one this
    app doesn't know (a later plan: its meter still shows, unnamed)."""
    words = {"lite": lambda: _tr("Lite"), "standard": lambda: _tr("Standard")}
    return words[plan]() if plan in words else None


def meter_text(meter: UsageMeter, zone: QTimeZone | None = None) -> str:
    """The meter in one line: the ring's tip and its screen-reader text.
    `zone`: another clock than this PC's, for tests."""
    reset = meter.resets_at
    if meter.daily:
        if reset is None:
            return _tr("Free today: {percent}% left").format(percent=meter.percent)
        local = _on_clock(reset, zone).time()
        if (local.hour(), local.minute()) == (0, 0):
            return _tr("Free today: {percent}% left - resets at midnight").format(
                percent=meter.percent
            )
        return _tr("Free today: {percent}% left - resets at {time}").format(
            percent=meter.percent, time=clock_time(reset, zone)
        )
    plan = _plan_word(meter.plan)
    if plan is None or reset is None:
        return tray_line(meter)
    return _tr("{plan}: {percent}% of this month’s hours left - resets {date}").format(
        plan=plan, percent=meter.percent, date=reset_day(reset, zone)
    )


def tray_line(meter: UsageMeter) -> str:
    """The tray's one line."""
    if meter.daily:
        return _tr("{percent}% of today’s free captions left").format(
            percent=meter.percent
        )
    return _tr("{percent}% of this month’s hours left").format(percent=meter.percent)


def warning_text(meter: UsageMeter) -> str:
    """What a warning level says once (20 % and 5 % left)."""
    if meter.daily:
        return _tr(
            "{percent}% of today’s free captions left. Upgrade for more listening."
        ).format(percent=meter.percent)
    return tray_line(meter)


def exhausted_text(meter: UsageMeter) -> str:
    """What's said once when the allowance runs out while listening."""
    if meter.daily:
        return _tr(
            "Today’s free captions are used up. Upgrade in Polyglotic to keep"
            " listening."
        )
    return _tr(
        "This month’s hours are used up. Upgrade in Polyglotic to keep listening."
    )


class UsageRing(QWidget):
    """The bar's meter: a ring whose bright part is what's left. It starts
    at the top and runs clockwise, so use eats it back towards the top.
    Hidden with no meter (an unlimited plan)."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("caption_window.band.usage")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.meter: UsageMeter | None = None
        # the caption window gives its colours and size before it shows
        self._side = 0
        self._left, self._used, self._low = QColor(), QColor(), QColor(LOW_COLOUR)
        self.hide()

    def set_ink(self, left: str, used: str, low: str, side: int) -> None:
        """Its colours on the window's panel and its glyph side, in pixels."""
        self._left, self._used, self._low = QColor(left), QColor(used), QColor(low)
        self._used.setAlphaF(RING_TRACK_OPACITY.value)
        self._side = side
        self.setFixedWidth(self.sizeHint().width())
        self.updateGeometry()
        self.update()

    def show_meter(self, meter: UsageMeter | None) -> None:
        if meter == self.meter:
            return
        self.meter = meter
        text = meter_text(meter) if meter is not None else ""
        self.setToolTip(text)
        self.setAccessibleName(_tr("Listening allowance"))
        self.setAccessibleDescription(text)
        self.setVisible(meter is not None)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._side + 2 * style.px(RING_PAD.value), self._side)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: QPaintEvent) -> None:
        meter = self.meter
        if meter is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        stroke = max(1, style.px(RING_STROKE.value))
        side = self._side - stroke
        ring = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        pen = QPen(self._used, stroke)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawEllipse(ring)
        if meter.percent > 0:
            # the warning colour from the first warning level down (v17)
            low = meter.percent <= max(USAGE_WARNING_PERCENTS.value)
            pen.setColor(self._low if low else self._left)
            painter.setPen(pen)
            painter.drawArc(ring, _TOP, -round(_FULL_TURN * meter.percent / 100))
        painter.end()
