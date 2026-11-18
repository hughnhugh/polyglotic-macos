"""Words' Saved sentences (polyglotic-hq 459; the user, 2026-11-14:
"filtering for a given save word or plain text search, matching on both
original / translation texts"): the search over both sides, the
category and saved-word filters, Show more, Move to and Remove. Offscreen,
the sample dictionary, made-up sentences."""

from PySide6.QtCore import QDate, QLocale
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionComboBox
from tests.learning.fakes import Clock
from tests.ui_next.test_words import entry, page, settle, tools, windows_deleted

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.sentences import SentencePart
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.saved_sentences import SHOWN, SentenceRow, found_said
from polyglotic_desktop.ui_next.words_page import WordsPage

__all__ = ["page", "tools", "windows_deleted"]  # the fixtures, shared


def save(tools: LearningTools, original: str, translation: str, category: str = "saved") -> None:  # fmt: skip
    clock = tools.vocabulary._clock  # the made-up learner's: a second on each
    assert isinstance(clock, Clock)
    clock.advance(seconds=1)
    tools.vocabulary.save_sentence(
        (SentencePart(original, translation, (), "Discord"),),
        original,
        translation,
        category,
        "en",
    )


def rows(page: WordsPage) -> list[SentenceRow]:
    card = page.first.sentences
    found = [card.list.itemAt(n).widget() for n in range(card.list.count())]  # type: ignore[union-attr]
    return [r for r in found if isinstance(r, SentenceRow) and not r.isHidden()]


def search(page: WordsPage, text: str) -> None:
    card = page.first.sentences
    card.search.setText(text)
    card._searching.stop()
    card.refresh()
    settle()


def originals(page: WordsPage) -> list[str]:
    return [r.original.text() for r in rows(page)]


def test_none_yet_says_how_to_save_one(page: WordsPage) -> None:
    card = page.first.sentences
    assert card.isVisible() and card.empty.isVisible()
    assert not card.search.isVisible()


def test_saved_sentences_list_newest_first_and_a_search_finds_either_side(
    page: WordsPage, tools: LearningTools
) -> None:
    save(tools, "我的电脑又卡了", "My computer froze again")
    save(tools, "我们去吃饭吧", "Let's go and eat")
    save(tools, "电脑游戏很好玩", "Computer games are fun", "tricky")
    settle()
    assert originals(page) == ["电脑游戏很好玩", "我们去吃饭吧", "我的电脑又卡了"]
    card = page.first.sentences
    assert card.said.text() == "3 saved sentences"
    search(page, "电脑")  # what was said, character by character
    assert originals(page) == ["电脑游戏很好玩", "我的电脑又卡了"]
    assert card.said.text() == "2 of 3 saved sentences"
    search(page, "eat")  # the translation
    assert originals(page) == ["我们去吃饭吧"]
    search(page, "computer froze")  # most of the words
    assert originals(page)[0] == "我的电脑又卡了"


def test_a_category_and_a_saved_word_filter_it(
    page: WordsPage, tools: LearningTools
) -> None:
    save(tools, "我的电脑又卡了", "My computer froze again")
    save(tools, "我们去吃饭吧", "Let's go and eat", "tricky")
    computer = entry(tools, "电脑")
    tools.vocabulary.save(
        computer, "电脑", "電腦", "diàn nǎo", "computer", "saved", LookupContext("")
    )
    settle()
    card = page.first.sentences
    card.category.setCurrentIndex(card.category.findData("tricky"))
    assert originals(page) == ["我们去吃饭吧"]
    card.category.setCurrentIndex(0)
    card.word.setCurrentIndex(card.word.findData(computer))
    assert originals(page) == ["我的电脑又卡了"]


def test_a_few_then_show_more(page: WordsPage, tools: LearningTools) -> None:
    for n in range(SHOWN + 5):
        save(tools, f"第{n}句", f"Sentence {n}")
    settle()
    card = page.first.sentences
    assert len(rows(page)) == SHOWN and card.more.isVisible()
    card.more.click()
    settle()
    assert len(rows(page)) == SHOWN + 5 and not card.more.isVisible()


def test_remove_and_move_to(page: WordsPage, tools: LearningTools) -> None:
    save(tools, "我们去吃饭吧", "Let's go and eat")
    save(tools, "我的电脑又卡了", "My computer froze again")
    settle()
    first = rows(page)[0]
    first.remove.click()
    settle()
    assert originals(page) == ["我们去吃饭吧"]
    assert len(tools.vocabulary.sentences) == 1
    rows(page)[0].move_to.click()
    menu = page.first.sentences.menu
    assert menu is not None
    next(a for a in menu.actions() if a.text() == "Tricky").trigger()
    settle()
    assert tools.vocabulary.sentences[0].category_id == "tricky"
    assert "Tricky" in rows(page)[0].about.text()
    menu.close()


def test_what_the_count_says(qapp: QApplication) -> None:
    assert found_said(0, 1, False) == "1 saved sentence"
    assert found_said(1, 12, True) == "1 of 12 saved sentences"


def test_a_sentence_shows_its_category_speaker_and_day(
    page: WordsPage, tools: LearningTools
) -> None:
    save(tools, "好吃吗", "Is it good?")
    settle()
    about = rows(page)[0].about.text()
    assert about.startswith("Saved · Discord · ")
    saved_on = QDate(2026, 11, 4)  # the made-up learner's clock's day (UTC 09:00)
    short = QLocale().toString(saved_on, QLocale.FormatType.ShortFormat)
    assert about.endswith(short)


def test_a_filter_box_has_room_for_its_widest_choice_as_drawn(
    page: WordsPage,
) -> None:
    """472: Qt sizes a box to its choices' ink but draws them by their
    advance - in Korean ("모든 저장한 단어", Malgun Gothic) 2 px wider, past
    the box's text room. The filters have room for what they draw."""
    card = page.first.sentences
    card.setStyleSheet(style.stylesheet(style.current()))  # the app's, as in the lab
    font = QFont(card.word.font())
    font.setFamilies(["Segoe UI", "Malgun Gothic"])
    font.setPixelSize(13)
    for box in (card.word, card.category):
        box.setFont(font)
        box.addItem("모든 저장한 단어")
        box.resize(box.sizeHint())
        option = QStyleOptionComboBox()
        box.initStyleOption(option)
        room = box.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxEditField,
            box,
        )
        widest = max(
            box.fontMetrics().horizontalAdvance(box.itemText(i))
            for i in range(box.count())
        )
        assert room.width() >= widest, box.objectName()
