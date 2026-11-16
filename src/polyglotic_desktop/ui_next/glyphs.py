"""The caption windows' small icons - word links, lock, settings, close,
more and the mic - drawn with QPainter, so they're the same on every OS.

They were Windows' icon font, Segoe Fluent Icons, whose private-use
characters are empty boxes wherever the font isn't installed - macOS,
Linux, and any Windows without it (polyglotic-hq 171, 179). Drawn here in
that font's manner and at its size: outlines on a 16-unit square that is
the font's em box, a stroke one unit wide (at least a pixel), round ends,
so the band looks as it did on Windows.
"""

import math
from enum import StrEnum

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontInfo,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

GRID = 16.0
"""The icons' design square: the icon font's em box."""
STROKE = 1.25
"""Units: the font's strokes as Windows draws them at this size, hinted a
little heavier than their outlines."""
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
"""Display scales an icon carries a pixmap for: Windows' usual steps."""


WIDTH_FROM = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]
"""Windows' icon fonts, which these icons were until 179: only measured, so
a button keeps the width it had - its glyph an em wide and a space either
side - and the band lays out as it did on Windows. Where they aren't
installed, their space is taken as a third of an em."""


class Glyph(StrEnum):
    LOCK = "lock"
    SETTINGS = "settings"
    CLOSE = "close"
    MORE = "more"
    MIC = "mic"
    LINKS = "links"
    REPORT = "report"
    SPEAKER = "speaker"
    """The lookup card's "say it" (polyglotic-hq 286): a speaker, one wave."""
    SPEAKING = "speaking"
    """...while it says the word: two waves."""
    NO_VOICE = "no_voice"
    """...with no voice for the word's language: a speaker and a cross."""
    FILL = "fill"
    """A caption window's filled lines (polyglotic-hq 372): lines as wide
    as the window, a pair of them over another - text justified."""
    ALIGNED = "aligned"
    """Parts lined up (372): two lines whose parts start at the same
    places, a tick at each start."""


def _gear() -> QPainterPath:
    """Six teeth around the centre, and the hole."""
    outer, inner = 7.4, 5.5
    path = QPainterPath()
    for tooth in range(6):
        middle = math.radians(tooth * 60 - 90)
        for offset, radius in ((-21, inner), (-11, outer), (11, outer), (21, inner)):
            angle = middle + math.radians(offset)
            point = QPointF(8 + radius * math.cos(angle), 8 + radius * math.sin(angle))
            if path.elementCount() == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
    path.closeSubpath()
    path.addEllipse(QPointF(8, 8), 2.4, 2.4)
    return path


def _outline(glyph: Glyph) -> tuple[QPainterPath, QPainterPath]:
    """`glyph`'s lines (stroked) and dots (filled), on the 16-unit grid."""
    lines, dots = QPainterPath(), QPainterPath()
    if glyph is Glyph.LOCK:
        lines.addRoundedRect(QRectF(2.25, 6.5, 11.5, 8.75), 2, 2)
        lines.moveTo(4.5, 6.5)
        lines.lineTo(4.5, 4.5)
        lines.arcTo(QRectF(4.5, 1, 7, 7), 180, -180)
        lines.lineTo(11.5, 6.5)
        dots.addEllipse(QPointF(8, 10.9), 0.9, 0.9)
    elif glyph is Glyph.SETTINGS:
        lines = _gear()
    elif glyph is Glyph.CLOSE:
        lines.moveTo(3.25, 3.25)
        lines.lineTo(12.75, 12.75)
        lines.moveTo(12.75, 3.25)
        lines.lineTo(3.25, 12.75)
    elif glyph is Glyph.MORE:
        for x in (2.5, 8.0, 13.5):
            dots.addEllipse(QPointF(x, 8), 1.25, 1.25)
    elif glyph is Glyph.LINKS:  # a chain's link, as Windows' own (249)
        lines.moveTo(6.5, 4.5)
        lines.lineTo(4.5, 4.5)
        lines.arcTo(QRectF(1, 4.5, 7, 7), 90, 180)
        lines.lineTo(6.5, 11.5)
        lines.moveTo(9.5, 4.5)
        lines.lineTo(11.5, 4.5)
        lines.arcTo(QRectF(8, 4.5, 7, 7), 90, -180)
        lines.lineTo(9.5, 11.5)
        lines.moveTo(5.5, 8)
        lines.lineTo(10.5, 8)
    elif glyph is Glyph.REPORT:  # a flag: "Report a problem" (polyglotic-hq 275)
        lines.moveTo(3.5, 15)
        lines.lineTo(3.5, 1.5)
        lines.lineTo(12.75, 1.5)
        lines.lineTo(10.5, 5)
        lines.lineTo(12.75, 8.5)
        lines.lineTo(3.5, 8.5)
    elif glyph is Glyph.FILL:  # four lines edge to edge: text filling its width
        for y in (2.5, 6.0, 10.0, 13.5):
            lines.moveTo(1.75, y)
            lines.lineTo(14.25, y)
    elif glyph is Glyph.ALIGNED:  # two lines, their parts starting together
        for y, ends in ((5.0, (6.5, 14.25)), (11.0, (5.0, 12.0))):
            lines.moveTo(1.75, y)
            lines.lineTo(ends[0], y)
            lines.moveTo(8.75, y)
            lines.lineTo(ends[1], y)
        for x in (1.75, 8.75):
            dots.addEllipse(QPointF(x, 8), 0.7, 0.7)
    elif glyph is Glyph.MIC:
        lines.addRoundedRect(QRectF(5.5, 0.75, 5, 9.5), 2.5, 2.5)
        lines.moveTo(3, 7.25)
        lines.arcTo(QRectF(3, 2.25, 10, 10), 180, 180)
        lines.moveTo(8, 12.75)
        lines.lineTo(8, 15.25)
    elif glyph in (Glyph.SPEAKER, Glyph.SPEAKING, Glyph.NO_VOICE):
        lines.moveTo(1.5, 5.75)
        lines.lineTo(4.25, 5.75)
        lines.lineTo(7.75, 2.5)
        lines.lineTo(7.75, 13.5)
        lines.lineTo(4.25, 10.25)
        lines.lineTo(1.5, 10.25)
        lines.closeSubpath()
        if glyph is Glyph.NO_VOICE:
            lines.moveTo(10.5, 5.75)
            lines.lineTo(14.75, 10.25)
            lines.moveTo(14.75, 5.75)
            lines.lineTo(10.5, 10.25)
        else:
            radii = (3.25, 6.0) if glyph is Glyph.SPEAKING else (3.25,)
            for radius in radii:
                wave = QRectF(7.75 - radius, 8 - radius, 2 * radius, 2 * radius)
                lines.arcMoveTo(wave, -45)
                lines.arcTo(wave, -45, 90)
    return lines, dots


def paint(painter: QPainter, glyph: Glyph, box: QRectF, color: QColor) -> None:
    """`glyph` in the square `box`, in `color`."""
    scale = box.width() / GRID
    lines, dots = _outline(glyph)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(box.topLeft())
    painter.scale(scale, scale)
    pen = QPen(color, STROKE)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(lines)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(dots)
    painter.restore()


def text_width(px: int) -> int:
    """The room a glyph of Windows' icon font at `px` pixels took as a
    button's text: itself (an em) and a space either side."""
    font = QFont()
    font.setFamilies(WIDTH_FROM)
    font.setPixelSize(px)
    if QFontInfo(font).family() in WIDTH_FROM:
        space = QFontMetrics(font).horizontalAdvance(" ")
    else:  # not installed (macOS, Linux): their space, about a third of an em
        space = round(px / 3)
    return px + 2 * space


def icon(glyph: Glyph, color: str, size: int, disabled: str | None = None) -> QIcon:
    """`glyph` as an icon `size` pixels square, sharp at each display scale;
    in `disabled`'s colour while its button is off to clicks (Qt's own
    greying leaves a near-white glyph near white, 258)."""
    found = QIcon()
    modes = [(QIcon.Mode.Normal, color)]
    if disabled is not None:
        modes.append((QIcon.Mode.Disabled, disabled))
    for mode, ink in modes:
        for scale in SCALES:
            side = round(size * scale)
            pixmap = QPixmap(QSize(side, side))
            pixmap.setDevicePixelRatio(scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            paint(painter, glyph, QRectF(0, 0, side / scale, side / scale), QColor(ink))
            painter.end()
            found.addPixmap(pixmap, mode)
    return found
