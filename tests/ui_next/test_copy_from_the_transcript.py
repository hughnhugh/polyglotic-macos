"""Copying from a transcript window (polyglotic-hq 343): a drag across
lines and within them selects what was said and its translation as they
show; Shift-click extends; Ctrl+C and the right-click menu copy it; a
click without a drag still looks the word up. Offscreen, with made-up
captions and the sample dictionary."""

import logging
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_transcript_lookup import both, card, find, listed, mouse

from polyglotic_desktop.ui_next.caption_layout import cursor_x
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.transcript_window import TranscriptList
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.transcript import selected_text

__all__ = ["both"]  # the fixture, shared

UNTOUCHED = "what was on the clipboard before"


@pytest.fixture
def shown(both: tuple[CaptionWindows, Transcripts]) -> Iterator[TranscriptList]:
    QGuiApplication.clipboard().setText(UNTOUCHED)
    yield listed(both[1])


def drag(shown: TranscriptList, start: QPointF, end: QPointF) -> None:
    mouse(shown, QEvent.Type.MouseButtonPress, start)
    mouse(shown, QEvent.Type.MouseMove, (start + end) / 2)
    mouse(shown, QEvent.Type.MouseMove, end)
    mouse(shown, QEvent.Type.MouseButtonRelease, end)


def press_copy(shown: TranscriptList) -> None:
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, "\x03"
    )
    QApplication.sendEvent(shown, event)


def shift_click(shown: TranscriptList, pos: QPointF) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        shown.mapToGlobal(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
    )
    shown.mousePressEvent(event)


# -- the text (the view) -----------------------------------------------------------------


def test_the_text_between_two_places_is_each_row_on_its_own_line(
    shown: TranscriptList,
) -> None:
    lines = shown.transcript.lines
    first, second = lines[-2], lines[-1]
    start = (first.key, 0, 1)
    end = (second.key, 0, 2)
    rows = [row.text for row in first.rows]
    expected = "\n".join([rows[0][1:], *rows[1:], second.rows[0].text[:2]])
    assert selected_text(lines, start, end) == expected
    assert selected_text(lines, end, start) == expected  # either way round
    assert selected_text(lines, start, start) == ""


def test_a_search_s_lines_are_what_s_copied(shown: TranscriptList) -> None:
    """Only the lines listed: those between that a search hides aren't."""
    lines = shown.transcript.lines
    shown_lines = (lines[-3], lines[-1])
    start, end = (lines[-3].key, 0, 0), (lines[-1].key, 0, 1)
    rows = [row.text for row in lines[-3].rows]
    expected = "\n".join([*rows, lines[-1].rows[0].text[:1]])
    assert selected_text(shown_lines, start, end) == expected


# -- in the window ----------------------------------------------------------------------


def test_a_drag_across_lines_selects_them_and_ctrl_c_copies_it(
    shown: TranscriptList,
) -> None:
    _, start = find(shown, "电脑")
    _, end = find(shown, "游戏")
    drag(shown, start, end)
    said = shown.selectedText()
    assert said and "\n" in said
    assert shown.hasSelectedText()
    press_copy(shown)
    assert QGuiApplication.clipboard().text() == said


def test_a_drag_within_a_line_selects_part_of_it(shown: TranscriptList) -> None:
    word, start = find(shown, "电脑")
    end = QPointF(start.x() + 1, start.y())
    for line, laid, at in shown.drawn:
        if line.key != word.key:
            continue
        row = next(r for r in laid.rows if r.index == word.row)
        text_line = row.layout.lineForTextPosition(word.end)
        end = QPointF(at.x() + cursor_x(text_line, word.end), start.y())
    drag(shown, QPointF(start.x() - 4, start.y()), end)
    assert shown.selectedText() == "电脑"


def test_a_drag_doesn_t_look_the_word_up_and_a_click_does(
    both: tuple[CaptionWindows, Transcripts], shown: TranscriptList
) -> None:
    shared = card(both[0])
    _, start = find(shown, "电脑")
    _, end = find(shown, "游戏")
    drag(shown, start, end)
    assert not shared.pinned
    mouse(shown, QEvent.Type.MouseButtonPress, end)
    mouse(shown, QEvent.Type.MouseButtonRelease, end)
    assert shared.pinned  # a click: as before
    assert not shown.hasSelectedText()  # and it clears the selection


def test_shift_click_extends_the_selection(shown: TranscriptList) -> None:
    _, start = find(shown, "电脑")
    _, end = find(shown, "游戏")
    drag(shown, start, QPointF(start.x() + 12, start.y()))
    before = shown.selectedText()
    shift_click(shown, end)
    mouse(shown, QEvent.Type.MouseButtonRelease, end)
    assert len(shown.selectedText()) > len(before)
    assert shown.selectedText().startswith(before[:1])


def test_the_right_click_menu_copies_the_selection_or_offers_the_line_s(
    shown: TranscriptList,
) -> None:
    _, start = find(shown, "电脑")
    menu = shown.menu_at(start.y())
    assert menu is not None
    assert [a.text() for a in menu.actions()][:2] == ["Copy", "Copy what was said"]
    menu.deleteLater()
    _, end = find(shown, "游戏")
    drag(shown, start, end)
    menu = shown.menu_at(start.y())
    assert menu is not None
    assert [a.text() for a in menu.actions()] == [
        "Copy",
        "Select all",
        "Save sentence to",  # more than a word (459)
    ]
    menu.actions()[0].trigger()
    assert QGuiApplication.clipboard().text() == shown.selectedText()
    menu.actions()[1].trigger()
    lines = shown.transcript.lines
    assert shown.selectedText().startswith(lines[0].rows[0].text)
    assert shown.selectedText().endswith(lines[-1].rows[-1].text)
    menu.deleteLater()


def test_ctrl_c_is_the_transcript_s_with_a_card_pinned(
    both: tuple[CaptionWindows, Transcripts],
    shown: TranscriptList,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pinned card's Ctrl+C copies the card (333) - but not over text
    selected where the keyboard is."""
    shared = card(both[0])
    _, word = find(shown, "游戏")
    mouse(shown, QEvent.Type.MouseButtonPress, word)
    mouse(shown, QEvent.Type.MouseButtonRelease, word)
    assert shared.pinned
    _, start = find(shown, "电脑")
    drag(shown, start, word)
    monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: shown))
    press_copy(shown)
    assert QGuiApplication.clipboard().text() == shown.selectedText()


def test_nothing_copied_is_logged(
    shown: TranscriptList, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _, start = find(shown, "电脑")
    _, end = find(shown, "游戏")
    drag(shown, start, end)
    press_copy(shown)
    assert "电脑" not in caplog.text and "游戏" not in caplog.text
