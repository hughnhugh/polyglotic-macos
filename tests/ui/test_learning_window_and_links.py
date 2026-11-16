"""Learning's page offers the learning window and word links, per language
(polyglotic-hq 323): the window's size for the language in use once its
level is a number of words; which words are linked for every language
learned, and where links start while they follow what's known. A choice
is a setting, and the learning tools follow it at once. Offscreen."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import (
    MAX_WINDOW,
    MIN_WINDOW,
    UNLIMITED,
    KnownLine,
    LanguageChoices,
    LinkChoice,
)
from polyglotic_desktop.core.shared import Level
from polyglotic_desktop.ui_next.views.learning import (
    WINDOW_CHOICES,
    Custom,
    cards,
    typed_window,
    window_choice,
)

# -- what each card offers ---------------------------------------------------------------


def lines(code: str) -> KnownLine | None:
    return {"zh": KnownLine.words(1000), "en": KnownLine.words(3000)}.get(code)


def chosen(code: str) -> LanguageChoices:
    return {
        "zh": LanguageChoices(window_size=500, links=LinkChoice.PAST_KNOWN),
        "vi": LanguageChoices(links=LinkChoice.PAST_KNOWN),
    }.get(code, LanguageChoices())


def test_the_window_is_offered_for_the_language_in_use_with_a_level_in_words() -> None:
    languages = LearningLanguages("zh", ("en", "vi"))
    chinese, english, vietnamese = cards(languages, "zh", lines, (), chosen)
    assert chinese.window == 500 and chinese.offers_links_from
    assert english.window is None  # not in use: its window can't be seen yet
    assert english.choices.links is LinkChoice.EVERY and not english.offers_links_from
    assert vietnamese.window is None and vietnamese.key_words_only
    assert not vietnamese.offers_links_from  # nothing ranks its words
    (plain,) = cards(LearningLanguages("zh"), "zh", lines)
    assert plain.window == 1000 and plain.choices == LanguageChoices()  # defaults


def test_a_basic_language_with_its_pack_here_offers_where_links_start() -> None:
    """Its pack ranks its words (decision 0120; polyglotic-hq 338): links
    start at a number of words - no level is kept for it, so not "what you
    know". Without its pack, key words only, as before."""
    languages = LearningLanguages("zh", ("vi",))
    _, here = cards(languages, "zh", lines, ("vi",), chosen)
    assert here.ranked and here.offers_links_from and not here.key_words_only
    assert not here.links_from_line
    _, away = cards(languages, "zh", lines, (), chosen)
    assert away.key_words_only and not away.offers_links_from


@pytest.mark.parametrize(
    "line", [None, KnownLine.picked(Level("hsk-2025", 3))], ids=["unset", "before 323"]
)
def test_a_level_from_before_keeps_its_own_window(line: KnownLine | None) -> None:
    """A level kept from before 323, or none set: the next level is what's
    pointed out, as it always was - no size to choose until the level is
    chosen again, in words."""
    (card,) = cards(LearningLanguages("zh"), "zh", lambda code: line)
    assert card.window is None


# -- the page, in the app -------------------------------------------------------------------


STORES: list[MemorySettingsStore] = []
"""The store of the app `built` made, for what a choice kept."""


@pytest.fixture
def built(qapp: QApplication) -> Iterator[Built]:
    STORES.append(MemorySettingsStore({"learning": "zh", "also_learning": ["vi"]}))
    made = Built(STORES[-1], tools=True)
    yield made
    made.close()
    STORES.clear()


def test_the_window_chosen_on_learning_is_kept_and_followed(built: Built) -> None:
    tools = built.desktop.tools
    assert tools is not None and tools.language == "zh"
    card = built.hub.learning.card("zh")
    assert card is not None and card.window_size is None  # no level set yet
    tools.vocabulary.set_known_words(1000)
    card = built.hub.learning.card("zh")
    assert card is not None and card.window_size is not None
    assert card.window_size.value() == 1000  # until one is chosen
    card.window_size.choose(2000)
    assert STORES[-1].values["language_choices"] == {"zh": {"window": 2000}}
    assert tools.choices.window_size == 2000
    again = built.hub.learning.card("zh")  # shown again from the settings
    assert again is not None and again.window_size is not None
    assert again.window_size.value() == 2000


def test_unlimited_and_a_number_of_ones_own_are_kept_and_followed(built: Built) -> None:
    """Decision 0144: Unlimited is chosen at once; Custom opens a line for a
    number, kept within its bounds; anything that isn't a number leaves the
    window as it was. Each is shown again from the settings."""
    tools = built.desktop.tools
    assert tools is not None
    tools.vocabulary.set_known_words(1000)
    card = built.hub.learning.card("zh")
    assert card is not None and card.window_size is not None
    assert card.window_custom is not None and not card.window_custom.isVisibleTo(card)
    card.window_size.choose(UNLIMITED)
    assert STORES[-1].values["language_choices"] == {"zh": {"window": "unlimited"}}
    assert tools.choices.window_size is UNLIMITED
    again = built.hub.learning.card("zh")
    assert again is not None and again.window_size is not None
    assert again.window_size.value() is UNLIMITED
    assert again.window_custom is not None
    assert (
        not again.window_custom.isVisibleTo(again) and again.window_custom.text() == ""
    )

    again.window_size.choose(Custom.CUSTOM)  # opens the line; nothing chosen yet
    assert again.window_custom.isVisibleTo(again)
    assert tools.choices.window_size is UNLIMITED
    again.window_custom.setText("3,000")
    again.window_custom.editingFinished.emit()
    assert STORES[-1].values["language_choices"] == {"zh": {"window": 3000}}
    assert tools.choices.window_size == 3000
    assert again.window_custom.text() == QLocale().toString(3000)
    again.window_custom.setText("lots")  # not a number: the window stays
    again.window_custom.editingFinished.emit()
    assert tools.choices.window_size == 3000
    assert again.window_custom.text() == QLocale().toString(3000)
    again.window_custom.setText("5")  # under the bounds: the least
    again.window_custom.editingFinished.emit()
    assert tools.choices.window_size == MIN_WINDOW

    again.window_custom.setText("3000")
    again.window_custom.editingFinished.emit()
    shown = built.hub.learning.card("zh")  # a number of one's own: Custom
    assert shown is not None and shown.window_size is not None
    assert shown.window_size.value() is Custom.CUSTOM
    assert shown.window_custom is not None and shown.window_custom.isVisibleTo(shown)
    assert shown.window_custom.text() == QLocale().toString(3000)
    shown.window_size.choose(500)  # a size again: the line goes
    assert (
        not shown.window_custom.isVisibleTo(shown) and tools.choices.window_size == 500
    )


def test_the_window_choices_on_a_card() -> None:
    assert WINDOW_CHOICES == (100, 500, 1000, 2000, UNLIMITED, Custom.CUSTOM)
    assert [window_choice(s) for s in (500, UNLIMITED, 3000, 10)] == [
        500, UNLIMITED, Custom.CUSTOM, Custom.CUSTOM,
    ]  # fmt: skip
    assert typed_window("3,000") == typed_window("3 000") == 3000
    assert typed_window("3.000") == typed_window("3 000") == 3000
    assert typed_window("") is None and typed_window("-5") is None
    assert typed_window("3k") is None and typed_window("٣") is None
    assert typed_window("1") == MIN_WINDOW and typed_window("999999") == MAX_WINDOW


def test_word_links_are_chosen_per_language(built: Built) -> None:
    tools = built.desktop.tools
    assert tools is not None
    tools.vocabulary.set_known_words(1000)
    chinese = built.hub.learning.card("zh")
    assert chinese is not None and chinese.links.value() is LinkChoice.EVERY
    assert chinese.links_from is None  # only while links follow what's known
    chinese.links.choose(LinkChoice.PAST_KNOWN)
    assert tools.choices.links is LinkChoice.PAST_KNOWN
    chinese = built.hub.learning.card("zh")
    assert chinese is not None and chinese.links_from is not None
    assert chinese.links_from.currentData() is None  # "What you know"
    at = chinese.links_from.findData(3000)
    chinese.links_from.setCurrentIndex(at)
    chinese.links_from.activated.emit(at)
    assert STORES[-1].values["language_choices"] == {
        "zh": {"links": "past_known", "links_from": 3000}
    }
    assert tools.choices.links_from == 3000
    # another language's choice is its own, and says what it can do
    vietnamese = built.hub.learning.card("vi")
    assert vietnamese is not None and vietnamese.window_size is None
    vietnamese.links.choose(LinkChoice.OFF)
    kept = STORES[-1].values["language_choices"]
    assert isinstance(kept, dict) and kept["vi"] == {"links": "off"}
    assert kept["zh"] == {"links": "past_known", "links_from": 3000}
    assert tools.choices.links is LinkChoice.PAST_KNOWN  # Chinese's, untouched


def test_a_custom_window_typed_in_full_width_digits() -> None:
    """A Chinese or Japanese keyboard in full-width mode types １２００ and
    ２，０００: the number, as typed (361: it was ignored)."""
    assert typed_window("１２００") == 1200
    assert typed_window("２，０００") == 2000
    assert typed_window("３　０００") == 3000  # an ideographic space
    assert typed_window("٣") is None  # other scripts' digits still not
