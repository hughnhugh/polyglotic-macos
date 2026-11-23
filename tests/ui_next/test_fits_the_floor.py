"""The main window at its floor (760 x 520) in every language and text size
(polyglotic-hq 354): rows wrap (`controls.Flow`), a long button's words
wrap (`WrapButton`, `WrapCheckBox`), a choice of several goes onto two
lines (`Segmented`), a word table's columns narrow (`word_table.fitted`)
and the sidebar at a large text size is only as wide as its words need.
The whole window, every page and Settings section, in every language: the
UI lab's `w4_pages_at_floor`."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QAction, QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QStyleFactory,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import (
    Flow,
    Segmented,
    SwitchButton,
    WrapButton,
    WrapCheckBox,
    WrapRadioButton,
    least_width,
    wrapped,
)
from polyglotic_desktop.ui_next.main_window import FLOOR, FRAME, SIZE, MainWindow
from polyglotic_desktop.ui_next.word_table import (
    LEAST_MEANING,
    LEAST_WORD,
    Column,
    fitted,
)

SENTENCE = "Show a hidden caption window when speech starts in its app"


@pytest.fixture
def at_normal(qapp: QApplication) -> Iterator[QApplication]:
    style.use_text_scale(1.0)
    style.use_app_text_size("normal")
    yield qapp
    style.use_text_scale(1.0)
    style.use_app_text_size("normal")


def _row(texts: list[str], **flow: object) -> tuple[QWidget, Flow, list[QPushButton]]:
    holder = QWidget()
    row = Flow(holder, **flow)  # type: ignore[arg-type]
    buttons = []
    for text in texts:
        button = QPushButton(text)
        row.addWidget(button)
        buttons.append(button)
    return holder, row, buttons


def test_a_flow_is_one_line_where_it_fits(qapp: QApplication) -> None:
    holder, row, buttons = _row(["Lock all", "Hide all", "Join windows"])
    wide = row.sizeHint().width() + 40
    holder.resize(wide, row.heightForWidth(wide))
    holder.show()
    qapp.processEvents()
    assert len({b.y() for b in buttons}) == 1
    assert buttons[0].x() < buttons[1].x() < buttons[2].x()
    holder.deleteLater()


def test_a_flow_wraps_where_it_doesnt(qapp: QApplication) -> None:
    holder, row, buttons = _row(["Lock all", "Hide all", "Join windows"])
    narrow = max(b.sizeHint().width() for b in buttons) + 4
    assert row.heightForWidth(narrow) > row.heightForWidth(row.sizeHint().width())
    holder.resize(narrow, row.heightForWidth(narrow))
    holder.show()
    qapp.processEvents()
    assert len({b.y() for b in buttons}) == 3  # one a line
    assert all(b.geometry().right() < narrow for b in buttons)
    holder.deleteLater()


def test_a_flows_least_is_its_widest_item(qapp: QApplication) -> None:
    holder, row, buttons = _row(["Lock all", "Reset every window's position"])
    widest = max(b.minimumSizeHint().width() for b in buttons)
    assert row.minimumSize().width() == widest  # not the sum, as a row's is
    holder.deleteLater()


def test_a_stretch_pushes_what_follows_right(qapp: QApplication) -> None:
    holder = QWidget()
    row = Flow(holder)
    left, right = QPushButton("Title"), QPushButton("Choice")
    row.addWidget(left)
    row.add_stretch()
    row.addWidget(right)
    holder.resize(600, 40)
    holder.show()
    qapp.processEvents()
    assert left.x() == 0 and right.geometry().right() == 599
    holder.deleteLater()


def test_a_right_flow_keeps_its_buttons_right(qapp: QApplication) -> None:
    holder, _flow, buttons = _row(["Privacy notice", "Tester agreement"], right=True)
    holder.resize(600, 40)
    holder.show()
    qapp.processEvents()
    assert buttons[-1].geometry().right() == 599
    holder.deleteLater()


def test_a_wrap_buttons_least_is_its_longest_word(qapp: QApplication) -> None:
    button = WrapButton(SENTENCE)
    one = button.sizeHint().width()
    least = button.minimumSizeHint().width()
    words = least_width(SENTENCE, button.font())
    assert least < one / 2
    assert least - words == one - button.fontMetrics().horizontalAdvance(SENTENCE)
    button.deleteLater()


def test_a_narrow_wrap_button_is_taller_and_keeps_its_words(qapp: QApplication) -> None:
    holder = QWidget()
    column = QVBoxLayout(holder)
    button = WrapButton(SENTENCE)
    column.addWidget(button)
    one = button.sizeHint()
    holder.resize(one.width() // 3, 300)
    holder.show()
    qapp.processEvents()
    assert button.width() < one.width()
    assert button.height() > one.height()  # its lines' height, given by the layout
    assert button.height() == button.heightForWidth(button.width())
    assert button.text() == SENTENCE  # only the painting breaks it
    button.grab()  # paints, wrapped
    holder.resize(one.width() + 40, 300)
    qapp.processEvents()
    assert button.height() == one.height()  # one line again
    holder.deleteLater()


def test_a_switch_and_a_check_box_wrap(qapp: QApplication) -> None:
    switch = SwitchButton()
    switch.setText(SENTENCE)
    box = WrapCheckBox(SENTENCE)
    for each in (switch, box):
        assert each.minimumSizeHint().width() < each.sizeHint().width() / 2
        assert each.heightForWidth(each.minimumSizeHint().width()) > (
            each.sizeHint().height()
        )
        each.deleteLater()


def test_a_wrapped_radio_button_accepts_clicks_on_its_last_line(
    qapp: QApplication,
) -> None:
    holder = QWidget()
    column = QVBoxLayout(holder)
    button = WrapRadioButton(SENTENCE)
    native = QStyleFactory.create("Fusion")
    assert native is not None
    native.setParent(button)
    button.setStyle(native)
    column.addWidget(button)
    one = button.sizeHint()
    holder.resize(one.width() // 2, 300)
    holder.show()
    qapp.processEvents()
    assert button.height() > one.height()
    metrics = button.fontMetrics()
    point = QPoint(
        one.width() - metrics.horizontalAdvance(SENTENCE) + 1,
        button.height() - metrics.lineSpacing() // 2,
    )
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, pos=point)
    assert button.isChecked()
    holder.deleteLater()


def test_chinese_breaks_between_any_characters(qapp: QApplication) -> None:
    font = QFont()
    text = "同时为电脑播放的其他声音加字幕"
    assert least_width(text, font) < least_width("字幕", font) + 2
    assert wrapped(text, font, least_width("字幕字幕字", font)).count("\n") >= 2


def test_a_segmented_choice_wraps_its_choices(qapp: QApplication) -> None:
    choices = Segmented(
        [(n, word) for n, word in enumerate(["Look", "Timing", "Speech", "Dictation"])]
    )
    widest = max(b.sizeHint().width() for b in choices.buttons)
    assert choices.minimumSizeHint().width() < 2 * widest  # not all four side by side
    choices.deleteLater()


def test_a_tables_columns_narrow_to_leave_the_meaning_room() -> None:
    """At the design sizes (a text size factor of 1.0: the app's Smaller
    since decision 0244), where the least widths are as named."""
    widths = {Column.WORD: 150, Column.ADD: 110, Column.KNOWN: 90}
    least = {Column.WORD: LEAST_WORD, Column.ADD: 60, Column.KNOWN: 70}
    assert fitted(widths, least, 1000) == widths  # room: as they were
    room = 150 + 110 + 90 + LEAST_MEANING - 50
    narrowed = fitted(widths, least, room)
    assert narrowed[Column.WORD] == 100 and narrowed[Column.ADD] == 110  # word first
    room = LEAST_WORD + 60 + 90 + LEAST_MEANING
    narrowed = fitted(widths, least, room)
    assert narrowed == {Column.WORD: LEAST_WORD, Column.ADD: 60, Column.KNOWN: 90}


@pytest.mark.parametrize("size", ["larger", "largest"])
def test_the_sidebar_at_a_large_text_size_leaves_the_page_room(
    at_normal: QApplication, size: str
) -> None:
    """At the Largest text size the sidebar was 267 of the floor's 760 px
    (184 times 1.45): now only as wide as its words need - under the usual
    first size; at it, as it was."""
    style.use_app_text_size(size)
    quit_action = QAction("Quit")
    window = MainWindow(quit_action)
    for key in ("home", "words", "learning", "account"):
        window.add_page(key, key.title(), QWidget())
    window.resize(*FLOOR)
    window._fit_sidebar(FLOOR[0])
    needs = window.sidebar_needs()  # its words, and a scroll bar where it scrolls
    assert window.sidebar.width() == max(184, needs) < style.px(184)
    window._fit_sidebar(SIZE[0])  # the usual size: its column's lines readable
    assert window.sidebar.width() >= style.px(184)  # 184 or, wider, 200
    window.deleteLater()


def test_at_the_floor_the_sidebar_scrolls_rather_than_squash_its_buttons(
    at_normal: QApplication,
) -> None:
    """At the Largest text size (1.75 since decision 0244) the floor's 520 px
    is shorter than the sidebar: its pages' buttons were squashed, their
    words cut top and bottom (the UI lab, polyglotic-hq 524). Its column
    scrolls instead, every button its own height."""
    style.use_app_text_size("largest")
    window = MainWindow(QAction("Quit"))
    for key in ("home", "words", "learning", "account"):
        window.add_page(key, key.title(), QWidget())
    window.add_page("settings", "Settings", QWidget(), "foot")
    window.add_page("help", "Help", QWidget(), "foot")
    window.fit_to(QRect(0, 0, FLOOR[0] + FRAME, FLOOR[1] + FRAME))
    window.show()
    at_normal.processEvents()
    assert (window.width(), window.height()) == FLOOR
    squashed = [
        b.text()
        for b in window.top_buttons + window.foot_buttons
        if b.height() < b.sizeHint().height()
    ]
    assert squashed == []
    assert window.side_scroll.verticalScrollBar().maximum() > 0
    window.keep_in_tray = False
    window.close()
    window.deleteLater()
