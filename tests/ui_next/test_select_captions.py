"""Selecting and copying in a caption window (polyglotic-hq 358, on 340's
design; the user, 2026-11-15: "I want drag and select and ctrl c / right
click to copy"): a drag from a word out of its clause selects across lines,
clauses and captions - no lookup - kept until a click elsewhere or Esc, and
copied by a right-click on it or Ctrl+C; within the clause it is the phrase
pinned as before, and copyable too. Real windows, offscreen; made-up
captions."""

import logging
from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget
from tests.ui_next import test_lookup_card as cards
from tests.ui_next.made_up import finished_updates
from tests.ui_next.test_caption_flow import a_chinese_face
from tests.ui_next.test_lookup_card import Keys, card, click, find, mouse, window
from tests.ui_next.test_transcript_lookup import double_click, pinned_lookups

from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.selection import Place, Selection
from polyglotic_desktop.ui_next.caption_layout import cursor_x
from polyglotic_desktop.ui_next.caption_selection import (
    held_rects,
    place_at,
    shown,
)
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, drag_distance
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill

windows = cards.windows  # the lookup card's fixtures: a window of 40 captions
keys = cards.keys
problem = cards.problem

UNTOUCHED = "what was on the clipboard before"
SAID, MEANT = RowKind.ORIGINAL, RowKind.TRANSLATION

LAYOUTS = {
    "today's": CaptionLab(),
    "new, plain": CaptionLab(flow=True),
    "new, run on": CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True),
    "new, lined up": CaptionLab(flow=True, fill=Fill.PAIRED, aligned=True),
}


def in_layout(windows: CaptionWindows, lab: CaptionLab) -> CaptionWindow:
    if lab.flow:
        a_chinese_face()  # the new layout's lines overlap without one (357)
    windows.set_look(replace(windows.look, lab=lab))
    shown_ = window(windows)
    QApplication.processEvents()
    shown_.canvas.repaint()
    return shown_


def last_two(shown_: CaptionWindow) -> tuple[Line, Line]:
    """The two newest captions drawn whole."""
    lines = [line for line, _, _ in shown_.canvas.placed]
    return lines[-2], lines[-1]


def point(shown_: CaptionWindow, key: int, side: RowKind, char: int) -> QPointF:
    """On character `char` of `key`'s first clause on `side`, as drawn."""
    row = shown_.canvas.row_of(key, 0, side)
    assert row is not None
    rect = next(rect for line, _, rect in shown_.canvas.placed if line.key == key)
    text_line = row.layout.lineForTextPosition(char)
    x = cursor_x(text_line, char)
    return QPointF(
        rect.x() + x + 3, rect.y() + row.top + text_line.y() + text_line.height() / 2
    )


def text_of(line: Line, side: RowKind) -> str:
    return "".join(
        clause.text(side) for clause in shown([line])[0].clauses
    )  # Chinese: no spaces between clauses


def right_click(shown_: CaptionWindow, pos: QPointF) -> None:
    shown_.mousePressEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonPress, pos, shown_.mapToGlobal(pos),
            Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )  # fmt: skip


def drag(shown_: CaptionWindow, start: QPointF, end: QPointF) -> None:
    mouse(shown_, "press", start)
    mouse(shown_, "move", QPointF((start.x() + end.x()) / 2, end.y()))
    mouse(shown_, "move", end)
    mouse(shown_, "release", end)


def copied() -> str:
    return QGuiApplication.clipboard().text()


@pytest.fixture(autouse=True)
def clipboard() -> None:
    QGuiApplication.clipboard().setText(UNTOUCHED)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_a_drag_across_captions_selects_and_a_right_click_copies_it(
    windows: CaptionWindows, layout: str
) -> None:
    shown_ = in_layout(windows, LAYOUTS[layout])
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, SAID, 1))
    held = shown_.held.selection
    assert held is not None and shown_.held.watching
    assert not card(windows).pinned  # a selection: no lookup
    assert shown_.canvas.selection is None
    said, then = shown_.held.text().split("\n")
    assert said == text_of(first, SAID)
    assert then and text_of(second, SAID).startswith(then)
    rects = held_rects(shown_.canvas.placed, held)
    assert rects  # drawn
    right_click(shown_, rects[-1].center())
    assert copied() == shown_.held.text()
    assert shown_.held.selection is not None  # kept: copy again, or Esc


def test_dragged_into_a_translation_it_takes_both_sides_whole(
    windows: CaptionWindows,
) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, MEANT, 1))
    lines = shown_.held.text().split("\n")
    meant = " ".join(c.text(MEANT) for c in shown([first])[0].clauses)
    ends_in = shown([second])[0].clauses[0]  # the clause the drag ended in
    assert lines == [
        text_of(first, SAID), meant, ends_in.text(SAID), ends_in.text(MEANT)
    ]  # fmt: skip


def test_a_drag_within_the_clause_still_pins_the_phrase_and_holds_it(
    windows: CaptionWindows,
) -> None:
    shown_, shared = window(windows), card(windows)
    _, start = find(shown_, "画")
    _, end = find(shown_, "很漂亮")  # under 4: no sentence (522)
    drag(shown_, start, QPointF(end.x() + 4, end.y()))
    assert shared.pinned and shared.model.word.startswith("画面")
    held = shown_.held.selection
    assert held is not None and held.one_clause
    assert shown_.held.text() == shared.model.word
    right_click(shown_, held_rects(shown_.canvas.placed, held)[0].center())
    assert copied() == shared.model.word


def test_a_click_still_looks_up_and_a_press_on_no_word_still_moves_it(
    windows: CaptionWindows,
) -> None:
    shown_, shared = window(windows), card(windows)
    _, at = find(shown_, "电脑")
    click(shown_, at)
    assert shared.pinned and shown_.held.selection is None
    mouse(shown_, "press", QPointF(shown_.width() - 40, shown_.height() / 2))
    assert shown_._drag is not None and shown_._selecting is None
    mouse(shown_, "release", QPointF(shown_.width() - 40, shown_.height() / 2))


def test_it_keeps_its_words_as_captions_arrive_and_the_window_resizes(
    windows: CaptionWindows,
) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, SAID, 1))
    held = shown_.held.text()
    for update in finished_updates(2, start=40):
        windows.apply(update)
    shown_.leaveEvent(None)  # the mouse went: what waited comes in
    QApplication.processEvents()
    shown_.setGeometry(480, 600, 640, 420)
    QApplication.processEvents()
    shown_.canvas.repaint()
    assert shown_.held.text() == held
    in_layout(windows, LAYOUTS["new, run on"])
    assert shown_.held.text() == held  # another layout: the same words
    selection = shown_.held.selection
    assert selection is not None
    assert held_rects(shown_.canvas.placed, selection)


def test_esc_and_a_click_elsewhere_let_go_of_it(
    windows: CaptionWindows, keys: Keys
) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    start = point(shown_, first.key, SAID, 0)
    end = point(shown_, second.key, SAID, 1)

    def select() -> None:
        drag(shown_, start, end)
        assert shown_.held.selection is not None

    select()
    QApplication.sendEvent(
        shown_,
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        ),
    )
    assert shown_.held.selection is None  # Esc while this app has the keyboard
    select()
    keys.held.add("escape")
    shown_.held._look_at_keys()
    assert shown_.held.selection is None  # Esc over a game: read, not taken
    select()
    elsewhere = QWidget()
    QApplication.sendEvent(
        elsewhere,
        QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(5, 5), QPointF(-500, -500),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )  # fmt: skip
    assert shown_.held.selection is None  # a click on another of its windows
    elsewhere.deleteLater()
    select()
    click(shown_, QPointF(shown_.width() - 40, shown_.height() / 2))
    assert shown_.held.selection is None  # a click elsewhere in the window
    select()
    right_click(shown_, QPointF(shown_.width() - 40, end.y()))
    assert shown_.held.selection is None  # and a right-click: its caption, 333's
    select()
    shown_.set_locked(True)
    assert shown_.held.selection is None
    shown_.set_locked(False)


def test_a_click_on_another_app_lets_go_of_it(
    windows: CaptionWindows, keys: Keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, SAID, 1))
    monkeypatch.setattr(
        "polyglotic_desktop.ui_next.caption_selection.QCursor.pos",
        lambda: shown_.mapToGlobal(QPointF(10, 10).toPoint()),
    )
    keys.held.add("mouse")
    shown_.held._look_at_keys()
    assert shown_.held.selection is not None  # a click on the window itself
    away = shown_.geometry().bottomRight() + QPointF(300, 300).toPoint()
    monkeypatch.setattr(
        "polyglotic_desktop.ui_next.caption_selection.QCursor.pos", lambda: away
    )
    keys.held.add("mouse")
    shown_.held._look_at_keys()
    assert shown_.held.selection is None


def ctrl_c(to: QWidget) -> bool:
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, "c"
    )
    return QApplication.sendEvent(to, event) and event.isAccepted()


def test_ctrl_c_copies_it_while_this_app_has_the_keyboard(
    windows: CaptionWindows,
) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, SAID, 1))
    somewhere = QWidget()
    ctrl_c(somewhere)
    assert copied() == shown_.held.text()
    QGuiApplication.clipboard().setText(UNTOUCHED)
    typing = QLineEdit("typed")
    typing.show()
    typing.setFocus()
    QApplication.processEvents()
    if QApplication.focusWidget() is typing:  # offscreen: focus where it can
        ctrl_c(typing)
        assert copied() != shown_.held.text()  # a text field's own Ctrl+C
    typing.close()
    typing.deleteLater()
    somewhere.deleteLater()


def test_with_a_phrase_pinned_ctrl_c_is_the_cards(windows: CaptionWindows) -> None:
    """333's Ctrl+C copies the pinned card: the phrase's right-click copies
    the phrase."""
    shown_ = window(windows)
    _, start = find(shown_, "画")
    _, end = find(shown_, "很漂亮")  # under 4: no sentence (522)
    drag(shown_, start, QPointF(end.x() + 4, end.y()))
    assert shown_.held.copy_is_cards()


def test_the_place_under_the_mouse_is_between_characters_and_off_text_the_nearest(
    windows: CaptionWindows,
) -> None:
    shown_ = window(windows)
    _, second = last_two(shown_)
    at = point(shown_, second.key, SAID, 2)
    found = place_at(shown_.canvas.placed, at, shown_.canvas.clear_top)
    assert found is not None and (found.caption, found.side) == (second.key, SAID)
    assert found.char in (2, 3)
    below = place_at(
        shown_.canvas.placed,
        QPointF(at.x(), shown_.height() + 200),
        shown_.canvas.clear_top,
    )
    assert below is not None and below.caption == second.key
    assert place_at([], at, 0.0) is None


def test_a_selection_over_a_caption_gone_holds_the_rest(
    windows: CaptionWindows,
) -> None:
    shown_ = window(windows)
    first, second = last_two(shown_)
    gone = Selection(Place(-5, 0, 0, SAID), Place(second.key, 0, 1, SAID))
    shown_.held.hold(gone)
    assert shown_.held.text().split("\n")[-1] == text_of(second, SAID)[:1]
    shown_.held.clear()
    assert first.key < second.key


def test_nothing_selected_or_copied_is_logged(
    windows: CaptionWindows, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    shown_ = window(windows)
    first, second = last_two(shown_)
    drag(shown_, point(shown_, first.key, SAID, 0), point(shown_, second.key, SAID, 1))
    selection = shown_.held.selection
    assert selection is not None
    right_click(shown_, held_rects(shown_.canvas.placed, selection)[0].center())
    said = text_of(first, SAID)
    assert said and all(said not in record.getMessage() for record in caplog.records)


# -- character by character (polyglotic-hq 395) ----------------------------------------


def on(shown_: CaptionWindow, text: str) -> QPointF:
    """A point on the first character of `text` in the newest lines."""
    return find(shown_, text)[1]


def held_text(shown_: CaptionWindow) -> str:
    return shown_.held.text()


@pytest.mark.parametrize("layout", LAYOUTS)
def test_a_drag_selects_each_character_on_its_own(
    windows: CaptionWindows, layout: str
) -> None:
    """The user's preview-1 feedback (2026-11-16): "gang gang can't
    highlight individual gang, then can't highlight na individually - I
    want each character to be selectable one by one". 游戏 is one word of
    the split, as 刚刚 is: a drag selects 游, then 游戏, then 游戏的."""
    shown_, shared = in_layout(windows, LAYOUTS[layout]), card(windows)
    start = on(shown_, "游戏的")
    nudge = QPointF(drag_distance() + 1, 0)
    hit = shown_.canvas.hit(start + nudge)
    assert hit is not None and hit[1].row.text[hit[3]] == "游"  # still on 游
    drag(shown_, start, start + nudge)
    assert held_text(shown_) == "游"
    assert shared.pinned and shared.model.word == "游"  # a phrase: looked up
    for to, wanted in (("戏的", "游戏"), ("的画", "游戏的")):
        drag(shown_, start, on(shown_, to) + QPointF(2, 0))
        assert held_text(shown_) == wanted
        held = shown_.held.selection
        assert held is not None
        right_click(shown_, held_rects(shown_.canvas.placed, held)[0].center())
        assert copied() == wanted


def test_from_the_middle_of_a_word_too(windows: CaptionWindows) -> None:
    """Its second character alone, then on into the next word: 戏, 戏的."""
    shown_ = window(windows)
    start = on(shown_, "戏的")
    drag(shown_, start, start + QPointF(drag_distance() + 1, 0))
    assert held_text(shown_) == "戏"
    drag(shown_, start, on(shown_, "的画") + QPointF(2, 0))
    assert held_text(shown_) == "戏的"


def test_an_english_word_a_letter_at_a_time(windows: CaptionWindows) -> None:
    shown_ = window(windows)
    start = on(shown_, "beautiful")
    drag(shown_, start, on(shown_, "autiful") + QPointF(1, 0))
    assert held_text(shown_) == "bea"


def test_copy_is_what_was_highlighted_punctuation_and_all(
    windows: CaptionWindows,
) -> None:
    """The lookup trims a phrase's punctuation; the copy doesn't."""
    shown_, shared = window(windows), card(windows)
    drag(shown_, on(shown_, "漂亮，"), on(shown_, "，") + QPointF(2, 0))
    assert held_text(shown_) == "漂亮，"
    assert shared.model.word == "漂亮"


def test_across_captions_it_starts_at_the_character_pressed_on(
    windows: CaptionWindows,
) -> None:
    """From 游, the first character of 游戏, back into the caption before:
    it ends after 游, not stretched to the end of its word."""
    shown_ = window(windows)
    marked, start = find(shown_, "游戏的")
    shown_row = shown_.canvas.shown_row(marked.key, marked.row)
    assert shown_row is not None
    text = shown_row[1].row.text
    keys = [line.key for line, _, _ in shown_.canvas.placed]
    before = keys[keys.index(marked.key) - 1]
    drag(shown_, start, point(shown_, before, SAID, 1))
    last = held_text(shown_).split(chr(10))[-1]
    assert last == text[: text.index("游") + 1]


def test_a_small_wobble_is_still_a_click(windows: CaptionWindows) -> None:
    shown_, shared = window(windows), card(windows)
    start = on(shown_, "游戏的")
    drag(shown_, start, start + QPointF(drag_distance() - 2, 0))
    assert shown_.held.selection is None  # a click: no selection
    assert shared.pinned and shared.model.word == "游戏"  # the word looked up


def test_a_double_click_selects_the_word(windows: CaptionWindows) -> None:
    shown_ = window(windows)
    at = on(shown_, "游戏的")
    click(shown_, at)
    shown_.mouseDoubleClickEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonDblClick, at, shown_.mapToGlobal(at),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )  # fmt: skip
    mouse(shown_, "release", at)
    assert held_text(shown_) == "游戏"
    assert shown_.held.watching


def test_a_double_click_is_one_lookup(
    windows: CaptionWindows, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 400 (found by 397): with no double-click handler, Qt's
    own sent the press again and its release pinned the word twice - two
    lookups, the second turning a word assumed known new (#752), and two in
    DECISIONS #176 (d)'s count. Through Qt's own event handling."""
    shown_, shared = window(windows), card(windows)
    told = pinned_lookups(shared, monkeypatch)
    at = on(shown_, "游戏的")
    double_click(shown_, at)
    assert told == [True]
    assert shared.pinned and shared.model.word == "游戏"
    assert held_text(shown_) == "游戏"
