"""Copying from the lookup card (polyglotic-hq 343): a drag across its
text selects it; a right-click on the selection copies it, with "Copied"
by the mouse - no menu, never the keyboard (a game keeps it); Ctrl+C
copies it while one of the app's windows has the keyboard, or the whole
card with nothing selected. The card's own clicks still work. Real cards,
offscreen."""

import logging
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QWidget
from tests.ui_next.test_lookup_view import learner
from tests.ui_next.test_say_it import has, pin

from polyglotic_desktop.ui_next import lookup_card
from polyglotic_desktop.ui_next.caption_layout import cursor_x
from polyglotic_desktop.ui_next.copying import Painted
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.toast import hide_toast, toast_text

UNTOUCHED = "what was on the clipboard before"
WHOLE = "电脑 電腦\ndiàn nǎo: computer"
"""The whole card, as its Copy copies it (333)."""


class Keys:
    """The `KeyState` port, made up: whether each key is "held"."""

    def __init__(self) -> None:
        self.held: set[str] = set()

    def __call__(self, name: str) -> bool:
        return name in self.held


@pytest.fixture
def keys() -> Keys:
    return Keys()


@pytest.fixture
def card(qapp: QApplication, keys: Keys) -> Iterator[LookupCard]:
    QGuiApplication.clipboard().setText(UNTOUCHED)
    made = LookupCard(learner(), keys)
    yield made
    made.close_card()
    made.close()
    made.deleteLater()
    hide_toast()
    qapp.processEvents()


def piece(card: LookupCard, text: str) -> Painted:
    return next(p for p in card._painted.texts if p.text == text)


def inside(card: LookupCard, text: str, at: int = 0) -> QPoint:
    """A point on `text`'s first line, just after its `at`-th character."""
    found = piece(card, text)
    line = found.layout.lineAt(0)
    x = cursor_x(line, at) + (1 if at == 0 else -1)
    return QPointF(found.at.x() + x, found.at.y() + line.height() / 2).toPoint()


def drag(card: LookupCard, start: QPoint, end: QPoint) -> None:
    QTest.mousePress(card, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(card, (start + end) / 2)
    QTest.mouseMove(card, end)
    QTest.mouseRelease(card, Qt.MouseButton.LeftButton, pos=end)


def right_click(card: LookupCard, at: QPoint) -> None:
    QTest.mousePress(card, Qt.MouseButton.RightButton, pos=at)
    QTest.mouseRelease(card, Qt.MouseButton.RightButton, pos=at)


def menus_now() -> list[QMenu]:
    return [w for w in QApplication.topLevelWidgets() if isinstance(w, QMenu)]


def texts(card: LookupCard) -> list[str]:
    return [p.text for p in card._painted.texts]


# -- what can be selected ---------------------------------------------------------------


def test_the_word_its_reading_senses_parts_and_context_can_be_selected(
    card: LookupCard,
) -> None:
    pin(card, "电脑")
    found = texts(card)
    for each in ("电脑", "電腦", "我的电脑坏了", "电", "脑"):
        assert each in found, each
    assert any("computer" in t for t in found)
    for button in ("Add to deck", "Known", "Copy"):  # buttons and chips: not
        assert button not in found


# -- selecting and copying --------------------------------------------------------------


def test_a_drag_across_the_word_selects_it_and_a_right_click_copies_it(
    qapp: QApplication, card: LookupCard
) -> None:
    pin(card, "电脑")
    drag(card, inside(card, "电脑"), inside(card, "电脑", 2))
    assert card.selection.text() == "电脑"
    focus, active = QApplication.focusWidget(), QApplication.activeWindow()
    menus = set(menus_now())
    right_click(card, inside(card, "电脑", 1))
    assert QGuiApplication.clipboard().text() == "电脑"
    assert toast_text() == "Copied to clipboard"
    # no menu, and the keyboard stays where it was (a game keeps it)
    assert not card.findChildren(QMenu)
    assert set(menus_now()) == menus
    assert QApplication.focusWidget() is focus
    assert QApplication.activeWindow() is active
    assert card.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_a_drag_across_lines_copies_them_in_order(card: LookupCard) -> None:
    pin(card, "电脑")
    drag(card, inside(card, "电脑"), inside(card, "我的电脑坏了", 6))
    said = card.selection.text().split("\n")
    assert said[0] == "电脑 diàn nǎo 電腦"  # one line: a space between its pieces
    assert said[-1] == "我的电脑坏了"
    assert any("computer" in line for line in said)
    assert said.index("我的电脑坏了") > 0


def test_a_drag_within_a_line_selects_part_of_it(card: LookupCard) -> None:
    pin(card, "电脑")
    drag(card, inside(card, "我的电脑坏了", 2), inside(card, "我的电脑坏了", 4))
    assert card.selection.text() == "电脑"
    assert card.selection.highlights()  # painted as selected


def test_a_right_click_with_nothing_selected_copies_nothing(card: LookupCard) -> None:
    pin(card, "电脑")
    right_click(card, inside(card, "电脑", 1))
    assert QGuiApplication.clipboard().text() == UNTOUCHED


def test_a_click_without_a_drag_clears_the_selection(card: LookupCard) -> None:
    pin(card, "电脑")
    drag(card, inside(card, "电脑"), inside(card, "电脑", 2))
    QTest.mouseClick(
        card, Qt.MouseButton.LeftButton, pos=inside(card, "我的电脑坏了", 1)
    )
    assert card.selection.empty
    assert card.isVisible()


def test_another_word_starts_with_nothing_selected(card: LookupCard) -> None:
    pin(card, "电脑")
    drag(card, inside(card, "电脑"), inside(card, "电脑", 2))
    pin(card, "电")
    assert card.selection.empty


# -- Ctrl+C ------------------------------------------------------------------------------


def press_copy(target: QWidget) -> bool:
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, "\x03"
    )
    return QApplication.sendEvent(target, event)


def test_ctrl_c_copies_the_selection_or_the_whole_card(
    qapp: QApplication, card: LookupCard, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = QWidget()  # the main window, say, with the keyboard
    try:
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: page))
        pin(card, "电脑")
        press_copy(page)
        assert QGuiApplication.clipboard().text() == WHOLE  # nothing selected
        drag(card, inside(card, "我的电脑坏了", 2), inside(card, "我的电脑坏了", 4))
        press_copy(page)
        assert QGuiApplication.clipboard().text() == "电脑"
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_ctrl_c_on_words_selected_in_the_main_window_copies_those(
    qapp: QApplication, card: LookupCard, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = QWidget()
    words = QLabel("Polyglotic 0.1.5", page)
    words.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    words.setSelection(0, 10)
    try:
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: words))
        pin(card, "电脑")
        press_copy(words)
        assert QGuiApplication.clipboard().text() == "Polyglotic"  # the label's
    finally:
        page.deleteLater()
        qapp.processEvents()


# -- the card's own clicks ---------------------------------------------------------------


def test_a_click_on_a_part_still_looks_it_up_and_a_drag_on_it_selects(
    card: LookupCard,
) -> None:
    pin(card, "电脑")
    # along the part's row, further than Qt's drag distance whatever the
    # font (Linux's CI has no Chinese one: a character there is narrow)
    start = inside(card, "电")
    drag(card, start, start + QPoint(QApplication.startDragDistance() + 30, 0))
    assert card.selection.text().startswith("电 ")
    assert card.model.card().word == "电脑"  # a drag: not a lookup
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=inside(card, "脑"))
    assert card.model.card().word == "脑"


def test_a_button_still_works_at_a_press(card: LookupCard) -> None:
    pin(card, "电脑")
    copy = next(rect for rect, hit in card._hits if hit == "copy")
    QTest.mousePress(card, Qt.MouseButton.LeftButton, pos=copy.center().toPoint())
    assert QGuiApplication.clipboard().text() == WHOLE
    assert has(card, "copy")


def test_a_drag_that_leaves_the_card_doesn_t_close_it(
    card: LookupCard, keys: Keys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While pinned, a mouse button held off the card closes it (its look
    at the keys) - but not the button that's dragging a selection from it."""
    pin(card, "电脑")
    away = card.frameGeometry().bottomRight() + QPoint(300, 300)
    monkeypatch.setattr(lookup_card.QCursor, "pos", staticmethod(lambda: away))
    monkeypatch.setattr(QApplication, "widgetAt", staticmethod(lambda _at: None))
    keys.held.add("mouse")
    QTest.mousePress(card, Qt.MouseButton.LeftButton, pos=inside(card, "电脑"))
    QTest.mouseMove(card, card.mapFromGlobal(away))
    card._look_at_keys()
    assert card.isVisible()
    QTest.mouseRelease(card, Qt.MouseButton.LeftButton, pos=card.mapFromGlobal(away))
    assert not card.selection.empty
    card._look_at_keys()  # a click elsewhere, after the drag: closes it
    assert not card.isVisible()


def test_nothing_copied_is_logged(
    card: LookupCard, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    pin(card, "电脑")
    drag(card, inside(card, "我的电脑坏了"), inside(card, "我的电脑坏了", 6))
    right_click(card, inside(card, "我的电脑坏了", 1))
    assert "电脑" not in caplog.text and "computer" not in caplog.text
