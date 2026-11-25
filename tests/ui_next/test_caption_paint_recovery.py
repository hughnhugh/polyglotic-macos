"""The caption window can finish a frame when a translation is late or paint fails."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QTextLayout
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import EN, ZH, at_one_moment
from tests.ui_next.test_caption_window import areas

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
)
from polyglotic_desktop.core.listening.display import (
    CaptionRow,
    JapaneseReading,
    LongLines,
    RowKind,
)
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_layout import (
    Ink,
    LaidLine,
    LaidRow,
    Marks,
    reserve_translation_space,
)
from polyglotic_desktop.ui_next.caption_window import (
    PAINT_ERROR_LOG_INTERVAL_SEC,
    CaptionWindow,
)
from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
from polyglotic_desktop.ui_next.views.captions import Line


@pytest.fixture
def caption_window(qapp: QApplication) -> Iterator[CaptionWindow]:
    window = CaptionWindow(
        "app",
        APP,
        WindowChoices(translate_into=EN, show_mic=True, show_caption_info=False),
        SourceLabel("App", "#4dd0e1"),
        mic=MIC,
        areas=areas,
        learner=chinese_tools(ready=True),
    )
    window.set_timing(CaptionMode.INSTANT)
    window.resize(760, 440)
    try:
        yield window
    finally:
        window.close()
        shiboken6.delete(window)


@pytest.mark.parametrize("long_lines", LongLines)
def test_late_translation_keeps_one_break_per_visual_line(
    caption_window: CaptionWindow, long_lines: LongLines
) -> None:
    window = caption_window
    at_one_moment(window)
    window.set_look(
        replace(
            window.look,
            reading_lines=("yue", "zh"),
            japanese_reading=JapaneseReading.BOTH,
        )
    )
    window.set_second_languages({EN: ZH})
    window.set_presets(replace(window.preset_menu, long_lines=long_lines))
    window.show()
    words = ["play", "games", "and", "take", "a", "walk", "outside"]
    # Two short clauses fit side by side, with the second translation still pending.
    first = Clause("I play games,", {ZH: "\u6211\u6253\u6e38\u620f"})
    for source in (APP, MIC):
        window.resize(760, 440)
        update = CaptionUpdate(CaptionId(str(source)), source, CaptionKind.LIVE, (), EN)
        for count in range(1, len(words) + 1):
            waiting = Clause(" ".join(words[:count]))
            # Paint this view revision before the scrollbar also measures it.
            assert window.view.apply(replace(update, clauses=(first, waiting)))
            window.canvas.grab()
            assert window.canvas._drawn_revision == window.view.revision
            line = next(line for line in window.view.lines if line.source == source)
            bare = window.canvas.laid_at(line, window.canvas._width())
            reserved = window.canvas._laid(line)
            if long_lines is LongLines.DISPLAY_NEW_LINES:
                # The pending words still fit alongside the existing translation.
                assert reserved.height == bare.height
                assert not window._translation_slots[line.key].spaces
            else:
                assert reserved.height > bare.height
            assert reserved.breaks[-1] == reserved.height
        finished = replace(update, kind=CaptionKind.FINISHED, clauses=(first, waiting))
        assert window.receive(finished)
        window.grab()
        completed = replace(waiting, translations={ZH: "\u6211\u4e00\u4e0b"})
        assert window.receive(replace(finished, clauses=(first, completed)))
        window.resize(300, 440)
        window.grab()
        line = next(line for line in window.view.lines if line.source == source)
        laid = window.canvas._laid(line)
        baselines = {
            round(row.top + text.y() + text.ascent(), 3)
            for row in laid.rows
            for n in range(row.layout.lineCount())
            if (text := row.layout.lineAt(n)).isValid()
        }
        assert len(laid.breaks) == len(baselines) > 2
        assert laid.breaks[-1] == laid.height
        assert any(
            row.above for row in laid.rows if row.row.kind is RowKind.TRANSLATION
        )


def test_reserving_translation_space_without_a_text_line(qapp: QApplication) -> None:
    empty = LaidRow(
        CaptionRow("", RowKind.ORIGINAL, EN, 0, True), QTextLayout(), 0.0, 0
    )
    for laid in (
        LaidLine((), 0.0),
        LaidLine((empty,), 0.0),
        LaidLine((empty, empty), 20.0, breaks=(20.0,)),
    ):
        assert reserve_translation_space(laid, {0: 20.0}) is laid


def test_a_failed_caption_paint_clears_the_frame_and_logs_once_per_minute(
    caption_window: CaptionWindow,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    window = caption_window
    # The clock stands still below, so a caption's arrival would never finish
    # moving in: draw it where it ends, as with animations off (flaked on
    # GitHub's Linux machine, train #1205, 2026-11-25).
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: True)
    now = window.clock()
    window.clock = lambda: now
    window.show()
    good = CaptionUpdate(
        CaptionId("good"),
        APP,
        CaptionKind.FINISHED,
        (Clause("We can still read this."),),
        EN,
    )
    bad = replace(
        good, caption_id=CaptionId("bad"), clauses=(Clause("Another caption."),)
    )
    assert window.receive(good)
    assert window.receive(bad)
    window.canvas.grab()
    paint = window.canvas.engine.paint
    fault_colour = QColor("magenta")
    drawn: list[str] = []

    def broken(
        painter: QPainter,
        line: Line,
        laid: LaidLine,
        at: QPointF,
        ink: Ink,
        marks: Marks | None = None,
    ) -> None:
        if line.caption_id == bad.caption_id:
            painter.setClipping(False)
            painter.fillRect(680, 160, 28, 28, fault_colour)
            raise RuntimeError("private caption text")
        paint(painter, line, laid, at, ink, marks)
        drawn.append(str(line.caption_id))

    monkeypatch.setattr(window.canvas.engine, "paint", broken)
    for _ in range(2):
        drawn.clear()
        frame = window.canvas.grab().toImage()
        restored = frame.pixelColor(690, 170)
        assert restored == frame.pixelColor(640, 170)
        assert restored.alphaF() == pytest.approx(window.look.opacity, abs=0.01)
        [(line, _, _)] = window.canvas.placed
        assert line.caption_id == good.caption_id
        # the caption that can be drawn is drawn in the same frame (where its
        # pixels land depends on the machine's window and fonts: flaked as a
        # pixel scan on GitHub's Linux machine, train #1205, 2026-11-25)
        assert str(good.caption_id) in drawn
    logged = [
        record.message
        for record in caplog.records
        if "Caption paint failed" in record.message
    ]
    assert len(logged) == 1
    assert "test_caption_paint_recovery.py" in logged[0]
    assert "broken" in logged[0] and "RuntimeError" in logged[0]
    assert "private caption text" not in caplog.text

    def broken_band(painter: QPainter) -> None:
        painter.fillRect(680, 160, 28, 28, fault_colour)
        raise RuntimeError("private toolbar text")

    # past the once-a-minute limit as it stands now (not a literal 60: the
    # second log went missing in GitHub's full Windows suite, train #1205,
    # 2026-11-25, though the test passes alone there)
    now += PAINT_ERROR_LOG_INTERVAL_SEC.value + 1
    monkeypatch.setattr(window.canvas.engine, "paint", paint)
    monkeypatch.setattr(window.canvas, "_paint_band", broken_band)
    window.band_shown = True
    frame = window.canvas.grab().toImage()
    assert frame.pixelColor(690, 170) == frame.pixelColor(640, 170)
    assert {line.caption_id for line, _, _ in window.canvas.placed} == {
        good.caption_id,
        bad.caption_id,
    }
    assert any("broken_band" in record.message for record in caplog.records)
    assert "private toolbar text" not in caplog.text
    assert (
        sum("Caption paint failed" in record.message for record in caplog.records) == 2
    )
