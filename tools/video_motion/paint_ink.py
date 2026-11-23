"""Check overlapping shaped glyph bounds at Video's caption paint call."""

from dataclasses import dataclass
from itertools import combinations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QGlyphRun, QPainter

from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.ui_next import reading_lines
from polyglotic_desktop.ui_next.caption_layout import Ink, LaidLine

# Project 741 counts faint copies down to and including 2% layer opacity.
MIN_OPACITY = 0.02


@dataclass(frozen=True)
class PaintedRow:
    caption: int
    kind: RowKind
    start: int
    phase: str
    cell: QRectF
    glyphs: list[QRectF]
    readings: list[QRectF]


def bounds(runs: list[QGlyphRun], origin: QPointF) -> list[QRectF]:
    boxes = []
    for run in runs:
        font = run.rawFont()
        for glyph, pos in zip(run.glyphIndexes(), run.positions(), strict=True):
            box = font.boundingRect(glyph).translated(origin + pos)
            if not box.isEmpty():
                boxes.append(box)
    return boxes


class PaintInk:
    """Ink in one grab, including fading rows that are absent from hit testing."""

    def __init__(self) -> None:
        self.rows: list[PaintedRow] = []
        self.reading_clipped = False

    def clear(self) -> None:
        self.rows.clear()
        self.reading_clipped = False

    def observe(
        self,
        painter: QPainter,
        laid: LaidLine,
        at: QPointF,
        ink: Ink,
        caption: int,
        phase: str,
        fade_width: float,
        right_fade_width: float = 0,
        start: int = 0,
    ) -> None:
        if not laid.rows:
            return
        cell = painter.clipBoundingRect()
        for row in laid.rows:
            opacity = ink.alpha
            if row.row.kind is RowKind.TRANSLATION:
                opacity = min(1.0, opacity * ink.translation_alpha)
            if opacity < MIN_OPACITY:
                continue
            # Video's left-edge mask ramps from transparent to fully opaque.
            # Limit the glyph bounds to the part that reaches the threshold.
            visible = QRectF(cell)
            visible.setLeft(max(cell.left(), fade_width * MIN_OPACITY / opacity))
            visible.setRight(cell.right() - right_fade_width * MIN_OPACITY / opacity)
            if visible.isEmpty():
                continue
            origin = at + QPointF(0, row.top) + row.layout.position()
            glyphs = bounds(row.layout.glyphRuns(), origin)
            readings = (
                bounds(
                    reading_lines.glyphs(row.above, row.above_font),
                    at + QPointF(0, row.top),
                )
                if row.above and row.above_font is not None
                else []
            )
            self.reading_clipped |= any(
                (box.top() < cell.top() - 0.5 or box.bottom() > cell.bottom() + 0.5)
                and box.right() > visible.left()
                and box.left() < visible.right()
                for box in readings
            )
            glyphs = [
                box.intersected(visible) for box in glyphs if box.intersects(visible)
            ]
            readings = [
                box.intersected(visible) for box in readings if box.intersects(visible)
            ]
            if glyphs or readings:
                self.rows.append(
                    PaintedRow(
                        caption, row.row.kind, start, phase, cell, glyphs, readings
                    )
                )

    def overlaps(self) -> bool:
        if any(
            a.intersects(b)
            for row in self.rows
            for a in row.readings
            for b in row.glyphs
        ):
            return True
        for a, b in combinations(self.rows, 2):
            # Multiple shaped clauses can belong to one painted row.
            if (
                a.caption == b.caption
                and a.kind is b.kind
                and a.cell == b.cell
                and a.start != b.start
            ):
                continue
            if a.cell.intersects(b.cell) and any(
                first.intersects(second)
                for first in a.glyphs + a.readings
                for second in b.glyphs + b.readings
            ):
                return True
        return False

    def duplicates(self) -> bool:
        return any(
            (a.caption, a.kind, a.start) == (b.caption, b.kind, b.start)
            for a, b in combinations(self.rows, 2)
        )
