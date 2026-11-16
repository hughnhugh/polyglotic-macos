"""The Learning page (polyglotic-hq 262; 248's IA.md section 3; the user's
F19, F29, F30): a card per language - its tier, its level, what it can do
now - Learn another language, Word introductions with the three choices
and what each does. Offscreen."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.languages import LearningLanguages, Tier
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.ui_next.learning_page import (
    LearningPage,
    introductions_line,
    learnable,
)
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.learning import LanguageCard, cards, offered

HSK4 = KnownLine("hsk-2025", 4)
MADE: list[LearningPage] = []
"""The pages a test made, deleted at its end (`deleted`)."""


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each page deleted when its test ends, not at the interpreter's exit,
    where one left over crashes the run after every test passed (261's
    finding; here too: the run exited 127)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def made() -> LearningPage:
    page = LearningPage()
    MADE.append(page)
    return page


def levels(code: str) -> KnownLine | None:
    return {"zh": HSK4}.get(code)


def test_the_language_in_use_can_change_its_level_now() -> None:
    (chinese,) = cards(LearningLanguages("zh"), ("zh",), levels)
    assert chinese.main and chinese.running and chinese.can_change_level
    assert not chinese.can_switch
    assert chinese.level is not None and chinese.level.level == "4"


def test_every_full_language_learned_is_open_each_with_its_level() -> None:
    """306 (DECISIONS #110): Chinese and English both open - each its own
    level, changed at once; the other can be made the main one."""
    chinese, english = cards(LearningLanguages("zh", ("en",)), ("zh", "en"), levels)
    assert chinese.can_change_level and english.can_change_level
    assert english.can_switch and not chinese.can_switch  # "Make English main"


def test_a_full_language_not_open_has_no_level_to_change_yet() -> None:
    """Only if it couldn't open (306: `main` opens one at once as it's
    added): its level as kept, nothing to change."""
    _, english = cards(LearningLanguages("zh", ("en",)), ("zh",), levels)
    assert not english.can_change_level and english.can_switch
    assert english.level is not None and not english.level.picked  # none kept


def test_basic_and_no_dictionary_cards_say_what_they_can_do() -> None:
    languages = LearningLanguages("zh", ("ja", "th"))
    _, japanese, thai = cards(languages, ("zh",), levels, ("ja",))
    assert (japanese.tier, japanese.pack_here, japanese.level) == (
        Tier.BASIC,
        True,
        None,
    )
    assert (thai.tier, thai.level, thai.can_switch) == (Tier.NONE, None, False)


def test_a_basic_language_with_no_pack_in_the_list_says_there_is_none_yet(
    qapp: QApplication,
) -> None:
    """329's QA (K11): Vietnamese's card said "lookups in Vietnamese
    captions once it's downloaded", but no Vietnamese pack is published or
    built. With the list held and nothing in it for the language, the card
    says there's no dictionary yet and what works without one, and its row
    "isn't ready" with Retry - a pack published since is found (330's
    addendum); one whose pack is offered keeps today's words (330)."""
    from polyglotic_desktop.ui_next.views.learning import PackLine

    languages = LearningLanguages("zh", ("vi", "ru"))
    lines = {"vi": PackLine(not_offered=True), "ru": PackLine(size=13_000_000)}
    _, vietnamese, russian = cards(
        languages, ("zh",), levels, pack_line=lines.__getitem__
    )
    assert vietnamese.no_pack_yet and not russian.no_pack_yet
    here = cards(languages, ("zh",), levels, ("vi",), pack_line=lines.__getitem__)
    assert not here[1].no_pack_yet  # on this PC (the installer's): it works
    page = made()
    page.show_learning(
        languages,
        cards(languages, ("zh",), levels, pack_line=lines.__getitem__),
        WordIntroductions.A_FEW,
        "zh",
    )
    shown = {card.code: card for card in page.cards}
    gives = shown["vi"].gives.text()
    assert gives.startswith("Captions and translation work without one,")
    assert "once it's downloaded" not in gives
    row = shown["vi"].pack
    assert row is not None and not row.buttons["retry"].isHidden()
    assert row.said.text() == "Its dictionary isn't ready to download yet."
    tier = [w.text() for w in shown["vi"].findChildren(QLabel)]
    assert "No dictionary yet" in tier and "Basic dictionary" not in tier
    assert "once it's downloaded" in shown["ru"].gives.text()  # offered: as before
    assert shown["ru"].pack is not None
    # the list comes to offer it: the card is worded again
    lines["vi"] = PackLine(size=9_000_000)
    page.show_learning(
        languages,
        cards(languages, ("zh",), levels, pack_line=lines.__getitem__),
        WordIntroductions.A_FEW,
        "zh",
    )
    vietnamese_now = page.card("vi")
    assert vietnamese_now is not None and vietnamese_now.pack is not None
    assert "once it's downloaded" in vietnamese_now.gives.text()


def test_with_no_list_held_a_basic_card_promises_no_download(
    qapp: QApplication,
) -> None:
    """The release may come before any list is published (330's addendum):
    with none read yet, or one that couldn't be read, a basic language's
    card says what's true either way - and its row, that it's checking or
    couldn't check, never "isn't ready"."""
    from polyglotic_desktop.ui_next.views.learning import PackKnown, PackLine

    languages = LearningLanguages("zh", ("ru", "ja"))
    lines = {"ru": PackLine(), "ja": PackLine(unlisted=True)}
    made_cards = cards(languages, ("zh",), levels, pack_line=lines.__getitem__)
    assert [c.pack_known for c in made_cards] == [
        None,
        PackKnown.UNKNOWN,
        PackKnown.UNKNOWN,
    ]
    page = made()
    page.show_learning(languages, made_cards, WordIntroductions.A_FEW, "zh")
    russian, japanese = page.card("ru"), page.card("ja")
    assert russian is not None and japanese is not None
    for card, name in ((russian, "Russian"), (japanese, "Japanese")):
        assert card.gives.text() == (
            "A basic dictionary from open data (meanings not checked by a person), "
            f"if one is ready: lookups in {name} captions once it's on this"
            f" {pc_or_mac('PC', 'Mac')}. "
            "Captions and translation work either way."
        )
    assert russian.pack is not None and japanese.pack is not None
    assert russian.pack.said.text() == "Checking the list of dictionaries."
    assert japanese.pack.said.text() == "The list of dictionaries couldn't be checked."
    assert not japanese.pack.buttons["retry"].isHidden()


def test_learn_another_says_only_what_the_app_knows_of_a_pack(
    qapp: QApplication,
) -> None:
    """ "Learn another language" said "lookups ... once it's downloaded" for
    every basic language, list or not (330's addendum): from the list held,
    none to be had says so ("No dictionary yet"), one offered keeps today's
    words, and with nothing known it promises nothing either way."""
    from polyglotic_desktop.ui_next.views.learning import PackLine

    lines = {"vi": PackLine(not_offered=True), "ru": PackLine(size=13_000_000)}
    page = made()
    page.pack_line = lambda code: lines.get(code)
    languages = LearningLanguages("zh")
    page.show_learning(
        languages, cards(languages, ("zh",), levels), WordIntroductions.A_FEW, "zh"
    )

    def chosen(code: str) -> tuple[str, str]:
        at = page.choices.findData(code)
        page.choices.setCurrentIndex(at)
        return page.choices.itemText(at), page.chosen_gives.text()

    assert chosen("vi") == (
        "Vietnamese - No dictionary yet",
        (
            "There's no Vietnamese dictionary to download yet. Captions and "
            "translation work, and a word you look up says what it is in that "
            "line's translation."
        ),
    )
    label, gives = chosen("ru")
    assert label == "Russian - Basic dictionary" and "once it's downloaded" in gives
    label, gives = chosen("ja")  # nothing known of Japanese's
    assert label == "Japanese - Basic dictionary"
    assert gives == (
        "A basic dictionary from open data (meanings not checked by a person), if "
        "one is ready: its card offers it once you add Japanese. Captions and "
        "translation work either way."
    )
    # a list (or a 404) comes with none for Japanese: said, the choice kept
    lines["ja"] = PackLine(not_offered=True)
    page.show_learning(
        languages, cards(languages, ("zh",), levels), WordIntroductions.A_FEW, "zh"
    )
    assert page.choices.currentData() == "ja"
    assert page.choices.currentText() == "Japanese - No dictionary yet"
    assert page.chosen_gives.text().startswith("There's no Japanese dictionary")


def test_learn_another_offers_those_not_learned_in_the_order_given() -> None:
    """No tier first (polyglotic-hq 293: Chinese and English on top made the
    app look as if it were only for them) - each names its tier instead."""
    codes = ["fr", "en", "zh", "yue", "th", "ja", "es", "fr"]
    assert offered(LearningLanguages("zh"), codes) == [
        "fr",
        "en",
        "yue",
        "th",
        "ja",
        "es",
    ]


def test_every_caption_language_can_be_learned_once(qapp: QApplication) -> None:
    found = learnable()
    assert "zh" in found and "zh-hant" not in found and "yue" in found
    assert len(found) == len(set(found)) == 23
    assert found[:3] == ["ar", "yue", "zh"]  # by name: Arabic, Cantonese, Chinese


@pytest.fixture
def page(qapp: QApplication) -> LearningPage:
    page = made()
    languages = LearningLanguages("zh", ("ja",))
    page.show_learning(
        languages,
        cards(languages, ("zh",), levels),
        WordIntroductions.A_FEW,
        "zh",
    )
    return page


def test_the_cards_say_the_tier_and_the_level(page: LearningPage) -> None:
    assert [c.code for c in page.cards] == ["zh", "ja"]
    chinese, japanese = page.cards
    assert chinese.change_level is not None and chinese.stop is None
    assert japanese.change_level is None and japanese.stop is not None
    assert page.choices.findData("zh") == page.choices.findData("ja") == -1
    assert page.choices.itemData(0) == "ar"  # by name, none pinned (293)
    assert page.choices.itemText(page.choices.findData("en")) == (
        "English - Full dictionary"  # each says its tier instead
    )


def test_learning_another_and_stopping_one_ask_for_the_list(
    page: LearningPage,
) -> None:
    wanted: list[LearningLanguages] = []
    page.languages_wanted.connect(wanted.append)
    page.choices.setCurrentIndex(page.choices.findData("th"))
    assert "no lookups" in page.chosen_gives.text()  # said before it's added
    page.add.click()
    japanese = page.card("ja")
    assert japanese is not None and japanese.stop is not None
    japanese.stop.click()
    assert wanted == [LearningLanguages("zh", ("ja", "th")), LearningLanguages("zh")]


def test_a_double_click_on_learn_it_adds_one_language(page: LearningPage) -> None:
    """Learn it's list moves on to the next language once one is added, so
    a double-click's second click added that one too - English, then
    Japanese (269). The page is told the new list at once, as `main` does."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    def apply(languages: LearningLanguages) -> None:
        page.show_learning(
            languages, cards(languages, ("zh",), levels), WordIntroductions.A_FEW, "zh"
        )

    wanted: list[LearningLanguages] = []
    page.languages_wanted.connect(wanted.append)
    page.languages_wanted.connect(apply)
    page.choices.setCurrentIndex(page.choices.findData("en"))
    page.add.click()
    page.add.click()  # the second click of a double-click, the mouse not moved
    assert wanted == [LearningLanguages("zh", ("ja", "en"))]
    # once added, none is chosen (293): Learn it waits for the next choice
    assert page.choices.currentIndex() == -1 and not page.add.isEnabled()
    page.choices.setCurrentIndex(page.choices.findData("fr"))
    QTest.keyClick(page.add, Qt.Key.Key_Space)  # a keyboard has no double-click
    assert len(wanted) == 2


def test_word_introductions_are_chosen_and_explained(page: LearningPage) -> None:
    chosen: list[object] = []
    page.introductions_chosen.connect(chosen.append)
    assert page.introductions.value() is WordIntroductions.A_FEW
    page.introductions.choose(WordIntroductions.OFF)
    assert chosen == [WordIntroductions.OFF]
    off = introductions_line(WordIntroductions.OFF)
    assert page.introductions_said.text() == off
    assert page.sample.choice is WordIntroductions.OFF


def test_with_nothing_learned_it_says_so(qapp: QApplication) -> None:
    page = made()
    page.show_learning(LearningLanguages(), (), WordIntroductions.A_FEW)
    assert page.cards == [] and not page.none_yet.isHidden()
    assert page.choices.itemData(0) == "ar"  # by name: Arabic (293)
    assert page.choices.currentIndex() == -1  # none suggested: "Choose a language"
    assert not page.add.isEnabled()


def test_a_card_has_its_parent_before_it_shows(qapp: QApplication) -> None:
    page = made()
    card = LanguageCard("zh", Tier.FULL, main=True, running=True)
    page.show_learning(LearningLanguages("zh"), (card,), WordIntroductions.EVERY)
    assert all(c.parent() is not None for c in page.cards)


def test_nothing_opens_as_a_window_of_its_own_while_the_page_is_built(
    qapp: QApplication,
) -> None:
    """ "Delete learning data…" follows Account's action from the first; shown
    with no parent it opened as a window until its card took it - 120 ms of
    the start with real windows (polyglotic-hq 314)."""

    class Shown(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.windows: list[str] = []

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            if (
                event.type() == QEvent.Type.Show
                and isinstance(watched, QWidget)
                and watched.isWindow()
            ):
                self.windows.append(watched.objectName())
            return False

    shown = Shown()
    action = QAction("Delete learning data…", qapp)
    action.setObjectName("delete")
    qapp.installEventFilter(shown)
    try:
        page = LearningPage(action)
        MADE.append(page)
    finally:
        qapp.removeEventFilter(shown)

    assert shown.windows == []
    button = page.findChild(QPushButton, "learning.delete")
    assert button is not None and not button.isHidden()  # shows with its page


def test_the_same_again_rebuilds_nothing(page: LearningPage) -> None:
    """`main` shows the page again on any change of setting: the cards stay
    as they are unless something they show changed."""
    before = list(page.cards)
    languages = LearningLanguages("zh", ("ja",))
    shown = cards(languages, ("zh",), levels)
    page.show_learning(languages, shown, WordIntroductions.A_FEW, "zh")
    assert page.cards == before
    page.show_learning(languages, shown, WordIntroductions.EVERY, "zh")
    assert page.introductions.value() is WordIntroductions.EVERY


def test_each_open_language_asks_for_its_own_level(qapp: QApplication) -> None:
    """306: with Chinese and English both open, each card's Change your
    level names its language, and English's switch makes it the main one -
    not "instead": both stay open."""
    page = made()
    languages = LearningLanguages("zh", ("en",))
    page.show_learning(
        languages,
        cards(languages, ("zh", "en"), levels),
        WordIntroductions.A_FEW,
        "zh",
    )
    asked: list[str] = []
    page.change_level_wanted.connect(asked.append)
    chinese, english = page.card("zh"), page.card("en")
    assert chinese is not None and chinese.change_level is not None
    assert english is not None and english.change_level is not None
    english.change_level.click()
    chinese.change_level.click()
    assert asked == ["en", "zh"]
    assert english.switch is not None and chinese.switch is None
    assert english.switch.text() == "Make English your main language"
    wanted: list[LearningLanguages] = []
    page.languages_wanted.connect(wanted.append)
    english.switch.click()
    assert wanted == [LearningLanguages("en", ("zh",))]


# -- a pack language that keeps learning data (decision 0175; 391) -----------


def test_an_open_pack_language_has_a_level_to_change_like_a_full_one() -> None:
    """Japanese learned with its pack here: its learning data is open, so
    its card has the level (a number of words), "Change your level" and
    quick marks, and links can start at what the learner knows."""
    from polyglotic_desktop.core.learning.first_known import QuickMarks

    def lines(code: str) -> KnownLine | None:
        return {"zh": HSK4, "ja": KnownLine.words(2000)}.get(code)

    languages = LearningLanguages("zh", ("ja", "ru"))
    _, japanese, russian = cards(
        languages,
        ("zh", "ja"),
        lines,
        ("ja",),
        quick_of=lambda _: (QuickMarks(), 0),
    )
    assert japanese.tier is Tier.BASIC and japanese.pack_here
    assert japanese.running and japanese.can_change_level
    assert japanese.level is not None and japanese.level.words == 2000
    assert japanese.in_words and japanese.window is not None
    assert japanese.links_from_line and japanese.quick is not None
    assert not japanese.can_switch  # the main language is a full one's
    # Russian's pack isn't here: nothing kept yet, as before
    assert (russian.level, russian.quick, russian.can_change_level) == (
        None,
        None,
        False,
    )
    assert not russian.links_from_line


def test_an_open_pack_language_with_no_line_yet_says_not_set(
    qapp: QApplication,
) -> None:
    page = made()
    languages = LearningLanguages("zh", ("ja",))
    shown = cards(languages, ("zh", "ja"), levels, ("ja",))
    page.show_learning(languages, shown, WordIntroductions.OFF, "zh")
    card = next(c for c in page.cards if c.code == "ja")
    assert card.change_level is not None  # "about how many words do you know?"
    level = card.findChild(QLabel, "learning.ja.level")
    assert level is not None and level.text().startswith("Not set yet")
    assert "the words you hear and save" in card.gives.text()
    assert "come later" not in card.gives.text()


def test_learn_another_says_checking_while_an_old_list_is_checked(
    qapp: QApplication,
) -> None:
    """425 (preview 2): from the list an earlier run kept, "Learn another
    language" named a language published since "No dictionary yet". While
    that list is checked again it says so instead - its tier as it is - and
    once the list comes, what it offers."""
    from polyglotic_desktop.ui_next.views.learning import PackLine

    lines = {"de": PackLine(checking=True)}
    page = made()
    page.pack_line = lambda code: lines.get(code)
    languages = LearningLanguages("zh")
    page.show_learning(
        languages, cards(languages, ("zh",), levels), WordIntroductions.A_FEW, "zh"
    )
    at = page.choices.findData("de")
    page.choices.setCurrentIndex(at)
    assert page.choices.itemText(at) == "German - Basic dictionary"
    assert page.chosen_gives.text() == "Checking the list of dictionaries."
    lines["de"] = PackLine(size=13_000_000)  # the list came: offered
    page.show_learning(
        languages, cards(languages, ("zh",), levels), WordIntroductions.A_FEW, "zh"
    )
    assert page.choices.currentText() == "German - Basic dictionary"
    assert "once it's downloaded" in page.chosen_gives.text()


def test_a_full_dictionarys_recorded_words_are_said_on_its_card(
    qapp: QApplication,
) -> None:
    """CC-CEDICT's commonest words recorded on this PC (decision 0197): its
    card says so, with their size, and who said them on hover - only a full
    language's (a basic one's say it on its pack's line), only with a file."""
    languages = LearningLanguages("zh", ("en", "ja"))

    def recorded(code: str) -> tuple[int, str]:
        return {"zh": (30_512_640, "Chatterbox Multilingual zh-cmn; MIT")}.get(
            code, (0, "")
        )

    chinese, english, japanese = cards(languages, ("zh",), levels, recorded_of=recorded)
    assert chinese.recorded_size == 30_512_640 and "MIT" in chinese.recorded_credits
    assert english.recorded_size == 0 and japanese.recorded_size == 0
    page = made()
    page.show_learning(
        languages,
        cards(languages, ("zh",), levels, recorded_of=recorded),
        WordIntroductions.A_FEW,
        "zh",
    )
    shown = {card.code: card for card in page.cards}
    said = shown["zh"].recorded
    assert said is not None
    assert said.text() == "Its commonest words are recorded (30.5 MB)."
    assert "Chatterbox" in said.toolTip()
    assert shown["en"].recorded is None and shown["ja"].recorded is None
