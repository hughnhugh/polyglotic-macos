"""A word's dictionaries, tried in turn until one has it (the user,
2026-11-15: "We can also use the various translate functions either target
or translation language / secondary as fallbacks, these should always be
fallback options"; polyglotic-hq 337):

1. its own script's language, where that's learned;
2. the row's language;
3. the window's translation target;
4. its second translation language;
5. every other learned language with a dictionary whose writing fits.

Every one of them with a dictionary here is tried before the card says
"not in the dictionary", and the card says which answered when it wasn't
the row's language. Through the real path: `main.learner_tools`,
`main.tools_beside` and `main.open_pack` on files written from samples, the
real `Lookup` and card. Made-up text; offscreen."""

import statistics
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import FakeDictionaryFile
from tests.ui.test_dictionaries_together import RUSSIAN, dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.adapters.sqlite_dictionary import write_dictionary
from polyglotic_desktop.core.learning.languages import LearningLanguages
from polyglotic_desktop.core.learning.levels import LanguageChoices
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.lookup_card import WIDTH, LookupCard, answered_by
from polyglotic_desktop.ui_next.views.lookup import Lookup, Shows

SPANISH = FakeDictionaryFile(
    [
        EntryRecord("wiktes:casa", "casa", "", "ˈkasa", ("house",), 300),
        EntryRecord("wiktes:ir", "ir", "", "ˈiɾ", ("to go",), 50),
    ],
    {"casa": ["wiktes:casa"], "ir": ["wiktes:ir"]},
    lemmas={"vamos": "ir"},
)
"""A Spanish pack's entries: no "brunch" - ECDICT has it."""


def pack(folder: Path, name: str, language: str, entries: FakeDictionaryFile) -> Path:
    path = folder / f"{name}.sqlite"
    write_dictionary(
        path,
        {"dictionary": name},
        list(entries.by_id.values()),
        entries.forms,
        lemmas=entries.lemmas,
        form_readings=entries.form_readings,
    )
    return path


@pytest.fixture
def tools(qapp: QApplication, tmp_path: Path) -> Iterator[LearningTools]:
    """English main; Chinese, Russian and Spanish learned too - Russian's
    and Spanish's packs opened as a download is."""
    folder = dictionaries(tmp_path / "dictionaries")
    ru, ru_file = main.open_pack(pack(folder, "wiktru-en", "ru", RUSSIAN), "ru")
    es, es_file = main.open_pack(pack(folder, "wiktes-en", "es", SPANISH), "es")
    data = tmp_path / "data"
    found, store = main.learner_tools(folder, True, data, {"ru": ru, "es": es})
    languages = LearningLanguages.of("en", ("zh", "ru", "es"))
    beside = main.tools_beside(found, folder, data, languages)
    found.set_choices(LanguageChoices(), {c: LanguageChoices() for c in languages.all})
    yield found
    for each in (store, *(s for _, s in beside)):
        each.close()
    ru_file.close()
    es_file.close()


def shown(
    tools: LearningTools,
    word: str,
    row: str,
    language: str | None,
    fallbacks: tuple[str, ...] = (),
) -> Lookup:
    lookup = Lookup(tools)
    at = (row.index(word), row.index(word) + len(word))
    lookup.show(word, LookupContext(row), True, at, language, fallbacks)
    return lookup


def test_the_order_is_script_row_target_second_then_other_learned(
    tools: LearningTools,
) -> None:
    # a Russian word in a Spanish row, the window into English, then Chinese
    assert tools.dictionaries_for("руку", "es", ("en",)) == ["ru", "es", "en"]
    # a Latin word in a Spanish row: the row, the target, the second, the rest
    assert tools.dictionaries_for("brunch", "es", ("ru", "en")) == ["es", "ru", "en"]
    assert tools.dictionaries_for("brunch", "es", ()) == ["es", "en"]
    # Chinese's only for a word with Chinese characters
    assert "zh" not in tools.dictionaries_for("brunch", "zh", ("zh", "en"))
    assert tools.dictionaries_for("北京", "en", ("es",)) == ["zh", "en", "es"]


def test_step_1_its_own_scripts_language(tools: LearningTools) -> None:
    lookup = shown(tools, "руку", "vamos руку", "es", ("en",))
    card = lookup.card()
    assert card.shows is Shows.ENTRY and card.basic and card.language == "ru"
    assert card.answered_by == "ru"


def test_step_2_the_rows_language_says_nothing_more(tools: LearningTools) -> None:
    card = shown(tools, "casa", "mi casa", "es", ("en",)).card()
    assert card.shows is Shows.ENTRY and card.language == "es"
    assert card.answered_by == ""


def test_step_3_the_windows_translation_target(tools: LearningTools) -> None:
    """A Latin word the row's language hasn't got: English, the window's
    target, has it - the Latin-script case (Spanish or English?) settled
    by trying both."""
    lookup = shown(tools, "brunch", "vamos al brunch", "es", ("en",))
    card = lookup.card()
    assert card.shows is Shows.ENTRY and not card.basic
    entry = lookup.entry()
    assert entry is not None and entry.entry_id == "ecdict:brunch"
    assert card.answered_by == "en"


def test_step_4_the_second_translation_language(tools: LearningTools) -> None:
    """Russian, the target, hasn't got it; English, the second, has."""
    assert tools.dictionaries_for("brunch", "es", ("ru", "en"))[1:] == ["ru", "en"]
    lookup = shown(tools, "brunch", "vamos al brunch", "es", ("ru", "en"))
    entry = lookup.entry()
    assert entry is not None and entry.entry_id == "ecdict:brunch"
    assert lookup.card().answered_by == "en"


def test_step_5_another_learned_language_whose_writing_fits(
    tools: LearningTools,
) -> None:
    """No translation languages (captions only): English, learned and
    written in Latin letters, still has it."""
    lookup = shown(tools, "brunch", "vamos al brunch", "es")
    entry = lookup.entry()
    assert entry is not None and entry.entry_id == "ecdict:brunch"
    assert lookup.card().answered_by == "en"


def test_none_has_it_every_one_is_tried_then_the_row_says_so(
    tools: LearningTools, monkeypatch: pytest.MonkeyPatch
) -> None:
    tried: list[str | None] = []
    looked = tools.lookup

    def lookup(word: str, language: str | None = None) -> list[DictionaryEntry]:
        tried.append(language)
        return looked(word, language)

    monkeypatch.setattr(tools, "lookup", lookup)
    card = shown(tools, "zzyzx", "vamos zzyzx", "es", ("ru", "en")).card()
    assert tried[:3] == ["es", "ru", "en"]
    assert card.shows is Shows.NOT_FOUND and card.basic and card.language == "es"
    assert card.answered_by == ""


def test_the_card_names_the_dictionary_that_answered(
    tools: LearningTools,
) -> None:
    card = LookupCard(tools)
    try:
        card.model.show(
            "brunch", LookupContext("vamos al brunch"), True, (9, 15), "es", ("en",)
        )
        painted = card._lay_out(card.model.card(), style.px(WIDTH))
        lines = [b.layout.text() for b in painted.blocks]
        assert answered_by("en") == "From the English dictionary"
        assert "From the English dictionary" in lines
        card.model.show("casa", LookupContext("mi casa"), True, (3, 7), "es", ("en",))
        painted = card._lay_out(card.model.card(), style.px(WIDTH))
        assert not any(b.layout.text().startswith("From the") for b in painted.blocks)
    finally:
        card.close()
        card.deleteLater()


def test_a_miss_through_every_step_costs_no_visible_time(
    tools: LearningTools,
) -> None:
    """Every step's dictionary tried for a word none has: a query each,
    about a millisecond in all - far under the card's 30 ms (the samples;
    the shipped files, through four, are measured in 337's report)."""
    tools.of("zh").prepare()
    assert len(tools.dictionaries_for("zzyzx", "es", ("ru", "en"))) == 3
    times = []
    for _ in range(50):
        start = time.perf_counter()
        shown(tools, "zzyzx", "vamos zzyzx", "es", ("ru", "en")).card()
        times.append(time.perf_counter() - start)
    assert statistics.median(times) < 0.010
