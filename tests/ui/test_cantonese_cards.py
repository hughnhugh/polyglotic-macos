"""A Cantonese line's words get Cantonese cards (polyglotic-hq 450, decision
0160; the user, 2026-11-17, DECISIONS #179): Cantonese is a language of
its own with a pack - its words read in Jyutping with Cantonese meanings,
found whole by the pack's word split `han`, learnable on Learning. Chinese's
dictionary is a fallback the card names.

Through the real path: `main.open_pack`, `main.learner_tools` and
`main.tools_beside` on files written from samples, and the real `Lookup`.
Made-up text; offscreen."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import FakeDictionaryFile
from tests.ui.test_dictionaries_together import dictionaries
from tests.ui.test_dictionary_fallbacks import pack

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.languages import (
    LearningLanguages,
    Tier,
    tier_of,
)
from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.views.lookup import Lookup, Shows

CANTONESE = FakeDictionaryFile(
    [
        EntryRecord("canto:1", "係", "", "hai⁶", ("(Cantonese) to be",), 2),
        EntryRecord("canto:2", "佢哋", "", "keoi⁵ dei⁶", ("(pronoun) they",), 120),
        EntryRecord("canto:3", "而家", "", "ji⁴ gaa¹", ("now",), 88),
        EntryRecord("canto:4", "佢", "", "keoi⁵", ("he; she",), 9),
    ],
    {
        "係": ["canto:1"],
        "佢哋": ["canto:2"],
        "渠哋": ["canto:2"],
        "而家": ["canto:3"],
        "佢": ["canto:4"],
    },
)
"""A Cantonese pack's entries, as `tools.dictionaries.packs` writes them."""


def test_cantonese_is_a_basic_language_with_its_own_split() -> None:
    assert tier_of("yue") is Tier.BASIC
    assert "han" in main.pack_reader("0.1.8").splits
    # a card on a Cantonese row offers Cantonese, not Chinese
    assert LearningLanguages.of("en", ("zh",)).asks_about("yue") == "yue"


def tools_with(tmp_path: Path, learned: tuple[str, ...]) -> Iterator[LearningTools]:
    folder = dictionaries(tmp_path / "dictionaries")
    yue, yue_file = main.open_pack(pack(folder, "canto-en", "yue", CANTONESE), "yue")
    data = tmp_path / "data"
    found, store = main.learner_tools(folder, True, data, {"yue": yue})
    languages = LearningLanguages.of("en", learned)
    beside = main.tools_beside(found, folder, data, languages)
    found.set_choices(LanguageChoices(), {c: LanguageChoices() for c in languages.all})
    yield found
    for each in (store, *(s for _, s in beside)):
        each.close()
    yue_file.close()


@pytest.fixture
def tools(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """English main; Chinese learned too; Cantonese's pack here, not learned."""
    yield from tools_with(tmp_path, ("zh",))


@pytest.fixture
def learner(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """English main; Chinese and Cantonese learned, Cantonese's pack here."""
    yield from tools_with(tmp_path, ("zh", "yue"))


def shown(tools: LearningTools, word: str, row: str) -> Lookup:
    lookup = Lookup(tools)
    at = (row.index(word), row.index(word) + len(word))
    lookup.show(word, LookupContext(row), True, at, "yue")
    return lookup


def test_a_cantonese_word_gets_a_cantonese_card(tools: LearningTools) -> None:
    """371: with Chinese learned, 係 had been "xì: to connect" and 佢哋 had
    no entry. The pack opens with its own split: 佢哋 is one word."""
    row = "佢哋而家係"
    assert tools.word_at(row, 1, "yue") == (0, 2)
    card = shown(tools, "佢哋", row).card()
    assert card.shows is Shows.ENTRY and card.basic and card.language == "yue"
    assert [(r.reading, r.senses[0]) for r in card.readings] == [
        ("keoi⁵ dei⁶", "(pronoun) they")
    ]
    assert card.answered_by == ""
    card = shown(tools, "係", row).card()
    assert [r.reading for r in card.readings] == ["hai⁶"]


def test_a_word_the_pack_hasnt_got_is_chinese_dictionarys_and_says_so(
    tools: LearningTools,
) -> None:
    card = shown(tools, "北京", "佢哋喺北京").card()
    assert card.shows is Shows.ENTRY and card.answered_by == "zh"


def test_learned_cantonese_keeps_its_own_learning_data(learner: LearningTools) -> None:
    """A pack language learned has tools of its own (decision 0175): the
    card's word is the learner's, with a status, and the row is counted as
    Cantonese - never as Chinese (`learns`)."""
    lookup = shown(learner, "而家", "佢哋而家")
    card = lookup.card()
    assert card.shows is Shows.ENTRY
    entry = lookup.entry()
    assert entry is not None and entry.entry_id == "canto:3"
    own = learner.of("yue")
    assert own is not learner and own.language == "yue"
    assert own.learns("yue") and not own.learns("zh")
    pack = own.dictionary
    assert isinstance(pack, BasicDictionary)
    assert pack.words("佢哋而家") == [(0, 2), (2, 4)]  # its split: han


def test_links_are_judged_by_cantonese_words_and_their_ranks(
    tools: LearningTools,
) -> None:
    """A Cantonese row's links past what you know are judged by the pack's
    words and ranks (371: a learner of Chinese alone saw 258 of 258 links
    at every level). Not learned, a line alone: "Start links at" moves it."""
    row = "佢哋而家係"
    words = tools.words_in(row, "yue")
    assert [(w.start, w.end, w.entry.entry_id) for w in words] == [
        (0, 2, "canto:2"),
        (2, 4, "canto:3"),
        (4, 5, "canto:1"),
    ]
    knows = tools.knowledge_of("yue")
    assert knows is not None
    # links from the 100th word: 佢哋 (120th) is past it, 而家 and 係 aren't
    known = [row[w.start : w.end] for w in words if knows.of(w.entry, 100).known]
    assert known == ["而家", "係"]
