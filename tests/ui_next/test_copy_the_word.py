"""The lookup card's Copy (polyglotic-hq 333): a pinned card's word, its
reading and meaning to the clipboard - and nowhere else - with "Copied"
on the button until the next click; Ctrl+C does the same unless a text
field has the keyboard. Real cards, offscreen."""

import logging
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget
from tests.ui_next.test_lookup_view import COMPUTER, CONTEXT, learner
from tests.ui_next.test_say_it import AREA, has, pin

from polyglotic_desktop.core.lexicon.entries import DictionarySense
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.os_words import hotkeys_here as keys
from polyglotic_desktop.ui_next.views.lookup import (
    Card,
    Lookup,
    LookupContext,
    Reading,
    Shows,
    WordAt,
    copy_text,
)
from polyglotic_desktop.ui_next.views.placement import Rect

UNTOUCHED = "what was on the clipboard before"


# -- the text (the view) -----------------------------------------------------------------


def test_a_chinese_word_copies_with_its_other_form_reading_and_meaning() -> None:
    lookup = Lookup(learner())
    lookup.show("电脑", CONTEXT, pinned=True, at=COMPUTER)
    assert copy_text(lookup.card()) == "电脑 電腦\ndiàn nǎo: computer"


def test_an_english_word_copies_its_entry_s_reading_and_meaning() -> None:
    lookup = Lookup(learner(english=True))
    lookup.show("ran", LookupContext("We ran out of time"), pinned=True)
    card = lookup.card()
    lines = copy_text(card).split("\n")
    assert lines[0] == "ran"
    reading = card.readings[0]
    assert lines[1] == f"{reading.reading}: {'; '.join(reading.senses)}"


def test_each_reading_a_line_and_nothing_empty() -> None:
    card = Card(
        "行",
        Shows.ENTRY,
        pinned=True,
        readings=(
            Reading("xíng", (DictionarySense("to walk"), DictionarySense("OK"))),
            Reading("háng", (DictionarySense("row"), DictionarySense("profession"))),
            Reading("", (DictionarySense("a sense with no reading"),)),
            Reading("hàng", ()),
        ),
    )
    assert copy_text(card) == (
        "行\nxíng: to walk; OK\nháng: row; profession\na sense with no reading\nhàng"
    )


# -- the card ----------------------------------------------------------------------------


@pytest.fixture
def card(qapp: QApplication) -> Iterator[LookupCard]:
    QGuiApplication.clipboard().setText(UNTOUCHED)
    made = LookupCard(learner())
    yield made
    made.close_card()
    made.close()
    made.deleteLater()
    qapp.processEvents()


def runs(card: LookupCard) -> list[str]:
    return [run.text for run in card._painted.runs]


def test_a_pinned_card_copies_its_word_and_says_copied(card: LookupCard) -> None:
    pin(card, "电脑")
    assert has(card, "copy") and "Copy" in runs(card)
    assert card.tip("copy") == keys("Copy the word, its reading and meaning (Ctrl+C)")
    card.do("copy")
    assert QGuiApplication.clipboard().text() == "电脑 電腦\ndiàn nǎo: computer"
    assert "✓ Copied" in runs(card) and "Copy" not in runs(card)
    card.do("save")  # any other click: Copy again
    assert "Copy" in runs(card) and "✓ Copied" not in runs(card)


def test_another_word_shows_copy_again(card: LookupCard) -> None:
    pin(card, "电脑")
    card.do("copy")
    pin(card, "电脑")
    assert "Copy" in runs(card)


def test_a_hover_card_has_no_copy(card: LookupCard) -> None:
    card.hover(
        WordAt(
            "电脑",
            LookupContext("我的电脑坏了"),
            (2, 4),
            Rect(900, 600, 40, 30),
            Rect(500, 600, 900, 30),
            AREA,
            (1, 0, 2, 4),
        )
    )
    card._show_pending()
    assert not has(card, "copy")
    assert QGuiApplication.clipboard().text() == UNTOUCHED


def press_copy(target: QWidget) -> bool:
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, "\x03"
    )
    return QApplication.sendEvent(target, event)


def test_ctrl_c_copies_it_unless_a_text_field_has_the_keyboard(
    qapp: QApplication, card: LookupCard, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = QWidget()  # the transcript window, say
    field = QLineEdit(page)
    try:
        pin(card, "电脑")
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: field))
        press_copy(field)  # copying in a search box is the box's
        assert QGuiApplication.clipboard().text() == UNTOUCHED
        monkeypatch.setattr(QApplication, "focusWidget", staticmethod(lambda: page))
        press_copy(page)
        assert QGuiApplication.clipboard().text() == "电脑 電腦\ndiàn nǎo: computer"
        assert "✓ Copied" in runs(card)
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_nothing_copied_is_logged(
    card: LookupCard, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    pin(card, "电脑")
    card.do("copy")
    assert "电脑" not in caplog.text and "computer" not in caplog.text
