"""The design detector: Impeccable's deterministic rules, translated for Qt
(polyglotic-hq 347; desktop decision 0140).

Impeccable (pbakaus/impeccable) checks a web page's rendered DOM against
rules a design director would hold it to. Here the same questions are asked
of each window a UI lab state shows, from what the window draws - each run
of text with its place, size, font and colour (the code checks' recorder,
`checks._TextRecorder`), each rounded shape with its corner radius - and
from its pixels (`grab()`, over the stand-in video when see-through), never
from the stylesheet:

- **type_scale:** text at a size off the interface's type scale (`TYPE_SCALE`,
  at the text size now). Captions are the learner's size: not judged; a
  transcript's lines are its own (A- / A+), on the scale at 1.0 whatever the
  app's text size (decision 0084).
- **font_family:** text named in a family the interface doesn't use
  (`FAMILIES`). Captions and the lookup card's words are judged too. Text
  that names no family is in the application's font, which isn't judged:
  on Windows that's Segoe UI, offscreen on Linux "Sans Serif" (357).
- **text_overlap:** text drawn over other text (Impeccable's text-occlusion).
- **target_size:** a control smaller than 24 x 24 px (WCAG 2.2, 2.5.8).
- **accent_count:** more than `MOST_ACCENTS` saturated hues in one window,
  captions and the stand-in video aside (Impeccable's "one accent").
- **corner_radius:** a corner radius off the scale (`RADII`); and a window
  with more than `MOST_RADII` radii.
- **misaligned:** left edges of text or controls stacked in one column that
  miss each other by 1-3 px: a near miss reads as a mistake.
- **spacing_grid:** a layout's margins or spacing off the 2 px grid, at a
  text size factor of 1.0 only: the text sizes scale them. That's the
  app's Smaller since decision 0244 (Normal is 1.3): in the lab's run, the
  states built at Smaller (`text_sizes`).
- **line_length:** a wrapped line of more than 80 characters.
- **tight_leading:** lines of a paragraph closer than 1.2 times the text size.
- **all_caps:** a run of text longer than three words in capitals.
- **wide_tracking:** letter spacing over 0.08 em on text longer than a label.
- **nested_cards:** a card inside a card.
- **stray_stroke:** a long border-coloured edge in the main UI, outside an
  input, selected tile or focus ring.
- **gray_on_color:** grey text on a saturated background.
- **cramped:** text closer than 4 px to the side of the control that frames it.

Each finding is a `checks.Finding`: the rule, the widget (`checks.where`) and
what was found; the state is the result's. Caption text is never written:
text goes into a finding only as `checks._excerpt` allows.

The gate fails on **new** findings only: those not in `BASELINE`
(`design_baseline.json`, state, rule and widget), the findings accepted when
the detector came, to be worked down. A widget is keyed by its object name
and the Qt class it's built on, not its own class (`qt_classes`): 343's
`QLabel` -> `Text` made 124 known findings look new (polyglotic-hq 357). `python -m tools.ui_lab design` writes
`design.md` for the judge; `design --accept` rewrites the baseline.
"""

import colorsys
import itertools
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainterPath,
    QRegion,
    QTextItem,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QScrollBar,
    QStackedLayout,
    QTextEdit,
    QWidget,
)

from polyglotic_desktop.ui_next import fonts, style
from polyglotic_desktop.ui_next.caption_layout import CJK_FAMILIES, LATIN_FAMILIES
from polyglotic_desktop.ui_next.caption_surface import CaptionSurface
from polyglotic_desktop.ui_next.dictation_key import KeyBox
from polyglotic_desktop.ui_next.transcript_window import TranscriptList
from tools.ui_lab import checks
from tools.ui_lab.checks import Finding, TextPiece

RULES = (
    "type_scale",
    "font_family",
    "text_overlap",
    "target_size",
    "accent_count",
    "corner_radius",
    "misaligned",
    "spacing_grid",
    "line_length",
    "tight_leading",
    "all_caps",
    "wide_tracking",
    "nested_cards",
    "stray_stroke",
    "gray_on_color",
    "cramped",
)

TYPE_SCALE = (12, 13, 14, 15, 16, 17, 18, 20, 24, 26, 28)
"""The interface's text sizes at 100 %, in px: the stylesheet's
(`style.stylesheet`: 12, 13, 14, 15, 17, 20, 24, 28), the transcript's
lines (16) and the lookup card's word (18, 26)."""
FAMILIES = frozenset(
    {
        *style.UI_FAMILIES,
        style.SYMBOLS,
        "Segoe UI",
        "Segoe UI Variable Display",
        "Literata",
        *checks.ICON_FONTS,
        *LATIN_FAMILIES,
        *(face for faces in CJK_FAMILIES.values() for face in faces),
        *(face.family for face in (*fonts.BUNDLED, *fonts.PACKED)),
        *(face for faces in fonts.WINDOWS.values() for face in faces),
        *(face for faces in fonts.WEIGHT_FACES.values() for face in faces),
    }
)
"""The families the interface names first (its fonts' lists, the captions'
and the lookup card's by script; the captions' faces by language, 482; and
a caption weight's own face: 481)."""
RADII = (2, 3, 6, 8, 9, 10, 12)
"""Corner radii in px: the stylesheet's."""
MOST_RADII = 5
MOST_ACCENTS = 3
SMALLEST_TARGET = 24
LONGEST_LINE = 80
LEADING = 1.2
WIDE_TRACKING_EM = 0.08
CRAMPED_PX = 4.0
NEAR_MISS = (1.5, 4.0)
"""A miss of 2-4 px: 1 px is a glyph's side bearing, more is a layout."""
GRID = 2
SMALL_INSET = 6
"""Margins and spacing up to this are optical insets (a segmented control's
3 px): any value. Above it, the grid; an odd one is usually a margin Qt's
style gave a layout that set none (9 or 11)."""
MOST_CAPS_WORDS = 6
CARD_NAMES = frozenset({"Card"})
BASELINE = Path(__file__).with_name("design_baseline.json")


@dataclass(frozen=True)
class Face:
    """A text piece's font, as drawn: its first family, letter spacing (em)
    and capitals."""

    family: str
    tracking_em: float


@dataclass(frozen=True)
class Shape:
    """A rounded shape a widget drew: where (on the device) and its corner."""

    widget: QWidget
    rect: QRectF
    radius: float


@dataclass
class Drawn:
    """What a window drew: its text pieces and their faces, its shapes."""

    pieces: list[TextPiece] = field(default_factory=list)
    faces: list[Face] = field(default_factory=list)
    shapes: list[Shape] = field(default_factory=list)


class _Recorder(checks._TextRecorder):
    """The code checks' text recorder, keeping each piece's face and each
    rounded shape too."""

    def __init__(self) -> None:
        super().__init__()
        self.faces: list[Face] = []
        self.shapes: list[Shape] = []

    def drawTextItem(
        self, p: QPointF | QPoint | QPainterPath.Element, textItem: QTextItem, /
    ) -> None:
        before = len(self.pieces)
        super().drawTextItem(p, textItem)
        if len(self.pieces) > before:
            font = textItem.font()
            self.faces.append(Face((font.families() or [font.family()])[0], _em(font)))

    def drawPath(self, path: object) -> None:
        if self.widget is None or not isinstance(path, QPainterPath):
            return
        radius = corner_radius(path)
        if radius is None:
            return
        rect = self._transform.mapRect(path.boundingRect())
        self.shapes.append(Shape(self.widget, rect, radius))


def _em(font: QFont) -> float:
    """The font's letter spacing in em."""
    spacing = font.letterSpacing()
    if font.letterSpacingType() == QFont.SpacingType.PercentageSpacing:
        return (spacing - 100) / 100 if spacing else 0.0
    px = font.pixelSize() if font.pixelSize() > 0 else font.pointSizeF() * 96 / 72
    return spacing / px if px > 0 else 0.0


def corner_radius(path: QPainterPath) -> float | None:
    """A rounded rectangle's corner radius, from its curves: each corner is
    a curve from one side to the next, as far across as it is down. None
    for a path with no curves, a circle or a pill (a radius of half its
    height: a shape, not a corner) - and for a drawing that isn't one box
    with four corners: an icon's outline (`ui_next.glyphs`: a lock, a
    speaker and its wave, two chain links) has curves, and no corner to
    hold to the scale (polyglotic-hq 376: 25 of the first run's 34 radius
    findings were the caption window's icons)."""
    radii = []
    pieces = 0
    for i in range(path.elementCount()):
        element = path.elementAt(i)
        if element.type == QPainterPath.ElementType.MoveToElement:
            pieces += 1
        if element.type != QPainterPath.ElementType.CurveToElement:
            continue
        if not 1 <= i < path.elementCount() - 2:
            continue
        start, end = path.elementAt(i - 1), path.elementAt(i + 2)
        radii.append(max(abs(end.x - start.x), abs(end.y - start.y)))
    if pieces != 1 or not 1 <= len(radii) <= 4:
        return None
    radius = max(radii)
    bounds = path.boundingRect()
    if radius >= min(bounds.width(), bounds.height()) / 2 - 0.75:
        return None  # a circle, a pill: round by shape
    return radius


def record(window: QWidget) -> Drawn:
    """What `window` draws, with its children (`checks.record_text`'s way)."""
    recorder = _Recorder()
    device = checks._Device(window.size(), recorder)
    who = checks._WhoPaints(recorder)
    app = QApplication.instance()
    assert app is not None
    app.installEventFilter(who)
    try:
        window.render(device, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    finally:
        app.removeEventFilter(who)
    recorder.end_run()
    return Drawn(recorder.pieces, recorder.faces, recorder.shapes)


def inspect(
    widget: QWidget,
    photograph: Callable[[QWidget], QImage],
    windows: list[QWidget] | None = None,
) -> list[Finding]:
    """Every rule on each window the state shows (as `checks.inspect`)."""
    found: list[Finding] = []
    for window in checks.shown_windows(widget) if windows is None else windows:
        drawn = record(window)
        pixels = checks._array(photograph(window))
        here = _type(drawn)
        here += _families(drawn)
        here += _overlaps(window, drawn.pieces)
        here += _targets(window)
        here += _accents(window, pixels)
        here += _radii(drawn.shapes, window)
        here += _alignment(window, drawn.pieces)
        here += _grid(window)
        here += _lines(drawn.pieces)
        here += _caps_and_tracking(drawn)
        here += _nested(window)
        here += _stray_strokes(window, pixels)
        here += _gray_on_color(drawn.pieces, pixels)
        here += _cramped(window, drawn.pieces)
        found += [_in_picture(finding, window, widget) for finding in here]
    return list(dict.fromkeys(found))


def _stray_strokes(window: QWidget, pixels: np.ndarray) -> list[Finding]:
    """Find long horizontal and vertical edges in the main UI's border colour."""
    if not isinstance(window, QMainWindow) and window.objectName() not in {
        "Content",
        "Page",
    }:
        return []
    border = QColor(style.current()["BORDER"])
    channels = (border.red(), border.green(), border.blue())
    matching = np.all(np.abs(pixels[:, :, :3].astype(np.int16) - channels) <= 3, axis=2)
    scale = pixels.shape[1] / max(1, window.width())
    inset = max(1, round(2 * scale))
    for control in window.findChildren(QWidget):
        if control.isVisibleTo(window) and (
            isinstance(
                control, (QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, KeyBox)
            )
            or control.hasFocus()
            or (
                isinstance(control, QAbstractButton)
                and control.property("tile")
                and control.isChecked()
            )
        ):
            top_left = control.mapTo(window, QPoint())
            _ignore_edges(
                matching,
                top_left.x(),
                top_left.y(),
                control.width(),
                control.height(),
                scale,
                inset,
            )

    length = round(style.px(48) * scale)
    found = []
    for vertical, oriented in ((False, matching), (True, matching.T)):
        transitions = np.diff(oriented, axis=1, prepend=False, append=False)
        lines, ends = np.nonzero(transitions)
        for left, right in zip(
            range(0, len(ends), 2), range(1, len(ends), 2), strict=True
        ):
            run = int(ends[right] - ends[left])
            if run < length:
                continue
            x, y = int(ends[left]), int(lines[left])
            box = (y, x, 1, run) if vertical else (x, y, run, 1)
            box = tuple(round(value / scale) for value in box)
            px, py, width, height = box
            found.append(
                Finding(
                    "stray_stroke",
                    checks.where(window),
                    f"{'Vertical' if vertical else 'Horizontal'} border at ({px}, {py}), {max(width, height)} px",
                    box=(px, py, max(1, width), max(1, height)),
                )
            )
    return found


def _ignore_edges(
    mask: np.ndarray, x: int, y: int, width: int, height: int, scale: float, inset: int
) -> None:
    """Remove pixels within the given distance of an allowed outline."""
    left, top, right, bottom = (
        round(value * scale) for value in (x, y, x + width - 1, y + height - 1)
    )
    for edge in (top, bottom):
        mask[
            max(0, edge - inset) : max(0, edge + inset + 1),
            max(0, left - inset) : max(0, right + inset + 1),
        ] = False
    for edge in (left, right):
        mask[
            max(0, top - inset) : max(0, bottom + inset + 1),
            max(0, edge - inset) : max(0, edge + inset + 1),
        ] = False


def boxed(rects: Iterable[QRectF | QRect]) -> checks.Box | None:
    """The box around `rects`, in whole px (x, y, width, height)."""
    around = QRectF()
    for rect in rects:
        around = around.united(QRectF(rect))
    if around.isEmpty():
        return None
    out = around.toAlignedRect()
    return (out.x(), out.y(), out.width(), out.height())


def _in_picture(finding: Finding, window: QWidget, pictured: QWidget) -> Finding:
    """`finding` with its box where the state's picture shows it: the rules
    box what they find in their window; the picture is of `pictured`
    (`checks.place_in`). A window the picture doesn't show (a menu, a
    popover of its own) has no box."""
    if finding.box is None or window is pictured:
        return finding
    at = checks.place_in(pictured, window)
    if at is None:
        return replace(finding, box=None)
    by, scale = at
    x, y, width, height = finding.box
    moved = QRectF(
        by.x() + x * scale, by.y() + y * scale, width * scale, height * scale
    ).toAlignedRect()
    if not moved.intersects(pictured.rect()):
        return replace(finding, box=None)
    return replace(finding, box=(moved.x(), moved.y(), moved.width(), moved.height()))


# -- type ------------------------------------------------------------------------------


def scale_now() -> tuple[int, ...]:
    """The type scale at the text size now."""
    return tuple(sorted({style.px(size) for size in TYPE_SCALE}))


def _judged(piece: TextPiece) -> bool:
    """Text the rules judge: shown, not an icon, not a caption (the
    learner's size and font)."""
    if piece.icon or piece.rect.width() < 1:
        return False
    shown: QWidget | None = piece.widget
    while shown is not None:
        if isinstance(shown, CaptionSurface):
            return False
        shown = shown.parentWidget()
    return True


def _transcripts_own(piece: TextPiece) -> bool:
    """Text a transcript's list draws: at the transcript's own size (A- /
    A+), which the app's text size doesn't touch (decision 0084) - its 12 px
    headings were off the scale at the app's Normal since 0244 (1.3)."""
    shown: QWidget | None = piece.widget
    while shown is not None:
        if isinstance(shown, TranscriptList):
            return True
        shown = shown.parentWidget()
    return False


def _type(drawn: Drawn) -> list[Finding]:
    now = scale_now()
    off: dict[tuple[str, float, tuple[int, ...]], list[TextPiece]] = defaultdict(list)
    for piece in drawn.pieces:
        if not _judged(piece):
            continue
        scale = TYPE_SCALE if _transcripts_own(piece) else now
        if min(abs(piece.px - size) for size in scale) > 0.6:
            off[(checks.where(piece.widget), round(piece.px, 1), scale)].append(piece)
    found = []
    for (name, px, scale), pieces in off.items():
        texts = sorted({checks._excerpt(p.text, p.rect) for p in pieces})
        found.append(
            Finding(
                "type_scale",
                name,
                f"{px:g} px, off the type scale ({', '.join(map(str, scale))}):"
                f" {', '.join(texts[:2])}",
                box=boxed(p.rect for p in pieces),
            )
        )
    return found


def _families(drawn: Drawn) -> list[Finding]:
    default = QApplication.font()
    unnamed = (default.families() or [default.family()])[0]
    off: dict[tuple[str, str], list[QRectF]] = defaultdict(list)
    for piece, face in zip(drawn.pieces, drawn.faces, strict=False):
        if (
            piece.icon
            or face.family in FAMILIES
            or face.family in style.CHINESE_FACES
            or face.family == unnamed  # names no family: the platform's own
        ):
            continue
        off[(checks.where(piece.widget), face.family)].append(piece.rect)
    return [
        Finding(
            "font_family",
            name,
            f"text in {family}, a family the interface doesn't use",
            box=boxed(rects),
        )
        for (name, family), rects in off.items()
    ]


def _caps_and_tracking(drawn: Drawn) -> list[Finding]:
    found = []
    for piece, face in zip(drawn.pieces, drawn.faces, strict=False):
        if not _judged(piece) or piece.text is None:
            continue
        letters = [c for c in piece.text if c.isalpha()]
        words = piece.text.split()
        if (
            len(words) > MOST_CAPS_WORDS
            and letters
            and all(c.isupper() for c in letters)
        ):
            found.append(
                Finding(
                    "all_caps",
                    checks.where(piece.widget),
                    f"{len(words)} words in capitals: {checks._excerpt(piece.text)}",
                    box=boxed([piece.rect]),
                )
            )
        if face.tracking_em > WIDE_TRACKING_EM and len(piece.text) > 24:
            found.append(
                Finding(
                    "wide_tracking",
                    checks.where(piece.widget),
                    f"{face.tracking_em:.2f} em letter spacing on"
                    f" {checks._excerpt(piece.text)}",
                    box=boxed([piece.rect]),
                )
            )
    return found


def _lines(pieces: list[TextPiece]) -> list[Finding]:
    """Line length and leading, of each wrapped label's lines."""
    found = []
    by_widget: dict[int, list[TextPiece]] = defaultdict(list)
    for piece in pieces:
        if (
            _judged(piece)
            and isinstance(piece.widget, QLabel)
            and piece.widget.wordWrap()
        ):
            by_widget[id(piece.widget)].append(piece)
    for lines in by_widget.values():
        widget = lines[0].widget
        name = checks.where(widget)
        font = widget.font()
        average = QFontMetricsF(font).averageCharWidth() or 1.0
        rows = _rows(lines)
        longest = max(
            (
                sum(len(p.text) if p.text else p.rect.width() / average for p in row)
                for row in rows
            ),
            default=0.0,
        )
        if longest > LONGEST_LINE:
            found.append(
                Finding(
                    "line_length",
                    name,
                    f"lines of ~{longest:.0f} characters (at most {LONGEST_LINE})",
                    box=boxed(p.rect for p in lines),
                )
            )
        if len(rows) >= 2:
            tops = sorted(row[0].rect.top() for row in rows)
            gaps = [b - a for a, b in itertools.pairwise(tops)]
            px = max(p.px for p in lines)
            tightest = min(gaps) / px if px else 9.0
            if tightest < LEADING:
                found.append(
                    Finding(
                        "tight_leading",
                        name,
                        f"lines {tightest:.2f}x the text size apart (at least {LEADING:g})",
                        box=boxed(p.rect for p in lines),
                    )
                )
    return found


def _rows(lines: list[TextPiece]) -> list[list[TextPiece]]:
    """Pieces on the same line together (a line drawn in several pieces)."""
    rows: list[list[TextPiece]] = []
    for piece in sorted(lines, key=lambda p: (round(p.rect.top()), p.rect.left())):
        if rows and abs(rows[-1][0].rect.top() - piece.rect.top()) < 1:
            rows[-1].append(piece)
        else:
            rows.append([piece])
    return rows


def _seen(piece: TextPiece, window: QWidget) -> QRectF:
    """Where `piece` can be seen: within its clip and its widget's own box (a
    painted list's top row, scrolled above the list's edge, isn't)."""
    seen = piece.rect if piece.shown.isEmpty() else piece.rect.intersected(piece.shown)
    if piece.widget is window:
        return seen
    return seen.intersected(_box(piece.widget, window))


def _overlaps(window: QWidget, pieces: list[TextPiece]) -> list[Finding]:
    found = []
    shown = [(p, _seen(p, window)) for p in pieces if not p.icon]
    shown = [(p, seen) for p, seen in shown if seen.width() >= 1 and seen.height() >= 1]
    for i, (a, seen_a) in enumerate(shown):
        for b, seen_b in shown[i + 1 :]:
            if a.widget is b.widget:
                continue
            # A pinned heading deliberately covers title/description text that
            # scrolls underneath it. Ignore only that actual stacking case:
            # children in the same card, and controls raised above the card,
            # remain genuine overlap findings.
            if _named_container_occludes(a.widget, b.widget, "PinnedCard") or (
                _named_container_occludes(b.widget, a.widget, "PinnedCard")
            ):
                continue
            both = seen_a.intersected(seen_b)
            smaller = min(
                seen_a.width() * seen_a.height(), seen_b.width() * seen_b.height()
            )
            if smaller > 0 and both.width() * both.height() > 0.25 * smaller:
                found.append(
                    Finding(
                        "text_overlap",
                        checks.where(a.widget),
                        f"{checks._excerpt(a.text, a.rect)} drawn over by"
                        f" {checks.where(b.widget)}'s {checks._excerpt(b.text, b.rect)}",
                        box=boxed([both]),
                    )
                )
    return found


def _named_container_occludes(under: QWidget, over: QWidget, name: str) -> bool:
    """Whether ``over`` is in a named container stacked above ``under``."""
    container = over
    while container.objectName() != name:
        parent = container.parentWidget()
        if not isinstance(parent, QWidget):
            return False
        container = parent
    if container.isAncestorOf(under):
        return False

    under_branch = under
    while under_branch.parentWidget() is not container.parentWidget():
        parent = under_branch.parentWidget()
        if not isinstance(parent, QWidget):
            return False
        under_branch = parent
    parent = container.parentWidget()
    if not isinstance(parent, QWidget):
        return False
    siblings = [child for child in parent.children() if isinstance(child, QWidget)]
    return siblings.index(container) > siblings.index(under_branch)


# -- controls and layout ---------------------------------------------------------------


def _targets(window: QWidget) -> list[Finding]:
    found = []
    for control in checks._controls(window):
        if (
            isinstance(control, QScrollBar | QAbstractItemView)
            or not control.isEnabled()
        ):
            continue
        if min(control.width(), control.height()) < SMALLEST_TARGET and _crowded(
            control, window
        ):
            found.append(
                Finding(
                    "target_size",
                    checks.where(control),
                    f"{control.width()} x {control.height()} px (at least"
                    f" {SMALLEST_TARGET} x {SMALLEST_TARGET})",
                    box=boxed([_box(control, window)]),
                )
            )
    return found


def _box(widget: QWidget, window: QWidget) -> QRectF:
    return QRectF(QRect(widget.mapTo(window, QPoint(0, 0)), widget.size()))


def _crowded(control: QWidget, window: QWidget) -> bool:
    """WCAG 2.5.8's spacing exception, read as a box: an undersized target
    passes when a 24 px box centred on it touches no other target."""
    box = _box(control, window)
    grow_x = max(0.0, (SMALLEST_TARGET - box.width()) / 2)
    grow_y = max(0.0, (SMALLEST_TARGET - box.height()) / 2)
    reach = box.adjusted(-grow_x, -grow_y, grow_x, grow_y)
    for other in checks._controls(window):
        if (
            other is control
            or other.isAncestorOf(control)
            or control.isAncestorOf(other)
        ):
            continue
        if isinstance(other, QScrollBar) or not other.isVisibleTo(window):
            continue
        if reach.intersects(_box(other, window)):
            return True
    return False


def _grid(window: QWidget) -> list[Finding]:
    if abs(style.text_scale() - 1.0) > 0.01:
        return []  # the text sizes scale spacing off any grid on purpose
    found = []
    for layout in window.findChildren(QLayout):
        owner = layout.parentWidget()
        if owner is None or not owner.isVisibleTo(window):
            continue
        if isinstance(layout, QStackedLayout) or isinstance(
            owner, QMainWindow | QMessageBox
        ):
            continue  # Qt's own: a stack fills its rect; a main window's, a message box's
        margins = layout.contentsMargins()
        values = {
            "spacing": layout.spacing(),
            "margins": max(
                margins.left(), margins.top(), margins.right(), margins.bottom()
            ),
        }
        odd = {k: v for k, v in values.items() if v > SMALL_INSET and v % GRID}
        sides = [margins.left(), margins.top(), margins.right(), margins.bottom()]
        odd_sides = [v for v in sides if v > SMALL_INSET and v % GRID]
        if odd or odd_sides:
            said = ", ".join(f"{k} {v}" for k, v in odd.items())
            if odd_sides and "margins" not in odd:
                said = ", ".join(filter(None, [said, f"a margin of {odd_sides[0]}"]))
            found.append(
                Finding(
                    "spacing_grid",
                    f"{checks.where(owner)} {type(layout).__name__}",
                    f"{said} px, off the {GRID} px grid",
                    box=boxed([_box(owner, window)]),
                )
            )
    return found


def _left_edges(
    window: QWidget, pieces: list[TextPiece]
) -> list[tuple[QWidget, QRectF]]:
    """Where each left-aligned label's text and each framed control start."""
    edges: dict[int, tuple[QWidget, QRectF]] = {}
    for piece in pieces:
        widget = piece.widget
        if not _judged(piece) or not isinstance(widget, QLabel):
            continue
        if not widget.alignment() & Qt.AlignmentFlag.AlignLeft:
            continue
        if id(widget) not in edges or piece.rect.left() < edges[id(widget)][1].left():
            edges[id(widget)] = (widget, piece.rect)
    for control in checks._controls(window):
        if isinstance(control, QLineEdit | QComboBox):
            top_left = control.mapTo(window, QPoint(0, 0))
            edges[id(control)] = (control, QRectF(QRect(top_left, control.size())))
    return list(edges.values())


def _alignment(window: QWidget, pieces: list[TextPiece]) -> list[Finding]:
    found = []
    edges = sorted(_left_edges(window, pieces), key=lambda e: e[1].top())
    for i, (a, rect_a) in enumerate(edges):
        for b, rect_b in edges[i + 1 :]:
            if b.parentWidget() is not a.parentWidget():
                continue  # one column: siblings in one layout
            gap = rect_b.top() - rect_a.bottom()
            if gap < 0 or gap > 48:
                continue
            miss = abs(rect_a.left() - rect_b.left())
            if NEAR_MISS[0] < miss <= NEAR_MISS[1]:
                found.append(
                    Finding(
                        "misaligned",
                        checks.where(b),
                        f"starts {miss:.0f} px from {checks.where(a)} above it",
                        box=boxed([rect_a, rect_b]),
                    )
                )
    return found


def _nested(window: QWidget) -> list[Finding]:
    found = []
    for card in window.findChildren(QWidget):
        if card.objectName() not in CARD_NAMES or not card.isVisibleTo(window):
            continue
        parent = card.parentWidget()
        while parent is not None and parent is not window:
            if parent.objectName() in CARD_NAMES:
                found.append(
                    Finding(
                        "nested_cards",
                        checks.where(card),
                        "a card inside a card",
                        box=boxed([_box(card, window)]),
                    )
                )
                break
            parent = parent.parentWidget()
    return found


def _cramped(window: QWidget, pieces: list[TextPiece]) -> list[Finding]:
    found = []
    closest: dict[int, tuple[QWidget, float]] = {}
    for piece in pieces:
        widget = piece.widget
        if not _judged(piece) or not isinstance(
            widget, QAbstractButton | QLineEdit | QComboBox
        ):
            continue
        if isinstance(widget, QAbstractButton) and widget.property("kind") in (
            "ghost",
            "name",
        ):
            continue  # unframed: text with no box around it
        box = QRectF(QRect(widget.mapTo(window, QPoint(0, 0)), widget.size()))
        side = min(piece.rect.left() - box.left(), box.right() - piece.rect.right())
        if id(widget) not in closest or side < closest[id(widget)][1]:
            closest[id(widget)] = (widget, side)
    for widget, side in closest.values():
        if -1 < side < CRAMPED_PX:
            found.append(
                Finding(
                    "cramped",
                    checks.where(widget),
                    f"text {side:.0f} px from the side",
                    box=boxed([_box(widget, window)]),
                )
            )
    return found


# -- colour and shape ------------------------------------------------------------------


HUES = (
    "red",
    "orange",
    "yellow",
    "lime",
    "green",
    "teal",
    "cyan",
    "sky",
    "blue",
    "violet",
    "purple",
    "pink",
)


def _accents(window: QWidget, pixels: np.ndarray) -> list[Finding]:
    """The saturated hues a window shows, captions and the scene aside."""
    rgb = pixels[::2, ::2, :3].astype(np.float32) / 255
    mask = np.ones(rgb.shape[:2], dtype=bool)
    for surface in window.findChildren(CaptionSurface):
        if surface.isVisibleTo(window):
            top_left = surface.mapTo(window, QPoint(0, 0))
            x, y = top_left.x() // 2, top_left.y() // 2
            mask[
                max(0, y) : y + surface.height() // 2 + 1,
                max(0, x) : x + surface.width() // 2 + 1,
            ] = False
    high, low = rgb.max(axis=2), rgb.min(axis=2)
    saturation = np.where(high > 0, (high - low) / np.maximum(high, 1e-6), 0)
    vivid = mask & (saturation > 0.35) & (high > 0.3)
    if vivid.sum() == 0:
        return []
    hsv_hue = np.array(
        [
            colorsys.rgb_to_hsv(*c)[0]
            for c in rgb[vivid][:: max(1, int(vivid.sum() // 4000))]
        ]
    )
    bins = Counter((hsv_hue * len(HUES)).astype(int) % len(HUES))
    total = mask.sum()
    sampled = len(hsv_hue)
    share = {b: n / sampled * vivid.sum() / total for b, n in bins.items()}
    accents = sorted(b for b, s in share.items() if s >= 0.0015)
    if len(accents) <= MOST_ACCENTS:
        return []
    names = ", ".join(HUES[b] for b in accents)
    return [
        Finding(
            "accent_count", checks.where(window), f"{len(accents)} accent hues: {names}"
        )
    ]


def _radii(shapes: list[Shape], window: QWidget) -> list[Finding]:
    found = []
    seen: dict[float, list[Shape]] = defaultdict(list)
    for shape in shapes:
        if shape.radius < 1.5 or shape.rect.width() < 6:
            continue
        # a stylesheet's border is drawn on the half pixel: its radius less
        # 0.5 (8 px corners draw 7.5), the fill inside it a little less
        radius = float(np.ceil(shape.radius - 0.01))
        seen[radius].append(shape)
    drawn = dict(seen)
    for radius in sorted(seen, reverse=True):  # a border and the fill inside it
        if radius in seen and radius - 1 in seen:
            seen[radius] += seen.pop(radius - 1)
    for radius, owners in drawn.items():
        if radius + 1 in drawn:
            # the fill inside a border a pixel rounder, judged by the border:
            # by what's drawn, not by the pairs above (they count the window's
            # radii: of 9, 8 and 7 they pair 9 with 8, and 7 was left alone)
            continue
        if min(abs(radius - r) for r in RADII) > 0.6:
            found.append(
                Finding(
                    "corner_radius",
                    checks.where(owners[0].widget),
                    f"{radius:g} px corners, off the scale ({', '.join(map(str, RADII))})",
                    box=boxed([owners[0].rect]),
                )
            )
    if len(seen) > MOST_RADII:
        found.append(
            Finding(
                "corner_radius",
                checks.where(window),
                f"{len(seen)} corner radii in one window: {', '.join(f'{r:g}' for r in sorted(seen))}",
            )
        )
    return found


def _gray_on_color(pieces: list[TextPiece], pixels: np.ndarray) -> list[Finding]:
    found = []
    for piece in pieces:
        if not _judged(piece):
            continue
        background = checks._behind(pixels, piece.rect)
        if background is None:
            continue
        text = piece.color
        if (
            text.hsvSaturationF() < 0.12
            and 0.25 < text.valueF() < 0.85
            and (background.hsvSaturationF() > 0.35 and background.valueF() > 0.25)
        ):
            found.append(
                Finding(
                    "gray_on_color",
                    checks.where(piece.widget),
                    f"grey {text.name()} on {background.name()}:"
                    f" {checks._excerpt(piece.text, piece.rect)}",
                    box=boxed([piece.rect]),
                )
            )
    return list(dict.fromkeys(found))


# -- the gate --------------------------------------------------------------------------


def _is_qt(cls: type) -> bool:
    return cls.__module__.startswith(("PySide6.", "shiboken6"))


def qt_classes() -> dict[str, str]:
    """The widget (and layout) classes loaded now that aren't Qt's own, by
    name: the Qt class each is built on (`Text` -> `QLabel`). A name that
    classes on different Qt classes share is left out: kept as it is."""
    bases: dict[str, set[str]] = defaultdict(set)
    seen: set[type] = set()
    todo: list[type] = [QObject]
    while todo:
        subs: list[type] = todo.pop().__subclasses__()
        for sub in subs:
            if sub in seen:
                continue
            seen.add(sub)
            todo.append(sub)
            if not _is_qt(sub):
                qt = next(c for c in sub.__mro__ if _is_qt(c))
                bases[sub.__name__].add(qt.__name__)
    return {name: next(iter(qt)) for name, qt in bases.items() if len(qt) == 1}


_CLASS = re.compile(
    r"\((\w+)\)(?= |$)"  # name (Class)
    r"|> (\w+)(?= |$)"  # parent > Class
    r"|^(\w+)(?=$| [^(>])"  # Class alone, or before its layout
    r"|(?<=[\w)]) (\w+)$"  # ... its layout's class (spacing_grid)
)
"""Where `checks.where` (and spacing_grid's layout) puts a class's name."""


def on_qt(where: str, classes: dict[str, str]) -> str:
    """`where` with each class named by the Qt class it's built on."""

    def qt(match: re.Match[str]) -> str:
        name = next(g for g in match.groups() if g)
        return match.group(0).replace(name, classes.get(name, name))

    return _CLASS.sub(qt, where)


def key(state: str, finding: Finding, classes: dict[str, str] | None = None) -> str:
    """A finding as the baseline holds it: state, rule, widget - by its
    object name and Qt's class (`on_qt`; `classes`: `qt_classes()` if
    None), not the detail, whose numbers move."""
    where = on_qt(finding.where, qt_classes() if classes is None else classes)
    return f"{state} | {finding.check} | {re.sub(r'[0-9]+', '#', where)}"


def baseline(path: Path | None = None) -> frozenset[str]:
    """The accepted findings' keys (`BASELINE`, read when asked), each
    with its widget's class as Qt's (`on_qt`): a key kept before 360 named
    its own."""
    path = path or BASELINE
    if not path.exists():
        return frozenset()
    classes = qt_classes()
    keys = []
    for kept in json.loads(path.read_text(encoding="utf-8")):
        state, check, where = kept.split(" | ", 2)
        keys.append(f"{state} | {check} | {on_qt(where, classes)}")
    return frozenset(keys)


def new(found: Iterable[tuple[str, Finding]], accepted: frozenset[str]) -> list[str]:
    """The findings not in the baseline, as "state: rule - widget: detail"."""
    classes = qt_classes()
    return [
        f"{state}: {finding.check} - {finding.where}: {finding.detail}"
        for state, finding in found
        if key(state, finding, classes) not in accepted
    ]


def accept(found: Iterable[tuple[str, Finding]], path: Path | None = None) -> int:
    path = path or BASELINE
    classes = qt_classes()
    keys = sorted({key(state, finding, classes) for state, finding in found})
    path.write_text(json.dumps(keys, indent=1) + "\n", encoding="utf-8", newline="\n")
    return len(keys)


def markdown(found: list[tuple[str, Finding]], accepted: frozenset[str]) -> str:
    """The detector's findings by rule, for the judge: new ones marked."""
    lines = [
        "# Design findings",
        "",
        "Impeccable's rules, translated for Qt (tools/ui_lab/design.py). **new**:",
        " not in the baseline - the gate fails on these.",
        "",
    ]
    by_rule: dict[str, list[tuple[str, Finding]]] = defaultdict(list)
    for state, finding in found:
        by_rule[finding.check].append((state, finding))
    classes = qt_classes()
    for rule in RULES:
        if rule not in by_rule:
            continue
        lines += [f"## {rule} ({len(by_rule[rule])})", ""]
        for state, finding in by_rule[rule]:
            mark = "" if key(state, finding, classes) in accepted else " **new**"
            lines.append(f"- {state} · {finding.where} · {finding.detail}{mark}")
        lines.append("")
    return "\n".join(lines) if by_rule else "# Design findings\n\nNone.\n"
