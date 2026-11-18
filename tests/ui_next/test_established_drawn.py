"""Established text drawn as final, and a quiet correction (polyglotic-hq
494, decision 0228). Made-up text only."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import live_update
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.core.listening.captions import CaptionKind
from polyglotic_desktop.core.listening.display import CaptionRow, RowKind
from polyglotic_desktop.core.listening.established import CORRECTION_SEC
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, Ink
from polyglotic_desktop.ui_next.caption_window import CORRECTION
from polyglotic_desktop.ui_next.views.captions import Line

TEXT = "HHHH HHHH"
SPLIT = 4  # "HHHH" established, " HHHH" still being spoken


def _line(
    live: bool, established: int | None, corrected: tuple[tuple[int, int], ...] = ()
) -> Line:
    row = CaptionRow(
        TEXT,
        RowKind.ORIGINAL,
        None,
        0,
        True,
        established=established,
        corrected=corrected,
    )
    return Line(
        key=1,
        source=SourceId("app"),
        by_you=False,
        rows=(row,),
        live=live,
        provisional=False,
        started_at=datetime(2026, 11, 18, tzinfo=UTC),
    )


def _drawn(line: Line, ink: Ink) -> tuple[QImage, int]:
    """`line` painted on black, and where its established part ends (px)."""
    engine = CaptionLayout()
    laid = engine.laid(line, 600, 1.0)
    image = QImage(640, 120, QImage.Format.Format_ARGB32)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    try:
        engine.paint(painter, line, laid, QPointF(0, 0), ink)
    finally:
        painter.end()
    row = laid.rows[0]
    found = cast(tuple[float, int], row.layout.lineAt(0).cursorToX(SPLIT))
    split = found[0] + row.layout.position().x()
    return image, round(split)


def _brightest(image: QImage, left: int, right: int) -> tuple[int, int, int]:
    """The brightest pixel's (red, green, blue) between two columns."""
    best = (0, 0, 0)
    for x in range(max(0, left), min(image.width(), right)):
        for y in range(image.height()):
            c = image.pixelColor(x, y)
            if c.red() + c.green() + c.blue() > sum(best):
                best = (c.red(), c.green(), c.blue())
    return best


def test_established_text_is_drawn_as_final_and_the_rest_as_still_spoken(
    qapp: QApplication,
) -> None:
    image, split = _drawn(_line(live=True, established=SPLIT), Ink())
    established = _brightest(image, 0, split - 1)
    still = _brightest(image, split + 4, image.width())
    assert established[0] >= 250  # full ink, as a finished caption
    assert still[0] <= 230  # Live updates' 0.85


def test_without_established_text_a_live_caption_is_drawn_as_before(
    qapp: QApplication,
) -> None:
    image, split = _drawn(_line(live=True, established=0), Ink())
    assert _brightest(image, 0, split - 1)[0] <= 230
    image, split = _drawn(_line(live=True, established=len(TEXT)), Ink())
    assert _brightest(image, split + 4, image.width())[0] >= 250  # all of it


def test_a_correction_recolours_only_its_words(qapp: QApplication) -> None:
    line = _line(live=False, established=None, corrected=((SPLIT + 1, len(TEXT)),))
    image, split = _drawn(line, Ink(correction=QColor("#ff0000")))
    kept = _brightest(image, 0, split - 1)
    fixed = _brightest(image, split + 4, image.width())
    assert kept[1] >= 250  # white
    assert fixed[0] >= 250 and fixed[1] <= 40  # red
    image, split = _drawn(line, Ink())  # its moment over: as usual
    assert _brightest(image, split + 4, image.width())[1] >= 250


def test_the_window_shows_a_correction_for_a_moment_once(qapp: QApplication) -> None:
    window = window_of(qapp, captions=2)
    now = [100.0]
    window.clock = lambda: now[0]
    try:
        first = live_update("app-live")
        heard = replace(
            first,
            clauses=(replace(first.clauses[0], original="我在细管里面"),),
            established=5,
        )
        window.view.apply(heard)
        window.apply_changed(new_caption=True)
        done = replace(
            heard,
            kind=CaptionKind.FINISHED,
            clauses=(replace(first.clauses[0], original="我在系管里面。"),),
            established=0,
        )
        window.view.apply(done)
        window.apply_changed(new_caption=True)
        key = window.view.lines[-1].key
        white = QColor("#ffffff")
        at_once = window.correction_colour(key, now[0], white)
        assert at_once is not None and at_once.name() == QColor(CORRECTION).name()
        now[0] += CORRECTION_SEC * 0.75
        easing = window.correction_colour(key, now[0], white)
        assert easing is not None and easing.name() not in (CORRECTION, "#ffffff")
        assert window._correcting(now[0])
        now[0] += CORRECTION_SEC
        assert window.correction_colour(key, now[0], white) is None
        window.apply_changed(new_caption=False)  # the same caption again
        assert window.correction_colour(key, now[0], white) is None  # not twice
    finally:
        window.close()
