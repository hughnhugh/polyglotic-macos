"""A pack language learned keeps learning data of its own (polyglotic-hq
391, DECISIONS #184, decision 0175; the user, 2026-11-16: "can we make save
features for each dictionary too. I want them all to be full
dictionaries"): Spanish learned with its pack here, a word on a Spanish
line is looked up, given a status and saved in Spanish's own learning data
file - as Chinese's and English's are in theirs. Not learned, it is a
lookup only, as before. Made-up text, a fake pack; offscreen."""

from pathlib import Path
from typing import Self

from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import FakeDictionaryFile, english_sample
from tests.lexicon.test_basic import SPANISH, FakeSplit, record
from tests.ui.fakes import tools_for
from tests.ui.test_check_install import sample_dictionaries

from polyglotic_desktop import main
from polyglotic_desktop.core.learning.languages import (
    LearningLanguages,
    packs_beside,
)
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import ENGLISH_FREQUENCY
from polyglotic_desktop.core.shared import EntryId, WordStatus
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui_next.views.lookup import Lookup, Shows

CASA = EntryId("wiktes:casa")
LINE = LookupContext("vengo a casa", "I come home")


def spanish_pack() -> BasicDictionary:
    return BasicDictionary(SPANISH, FakeSplit(), "es")


def english(basic: dict[str, BasicDictionary]) -> LearningTools:
    """English's tools, the main language's, with the lookups' packs."""
    tools = tools_for(EnglishDictionary(english_sample()), ENGLISH_FREQUENCY.id)
    tools.basic = basic
    return tools


class Opened:
    """English's tools with Spanish's opened beside them over `data`, as
    `main` opens them; closed at the end."""

    def __init__(self, data: Path, basic: dict[str, BasicDictionary]) -> None:
        self.tools = english(basic)
        self.spanish, self.store = main.pack_learner_tools("es", data, basic)
        self.tools.learn_beside(self.spanish)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.store.close()


# -- which pack languages open -----------------------------------------------------------


def test_a_pack_language_opens_once_it_is_learned_and_its_pack_is_here() -> None:
    languages = LearningLanguages("en", ("es", "ru", "zh", "th"))
    assert packs_beside(languages, {"es", "ja"}) == ("es",)  # ja: not learned
    assert packs_beside(languages, {"ru", "es"}) == ("es", "ru")  # their order
    assert packs_beside(languages, ()) == ()  # ru's pack isn't here yet
    assert packs_beside(LearningLanguages(), {"es"}) == ()


def test_each_language_has_its_own_learning_data_file(tmp_path: Path) -> None:
    assert main.learning_file(tmp_path, "zh").name == "learning.sqlite"
    assert main.learning_file(tmp_path, "en").name == "learning-en.sqlite"
    assert main.learning_file(tmp_path, "es").name == "learning-es.sqlite"


def test_main_opens_a_learned_pack_languages_learning_data_beside_the_others(
    qapp: QApplication, tmp_path: Path
) -> None:
    folder = sample_dictionaries(tmp_path / "dictionaries")
    data = tmp_path / "data"
    basic = {"es": spanish_pack(), "ja": spanish_pack()}
    tools, store = main.learner_tools(folder, True, data, basic)
    languages = LearningLanguages("en", ("es", "ru"))  # ru: no pack here yet
    beside = main.tools_beside(tools, folder, data, languages)
    try:
        assert list(tools.also) == ["es"] and len(beside) == 1
        assert (data / "learning-es.sqlite").exists()
        assert not (data / "learning-ru.sqlite").exists()
        assert not (data / "learning-ja.sqlite").exists()  # not learned
        assert tools.of("es").language == "es"
        # opened once: asked again, nothing more
        assert main.tools_beside(tools, folder, data, languages) == []
    finally:
        store.close()
        for _, other in beside:
            other.close()


# -- lookups: learned or not --------------------------------------------------------------


def test_a_pack_language_not_learned_is_a_lookup_only(qapp: QApplication) -> None:
    tools = english({"es": spanish_pack()})
    assert tools.is_basic("es")
    lookup = Lookup(tools)
    lookup.show("casa", LINE, pinned=True, language="es")
    card = lookup.card()
    assert card.shows is Shows.ENTRY and card.basic
    assert card.status is None and not card.actions
    assert lookup.entry() is None and lookup.save_to("x") is None
    assert tools.vocabulary.lookups(CASA).pinned == 0  # nothing kept


def test_a_learned_pack_languages_word_has_a_status_and_the_actions(
    qapp: QApplication, tmp_path: Path
) -> None:
    with Opened(tmp_path, {"es": spanish_pack()}) as opened:
        tools, spanish = opened.tools, opened.spanish
        assert not tools.is_basic("es") and tools.of("es") is spanish
        lookup = Lookup(tools)
        lookup.show("casa", LINE, pinned=True, language="es")
        card = lookup.card()
        assert card.shows is Shows.ENTRY
        assert card.basic  # still marked: a pack's meanings
        assert card.language == "es"
        # casa is within the line the learner is assumed to know: one click
        # alone keeps it known (#752, DECISIONS #187)
        assert card.status is WordStatus.KNOWN and card.actions
        assert [c.name for c in card.categories]  # somewhere to save it
        assert card.context == LINE and card.found_at is None
        # the lookup is kept in Spanish's data, not English's
        assert spanish.vocabulary.lookups(CASA).pinned == 1
        assert tools.vocabulary.lookups(CASA).pinned == 0
        # on hover: its status, no actions
        lookup.show("casa", LINE, pinned=False, language="es")
        hovered = lookup.card()
        assert hovered.status is WordStatus.KNOWN and not hovered.actions


def test_a_pack_word_is_saved_in_its_own_languages_learning_data(
    qapp: QApplication, tmp_path: Path
) -> None:
    basic = {"es": spanish_pack()}
    with Opened(tmp_path, basic) as opened:
        tools, spanish = opened.tools, opened.spanish
        lookup = Lookup(tools)
        lookup.show("casa", LINE, pinned=True, language="es")
        category = spanish.vocabulary.categories[0]
        assert lookup.save_to(category.id) is not None
        saved = spanish.vocabulary.saved_word(CASA)
        assert saved is not None
        assert (saved.headword, saved.meaning) == ("casa", "house")
        assert saved.source_sentence == "vengo a casa"
        assert tools.vocabulary.saved_word(CASA) is None  # not English's
        assert lookup.card().saved_in == category
        # known already (assumed by the line, #752): Known turns it new, again known
        assert lookup.known() is not None
        assert lookup.card().status is WordStatus.NEW
        assert lookup.known() is not None
        assert lookup.card().status is WordStatus.KNOWN
        assert lookup.add_to_deck() is not None
        assert lookup.card().status is WordStatus.LEARNING
    # kept on this PC, in Spanish's own file: there at the next start
    assert (tmp_path / "learning-es.sqlite").exists()
    with Opened(tmp_path, basic) as again:
        vocabulary = again.spanish.vocabulary
        assert vocabulary.saved_word(CASA) is not None
        assert vocabulary.status_of_entry(CASA).status is WordStatus.LEARNING
        assert vocabulary.lookups(CASA).pinned == 1


def test_an_inflected_form_is_saved_as_its_entry(
    qapp: QApplication, tmp_path: Path
) -> None:
    with Opened(tmp_path, {"es": spanish_pack()}) as opened:
        lookup = Lookup(opened.tools)
        lookup.show("supe", LookupContext("lo supe"), pinned=True, language="es")
        vocabulary = opened.spanish.vocabulary
        lookup.save_to(vocabulary.categories[0].id)
        saved = vocabulary.saved_word(EntryId("wiktes:saber"))
        assert saved is not None and saved.headword == "saber"


# -- the line: a number of words -----------------------------------------------------------


def test_a_pack_languages_line_is_a_number_of_words_from_the_start(
    qapp: QApplication, tmp_path: Path
) -> None:
    """A pack has ranks, no levels (DECISIONS #176): until the learner says
    how many words they know, the first 1,000 are estimated known - where
    its links started before it kept anything."""
    with Opened(tmp_path, {"es": spanish_pack()}) as opened:
        vocabulary = opened.spanish.vocabulary
        assert vocabulary.line is None
        assert vocabulary.knowledge.known_words == 1000
        pack = opened.spanish.dictionary
        casa, casar = pack.lookup("casa")[0], pack.lookup("casar")[0]  # 300, 2,000
        scheme = vocabulary.scheme
        assert vocabulary.status(casa.facts(scheme)).status is WordStatus.KNOWN
        assert vocabulary.status(casar.facts(scheme)).status is WordStatus.NEW
        vocabulary.set_known_words(200)
        assert vocabulary.status(casa.facts(scheme)).status is WordStatus.NEW
        assert opened.tools.knowledge_of("es") is vocabulary.knowledge


# -- a pack that changes during the run ----------------------------------------------------


def test_a_pack_replaced_during_the_run_is_the_dictionary_from_then_on(
    qapp: QApplication, tmp_path: Path
) -> None:
    basic = {"es": spanish_pack()}
    with Opened(tmp_path, basic) as opened:
        spanish = opened.spanish
        assert spanish.lookup("gato") == []
        newer = FakeDictionaryFile(
            [record("wiktes:gato", "gato", "cat", 900)], {"gato": ["wiktes:gato"]}
        )
        basic["es"] = BasicDictionary(newer, FakeSplit(), "es")  # as a download does
        assert [e.headword for e in spanish.lookup("gato")] == ["gato"]
        assert spanish.vocabulary.status_of_entry(EntryId("wiktes:gato"))


def test_a_pack_removed_leaves_the_saved_words_and_finds_nothing(
    qapp: QApplication, tmp_path: Path
) -> None:
    basic = {"es": spanish_pack()}
    with Opened(tmp_path, basic) as opened:
        tools, spanish = opened.tools, opened.spanish
        lookup = Lookup(tools)
        lookup.show("casa", LINE, pinned=True, language="es")
        lookup.save_to(spanish.vocabulary.categories[0].id)
        del basic["es"]  # removed on Learning
        assert spanish.lookup("casa") == [] and spanish.entry(CASA) is None
        assert spanish.words_in("vengo a casa") == []
        assert not tools.has_dictionary("es")
        saved = spanish.vocabulary.saved_word(CASA)
        assert saved is not None and saved.headword == "casa"  # its own text
        lookup.show("casa", LINE, pinned=True, language="es")
        assert lookup.card().shows is Shows.NO_DICTIONARY
