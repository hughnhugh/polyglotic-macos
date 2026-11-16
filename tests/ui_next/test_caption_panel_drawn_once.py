"""A caption window's panel - its rounded, translucent background - is
drawn once for its size, colour, edge and the screen's scale, and copied
on every paint after (polyglotic-hq 406: drawn on every live update, it took
1.0 ms of new_caption's 4 ms on CI's Linux runner, and 0.26 ms on Windows;
copied, 0.05-0.07 ms). The copy is the same pixels as the drawing.
Offscreen, made-up captions."""

import math
from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPicture
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import live_update
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.ui_next import caption_window
from polyglotic_desktop.ui_next.caption_window import (
    CaptionWindow,
    copies_exactly,
    draw_panel,
    panel_picture,
)


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[QSize]:
    """Each time the panel is drawn (not copied): the size it was for."""
    sizes: list[QSize] = []
    real = caption_window.panel_picture

    def counted(size: QSize, *rest: object) -> object:
        sizes.append(size)
        return real(size, *rest)  # type: ignore[arg-type]

    monkeypatch.setattr(caption_window, "panel_picture", counted)
    return sizes


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp, captions=8)
    shown.resize(900, 460)
    qapp.processEvents()
    yield shown
    shown.close()
    shiboken6.delete(shown)


def test_live_updates_copy_the_panel_drawn_once(
    window: CaptionWindow, drawn: list[QSize]
) -> None:
    window.canvas.forget_panel()
    window.canvas.repaint()
    assert drawn == [QSize(900, 460)]
    before = len(drawn)
    for _ in range(5):
        window.view.apply(live_update("app-live"))
        window.apply_changed(new_caption=False)
        window.canvas.repaint()
    assert len(drawn) == before  # the same size and look: copied five times


def test_the_panel_is_drawn_again_for_a_new_size_edge_or_colour(
    window: CaptionWindow, drawn: list[QSize], qapp: QApplication
) -> None:
    window.canvas.repaint()
    window.resize(880, 440)
    qapp.processEvents()
    window.canvas.repaint()
    assert drawn[-1] == QSize(880, 440)
    before = len(drawn)
    window.hovered = True  # hovered: its edge shows
    window.canvas.repaint()
    assert len(drawn) == before + 1
    window.set_look(replace(window.look, background="#203040"))
    window.canvas.repaint()
    assert len(drawn) == before + 2


def test_a_hidden_window_lets_its_panels_picture_go(
    window: CaptionWindow, drawn: list[QSize], qapp: QApplication
) -> None:
    window.canvas.repaint()
    before = len(drawn)
    window.hide()
    assert window.canvas._panel_kept is None
    window.show()
    qapp.processEvents()
    window.canvas.repaint()
    assert len(drawn) == before + 1


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5, 2.0])
@pytest.mark.parametrize("edged", [False, True], ids=["plain", "edged"])
def test_the_copy_is_the_same_pixels_as_the_drawing(
    qapp: QApplication, ratio: float, edged: bool
) -> None:
    """At Windows' scales, the hovered edge and a joined column's divider
    and its run under the next column included."""
    size = QSize(901, 457)
    area = QRectF(-16.0, 0.0, size.width() + 32.0, size.height())  # a middle column
    color = QColor("#101418")
    color.setAlphaF(0.78)
    edge = QColor(255, 255, 255, 46) if edged else None
    divider = QColor(255, 255, 255, 38) if edged else None

    def painted(paint: object) -> QImage:
        image = QImage(
            math.ceil(size.width() * ratio),
            math.ceil(size.height() * ratio),
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint(painter)  # type: ignore[operator]
        painter.end()
        return image

    drawn_there = painted(lambda p: draw_panel(p, area, color, edge, divider))
    picture = panel_picture(size, ratio, area, color, edge, divider)
    copied = painted(lambda p: p.drawPixmap(QPointF(0.0, 0.0), picture))
    assert copied == drawn_there


def test_a_scaled_or_recording_painter_gets_the_drawing_not_the_copy(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A picture copied through a scale is smoothed, not drawn (the UI lab
    shows three windows at half size), and a recording - the lab's design
    check reads the shapes drawn - has no shape in a copy (406's first UI
    lab run: 3,702 pixels off in one golden, 25 corner findings)."""
    for ratio in (1.0, 1.5):
        image = QImage(40, 40, QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        painter = QPainter(image)
        assert copies_exactly(painter)
        painter.translate(2, 4)  # whole pixels at both scales
        assert copies_exactly(painter)
        painter.translate(0.5, 0)
        assert not copies_exactly(painter)
        painter.scale(0.5, 0.5)
        assert not copies_exactly(painter)
        painter.end()
    recorded = QPicture()
    painter = QPainter(recorded)
    assert not copies_exactly(painter)
    painter.end()
    window = window_of(qapp, captions=2)
    seen: list[bool] = []
    real = caption_window.copies_exactly

    def spied(painter: QPainter) -> bool:
        seen.append(real(painter))
        return seen[-1]

    monkeypatch.setattr(caption_window, "copies_exactly", spied)
    small = QImage(480, 260, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(small)
    painter.scale(0.5, 0.5)  # as the lab's screen draws its windows
    window.render(painter, QPoint(0, 0))
    painter.end()
    window.close()
    shiboken6.delete(window)
    assert seen and not any(seen)
