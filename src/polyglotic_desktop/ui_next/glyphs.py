"""The caption windows' small icons - word links, lock, settings, close,
more and the mic - and Settings' sections' and cards' marks (polyglotic-hq
470), drawn with QPainter, so they're the same on every OS.

They were Windows' icon font, Segoe Fluent Icons, whose private-use
characters are empty boxes wherever the font isn't installed - macOS,
Linux, and any Windows without it (polyglotic-hq 171, 179). Drawn here in
that font's manner and at its size: outlines on a 16-unit square that is
the font's em box, a stroke one unit wide (at least a pixel), round ends,
so the band looks as it did on Windows.
"""

import math
from enum import StrEnum
from functools import cache

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
    HOME = "home"
    """The main window's Home: a house."""
    WORDS = "words"
    """The main window's Words: an open book."""
    LEARNING = "learning"
    """The main window's Learning: a sprout."""
    ACCOUNT = "account"
    """The main window's Account: a person."""
    HELP = "help"
    """The main window's Help: a question mark in a circle."""
    LOCK = "lock"
    SETTINGS = "settings"
    CLOSE = "close"
    MINIMISE = "minimise"
    MORE = "more"
    MIC = "mic"
    MIC_OFF = "mic_off"
    LINKS = "links"
    REPORT = "report"
    COPY = "copy"
    """A caption's Copy button (polyglotic-hq 950): two overlapping pages."""
    SAVE = "save"
    """A caption's Save button (polyglotic-hq 950): a bookmark ribbon."""
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
    QUIET = "quiet"
    """The quiet view (polyglotic-hq 477): two lines of text, one word in
    the first filled in - the one word that stands out."""

    # Settings' sections and cards (polyglotic-hq 470, 449's design 4A):
    # always beside their words, never alone (NN/g's icon usability)
    LOOK = "look"
    """Settings > Look: a caption's panel, two lines of text on it."""
    READINGS = "readings"
    """Settings > Readings: a short line over a letter - ruby, a reading."""
    TIMING = "timing"
    """Settings > Timing: a clock."""
    LANGUAGES = "languages"
    """The caption bar's language choices: a globe."""
    PRESET = "preset"
    """The caption bar's preset choices: a stack of cards."""
    SPEECH = "speech"
    """Settings > Speech: a speech bubble."""
    APP = "app"
    """Settings > App: a window."""
    LAB = "lab"
    """Settings > Lab: a flask."""
    BEHAVIOUR = "behaviour"
    """Timing's Behaviour: lines arriving, an arrow down beside them."""
    RESET = "reset"
    """Look's Reset: an arrow going round."""
    FONTS = "fonts"
    """Look's Fonts: a capital A and a small a - a face (polyglotic-hq 482,
    marked as its cards are by 506)."""
    TEXT_SIZE = "text_size"
    """App's Text size: a small A and a large one."""
    THEME = "theme"
    """App's Appearance: a circle, half filled - light and dark."""
    TRANSCRIPTS = "transcripts"
    """App's Transcripts: a page of lines."""
    KEYS = "keys"
    """App's Hotkeys: a keyboard."""
    UPDATES = "updates"
    """App's Updates: an arrow down into a tray."""
    START = "start"
    """App's Start at sign-in: a power symbol (polyglotic-hq 571)."""
    ABOUT = "about"
    """App's About: an i in a circle."""


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


@cache
def _outline(glyph: Glyph) -> tuple[QPainterPath, QPainterPath]:
    """`glyph`'s lines (stroked) and dots (filled), on the 16-unit grid."""
    lines, dots = QPainterPath(), QPainterPath()
    if glyph is Glyph.HOME:
        lines.moveTo(1.5, 7.25)
        lines.lineTo(8, 1.75)
        lines.lineTo(14.5, 7.25)
        lines.moveTo(3.25, 6)
        lines.lineTo(3.25, 14.25)
        lines.lineTo(12.75, 14.25)
        lines.lineTo(12.75, 6)
        lines.moveTo(6.25, 14.25)
        lines.lineTo(6.25, 9.25)
        lines.lineTo(9.75, 9.25)
        lines.lineTo(9.75, 14.25)
    elif glyph is Glyph.WORDS:
        lines.moveTo(1.5, 3)
        lines.quadTo(5, 2, 8, 4.25)
        lines.quadTo(11, 2, 14.5, 3)
        lines.lineTo(14.5, 13.5)
        lines.quadTo(11, 12.5, 8, 14.5)
        lines.quadTo(5, 12.5, 1.5, 13.5)
        lines.closeSubpath()
        lines.moveTo(8, 4.25)
        lines.lineTo(8, 14.5)
    elif glyph is Glyph.LEARNING:
        # A sprout stays legible at the sidebar's 13--15 px; a cap's tassel
        # and overlapping edges would merge at the footer-sized strokes.
        lines.moveTo(8, 14.5)
        lines.lineTo(8, 6)
        lines.cubicTo(5.5, 6, 3.25, 4.5, 2.5, 2)
        lines.cubicTo(5.75, 1.75, 7.75, 3.25, 8, 6)
        lines.cubicTo(8.25, 3.25, 10.25, 1.75, 13.5, 2)
        lines.cubicTo(12.75, 4.5, 10.5, 6, 8, 6)
    elif glyph is Glyph.ACCOUNT:
        lines.addEllipse(QPointF(8, 4.5), 3, 3)
        lines.moveTo(2.25, 14.5)
        lines.cubicTo(2.75, 9.5, 5, 8.5, 8, 8.5)
        lines.cubicTo(11, 8.5, 13.25, 9.5, 13.75, 14.5)
    elif glyph is Glyph.HELP:
        lines.addEllipse(QPointF(8, 8), 6.25, 6.25)
        lines.moveTo(5.75, 6)
        lines.cubicTo(6, 3.25, 10.5, 3.25, 10.5, 6)
        lines.cubicTo(10.5, 7.75, 8, 7.75, 8, 10)
        dots.addEllipse(QPointF(8, 12.25), 0.75, 0.75)
    elif glyph is Glyph.LANGUAGES:
        lines.addEllipse(QRectF(1.5, 1.5, 13, 13))
        lines.addEllipse(QRectF(5, 1.5, 6, 13))
        lines.moveTo(1.5, 8)
        lines.lineTo(14.5, 8)
    elif glyph is Glyph.PRESET:
        lines.addRoundedRect(QRectF(1.5, 4.5, 10, 9.5), 1.5, 1.5)
        lines.moveTo(4.5, 2)
        lines.lineTo(13, 2)
        lines.quadTo(14.5, 2, 14.5, 3.5)
        lines.lineTo(14.5, 11)
        for y in (8, 10.5):
            lines.moveTo(4, y)
            lines.lineTo(9, y)
    elif glyph is Glyph.LOCK:
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
    elif glyph is Glyph.MINIMISE:
        lines.moveTo(3.25, 8)
        lines.lineTo(12.75, 8)
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
    elif glyph is Glyph.COPY:  # two overlapping pages (polyglotic-hq 950)
        lines.addRoundedRect(QRectF(5.5, 5.25, 8.25, 9.0), 1.5, 1.5)
        lines.moveTo(10.5, 5.25)
        lines.lineTo(10.5, 3.25)
        lines.quadTo(10.5, 2.0, 9.25, 2.0)
        lines.lineTo(3.5, 2.0)
        lines.quadTo(2.25, 2.0, 2.25, 3.25)
        lines.lineTo(2.25, 9.75)
        lines.quadTo(2.25, 11.0, 3.5, 11.0)
        lines.lineTo(5.5, 11.0)
    elif glyph is Glyph.SAVE:  # a bookmark ribbon (polyglotic-hq 950)
        lines.moveTo(3.5, 14.0)
        lines.lineTo(3.5, 3.25)
        lines.quadTo(3.5, 2.0, 4.75, 2.0)
        lines.lineTo(11.25, 2.0)
        lines.quadTo(12.5, 2.0, 12.5, 3.25)
        lines.lineTo(12.5, 14.0)
        lines.lineTo(8.0, 10.75)
        lines.closeSubpath()
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
    elif glyph is Glyph.QUIET:  # text, one word of it filled: the chosen word
        lines.moveTo(1.75, 5.5)
        lines.lineTo(4.25, 5.5)
        lines.moveTo(11.75, 5.5)
        lines.lineTo(14.25, 5.5)
        lines.moveTo(1.75, 10.5)
        lines.lineTo(14.25, 10.5)
        dots.addRoundedRect(QRectF(6.0, 4.0, 4.0, 3.0), 1.5, 1.5)
    elif glyph in (Glyph.MIC, Glyph.MIC_OFF):
        lines.addRoundedRect(QRectF(5.5, 0.75, 5, 9.5), 2.5, 2.5)
        lines.moveTo(3, 7.25)
        lines.arcTo(QRectF(3, 2.25, 10, 10), 180, 180)
        lines.moveTo(8, 12.75)
        lines.lineTo(8, 15.25)
        if glyph is Glyph.MIC_OFF:
            lines.moveTo(2.25, 2.25)
            lines.lineTo(13.75, 13.75)
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
    else:
        _settings_outline(glyph, lines, dots)
    return lines, dots


def _settings_outline(glyph: Glyph, lines: QPainterPath, dots: QPainterPath) -> None:
    """Settings' sections' and cards' marks (polyglotic-hq 470), drawn as
    449's wireframes had them, on the 16-unit grid."""
    if glyph is Glyph.LOOK:  # a caption's panel, its two lines
        lines.addRoundedRect(QRectF(1.75, 3.25, 12.5, 9.5), 2, 2)
        lines.moveTo(4.5, 6.5)
        lines.lineTo(11.5, 6.5)
        lines.moveTo(6, 9.5)
        lines.lineTo(10, 9.5)
    elif glyph is Glyph.READINGS:  # a short line over an A: a reading
        lines.moveTo(4.5, 2.5)
        lines.lineTo(11.5, 2.5)
        lines.moveTo(4, 13.75)
        lines.lineTo(8, 5.5)
        lines.lineTo(12, 13.75)
        lines.moveTo(5.5, 10.75)
        lines.lineTo(10.5, 10.75)
    elif glyph is Glyph.TIMING:  # a clock
        lines.addEllipse(QPointF(8, 8), 6, 6)
        lines.moveTo(8, 4.5)
        lines.lineTo(8, 8)
        lines.lineTo(10.5, 9.75)
    elif glyph is Glyph.SPEECH:  # a speech bubble
        lines.moveTo(4.5, 2.5)
        lines.lineTo(11.5, 2.5)
        lines.arcTo(QRectF(10.5, 2.5, 4, 4), 90, -90)
        lines.lineTo(14.5, 9)
        lines.arcTo(QRectF(10.5, 7, 4, 4), 0, -90)
        lines.lineTo(7.5, 11)
        lines.lineTo(4.5, 13.75)
        lines.lineTo(4.5, 11)
        lines.arcTo(QRectF(1.5, 7, 4, 4), 270, -90)
        lines.lineTo(1.5, 4.5)
        lines.arcTo(QRectF(1.5, 2.5, 4, 4), 180, -90)
        lines.closeSubpath()
    elif glyph is Glyph.APP:  # a window, its title bar
        lines.addRoundedRect(QRectF(1.75, 2.75, 12.5, 10.5), 1.75, 1.75)
        lines.moveTo(1.75, 5.75)
        lines.lineTo(14.25, 5.75)
    elif glyph is Glyph.LAB:  # a flask
        lines.moveTo(5.75, 1.75)
        lines.lineTo(10.25, 1.75)
        lines.moveTo(6.5, 1.75)
        lines.lineTo(6.5, 6.25)
        lines.lineTo(2.75, 12.5)
        lines.cubicTo(2.4, 13.4, 2.9, 14.25, 3.9, 14.25)
        lines.lineTo(12.1, 14.25)
        lines.cubicTo(13.1, 14.25, 13.6, 13.4, 13.25, 12.5)
        lines.lineTo(9.5, 6.25)
        lines.lineTo(9.5, 1.75)
        lines.moveTo(4.5, 10)
        lines.lineTo(11.5, 10)
    elif glyph is Glyph.BEHAVIOUR:  # lines arriving, an arrow down beside them
        for y, end in ((3.5, 14.25), (8.0, 9.5), (12.5, 7.0)):
            lines.moveTo(1.75, y)
            lines.lineTo(end, y)
        lines.moveTo(12.75, 7.25)
        lines.lineTo(12.75, 13.25)
        lines.moveTo(10.5, 11)
        lines.lineTo(12.75, 13.25)
        lines.lineTo(15, 11)
    elif glyph is Glyph.RESET:  # an arrow going round
        ring = QRectF(2.5, 2.5, 11, 11)
        lines.arcMoveTo(ring, 50)
        lines.arcTo(ring, 50, 280)
        lines.moveTo(12.25, 1.5)
        lines.lineTo(11.75, 4.75)
        lines.lineTo(8.5, 4.25)
    elif glyph is Glyph.FONTS:  # a capital A and a small a: a face
        lines.moveTo(1.25, 13.5)
        lines.lineTo(5, 2.75)
        lines.lineTo(8.75, 13.5)
        lines.moveTo(2.55, 9.75)
        lines.lineTo(7.45, 9.75)
        lines.addEllipse(QPointF(11.9, 11.1), 2.4, 2.4)
        lines.moveTo(14.3, 8.5)
        lines.lineTo(14.3, 13.5)
    elif glyph is Glyph.TEXT_SIZE:  # a small A and a large one
        lines.moveTo(1.25, 13.5)
        lines.lineTo(3.75, 7.5)
        lines.lineTo(6.25, 13.5)
        lines.moveTo(2.1, 11.5)
        lines.lineTo(5.4, 11.5)
        lines.moveTo(7.25, 13.5)
        lines.lineTo(11, 2.75)
        lines.lineTo(14.75, 13.5)
        lines.moveTo(8.6, 9.75)
        lines.lineTo(13.4, 9.75)
    elif glyph is Glyph.THEME:  # a circle, its left half filled
        lines.addEllipse(QPointF(8, 8), 6, 6)
        dots.moveTo(8, 2)
        dots.arcTo(QRectF(2, 2, 12, 12), 90, 180)
        dots.closeSubpath()
    elif glyph is Glyph.TRANSCRIPTS:  # a page of lines
        lines.addRoundedRect(QRectF(3, 1.75, 10, 12.5), 1.75, 1.75)
        for y in (5.0, 8.0, 11.0):
            lines.moveTo(5.5, y)
            lines.lineTo(10.5, y)
    elif glyph is Glyph.KEYS:  # a keyboard
        lines.addRoundedRect(QRectF(1.25, 3.75, 13.5, 8.5), 1.75, 1.75)
        for x in (4.0, 6.65, 9.35, 12.0):
            dots.addEllipse(QPointF(x, 6.75), 0.75, 0.75)
        lines.moveTo(5, 9.5)
        lines.lineTo(11, 9.5)
    elif glyph is Glyph.UPDATES:  # an arrow down into a tray
        lines.moveTo(8, 1.75)
        lines.lineTo(8, 10)
        lines.moveTo(4.75, 6.75)
        lines.lineTo(8, 10)
        lines.lineTo(11.25, 6.75)
        lines.moveTo(2.25, 10.75)
        lines.lineTo(2.25, 14)
        lines.lineTo(13.75, 14)
        lines.lineTo(13.75, 10.75)
    elif glyph is Glyph.START:  # a power symbol: a circle open at the top, a line in it
        ring = QRectF(2.25, 2.75, 11.5, 11.5)
        lines.arcMoveTo(ring, 120)
        lines.arcTo(ring, 120, 300)
        lines.moveTo(8, 1.5)
        lines.lineTo(8, 7.75)
    elif glyph is Glyph.ABOUT:  # an i in a circle
        lines.addEllipse(QPointF(8, 8), 6, 6)
        lines.moveTo(8, 7.25)
        lines.lineTo(8, 11.25)
        dots.addEllipse(QPointF(8, 4.9), 0.85, 0.85)


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


def icon(
    glyph: Glyph,
    color: str,
    size: int,
    disabled: str | None = None,
    on: str | None = None,
) -> QIcon:
    """`glyph` as an icon `size` pixels square, sharp at each display scale;
    in `disabled`'s colour while its button is off to clicks (Qt's own
    greying leaves a near-white glyph near white, 258); in `on`'s while its
    button is checked (Settings' chosen section, polyglotic-hq 470)."""
    found = QIcon()
    modes = [(QIcon.Mode.Normal, QIcon.State.Off, color)]
    if disabled is not None:
        modes.append((QIcon.Mode.Disabled, QIcon.State.Off, disabled))
    if on is not None:
        modes.append((QIcon.Mode.Normal, QIcon.State.On, on))
    for mode, state, ink in modes:
        for scale in SCALES:
            side = round(size * scale)
            pixmap = QPixmap(QSize(side, side))
            pixmap.setDevicePixelRatio(scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            paint(painter, glyph, QRectF(0, 0, side / scale, side / scale), QColor(ink))
            painter.end()
            found.addPixmap(pixmap, mode, state)
    return found
