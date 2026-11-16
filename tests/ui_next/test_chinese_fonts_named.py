"""The learning page's sample and the load card name Chinese fonts, not
language codes (polyglotic-hq 347: the UI lab's design detector found the
sample's text "in zh, a family the interface doesn't use").

`caption_layout.CJK_FAMILIES` is a dict of font lists by script; `list()` of
it gave the families "zh", "zh-hant", "yue", "ja", which no PC has, so the
text fell to whatever face Qt substituted."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.ui_next.caption_layout import CJK_FAMILIES, LATIN_FAMILIES
from polyglotic_desktop.ui_next.learning_page import IntroductionSample
from polyglotic_desktop.ui_next.load_card import LoadCard

MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted(qapp: QApplication) -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication(["test"])
    assert isinstance(app, QApplication)
    return app


def test_the_sample_names_chinese_fonts() -> None:
    sample = IntroductionSample()
    MADE.append(sample)
    assert sample._font().families() == list(CJK_FAMILIES["zh"])
    sample.chinese = False
    assert sample._font().families() == list(LATIN_FAMILIES)


def test_the_load_cards_words_name_chinese_fonts() -> None:
    card = LoadCard()
    MADE.append(card)
    card.chinese = True
    assert card._word_font().families() == list(CJK_FAMILIES["zh"])
    card.chinese = False
    assert card._word_font().families() == list(LATIN_FAMILIES)
