"""Several words picked at once in Words' lists (polyglotic-hq 342; the
user, 2026-11-15: "Should be a faster way to multiselect known words ...
yes shift clicking range"): Shift-click picks every row between, Ctrl-click
adds or takes one away, the keyboard does both, and the bar above the list
does an action to them all. Made-up learning, offscreen."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import tools_for

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryId, Level, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.word_table import Column, WordTable
from polyglotic_desktop.ui_next.words_page import LanguageWords, WordsPage

WORDS = ("电脑", "足球", "研究", "生命", "起源", "游戏")


@pytest.fixture(autouse=True)
def windows_deleted(qapp: QApplication) -> Iterator[None]:
    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def settle() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


@pytest.fixture
def tools() -> LearningTools:
    tools = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    tools.vocabulary.set_level(Level("hsk-2025", 0))  # every word new
    for n in range(3):
        tools.vocabulary.caption_finished(
            f"c{n}", tools.words_in("".join(WORDS)), False
        )
    return tools


@pytest.fixture
def words(qapp: QApplication, tools: LearningTools) -> LanguageWords:
    page = WordsPage(tools, None)
    tools.changed.connect(page.learning_changed)
    page.resize(900, 900)
    page.show()
    settle()
    return page.first


def entry(tools: LearningTools, word: str) -> EntryId:
    return tools.lookup(word)[0].entry_id


def click(table: WordTable, row: int, held: Qt.KeyboardModifier) -> None:
    column = table.words.columns.index(Column.MEANING)
    cell = table.visualRect(table.words.index(row, column))
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, held, cell.center())
    settle()


def shown(table: WordTable) -> list[EntryId]:
    return [item.entry_id for item in table.words.items]


def test_shift_click_picks_the_rows_between_without_doing_their_action(
    words: LanguageWords,
) -> None:
    table = words.words
    looked_up: list[str] = []
    table.acted.connect(lambda column, entry, _cell: looked_up.append(entry))
    assert len(shown(table)) >= 5
    click(table, 1, Qt.KeyboardModifier.NoModifier)  # one row: its lookup
    assert len(looked_up) == 1 and words.words_bar.isHidden()
    click(table, 4, Qt.KeyboardModifier.ShiftModifier)
    assert len(looked_up) == 1  # Shift picks, never looks up
    assert table.picked_entries() == shown(table)[1:5]
    assert not words.words_bar.isHidden()
    assert "4 words picked" in words.words_bar.count.text()
    click(table, 2, Qt.KeyboardModifier.ControlModifier)  # Ctrl takes one away
    assert table.picked_entries() == [shown(table)[i] for i in (1, 3, 4)]
    assert table.picked(1) and not table.picked(2)


def test_i_know_these_marks_every_word_picked_known(
    words: LanguageWords, tools: LearningTools
) -> None:
    table = words.words
    rows = shown(table)
    click(table, 0, Qt.KeyboardModifier.NoModifier)
    click(table, 2, Qt.KeyboardModifier.ShiftModifier)
    changes: list[object] = []
    tools.vocabulary.subscribe(changes.append)
    words.words_bar.buttons["known"].click()
    settle()
    status = tools.vocabulary.status_of_entry
    assert [status(e).status for e in rows[:3]] == [WordStatus.KNOWN] * 3
    assert status(rows[3]).status is WordStatus.NEW
    assert table.picked_entries() == [] and words.words_bar.isHidden()
    # each sent as the learner's own, the views told once
    from polyglotic_desktop.core.learning.vocabulary import Changed, VocabularyChanged
    from polyglotic_desktop.core.shared import WordStatusChanged

    assert sum(isinstance(c, WordStatusChanged) for c in changes) == 3
    assert changes.count(VocabularyChanged(Changed.STATUSES)) == 1


def test_the_keyboard_picks_too(words: LanguageWords) -> None:
    table = words.hearing
    rows = shown(table)
    assert len(rows) >= 3
    table.setFocus()
    table.setCurrentIndex(table.words.index(0, 0))
    QTest.keyClick(table, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClick(table, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert table.picked_entries() == rows[:3]
    QTest.keyClick(table, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
    assert table.picked_entries() == rows[:2]  # Ctrl+Space let the third go
    QTest.keyClick(table, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert table.picked_entries() == rows
    QTest.keyClick(table, Qt.Key.Key_Escape)
    assert table.picked_entries() == []


def test_words_you_keep_hearing_go_into_the_deck_together(
    words: LanguageWords, tools: LearningTools
) -> None:
    table = words.hearing
    rows = shown(table)
    click(table, 0, Qt.KeyboardModifier.NoModifier)
    click(table, 1, Qt.KeyboardModifier.ControlModifier)
    words.hearing_bar.buttons["deck"].click()
    settle()
    status = tools.vocabulary.status_of_entry
    assert [status(e).status for e in rows[:2]] == [WordStatus.LEARNING] * 2
    assert rows[0] not in shown(table)  # in the deck: no longer new


def test_saved_words_move_and_go_together_after_asking(
    words: LanguageWords, tools: LearningTools
) -> None:
    vocabulary = tools.vocabulary
    saved = [entry(tools, w) for w in WORDS[:3]]
    for word, entry_id in zip(WORDS, saved, strict=False):
        vocabulary.save(
            entry_id, word, word, "", "", vocabulary.categories[0].id,
            LookupContext(word),
        )  # fmt: skip
    settle()
    words._show_all_saved()
    table = words.saved
    assert sorted(shown(table)) == sorted(saved)
    table.selectAll()
    tricky = vocabulary.categories[1]
    words.saved_bar.buttons["move"].click()
    menu = words.menu
    action = next(a for a in menu.actions() if a.text() == tricky.name)
    action.trigger()
    settle()
    assert {vocabulary.saved_word(e).category_id for e in saved} == {tricky.id}  # type: ignore[union-attr]
    asked: list[int] = []

    def cancel(n: int) -> bool:
        asked.append(n)
        return False

    words.ask_remove = cancel
    table.selectAll()
    words.saved_bar.buttons["remove"].click()
    assert asked == [3] and len(vocabulary.saved_words) == 3
    words.ask_remove = lambda n: True
    words.saved_bar.buttons["remove"].click()
    settle()
    assert vocabulary.saved_words == []


def test_one_row_clicked_is_not_shaded(words: LanguageWords) -> None:
    table = words.words
    click(table, 0, Qt.KeyboardModifier.NoModifier)
    assert not table.picked(0)


def test_words_picked_stay_picked_as_the_list_is_shown_again(
    words: LanguageWords, tools: LearningTools
) -> None:
    """Captions coming in show the list again every few seconds: what the
    learner picked mustn't go with it."""
    table = words.words
    rows = shown(table)
    click(table, 1, Qt.KeyboardModifier.NoModifier)
    click(table, 3, Qt.KeyboardModifier.ShiftModifier)
    tools.vocabulary.caption_finished("again", tools.words_in("电脑北京"), False)
    words.refresh()
    settle()
    assert sorted(table.picked_entries()) == sorted(rows[1:4])  # wherever they are
    assert not words.words_bar.isHidden()
