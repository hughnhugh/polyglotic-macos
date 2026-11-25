"""Several of the learning load's words at once (polyglotic-hq 342; the
user, 2026-11-15: "Should be a faster way to multiselect known words"):
the picking rules in plain Python, and on Learning's load card Shift-click,
Ctrl-click and the keyboard, then one action for them all - "I know these"
for the words next to enter too. Made-up ranks and captions; offscreen."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.ui.test_learning_load_card import entry, hear, learner, seen

from polyglotic_desktop.core.learning.load import LoadRules
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.main import for_picked_in_load
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.load_card import LoadCard
from polyglotic_desktop.ui_next.views.load import Listed
from polyglotic_desktop.ui_next.views.picking import Picking

ORDER = ["a", "b", "c", "d", "e"]

# -- the rules ------------------------------------------------------------------------------


def test_shift_picks_the_range_from_the_last_plain_click() -> None:
    picking = Picking()
    picking.click("b", ORDER)
    picking.click("d", ORDER, shift=True)
    assert picking.in_order(ORDER) == ["b", "c", "d"]
    picking.click("a", ORDER, shift=True)  # from b again, the other way
    assert picking.in_order(ORDER) == ["a", "b"]
    picking.click("e", ORDER, ctrl=True)  # Ctrl adds one
    assert picking.in_order(ORDER) == ["a", "b", "e"]
    picking.click("a", ORDER, ctrl=True)  # and takes one away
    assert picking.in_order(ORDER) == ["b", "e"]
    picking.click("c", ORDER, shift=True)  # from the last Ctrl-click, a
    assert picking.in_order(ORDER) == ["a", "b", "c"]
    picking.click("a", ORDER)  # a plain click: that one alone
    assert picking.in_order(ORDER) == ["a"]


def test_the_keyboard_moves_and_picks() -> None:
    picking = Picking()
    picking.move(1, ORDER)  # on the first
    assert picking.current == "a" and not picking.picked
    picking.click("b", ORDER)
    picking.move(1, ORDER, shift=True)
    picking.move(1, ORDER, shift=True)
    assert picking.in_order(ORDER) == ["b", "c", "d"]
    picking.move(-1, ORDER, shift=True)
    assert picking.in_order(ORDER) == ["b", "c"]
    picking.toggle()  # Space: c let go
    assert picking.in_order(ORDER) == ["b"]
    picking.all(ORDER)
    assert picking.in_order(ORDER) == ORDER
    picking.move(10, ORDER)  # never past the end
    assert picking.current == "e"


def test_what_is_picked_stays_where_still_listed() -> None:
    picking = Picking()
    picking.click("b", ORDER)
    picking.click("d", ORDER, shift=True)
    picking.keep(["d", "x", "b", "a"])  # c gone, the rest moved
    assert picking.in_order(["d", "x", "b", "a"]) == ["d", "b"]
    picking.keep([])
    assert not picking.picked and picking.anchor is None


# -- the card -------------------------------------------------------------------------------


@pytest.fixture
def card(qapp: QApplication) -> Iterator[LoadCard]:
    made = LoadCard()
    made.resize(700, 900)
    made.show()
    yield made
    made.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wide(tools: LearningTools) -> LearningTools:
    """A load of all four: 电脑, 游戏, 研究, 足球."""
    tools.vocabulary.set_load_rules(LoadRules(size=4, step=3))
    return tools


def show(card: LoadCard, tools: LearningTools, listed: Listed) -> None:
    card.lists.set_value(listed)
    card.show_load(seen(tools, listed))
    QApplication.processEvents()


def ids(entries: list[str]) -> list[EntryId]:
    return [EntryId(e) for e in entries]


def click(card: LoadCard, row: int, held: Qt.KeyboardModifier) -> None:
    """A click on the row's word: the label lets it through to the list."""
    item = card.words.grid.itemAtPosition(row, 0)
    word = item.widget() if item is not None else None
    assert word is not None
    QTest.mouseClick(word, Qt.MouseButton.LeftButton, held, QPoint(3, 3))


def test_shift_click_and_i_know_these_on_the_load(card: LoadCard) -> None:
    tools = wide(learner())
    show(card, tools, Listed.IN_LOAD)
    order = card.words.order
    assert len(order) == 4 and card.picked_bar.isHidden()
    click(card, 0, Qt.KeyboardModifier.NoModifier)
    assert card.picked_bar.isHidden()
    assert card.picked_bar.count.text() == "1 word selected"
    click(card, 2, Qt.KeyboardModifier.ShiftModifier)
    assert card.words.picked() == order[:3]
    assert not card.picked_bar.isHidden()
    assert card.picked_bar.count.text() == "3 words selected"
    shown = [k for k, b in card.picked_bar.buttons.items() if not b.isHidden() and k]
    assert shown == ["known", "not_now"]  # and Clear
    asked: list[tuple[str, list[str]]] = []
    card.many_wanted.connect(lambda what, entries: asked.append((what, entries)))
    card.picked_bar.buttons["known"].click()
    assert asked == [("known", order[:3])]
    assert card.words.picked() == [] and card.picked_bar.isHidden()
    for_picked_in_load(tools, "known", ids(order[:3]))  # as main does it
    status = tools.vocabulary.status_of_entry
    assert [status(e).status for e in ids(order[:3])] == [WordStatus.KNOWN] * 3


def test_the_words_next_to_enter_can_be_known_together(card: LoadCard) -> None:
    """The learner's own case: words waiting to enter that they know
    already - picked with the keyboard, marked known, and the load takes
    the next ones."""
    tools = learner()  # a load of 3: 足球 is next to enter
    show(card, tools, Listed.NEXT)
    football = entry(tools, "足球")
    assert card.words.order == [football]
    card.words.setFocus()
    QTest.keyClick(card.words, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert card.words.picked() == [football]
    assert card.picked_bar.isHidden()  # one word: its own button does it
    shown = [k for k, b in card.picked_bar.buttons.items() if not b.isHidden() and k]
    assert shown == ["known", "add"]
    for_picked_in_load(tools, "known", [football])
    assert tools.vocabulary.status_of_entry(football).status is WordStatus.KNOWN


def test_the_check_answers_for_several_at_once(card: LoadCard) -> None:
    tools = wide(learner())
    hear(tools, "电脑 " * 12 + "游戏 " * 12)  # both past green: ready to check
    show(card, tools, Listed.READY)
    order = card.words.order
    assert len(order) == 2
    card.words.setFocus()
    QTest.keyClick(card.words, Qt.Key.Key_Down)
    QTest.keyClick(card.words, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert card.words.picked() == order
    shown = [k for k, b in card.picked_bar.buttons.items() if not b.isHidden() and k]
    assert shown == ["check_known", "not_yet"]
    for_picked_in_load(tools, "check_known", ids(order))
    status = tools.vocabulary.status_of_entry
    assert [status(e).status for e in ids(order)] == [WordStatus.KNOWN] * 2


def test_picked_words_stay_picked_as_the_card_is_shown_again(card: LoadCard) -> None:
    tools = wide(learner())
    show(card, tools, Listed.IN_LOAD)
    order = card.words.order
    click(card, 1, Qt.KeyboardModifier.NoModifier)
    click(card, 3, Qt.KeyboardModifier.ShiftModifier)
    hear(tools, "研究")  # a caption: the card is shown again
    show(card, tools, Listed.IN_LOAD)
    assert sorted(card.words.picked()) == sorted(order[1:4])
