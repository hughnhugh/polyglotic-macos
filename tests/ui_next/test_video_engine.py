"""The agreed Video motion and the glyph layout its painter uses."""

from itertools import pairwise
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QTextLayout, QTextOption
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.display import CaptionRow, RowKind
from polyglotic_desktop.ui_next.caption_layout import LaidRow, char_under, panned_row


def wrapped(text: str, width: int) -> LaidRow:
    font = QFont("Segoe UI")
    font.setPixelSize(18)
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    height = 0.0
    while (line := layout.createLine()).isValid():
        line.setLineWidth(width)
        line.setPosition(QPointF(0.0, height))
        height += line.height()
    layout.endLayout()
    return LaidRow(CaptionRow(text, RowKind.ORIGINAL, None, 0, True), layout, 0, 0)


def test_panned_graphemes_keep_their_full_size_and_source_coordinates(
    qapp: QApplication,
) -> None:
    row = wrapped("one two three four five six seven eight", 900)
    line = row.layout.lineAt(0)
    width = 101
    for offset in (0, -5, -22, -79, width - line.naturalTextWidth()):
        visible = panned_row(row, offset, width)
        assert visible is not None
        assert visible.layout.font() == row.layout.font()
        text = visible.row.text
        assert row.row.text[visible.start : visible.start + len(text)] == text
        ink = visible.layout.lineAt(0).naturalTextRect()
        assert ink.left() >= -0.5
        assert ink.right() <= width + 0.5
        assert char_under([(visible, QPointF())], ink.center()) is not None
    assert visible is not None
    assert visible.row.text.endswith("eight")
    assert visible.start > 0


def test_live_track_catches_a_burst_without_skipping_its_first_paint():
    from polyglotic_desktop.ui_next.video import FRAME, Pan
    from polyglotic_desktop.ui_next.views.card_window_defaults import (
        CATCHUP,
        GLIDE,
        MAX_STEP,
    )

    pan = Pan()
    positions = []
    for frame in range(round(CATCHUP.value / FRAME) + 1):
        pan.follow(350, frame * FRAME, FRAME)
        positions.append(pan.x)
    assert positions[0] == 0
    assert positions[-1] == 350
    steps = [b - a for a, b in pairwise(positions)]
    assert all(0 <= step <= MAX_STEP.value for step in steps)
    assert sum(step > 0 for step in steps) > 1
    assert max(steps) > steps[-2]
    pan.follow(370, CATCHUP.value + FRAME, FRAME)
    assert pan.x == pytest.approx(350 + GLIDE.value * FRAME)


@pytest.mark.parametrize("translation", [False, True])
def test_a_settled_track_wraps_the_script_actually_being_read(
    translation: bool,
) -> None:
    from polyglotic_desktop.ui_next.video import VideoFlow

    flow = VideoFlow(lambda text, tr: len(text) * 10, 100, 10, 200, 20, 18)
    assert flow.wrap("Second word here.", translation) == ["Second ", "word here."]
    chinese = "报告警告称没有人能保证目前采取的任何行动。"
    rows = flow.wrap(chinese, translation)
    assert len(rows) > 1 and "".join(rows) == chinese
    assert all(not row.startswith("。") for row in rows)


def test_finished_mandarin_gets_the_learners_reading_time() -> None:
    from polyglotic_desktop.ui_next.video import VideoFlow
    from polyglotic_desktop.ui_next.views import dwell

    text = "目前在伊拉克采取的任何行动"
    assert (
        VideoFlow.reading_need(text, False)
        >= dwell.READ_START_SEC.value + len(text) / dwell.SAID_PACE.value
    )
    assert VideoFlow.reading_need(text, False) > VideoFlow.reading_need(text, True)


@pytest.mark.parametrize("scrolling", [False, True])
def test_next_caption_waits_for_the_previous_caps_last_word(scrolling: bool) -> None:
    from polyglotic_desktop.core.listening.playout import each_character
    from polyglotic_desktop.ui_next.video import FRAME, Copy, VideoFlow

    flow = VideoFlow(lambda text, tr: len(text) * 10, 300, 10, 150, 20, 18)
    text = "Here are the very last words."
    first = Copy(Mock(key=0, live=False, provisional=False), "", text, True)
    later = Copy(Mock(key=1, live=False, provisional=False), "", "Next.", True)
    for frame in range(6):
        flow.advance(
            [first, later], frame * FRAME, scrolling=scrolling, split=each_character
        )
        assert flow.last_key == 0
    assert [row.text for row in flow.rows()] == [text]

    for frame in range(6, 150):
        flow.advance(
            [first, later], frame * FRAME, scrolling=scrolling, split=each_character
        )
    assert any(row.copy.line.key == 1 and row.text == "Next." for row in flow.rows())


@pytest.mark.parametrize("scrolling", [False, True])
def test_finished_rows_hold_their_shape_and_position(scrolling: bool) -> None:
    from polyglotic_desktop.ui_next.video import FRAME, Copy, VideoFlow
    from polyglotic_desktop.ui_next.views.card_window_defaults import SETTLE

    flow = VideoFlow(lambda text, tr: len(text) * 10, 100, 10, 100, 20, 18)
    live = Mock(key=0, live=True, provisional=False)
    final = Mock(key=0, live=False, provisional=False)
    next_line = Mock(key=1, live=True, provisional=False)
    text = "Second word here."
    for f in range(60):
        flow.advance([Copy(live, text, "", False)], f * FRAME, scrolling=scrolling)
    before = [(r.text, r.x, r.y) for r in flow.rows()]
    expected = [text] if scrolling else ["Second ", "word here."]
    assert [part[0] for part in before] == expected
    for f in range(round(SETTLE.value / FRAME)):
        flow.advance(
            [Copy(final, text, "", False), Copy(next_line, "Next", "", False)],
            1 + f * FRAME,
            scrolling=not scrolling,
        )
        assert [
            (r.text, r.x, r.y) for r in flow.rows() if r.copy.line.key == 0
        ] == before
    assert flow.tracks[0].scrolling is scrolling


def test_a_finished_original_leaves_room_for_its_pending_translation() -> None:
    from polyglotic_desktop.core.listening.playout import each_character
    from polyglotic_desktop.ui_next.video import FRAME, Copy, VideoFlow

    flow = VideoFlow(
        lambda text, tr: len(text) * 10, 180, 10, 140, 20, 18, lines_shown=2
    )
    first = Copy(Mock(key=0, live=False, provisional=False), "Earlier", "First.", True)
    later = Copy(
        Mock(key=1, live=False, provisional=False),
        "Friends.",
        "I read books with friends.",
        True,
    )
    for frame in range(240):
        flow.advance([first], frame * FRAME, split=each_character)

    admitted = None
    for frame in range(240, 275):
        flow.advance([first, later], frame * FRAME, split=each_character)
        if admitted is None and any(row.copy.line.key == 1 for row in flow.rows()):
            admitted = frame
        if any(
            row.start > 0 and row.text.rstrip().endswith("friends.")
            for row in flow.rows()
        ):
            assert admitted is not None
            assert (frame - admitted) * FRAME <= 0.2
            break
    else:
        pytest.fail("The translation's last word missed its 200 ms deadline")


def test_overfull_translation_paints_every_row_in_order() -> None:
    from polyglotic_desktop.core.listening.playout import each_character
    from polyglotic_desktop.ui_next.video import FRAME, Copy, VideoFlow

    flow = VideoFlow(
        lambda text, tr: len(text) * 10, 160, 10, 100, 20, 18, lines_shown=1
    )
    copy = Copy(
        Mock(key=0, live=False, provisional=False),
        "Here.",
        "The Amazon River is also the widest river on Earth.",
        True,
    )
    ink = {}
    for frame in range(13):
        flow.advance([copy], frame * FRAME, split=each_character)
        for row in flow.rows():
            if row.translation:
                ink[row.start] = row.text

    assert len(ink) > 2
    assert " ".join(row.strip() for row in ink.values()) == copy.translation
