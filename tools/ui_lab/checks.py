"""The lab's code checks: what a state shows, checked as a careful reviewer
would (polyglotic-hq project 108's design, section 5; built in project 119).

- **clipped_text:** a piece of text runs past the edge of what shows it -
  its widget, or the clip its widget drew it in. A caption surface's rows
  may be cut at the top or bottom as they scroll; never at the sides.
- **small_text:** text under 12 px at 100 % (icon fonts and symbols aside).
- **missing_glyph:** a character no font in the text's font list has,
  drawn as a box ("tofu") - in any language, a symbol after Chinese text
  above all (polyglotic-hq 170: the Chinese "Save to ▾"). Found by laying
  each run of text out again, whole, in its font: a glyph numbered 0 is
  the font's "missing" box. Whole, because a run is drawn in pieces, one
  per font, and a symbol takes the script - and the fonts tried for it -
  of the text before it; a piece alone may find the font it lacked.
- **japanese_font:** Chinese drawn in a Japanese face (MS UI Gothic,
  Meiryo, Yu Gothic, MS Gothic...) its fonts don't name - Japan's glyph
  shapes for a Chinese reader (polyglotic-hq 176, 198: Windows draws
  Chinese a font list has no face for in MS UI Gothic, in an English
  locale; the lab does too). Found as `missing_glyph` is, from the run
  laid out again, whole: the face each glyph came from. Text with kana is
  Japanese, and a font list naming a Japanese face meant one: neither is
  checked - nor a Japanese interface's own words (設定, 終了: Japanese
  with no kana; polyglotic-hq 294).
- **chinese_font:** Japanese (text with kana) whose kanji are drawn in a
  Chinese face (YaHei, JhengHei, SimSun...) - China's or Taiwan's glyph
  shapes for a Japanese reader (polyglotic-hq 215: Han characters are one
  script in both, so only the kana say text is Japanese). Found as
  `japanese_font` is.
- **contrast:** text against what is behind it at least 4.5:1, or 3:1 for
  large text (24 px, or 18.7 px bold) and icons (an icon font's glyph, or a
  symbol with no letter: "×", "⚙"); disabled controls and colour emoji
  aside (WCAG 2.2, 1.4.3 and 1.4.11). A widget (or a parent) with a
  `contrast_floor` property is held to that instead: a caption window the
  learner turned soft (Contrast, polyglotic-hq 481), whose text is kept at
  3.7:1 as it's worked out and 3:1 as it's drawn.
- **accessible_name:** every control has a name a screen reader can say -
  not empty, not an icon font's glyph.
- **keyboard:** in a window that takes the keyboard, Tab reaches every
  control. A window that never takes the focus (a caption window, its
  popovers, the lookup card: over a game, a click must never take the
  keyboard) is exempt, by design - its controls are the mouse's.
- **horizontal_scrollbar:** none shows.
- **minimum_size:** no widget is smaller than its layout needs (squashed),
  and a window that takes the keyboard declares a minimum size.

What is checked: every window the state shows, each on its own - not the
state's photograph, which may be several windows drawn together.

How text is found: a window is drawn a second time onto a paint device
that keeps no pixels, only each piece of text's place, font and colour and
which widget drew it (`_TextRecorder`), so text drawn by a standard widget
and text a surface paints itself are checked the same way. What is behind
the text comes from the window's own picture - over the stand-in video if
the window is see-through (a caption window, the lookup card).

Caption text is never kept or written. Text goes into a finding (and the
words list) only when it is a standard widget's own - a label's or a
button's text, a field's placeholder, a tooltip - and never under a caption
surface or the lookup card. Anything a widget paints itself (a caption, a
transcript's rows, the card's words) is named by its place, not its words.
"""

import fnmatch
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from functools import cache

import numpy as np
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAccessible,
    QColor,
    QFont,
    QImage,
    QPaintDevice,
    QPaintEngine,
    QPaintEngineState,
    QPainterPath,
    QPixmap,
    QRegion,
    QTextItem,
    QTextLayout,
    QTransform,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QScrollBar,
    QTabBar,
    QTextEdit,
    QWidget,
)

from polyglotic_desktop.core.lexicon.chinese import has_han, is_han
from polyglotic_desktop.ui_next.caption_surface import CaptionSurface
from polyglotic_desktop.ui_next.lookup_card import LookupCard

CONTENT = (CaptionSurface, LookupCard)
"""What shows the learner's captions, or words from them: never written down."""

CHECKS = (
    "clipped_text",
    "small_text",
    "missing_glyph",
    "japanese_font",
    "chinese_font",
    "contrast",
    "accessible_name",
    "keyboard",
    "horizontal_scrollbar",
    "minimum_size",
)
SMALLEST_PX = 12.0
CONTRAST = 4.5
CONTRAST_LARGE = 3.0
"""Large text: 24 px, or 18.66 px bold (WCAG's 18 pt and 14 pt bold)."""
LARGE_PX, LARGE_BOLD_PX = 24.0, 18.66
ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol")
JAPANESE_FONTS = (
    "MS UI Gothic",
    "MS Gothic",
    "MS PGothic",
    "MS Mincho",
    "MS PMincho",
    "Meiryo",
    "Yu Gothic",
    "Yu Mincho",
    "Hiragino",
    "Noto Sans CJK JP",
    "Noto Serif CJK JP",
    "Source Han Sans JP",
)
"""Japanese faces, by how their family's name starts ("Meiryo UI" and "Yu
Gothic UI" too): Chinese in one has Japan's glyph shapes."""
CHINESE_FONTS = (
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "SimSun",
    "NSimSun",
    "SimHei",
    "DengXian",
    "KaiTi",
    "FangSong",
    "PMingLiU",
    "MingLiU",
    "PingFang",
    "Noto Sans CJK SC",
    "Noto Sans CJK TC",
    "Source Han Sans SC",
    "Source Han Sans TC",
    "WenQuanYi",
)
"""Chinese faces, by how their family's name starts: Japanese in one has
China's or Taiwan's glyph shapes."""
TOLERANCE = 1.0
"""Pixels text may pass an edge by: anti-aliasing and rounding."""
CONTROLS = (
    QAbstractButton,
    QComboBox,
    QAbstractSlider,
    QAbstractSpinBox,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QAbstractItemView,
    QTabBar,
)


Box = tuple[int, int, int, int]
"""A place on a state's picture, in px: x, y, width, height."""


@dataclass(frozen=True)
class Finding:
    """Something a check found: which check, on what, in plain words."""

    check: str
    where: str
    detail: str
    waived: str = ""
    """Why it's accepted, if it is (`WAIVERS`); a waived finding never fails."""
    box: Box | None = field(default=None, compare=False)
    """Where it is on the state's picture, when the check knows (the design
    detector's do): the judge's kit draws it there (`judge.annotated`). Not
    part of what the finding is: two findings that differ only here are one."""

    def to_json(self) -> dict[str, object]:
        found: dict[str, object] = {
            "check": self.check,
            "where": self.where,
            "detail": self.detail,
        }
        if self.waived:
            found["waived"] = self.waived
        if self.box is not None:
            found["box"] = list(self.box)
        return found


@dataclass(frozen=True)
class Waiver:
    """A finding accepted on purpose, with the reason: `state` and `where`
    are shell patterns (`fnmatch`)."""

    check: str
    state: str
    where: str
    reason: str


WAIVERS: tuple[Waiver, ...] = (
    Waiver(
        "clipped_text",
        "ui_next.w1_pinyin_in_link_colours*",
        "caption_window.0 > Canvas",
        "the linked words drawn again in their link's colour (polyglotic-hq 395):"
        " Qt redraws the line clipped to each word, and in the newest caption"
        " those copies don't share a spot with the line drawn whole; the picture"
        " shows nothing cut",
    ),
    Waiver(
        "clipped_text",
        "ui_next.w1_translation_in_link_colours",
        "caption_window.0 > Canvas",
        "the same as 395's: the translation's linked words drawn again in their"
        " link's colour (polyglotic-hq 431)",
    ),
    Waiver(
        "contrast",
        "ui_next.*",
        "CaptionSurface",
        "the bare caption surface, photographed over the stand-in video without"
        " the panel its window gives it; W1's states check the same text on one",
    ),
    Waiver(
        "contrast",
        "ui_next.w1_three_windows",
        "caption_window.2 > Canvas",
        "the lab's `always_shown` draws an empty window's hint with no panel; in"
        " use an empty window shows it only while hovered, on its panel (w1_empty)",
    ),
    Waiver(
        "contrast",
        "ui_next.w4_settings*",
        "*.preview > PreviewSurface",  # Look's, and the Lab's (284)
        "Settings' live preview draws its caption panel over a painted still, so"
        " no one colour is behind the text and the check reads the text's own as"
        " its background; each preset's contrast is checked on a caption window"
        " (ui_next.preset_*) and in tests/ui_next/test_colour_presets.py (261)",
    ),
    Waiver(
        "contrast",
        "ui_next.qt_dialog",
        "qt_msgbox_buttonbox > QPushButton",
        "Qt's own message box in the lab's style (Fusion, offscreen): at large"
        " text a button's words reach its frame, which the check reads as their"
        " background. The app draws it in Windows' own style; the state is here"
        " for its fonts (polyglotic-hq 215)",
    ),
    Waiver(
        "keyboard",
        "ui_next.first_run_level_*",
        "level.* (QRadioButton)",
        "the level picker's choices are one group of radio buttons: Tab reaches"
        " the group and the arrow keys move within it, as in Windows' own"
        " dialogs (Qt's way for buttons that exclude each other; polyglotic-hq"
        " 425 added the state)",
    ),
)
"""Findings on the new interface accepted on purpose. Keep it short: each
one says why, and a fix removes its line."""


@dataclass
class Inspection:
    """A state's findings, and what the judge reads beside them."""

    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """Plain facts that aren't faults: exemptions, elided labels, the Tab order."""
    words: list[str] = field(default_factory=list)
    """The interface's own words on screen (labels, buttons, tooltips,
    names) for the glossary check - never caption text."""


def inspect(
    state: str,
    widget: QWidget,
    photograph: Callable[[QWidget], QImage],
    windows: list[QWidget] | None = None,
) -> Inspection:
    """Every check on each window the state shows (or on `widget`, if none
    shows) - or on `windows`. `photograph`: a window's picture, the same
    size, from its origin."""
    found = Inspection()
    for window in shown_windows(widget) if windows is None else windows:
        pieces = record_text(window)
        found.findings += _text_findings(pieces, photograph(window))
        found.notes += _elided(pieces)
        found.findings += _named(window)
        keyboard, order = _keyboard(window)
        found.findings += keyboard
        found.notes += order
        found.findings += _scrollbars(window)
        found.findings += _squashed(window)
        found.words += [w for w in _words(window) if w not in found.words]
    found.findings = [_waive(state, f) for f in _unique(found.findings)]
    return found


def shown_windows(widget: QWidget) -> list[QWidget]:
    """The windows showing, top-level - or `widget` alone, when it's a
    picture of windows drawn together, or shown on its own."""
    windows = [
        w
        for w in QApplication.topLevelWidgets()
        if w.isVisible() and not w.isHidden() and w.width() > 0 and w.height() > 0
    ]
    return sorted(windows, key=lambda w: w.objectName()) or [widget]


Place = tuple[QPoint, float]
"""Where a window is drawn on a state's picture: its top left corner there,
and how much smaller it's drawn (1.0: as it is)."""


def place_in(pictured: QWidget, window: QWidget) -> Place | None:
    """Where `window` is on the picture of `pictured`, the widget a state
    photographs: `pictured` itself, a widget in it, or a window that a
    picture of windows drawn together says it draws (its `places()`: each
    window, where, how much smaller). None for a window the picture doesn't
    show, such as a menu."""
    if window is pictured:
        return QPoint(0, 0), 1.0
    if pictured.isAncestorOf(window):
        return window.mapTo(pictured, QPoint(0, 0)), 1.0
    places: Callable[[], list[tuple[QWidget, QPoint, float]]] | None = getattr(
        pictured, "places", None
    )
    for drawn, at, scale in places() if places is not None else []:
        if drawn is window:
            return at, scale
        if drawn.isAncestorOf(window):
            return at + window.mapTo(drawn, QPoint(0, 0)) * scale, scale
    return None


def _unique(findings: list[Finding]) -> list[Finding]:
    return list(dict.fromkeys(findings))


def _waive(state: str, finding: Finding) -> Finding:
    for waiver in WAIVERS:
        if (
            waiver.check == finding.check
            and fnmatch.fnmatchcase(state, waiver.state)
            and fnmatch.fnmatchcase(finding.where, waiver.where)
        ):
            return replace(finding, waived=waiver.reason)
    return finding


# -- text, as drawn --------------------------------------------------------------------


@dataclass(frozen=True)
class TextPiece:
    """One run of text as drawn: where (on the device), what showed it, and
    how. `text` is None on a caption surface - caption text is never kept."""

    widget: QWidget
    rect: QRectF
    shown: QRectF
    """What the widget (and the clip it drew in) let show, on the device."""
    px: float
    bold: bool
    icon: bool
    color: QColor
    """The pen's colour, its alpha times the painter's opacity."""
    text: str | None
    boxes: int = 0
    """Characters drawn as the missing-glyph box in the run this piece
    begins (`missing_glyphs`); the run's other pieces hold 0."""
    japanese: str = ""
    """The Japanese face that run's Chinese is drawn in (`japanese_face`)."""
    chinese: str = ""
    """The Chinese face that run's Japanese is drawn in (`chinese_face`)."""
    run: str | None = None
    """That run's text, when it has boxes, `japanese` or `chinese` and is
    kept (`_kept`)."""


class _TextRecorder(QPaintEngine):
    """A paint engine that draws nothing and keeps every piece of text."""

    def __init__(self) -> None:
        super().__init__(QPaintEngine.PaintEngineFeature.AllFeatures)
        self.pieces: list[TextPiece] = []
        self.widget: QWidget | None = None
        self._pen = QColor()
        self._opacity = 1.0
        self._transform = QTransform()
        self._clip: QRectF | None = None
        self._clip_on = False
        # the run being drawn: its first piece's index, its text and font,
        # and where its last piece ended (x, baseline) - caption text too,
        # only until the run is checked (`end_run`)
        self._run: tuple[int, str, QFont, QPointF] | None = None

    def end_run(self) -> None:
        """The run drawn so far, checked whole for missing glyphs."""
        if self._run is not None:
            first, text, font, _ = self._run
            boxes = missing_glyphs(text, font)
            # a Japanese interface's own words with no kana (設定, 終了) are
            # Japanese, not Chinese (polyglotic-hq 294); captions still checked
            own_japanese = _japanese_interface() and not _is_content(
                self.pieces[first].widget
            )
            japanese = "" if own_japanese else japanese_face(text, font)
            chinese = chinese_face(text, font)
            if boxes or japanese or chinese:
                piece = self.pieces[first]
                kept = _kept(piece.widget, text)
                self.pieces[first] = replace(
                    piece, boxes=boxes, japanese=japanese, chinese=chinese, run=kept
                )
        self._run = None

    def begin(self, pdev: QPaintDevice) -> bool:
        return True

    def end(self) -> bool:
        return True

    def type(self) -> QPaintEngine.Type:
        return QPaintEngine.Type.User

    def new_widget(self, widget: QWidget) -> None:
        self.end_run()
        self.widget = widget
        self._clip, self._clip_on = None, False

    def updateState(self, state: QPaintEngineState) -> None:
        dirty = state.state()
        flags = QPaintEngine.DirtyFlag
        self._pen = state.pen().color()
        self._opacity = state.opacity()
        self._transform = state.transform()
        if dirty & (flags.DirtyClipRegion | flags.DirtyClipPath):
            # the clip is given as the painter had it: map it as drawn now
            region = state.clipRegion()
            area = (
                QRectF(region.boundingRect())
                if dirty & flags.DirtyClipRegion
                else state.clipPath().boundingRect()
            )
            mapped = self._transform.mapRect(area)
            operation = state.clipOperation()
            if operation == Qt.ClipOperation.NoClip:
                self._clip = None
            elif operation == Qt.ClipOperation.IntersectClip and self._clip is not None:
                self._clip = self._clip.intersected(mapped)
            else:
                self._clip = mapped
        if dirty & (
            flags.DirtyClipEnabled | flags.DirtyClipRegion | flags.DirtyClipPath
        ):
            self._clip_on = state.isClipEnabled() and self._clip is not None

    def drawPixmap(
        self, r: QRectF | QRect, pm: QPixmap | QImage, sr: QRectF | QRect, /
    ) -> None:
        pass

    def drawPath(self, path: object) -> None:
        pass

    def drawPolygon(self, *args: object) -> None:
        pass

    def drawTextItem(
        self, p: QPointF | QPoint | QPainterPath.Element, textItem: QTextItem, /
    ) -> None:
        widget = self.widget
        text = textItem.text()
        if widget is None or not text.strip():
            return
        font = textItem.font()
        x, y = (p.x(), p.y()) if isinstance(p, QPointF | QPoint) else (p.x, p.y)
        rect = self._transform.mapRect(
            QRectF(
                x,
                y - textItem.ascent(),
                textItem.width(),
                textItem.ascent() + textItem.descent(),
            )
        )
        shown = QRectF(self.systemClip().boundingRect())
        if self._clip_on and self._clip is not None:
            shown = shown.intersected(self._clip) if not shown.isEmpty() else self._clip
        px = font.pixelSize() if font.pixelSize() > 0 else font.pointSizeF() * 96 / 72
        # Fallback glyphs in one layout share the requested font. A span with
        # its own font (such as a translated label) needs its own check.
        start = self._transform.map(QPointF(x, y))
        end = self._transform.map(QPointF(x + textItem.width(), y))
        run = self._run
        if (
            run is not None
            and font == run[2]
            and abs(start.y() - run[3].y()) < 0.5
            and abs(start.x() - run[3].x()) < 0.5
        ):
            self._run = (run[0], run[1] + text, run[2], end)
        else:
            self.end_run()
            self._run = (len(self.pieces), text, font, end)
        color = QColor(self._pen)
        color.setAlphaF(color.alphaF() * self._opacity)
        self.pieces.append(
            TextPiece(
                widget,
                rect,
                shown,
                px,
                font.bold(),
                # an icon font first; the interface's list ends in one for
                # the symbols other fonts lack, which doesn't make text an icon
                (font.families() or [font.family()])[0] in ICON_FONTS
                or not readable(text),  # "×", "+", "⚙": a symbol is an icon
                color,
                _kept(widget, text),
            )
        )


def missing_glyphs(text: str, font: QFont) -> int:
    """How many of `text`'s glyphs, laid out in `font` (its whole family
    list and the system's fallbacks, as drawn), are glyph 0 - the font's
    missing-glyph box."""
    layout = QTextLayout(text, font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    return sum(list(run.glyphIndexes()).count(0) for run in layout.glyphRuns())


def japanese_face(text: str, font: QFont) -> str:
    """The Japanese face (`JAPANESE_FONTS`) `text`'s Chinese is drawn in,
    laid out in `font` as drawn - or "": none, the text isn't Chinese (it
    has kana: Japanese), or `font` names a Japanese face itself (on
    purpose: a Japanese word's)."""
    if not has_han(text) or any(_is_kana(c) for c in text):
        return ""
    if any(_is_japanese(f) for f in font.families() or [font.family()]):
        return ""
    layout = QTextLayout(text, font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    flags = QTextLayout.GlyphRunRetrievalFlag
    for run in layout.glyphRuns(
        -1, -1, flags.RetrieveString | flags.RetrieveStringIndexes
    ):
        face = run.rawFont().familyName()
        source = run.sourceString()  # the run's item: its indexes count from it
        if _is_japanese(face) and any(
            is_han(source[i]) for i in run.stringIndexes() if 0 <= i < len(source)
        ):
            return face
    return ""


@cache
def _japanese_has(character: str) -> bool:
    """Whether Japanese writes `character`: it's in Windows' Japanese code
    page (cp932, JIS X 0208 and its extensions). A Simplified-only one
    (这, 个) isn't, and Qt draws it in a Chinese face whatever the list."""
    try:
        character.encode("cp932")
    except UnicodeEncodeError:
        return False
    return True


def _japanese_interface() -> bool:
    """Whether the interface is in Japanese (the lab's application keeps
    which language it installed)."""
    app = QApplication.instance()
    return app is not None and app.property("interface_language") == "ja"


def chinese_face(text: str, font: QFont) -> str:
    """The Chinese face (`CHINESE_FONTS`) the kanji of `text` are drawn in
    when it's Japanese (it has kana), laid out in `font` as drawn - or "":
    none, or it isn't Japanese. Only kanji a Japanese face has: a
    Simplified-only character (这) in a Japanese sentence - a Chinese
    example in a Japanese interface (polyglotic-hq 294) - has no Japanese
    shape to be drawn in.

    Each kanji's face is asked of its own runs (`glyphRuns(at, length)`):
    a run's `stringIndexes` can name the wrong character - in "聞いた文：
    日风天水" the YaHei run drawing only 风 gave index 3, 文 (Qt 6.12;
    polyglotic-hq 472)."""
    if not has_han(text) or not any(_is_kana(c) for c in text):
        return ""
    layout = QTextLayout(text, font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    at = 0  # in UTF-16 code units, as Qt counts
    for character in text:
        length = 2 if ord(character) > 0xFFFF else 1
        if is_han(character) and _japanese_has(character):
            for run in layout.glyphRuns(at, length):
                face = run.rawFont().familyName()
                if face.startswith(CHINESE_FONTS):
                    return face
        at += length
    return ""


def _is_japanese(family: str) -> bool:
    return family.startswith(JAPANESE_FONTS)


def _is_kana(c: str) -> bool:
    """Hiragana, katakana (and its extensions), half-width katakana."""
    return (
        "\u3040" <= c <= "\u30ff"  # hiragana, katakana
        or "\u31f0" <= c <= "\u31ff"  # katakana for Ainu
        or "\uff66" <= c <= "\uff9f"  # half-width katakana
    )


class _Device(QPaintDevice):
    """The recorder's paint device: `size`, 96 dpi, one device pixel each."""

    def __init__(self, size: QSize, engine: _TextRecorder) -> None:
        super().__init__()
        self._size, self._engine = size, engine

    def paintEngine(self) -> QPaintEngine:
        return self._engine

    def metric(self, metric: QPaintDevice.PaintDeviceMetric) -> int:
        m = QPaintDevice.PaintDeviceMetric
        return {
            m.PdmWidth: self._size.width(),
            m.PdmHeight: self._size.height(),
            m.PdmWidthMM: round(self._size.width() * 25.4 / 96),
            m.PdmHeightMM: round(self._size.height() * 25.4 / 96),
            m.PdmNumColors: 0x7FFFFFFF,
            m.PdmDepth: 32,
            m.PdmDpiX: 96,
            m.PdmDpiY: 96,
            m.PdmPhysicalDpiX: 96,
            m.PdmPhysicalDpiY: 96,
            m.PdmDevicePixelRatio: 1,
            m.PdmDevicePixelRatioScaled: int(QPaintDevice.devicePixelRatioFScale()),
        }.get(metric, 0)


class _WhoPaints(QObject):
    """Tells the recorder which widget is painting (a paint event comes
    before each widget's own painting)."""

    def __init__(self, recorder: _TextRecorder) -> None:
        super().__init__()
        self.recorder = recorder

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint and isinstance(watched, QWidget):
            self.recorder.new_widget(watched)
        return False


def record_text(widget: QWidget) -> list[TextPiece]:
    """Every piece of text `widget` draws (with its children), as drawn."""
    recorder = _TextRecorder()
    device = _Device(widget.size(), recorder)
    who = _WhoPaints(recorder)
    app = QApplication.instance()
    assert app is not None
    app.installEventFilter(who)
    try:
        widget.render(device, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    finally:
        app.removeEventFilter(who)
    recorder.end_run()
    return recorder.pieces


def _is_content(widget: QWidget) -> bool:
    """A surface showing captions (or words from them): its text is the
    learner's, never written down."""
    shown: QWidget | None = widget
    while shown is not None:
        if isinstance(shown, CONTENT):
            return True
        shown = shown.parentWidget()
    return False


def _kept(widget: QWidget, text: str) -> str | None:
    """`text` if it is `widget`'s own (a label's, a button's...) and not on a
    caption surface or the lookup card; else None - never written down."""
    if _is_content(widget):
        return None
    drawn = " ".join(text.split())
    for own in _texts_of(widget):
        if drawn and drawn in " ".join(own.split()):
            return text
    return None


def _scrolls(widget: QWidget) -> bool:
    """A surface whose rows scroll - a caption surface, a scroll area, or a
    widget with a vertical scrollbar of its own (a transcript's list): rows
    cut at its top or bottom are expected."""
    shown: QWidget | None = widget
    while shown is not None:
        if isinstance(shown, (CaptionSurface, QAbstractScrollArea)) or any(
            bar.orientation() == Qt.Orientation.Vertical
            for bar in shown.findChildren(
                QScrollBar, options=Qt.FindChildOption.FindDirectChildrenOnly
            )
        ):
            return True
        shown = shown.parentWidget()
    return False


def _contrast_floor(widget: QWidget | None) -> float | None:
    """The contrast a widget's text is held to in place of WCAG's - its own
    `contrast_floor` property or its nearest parent's (481) - or None."""
    while widget is not None:
        found = widget.property("contrast_floor")
        if isinstance(found, int | float):
            return float(found)
        widget = widget.parentWidget()
    return None


def where(widget: QWidget) -> str:
    """The widget, by its object name - or its class, after its nearest
    named parent."""
    kind = type(widget).__name__
    if widget.objectName():
        return f"{widget.objectName()} ({kind})"
    parent = widget.parentWidget()
    while parent is not None and not parent.objectName():
        parent = parent.parentWidget()
    return f"{parent.objectName()} > {kind}" if parent is not None else kind


def _excerpt(text: str | None, rect: QRectF | None = None) -> str:
    """The text, shortened - or, when it isn't a standard widget's own
    (`_kept`), only where it is: its words are never written down."""
    if text is None:
        if rect is None:
            return "painted text"
        return f"painted text at {rect.x():.0f}, {rect.y():.0f}"
    text = " ".join(text.split())
    return f"'{text[:40]}…'" if len(text) > 40 else f"'{text}'"


def _text_findings(pieces: list[TextPiece], photo: QImage) -> list[Finding]:
    pixels = _array(photo)
    found: list[Finding] = []
    small: dict[tuple[str, float], list[str]] = {}
    boxes: dict[str, list[str]] = {}
    japanese: dict[tuple[str, str], list[str]] = {}
    chinese: dict[tuple[str, str], list[str]] = {}
    low: dict[tuple[str, str, str, float], list[float]] = {}
    whole = {_spot(p) for p in pieces if not _cut(p)}
    for piece in pieces:
        seen = piece.rect.intersected(piece.shown) if _bounded(piece) else piece.rect
        if seen.width() < 1 or seen.height() < 1:
            continue  # drawn, but clipped wholly out of view: nobody sees it
        name = where(piece.widget)
        if _spot(piece) not in whole:  # a copy cut to recolour a word isn't cut off
            found += _clipped(piece, name)
        if piece.boxes:
            boxes.setdefault(name, []).append(_excerpt(piece.run, piece.rect))
        if piece.japanese:
            japanese.setdefault((name, piece.japanese), []).append(
                _excerpt(piece.run, piece.rect)
            )
        if piece.chinese:
            chinese.setdefault((name, piece.chinese), []).append(
                _excerpt(piece.run, piece.rect)
            )
        if not piece.icon and piece.px < SMALLEST_PX - 0.01:
            small.setdefault((name, round(piece.px, 1)), []).append(
                _excerpt(piece.text, piece.rect)
            )
        if not piece.widget.isEnabled():
            continue  # WCAG: an inactive control needs no contrast
        if _emoji(piece):
            continue  # drawn in its own colours, not the pen's
        background = _behind(pixels, seen, piece.color)
        if background is None:
            continue
        text = _over(piece.color, background)
        needed = (
            CONTRAST_LARGE
            if piece.icon
            or piece.px >= LARGE_PX
            or (piece.bold and piece.px >= LARGE_BOLD_PX)
            else CONTRAST
        )
        floor = _contrast_floor(piece.widget)
        if floor is not None:
            needed = min(needed, floor)
        ratio = contrast(text, background)
        if ratio < needed - 0.005:
            halo = _outline_halo(pixels, seen, piece.color, background)
            if halo is not None:
                background = halo
                text = _over(piece.color, background)
                ratio = contrast(text, background)
        if ratio < needed - 0.005:
            key = (name, text.name(), background.name(), needed)
            low.setdefault(key, []).append(ratio)
    for (name, px), texts in small.items():
        examples = ", ".join(sorted(set(texts))[:3])
        found.append(
            Finding(
                "small_text",
                name,
                f"{px:g} px text (at least {SMALLEST_PX:g}): {examples}",
            )
        )
    for name, texts in boxes.items():
        examples = ", ".join(sorted(set(texts))[:3])
        found.append(
            Finding("missing_glyph", name, f"a character drawn as a box in {examples}")
        )
    for (name, face), texts in japanese.items():
        examples = ", ".join(sorted(set(texts))[:3])
        found.append(
            Finding(
                "japanese_font",
                name,
                f"Chinese drawn in {face}, a Japanese face its fonts don't name:"
                f" {examples}",
            )
        )
    for (name, face), texts in chinese.items():
        examples = ", ".join(sorted(set(texts))[:3])
        found.append(
            Finding(
                "chinese_font",
                name,
                f"Japanese drawn in {face}, a Chinese face: {examples}",
            )
        )
    for (name, text_color, background_color, needed), ratios in low.items():
        many = f"{len(ratios)} piece{'s' if len(ratios) > 1 else ''}"
        found.append(
            Finding(
                "contrast",
                name,
                f"{min(ratios):.2f}:1, needs {needed:g}:1 - {text_color} on"
                f" {background_color} ({many})",
            )
        )
    return found


def _emoji(piece: TextPiece) -> bool:
    """A colour emoji (🎤): its colours are its own, so the pen's say
    nothing about its contrast. Its text is kept only on standard widgets;
    a painted one counts as an emoji when it's a short symbol."""
    text = piece.text
    if text is None:
        return False
    return all(ord(ch) >= 0x1F000 or ch in "️‍ " for ch in text)


def _bounded(piece: TextPiece) -> bool:
    return not piece.shown.isEmpty()


def _spot(piece: TextPiece) -> tuple[int, int, int, int]:
    """Where a piece is drawn: the same text drawn twice in one place (the
    whole line, then cut to one word in another colour) shares it."""
    rect = piece.rect
    return (id(piece.widget), round(rect.x()), round(rect.y()), round(rect.width()))


def _cut(piece: TextPiece) -> dict[str, float]:
    """How far `piece` runs past each edge of what shows it."""
    shown, rect = piece.shown, piece.rect
    if not _bounded(piece):
        return {}
    sides = {
        "left": shown.left() - rect.left(),
        "right": rect.right() - shown.right(),
        "top": shown.top() - rect.top(),
        "bottom": rect.bottom() - shown.bottom(),
    }
    if _scrolls(piece.widget):
        sides["top"] = sides["bottom"] = 0.0  # rows scroll out of view
    return {side: by for side, by in sides.items() if by > TOLERANCE}


def _clipped(piece: TextPiece, name: str) -> list[Finding]:
    cut = _cut(piece)
    if not cut:
        return []
    edges = ", ".join(f"{by:.0f} px past the {side}" for side, by in cut.items())
    said = _excerpt(piece.text, piece.rect)
    return [Finding("clipped_text", name, f"{said} runs {edges}")]


def _elided(pieces: list[TextPiece]) -> list[str]:
    """Text shortened with an ellipsis to fit: by design in some places
    (the caption window's label at 320 px), worth a look in others."""
    seen = sorted(
        {
            f"elided: {where(p.widget)} shows {_excerpt(p.text)}"
            for p in pieces
            if p.text is not None
            and p.text.rstrip().endswith("…")
            and p.text != _own_text(p.widget)  # "Look…" is its whole label
        }
    )
    return seen


# -- colour ----------------------------------------------------------------------------


def _array(photo: QImage) -> np.ndarray:
    image = photo.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    data = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
    rows = data.reshape(height, image.bytesPerLine())[:, : width * 4]
    return rows.reshape(height, width, 4).copy()


def _behind(
    pixels: np.ndarray, rect: QRectF, pen: QColor | None = None
) -> QColor | None:
    """The colour most of `rect` shows: what is behind the text - but never
    the text's own `pen` while another colour shows: a short run of bold,
    dense script covers more of its box than what's behind it does (Hindi at
    the app's Normal, 1.3 since decision 0244: "#e9ecf1 on #e9ecf1",
    polyglotic-hq 524). Text on its own colour still shows only it."""
    height, width = pixels.shape[:2]
    left, top = max(0, int(rect.left())), max(0, int(rect.top()))
    right = min(width, int(np.ceil(rect.right())))
    bottom = min(height, int(np.ceil(rect.bottom())))
    if right - left < 1 or bottom - top < 1:
        return None
    area = pixels[top:bottom, left:right, :3].reshape(-1, 3).astype(np.uint32)
    packed = (area[:, 0] << 16) | (area[:, 1] << 8) | area[:, 2]
    values, counts = np.unique(packed, return_counts=True)
    order = np.argsort(counts)[::-1]
    most = int(values[order[0]])
    if pen is not None and pen.alpha() == 255 and len(order) > 1:
        own = (pen.red() << 16) | (pen.green() << 8) | pen.blue()
        if most == own:
            most = int(values[order[1]])
    return QColor((most >> 16) & 255, (most >> 8) & 255, most & 255)


def _dilate1(mask: np.ndarray) -> np.ndarray:
    """8-connected 1 px dilation of a 2D boolean mask."""
    out = mask.copy()
    height, width = mask.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            sy0, sy1 = max(0, -dy), height - max(0, dy)
            sx0, sx1 = max(0, -dx), width - max(0, dx)
            dy0, dy1 = max(0, dy), height - max(0, -dy)
            dx0, dx1 = max(0, dx), width - max(0, -dx)
            if sy1 > sy0 and sx1 > sx0:
                out[dy0:dy1, dx0:dx1] |= mask[sy0:sy1, sx0:sx1]
    return out


def _outline_halo(
    pixels: np.ndarray, rect: QRectF, pen: QColor, background: QColor
) -> QColor | None:
    """Return the outline halo colour (#000000 or #ffffff) if the text strokes
    inside `rect` are surrounded by a solid 1 px outline rather than sitting
    directly on `background`."""
    height, width = pixels.shape[:2]
    left, top = max(0, int(rect.left()) - 1), max(0, int(rect.top()) - 1)
    right = min(width, int(np.ceil(rect.right())) + 1)
    bottom = min(height, int(np.ceil(rect.bottom())) + 1)
    if right - left < 3 or bottom - top < 3:
        return None
    black, white = QColor("#000000"), QColor("#ffffff")
    halo = black if contrast(pen, black) >= contrast(pen, white) else white
    ink = _over(pen, halo)
    area = pixels[top:bottom, left:right, :3].astype(np.int16)
    p_rgb = np.array([ink.red(), ink.green(), ink.blue()], dtype=np.int16)
    b_rgb = np.array(
        [background.red(), background.green(), background.blue()], dtype=np.int16
    )
    h_rgb = np.array([halo.red(), halo.green(), halo.blue()], dtype=np.int16)
    d_pen = np.abs(area - p_rgb).max(axis=2)
    d_bg = np.abs(area - b_rgb).max(axis=2)
    d_halo = np.abs(area - h_rgb).max(axis=2)
    core = (d_pen <= 40) & (d_pen < d_bg)
    core_count = int(core.sum())
    if core_count < 4:
        return None
    ring = _dilate1(core) & ~core
    halo_pixels = ring & (d_halo <= 24)
    ring_bg = int((ring & (d_bg <= 16)).sum())
    # A one-pixel outline follows the perimeter, regardless of stroke thickness.
    edge = core & _dilate1(~core)
    backed = edge & _dilate1(halo_pixels)
    if 2 * backed.sum() > edge.sum() and halo_pixels.sum() >= 2 * ring_bg:
        return halo
    return None


def _over(color: QColor, background: QColor) -> QColor:
    """`color` (with its alpha) drawn over `background`."""
    a = color.alphaF()
    return QColor.fromRgbF(
        color.redF() * a + background.redF() * (1 - a),
        color.greenF() * a + background.greenF() * (1 - a),
        color.blueF() * a + background.blueF() * (1 - a),
    )


def _luminance(color: QColor) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


def contrast(a: QColor, b: QColor) -> float:
    """WCAG's contrast ratio, 1 to 21."""
    lighter, darker = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


# -- controls --------------------------------------------------------------------------


def _shown(widget: QWidget) -> Iterator[QWidget]:
    """`widget` and every child of it that shows."""
    yield widget
    for child in widget.findChildren(QWidget):
        if child.isVisibleTo(widget) and child.window() is widget.window():
            yield child


def _controls(widget: QWidget) -> list[QWidget]:
    return [
        w
        for w in _shown(widget)
        if isinstance(w, CONTROLS) and not isinstance(w, QScrollBar)
    ]


def accessible_name(widget: QWidget) -> str:
    """What a screen reader says for `widget`."""
    found = QAccessible.queryAccessibleInterface(widget)
    return found.text(QAccessible.Text.Name) if found is not None else ""


def readable(name: str) -> bool:
    """A name with a letter or digit that isn't an icon font's glyph."""
    return any(ch.isalnum() and not 0xE000 <= ord(ch) <= 0xF8FF for ch in name)


def _named(widget: QWidget) -> list[Finding]:
    found = []
    for control in _controls(widget):
        name = accessible_name(control)
        if not readable(name):
            said = "no name" if not name.strip() else f"only {name!r}"
            found.append(
                Finding(
                    "accessible_name",
                    where(control),
                    f"a screen reader hears {said}: give it an accessible name",
                )
            )
    return found


def takes_keyboard(window: QWidget) -> bool:
    """A window that may take the keyboard (not one that never takes the
    focus, like a caption window over a game)."""
    flags = window.windowFlags()
    return not (
        flags & Qt.WindowType.WindowDoesNotAcceptFocus
        or window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    )


def tab_order(window: QWidget) -> list[QWidget]:
    """The widgets Tab visits in `window`, in order (as Qt's own
    `focusNextPrevChild` picks them)."""
    order: list[QWidget] = []
    seen: set[int] = set()
    current: QWidget | None = window.nextInFocusChain()
    while (
        current is not None
        and current is not window
        and id(current) not in seen
        and len(seen) < 5000
    ):
        seen.add(id(current))
        if (
            current.focusPolicy() & Qt.FocusPolicy.TabFocus
            and current.isVisibleTo(window)
            and current.isEnabled()
            and current.window() is window
            and current.focusProxy() is None
        ):
            order.append(current)
        current = current.nextInFocusChain()
    return order


def _keyboard(widget: QWidget) -> tuple[list[Finding], list[str]]:
    window = widget.window()
    controls = [c for c in _controls(widget) if c.isEnabled()]
    if not controls:
        return [], []
    if not takes_keyboard(window):
        exempt = (
            f"keyboard: exempt - {where(window)} never takes the focus, by design"
            " (over a game a click must not take the keyboard)"
        )
        return [], [exempt]
    order = tab_order(window)
    reached = {id(w) for w in order}
    found = []
    for control in controls:
        target = control.focusProxy() or control
        if id(target) not in reached:
            found.append(
                Finding(
                    "keyboard",
                    where(control),
                    "Tab never reaches it: give it Qt.TabFocus (or StrongFocus)",
                )
            )
    names = " > ".join(where(w) for w in order)
    return found, [f"tab order: {names}"]


def _scrollbars(widget: QWidget) -> list[Finding]:
    return [
        Finding("horizontal_scrollbar", where(bar), "a horizontal scrollbar shows")
        for bar in widget.findChildren(QScrollBar)
        if bar.orientation() == Qt.Orientation.Horizontal
        and bar.isVisibleTo(widget)
        and bar.window() is widget.window()
    ]


def _squashed(widget: QWidget) -> list[Finding]:
    found = []
    for shown in _shown(widget):
        if shown.layout() is None:
            continue
        needs = shown.minimumSizeHint()
        if (
            shown.width() < needs.width() - TOLERANCE
            or shown.height() < needs.height() - TOLERANCE
        ):
            found.append(
                Finding(
                    "minimum_size",
                    where(shown),
                    f"{shown.width()} x {shown.height()}, its layout needs at"
                    f" least {needs.width()} x {needs.height()}",
                )
            )
    window = widget.window()
    if window is widget and takes_keyboard(window) and _controls(widget):
        least = window.minimumSize()
        if least.width() <= 0 or least.height() <= 0:
            found.append(
                Finding(
                    "minimum_size",
                    where(window),
                    "a window with controls declares no minimum size",
                )
            )
    return found


def _own_text(widget: QWidget) -> str | None:
    """A label's or a button's text - not what the learner typed into a
    field (a search), which is theirs."""
    if isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
        return None
    text = getattr(widget, "text", None)
    try:
        value = text() if callable(text) else None
    except TypeError:
        return None
    return value if isinstance(value, str) else None


def _words(widget: QWidget) -> list[str]:
    """The interface's own words: labels, buttons, tooltips, names, titles -
    not what a caption surface paints."""
    words: list[str] = []
    for shown in _shown(widget):
        if _is_content(shown):
            continue
        for text in _texts_of(shown):
            text = " ".join(text.split())
            if text and readable(text) and text not in words:
                words.append(text)
    return words


def _texts_of(widget: QWidget) -> Iterable[str]:
    """`widget`'s own words: its title, text, placeholder, current choice,
    tooltip, accessible name and actions' words."""
    if widget.isWindow():
        yield widget.windowTitle()
    own = _own_text(widget)
    if own is not None:
        yield own
    for name in ("placeholderText", "currentText"):
        found = getattr(widget, name, None)
        if callable(found):
            value = found()
            if isinstance(value, str):
                yield value
    yield widget.toolTip()
    yield widget.accessibleName()
    for action in widget.actions():
        yield action.text()
        yield action.toolTip()


def count(findings: Iterable[Finding]) -> Counter[str]:
    """Findings that fail (not waived), by check."""
    return Counter(f.check for f in findings if not f.waived)
