"""W3, the lookup's view (`ui_next.views.lookup`): what the card shows on
hover and pinned, its parts and Back, the not-in-the-dictionary cards,
"Chinese for it", the Learning commands, and where the card goes. Plain
Python: the sample dictionary and a learner in memory, no Qt."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from tests.learning.fakes import Clock, MemoryLearningStore
from tests.lexicon.sample import FakeDictionaryFile, chinese_sample, english_sample
from tests.lexicon.test_basic import SPANISH, FakeSplit
from tests.lexicon.test_compounds import GERMAN

from polyglotic_desktop.core.learning.knowledge import Knowledge
from polyglotic_desktop.core.learning.languages import LearningLanguages, learned_code
from polyglotic_desktop.core.learning.levels import (
    UNKNOWN_LEVEL_LINKS_FROM,
    LanguageChoices,
)
from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon import compounds
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary, entry_from_record
from polyglotic_desktop.core.lexicon.english import word_at as english_word_at
from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    WordInLine,
    WordLookedUp,
    WordStatus,
)
from polyglotic_desktop.ports.dictionary import DictionaryProblem, EntryRecord
from polyglotic_desktop.ui_next.views.lookup import (
    Lookup,
    PartsTitle,
    Shows,
    place,
    said,
)
from polyglotic_desktop.ui_next.views.placement import Rect, Size

LINE = "我的电脑又卡了，"
CONTEXT = LookupContext(LINE, "My computer froze again,")
COMPUTER = (2, 4)


@dataclass
class Learner:
    """The learning tools without Qt: a vocabulary and a dictionary."""

    vocabulary: Vocabulary
    dictionary: ChineseDictionary | EnglishDictionary
    basic: dict[str, BasicDictionary] = field(default_factory=dict)
    dictionary_problem: DictionaryProblem | None = None
    also: dict[str, "Learner"] = field(default_factory=dict)
    """Other full languages learned, open beside this one (306)."""
    choices: LanguageChoices = field(default_factory=LanguageChoices)

    @property
    def ready(self) -> bool:
        return True

    def of(self, language: str | None) -> "Learner":
        return self.also.get(learned_code(language or ""), self)

    def word_language(self, word: str, language: str | None) -> str | None:
        return language  # by the row (337's routing: test_dictionaries_together)

    def found_in(
        self, word: str, language: str | None, fallbacks: Sequence[str] = ()
    ) -> str | None:
        return None  # by the row (337's fallbacks: test_dictionaries_together)

    def words_in(
        self,
        line: str,
        language: str | None = None,
        said: Iterable[tuple[int, int, str]] = (),
    ) -> list[WordInLine]:
        tools = self.of(language)
        return tools.dictionary.words_in(line, tools.vocabulary.scheme)

    def has_dictionary(self, language: str | None) -> bool:
        return True

    def learns(self, language: str | None) -> bool:
        return True

    def choices_of(self, language: str | None) -> LanguageChoices | None:
        return self.choices

    def word_at(
        self, line: str, index: int, language: str | None = None
    ) -> tuple[int, int] | None:
        if language in self.basic:
            return self.basic[language].word_at(line, index)
        dictionary = self.of(language).dictionary
        if isinstance(dictionary, ChineseDictionary):
            return dictionary.word_at(line, index)
        return english_word_at(line, index)

    def lookup(self, word: str, language: str | None = None) -> list[DictionaryEntry]:
        if language in self.basic:
            return self.basic[language].lookup(word)
        return self.of(language).dictionary.lookup(word)

    def is_basic(self, language: str | None) -> bool:
        return language in self.basic

    def knowledge_of(self, language: str | None) -> Knowledge | None:
        if language in self.basic:
            return Knowledge.by_line(UNKNOWN_LEVEL_LINKS_FROM)
        return self.of(language).vocabulary.knowledge

    def form_reading(self, word: str, language: str | None = None) -> str:
        if language in self.basic:
            return self.basic[language].form_reading(word)
        return ""

    def parts(self, word: str, language: str | None = None) -> list[compounds.Part]:
        if language in self.basic:
            return self.basic[language].parts(word)
        return []

    def facts(self, entry: DictionaryEntry) -> EntryFacts:
        return entry.facts(self.vocabulary.scheme)

    def add_to_load(self, entry_id: EntryId) -> bool:
        return self.vocabulary.add_to_load(entry_id)


def learner(english: bool = False) -> Learner:
    dictionary: ChineseDictionary | EnglishDictionary = (
        EnglishDictionary(english_sample())
        if english
        else ChineseDictionary(chinese_sample())
    )

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    scheme = "en-frequency" if english else "hsk-2025"
    return Learner(
        Vocabulary(MemoryLearningStore(), facts, scheme, Clock()), dictionary
    )


def test_hover_shows_the_headword_reading_status_and_first_sense_only() -> None:
    lookup = Lookup(learner())
    lookup.show("电脑", CONTEXT, pinned=False, at=COMPUTER)
    card = lookup.card()
    assert (card.word, card.shows, card.pinned) == ("电脑", Shows.ENTRY, False)
    assert card.other == "電腦" and card.status is WordStatus.NEW
    assert [(r.reading, r.senses) for r in card.readings] == [
        ("diàn nǎo", ("computer",))
    ]
    assert not card.actions and not card.parts and card.context is None
    assert not card.categories and card.heard == 0


def test_pinned_shows_the_actions_parts_heard_and_the_context_line() -> None:
    tools = learner()
    lookup = Lookup(tools)
    lookup.show("电脑", CONTEXT, pinned=True, at=COMPUTER)
    card = lookup.card()
    assert card.actions and card.pinned
    assert card.readings[0].measure_words == ("台 tái",)
    assert card.parts_title is PartsTitle.INSIDE
    assert [(p.word, p.reading, p.meaning) for p in card.parts] == [
        ("电", "diàn", "electric; electricity; electrical"),
        ("脑", "nǎo", "brain; mind; head"),
    ]
    assert card.context == CONTEXT and card.found_at == COMPUTER
    assert [c.name for c in card.categories] == ["Saved", "Tricky"]
    assert card.back_to == ""


def test_up_to_three_readings_and_the_rest_counted() -> None:
    lookup = Lookup(learner())
    lookup.show("还", LookupContext("还钱"), pinned=True)
    card = lookup.card()
    assert [r.reading for r in card.readings] == ["hái", "huán"]
    assert card.more_readings == 0
    lookup.show("还", LookupContext("还钱"), pinned=False)
    assert len(lookup.card().readings) == 1


def test_card_puts_a_person_written_reading_before_a_machine_draft() -> None:
    rows = [
        EntryRecord("ja:draft", "学ぶ", "", "まなぶ", ("learn · Machine-made",)),
        EntryRecord("ja:person", "学ぶ", "", "まなぶ", ("to study",)),
    ]
    file = FakeDictionaryFile(rows, {"学ぶ": [row.entry_id for row in rows]})
    tools = learner()
    tools.basic["ja"] = BasicDictionary(file, FakeSplit(), "ja")
    lookup = Lookup(tools)
    lookup.show("学ぶ", LookupContext("学ぶ"), pinned=True, language="ja")
    assert [reading.senses for reading in lookup.card().readings] == [
        ("to study",),
        ("learn · Machine-made",),
    ]


def test_a_part_then_back_to_the_word() -> None:
    lookup = Lookup(learner())
    lookup.show("电脑", CONTEXT, pinned=True, at=COMPUTER)
    lookup.part(1)
    card = lookup.card()
    assert card.word == "脑" and card.back_to == "电脑"
    assert card.context is None  # the line was the word's, not the part's
    assert lookup.back() and lookup.card().word == "电脑"
    assert not lookup.back()  # nothing before it
    assert lookup.card().context == CONTEXT


def test_not_in_the_dictionary_as_a_whole() -> None:
    lookup = Lookup(learner())
    lookup.show("画蛇", LookupContext("画蛇"), pinned=True)
    card = lookup.card()
    assert card.shows is Shows.NOT_FOUND and not card.actions
    assert card.guess == "huà shé"
    assert card.meaning == "to draw; to paint + snake; serpent"
    assert card.parts_title is PartsTitle.WORDS_AND_CHARACTERS
    assert [p.word for p in card.parts] == ["画", "蛇"]
    english = Lookup(learner(english=True))
    english.show("zzz", LookupContext("zzz"), pinned=True)
    assert english.card().shows is Shows.NOT_FOUND
    assert english.card().guess == "" and not english.card().parts


def test_an_english_word_for_a_chinese_learner_shows_chinese_for_it() -> None:
    lookup = Lookup(learner())
    lookup.show("computer", LookupContext("My computer froze"), pinned=True)
    card = lookup.card()
    assert card.shows is Shows.CHINESE_FOR
    assert card.parts_title is PartsTitle.CHINESE_FOR
    assert [p.word for p in card.parts] == ["电脑"]
    lookup.part(0)
    assert lookup.card().word == "电脑" and lookup.card().back_to == "computer"


def test_an_english_learner_sees_an_inflected_words_entry() -> None:
    lookup = Lookup(learner(english=True))
    for _ in range(2):  # looked up twice: no longer taken as known (397)
        lookup.show("ran", LookupContext("We ran out of time"), pinned=True)
    card = lookup.card()
    assert card.base == "run" and card.readings[0].reading == "run"
    assert lookup.known() is not None
    status = lookup.learner.vocabulary.status_of_entry(EntryId("ecdict:run"))
    assert status.status is WordStatus.KNOWN


def test_add_to_deck_and_known_toggle_and_keep_the_line() -> None:
    tools = learner()
    lookup = Lookup(tools)
    lookup.show("电脑", CONTEXT, pinned=True, at=COMPUTER)
    entry = lookup.add_to_deck()
    assert entry is not None and lookup.card().in_deck
    deck = tools.vocabulary.deck_word(entry.entry_id)
    assert deck is not None and deck.sentence == LINE
    assert deck.translation == "My computer froze again,"
    lookup.add_to_deck()  # again: out of the deck
    assert lookup.card().status is WordStatus.NEW
    lookup.known()
    assert lookup.card().known
    lookup.known()
    assert lookup.card().status is WordStatus.NEW


def test_save_to_move_remove_and_a_new_category() -> None:
    tools = learner()
    lookup = Lookup(tools)
    lookup.show("电脑", CONTEXT, pinned=True, at=COMPUTER)
    lookup.save_to("saved")
    saved_in = lookup.card().saved_in
    assert saved_in is not None and saved_in.name == "Saved"
    lookup.save_to("tricky")  # moved
    saved_in = lookup.card().saved_in
    assert saved_in is not None and saved_in.name == "Tricky"
    assert lookup.save_to("no-such-category") is None
    lookup.remove()
    assert lookup.card().saved_in is None
    lookup.new_category("New category")
    lookup.show("游戏", LookupContext("打游戏"), pinned=True)
    lookup.new_category("New category")
    names = [c.name for c in tools.vocabulary.categories]
    assert names[-2:] == ["New category", "New category 2"]
    saved_in = lookup.card().saved_in
    assert saved_in is not None and saved_in.name == "New category 2"


def test_every_lookup_shown_is_reported_and_a_pin_says_it_isnt_known() -> None:
    tools = learner()
    events: list[object] = []
    tools.vocabulary.subscribe(events.append)
    lookup = Lookup(tools)
    lookup.show("电脑", CONTEXT, pinned=False)
    assert any(isinstance(e, WordLookedUp) for e in events)
    lookup.close()
    assert not lookup.showing and lookup.add_to_deck() is None


def test_the_dictionary_out_says_so_never_that_the_word_isnt_in_it() -> None:
    """The learner's dictionary missing or damaged (polyglotic-hq 199):
    the card says what's wrong - not "Not in the dictionary", which it
    can't know - with no actions; an English word too, not "Chinese for
    it"."""
    found = learner()
    found.dictionary_problem = DictionaryProblem.DAMAGED
    model = Lookup(found)
    for pinned in (False, True):
        model.show("电脑", CONTEXT, pinned, COMPUTER)
        card = model.card()
        assert card.shows is Shows.DICTIONARY_OUT
        assert card.problem is DictionaryProblem.DAMAGED
        assert not card.actions and not card.parts
    model.show("computer", CONTEXT, True)
    assert model.card().shows is Shows.DICTIONARY_OUT


def test_a_lookup_that_puts_the_dictionary_out_shows_it_at_once() -> None:
    """The card's own query meets the damage (here reverse lookup, for an
    English word): that card says so, not "No Chinese for it"."""
    found = learner()

    class Failing(ChineseDictionary):
        def reverse_lookup(self, query: str, limit: int = 8) -> list[DictionaryEntry]:
            found.dictionary_problem = DictionaryProblem.DAMAGED
            return []

    found.dictionary = Failing(chinese_sample())
    model = Lookup(found)
    model.show("computer", CONTEXT, pinned=True)
    assert model.card().shows is Shows.DICTIONARY_OUT


def test_the_card_goes_above_the_word_centred_clear_of_its_row() -> None:
    area = Rect(0, 0, 1920, 1040)
    word = Rect(500, 800, 40, 30)
    row = Rect(300, 798, 800, 34)
    card, above = place(word, row, Size(360, 200), area)
    assert above and card.bottom <= row.y and card.x + 180 == 520


def test_near_the_top_it_flips_below_and_stays_on_the_screen() -> None:
    area = Rect(0, 0, 1920, 1040)
    word = Rect(4, 40, 40, 30)
    row = Rect(0, 38, 800, 34)
    card, above = place(word, row, Size(360, 200), area)
    assert not above and card.y >= row.bottom and card.x >= area.x
    tall, above = place(word, row, Size(360, 1100), area)
    assert tall.bottom <= area.bottom or tall.y == area.y + 8


# -- a basic dictionary, behind the developer switch (decision 0035) -----------


def with_spanish() -> Learner:
    tools = learner()
    tools.basic["es"] = BasicDictionary(SPANISH, FakeSplit(), "es")
    return tools


def test_a_word_in_a_spanish_row_is_looked_up_in_the_spanish_pack() -> None:
    model = Lookup(with_spanish())
    model.show("supe", LookupContext("No lo supe."), pinned=False, language="es")
    card = model.card()
    assert card.shows is Shows.ENTRY and card.basic and card.language == "es"
    assert card.base == "saber"  # the form's lemma (the fake has no IPA)
    assert [r.reading for r in card.readings] == [""]  # base names it
    assert card.readings[0].senses == ("to know",)


def test_a_basic_dictionarys_word_is_read_only_and_kept_out_of_learning() -> None:
    tools = with_spanish()
    seen: list[object] = []
    tools.vocabulary.subscribe(seen.append)
    model = Lookup(tools)
    model.show("casa", LookupContext("Mi casa."), pinned=True, language="es")
    card = model.card()
    assert card.basic and card.shows is Shows.ENTRY
    assert not card.actions and card.status is None and card.categories == ()
    assert model.entry() is None and model.add_to_deck() is None
    assert model.known() is None
    assert not any(isinstance(e, WordLookedUp) for e in seen)  # nothing reported


def test_a_spanish_word_the_pack_hasnt_got_is_not_found_and_marked_basic() -> None:
    model = Lookup(with_spanish())
    model.show("Wallace", LookupContext("Wallace."), pinned=True, language="es")
    card = model.card()
    assert card.shows is Shows.NOT_FOUND and card.basic


def test_a_compound_the_pack_hasnt_got_shows_its_parts_not_as_its_own() -> None:
    # polyglotic-hq 390: "Internetmaterialien" on real German captions
    tools = learner()
    tools.basic["de"] = BasicDictionary(GERMAN, FakeSplit(), "de")
    model = Lookup(tools)
    line = LookupContext("Die Internetmaterialien.")
    model.show("Internetmaterialien", line, pinned=False, language="de")
    card = model.card()
    assert card.shows is Shows.NOT_FOUND and card.basic  # not in it as a whole
    assert card.meaning == "Internet + material"  # the hover's
    model.show("Internetmaterialien", line, pinned=True, language="de")
    card = model.card()
    assert card.parts_title is PartsTitle.INSIDE
    assert [(p.word, p.reading, p.meaning) for p in card.parts] == [
        ("Internet", "", "(noun) Internet"),
        ("Materialien", "Material", "(noun) material"),  # the entry's word
    ]
    model.part(1)  # a part looks up as any word, and Back returns
    assert model.card().shows is Shows.ENTRY and model.card().base == "Material"
    assert model.back() and model.word == "Internetmaterialien"


def test_a_word_with_no_parts_is_just_not_in_the_dictionary() -> None:
    tools = learner()
    tools.basic["de"] = BasicDictionary(GERMAN, FakeSplit(), "de")
    model = Lookup(tools)
    model.show("Kovelun", LookupContext("Kovelun."), pinned=True, language="de")
    card = model.card()
    assert card.shows is Shows.NOT_FOUND and card.meaning == "" and card.parts == ()


def test_without_a_pack_for_its_language_a_row_uses_the_learners_dictionary() -> None:
    model = Lookup(with_spanish())
    model.show("电脑", CONTEXT, pinned=False, language="zh")
    card = model.card()
    assert card.shows is Shows.ENTRY and not card.basic
    assert model.entry() is not None


RUSSIAN = FakeDictionaryFile(
    [
        EntryRecord("wiktru:ruka", "рука", "", "рука́", ("(noun) hand",), 300),
        EntryRecord("wiktru:dom", "дом", "", "", ("(noun) house",), 200),
    ],
    {"рука": ["wiktru:ruka"], "дом": ["wiktru:dom"]},
    lemmas={"руку": "рука", "руки": "рука", "дома": "дом"},
    form_readings={"руку": "ру́ку", "руки": "ру́ки, руки́", "дома": "до́ма, дома́"},
)


def test_a_russian_word_shows_its_stress_and_an_inflected_form_its_own() -> None:
    tools = learner()
    tools.basic["ru"] = BasicDictionary(RUSSIAN, FakeSplit(), "ru")
    model = Lookup(tools)
    model.show("рука", LookupContext("Моя рука."), pinned=True, language="ru")
    card = model.card()
    assert card.base == "" and [r.reading for r in card.readings] == ["рука́"]
    # an inflected form: the stress moves - its own on its line, the
    # word it belongs to with its stress once, not "рука  рука́"
    model.show("Руку", LookupContext("Дай руку."), pinned=True, language="ru")
    card = model.card()
    assert card.base == "рука́" and [r.reading for r in card.readings] == ["ру́ку"]
    # two forms written alike, each said its own way
    model.show("руки", LookupContext("Мои руки."), pinned=False, language="ru")
    assert [r.reading for r in model.card().readings] == ["ру́ки, руки́"]
    # one syllable: nothing to mark on the word it belongs to
    model.show("дома", LookupContext("Я дома."), pinned=True, language="ru")
    card = model.card()
    assert card.base == "дом" and [r.reading for r in card.readings] == ["до́ма, дома́"]


def test_a_spanish_inflected_form_still_names_its_lemma_with_its_ipa() -> None:
    record = EntryRecord("wiktes:saber", "saber", "", "/saˈbeɾ/", ("to know",), 160)
    entry = entry_from_record(record)
    assert said(entry) == "saber  /saˈbeɾ/"
    assert said(replace(entry, reading="")) == "saber"
    stressed = replace(entry, headword="творог", reading="тво́рог, творо́г")
    assert said(stressed) == "тво́рог, творо́г"


def test_a_basic_dictionary_still_looks_up_while_the_learners_is_out() -> None:
    tools = with_spanish()
    tools.dictionary_problem = DictionaryProblem.MISSING
    model = Lookup(tools)
    model.show("supe", LookupContext("No lo supe."), pinned=True, language="es")
    card = model.card()
    assert card.shows is Shows.ENTRY and card.basic and card.base == "saber"


# -- "Learn Spanish too?" (DECISIONS.md #65, polyglotic-hq 262) ---------------


class Offer:
    """The languages being learned, as `main` keeps them in the settings."""

    def __init__(self) -> None:
        self.languages = LearningLanguages("zh")

    def asks_about(self, caption_language: str | None) -> str | None:
        return self.languages.asks_about(caption_language)

    def learn_too(self, code: str) -> None:
        self.languages = self.languages.added(code)

    def not_now(self, code: str) -> None:
        self.languages = self.languages.declined(code)

    def pack_size(self, code: str) -> int:
        return 13_131_253 if code == "es" else 0


def test_a_pinned_word_in_a_language_not_learned_asks_once() -> None:
    offer = Offer()
    model = Lookup(with_spanish(), offer)
    model.show("casa", LookupContext("Mi casa."), pinned=False, language="es")
    assert model.card().offer == ""  # a hover never asks
    model.show("casa", LookupContext("Mi casa."), pinned=True, language="es")
    assert model.card().offer == "es"
    model.learn_too()
    assert offer.languages.learns("es")
    card = model.card()
    assert (card.offer, card.added) == ("", "es")  # said once, on this card
    assert card.added_pack == 13_131_253  # its dictionary's download (327)
    model.show("supe", LookupContext("No lo supe."), pinned=True, language="es")
    assert (model.card().offer, model.card().added) == ("", "")


def test_not_now_isnt_asked_again_and_learned_languages_never_are() -> None:
    offer = Offer()
    model = Lookup(learner(), offer)
    model.show("电脑", CONTEXT, pinned=True, language="zh-hant")
    assert model.card().offer == ""  # Chinese, in either script, is learned
    model.show("computer", LookupContext("my computer"), pinned=True, language="en")
    assert model.card().offer == "en"
    model.not_now()
    assert offer.languages.not_now == ("en",)
    assert model.card().offer == "" and model.card().added == ""
    model.show("Wallace", LookupContext("Wallace."), pinned=True, language="th")
    assert model.card().offer == ""  # no dictionary: nothing to learn it with


def test_a_word_on_another_languages_line_is_never_chinese_for_it() -> None:
    """ "Chinese for it" searches CC-CEDICT's English meanings: right for an
    English line, and for a Latin word on a Chinese one - but a word on a
    Vietnamese or Spanish line with no dictionary here isn't English, and a
    match there is chance (polyglotic-hq 329: "ngân" showed a politician's
    name). It says the language has no dictionary here, with its "Here:"."""
    model = Lookup(learner())
    for language, line in (("vi", "computer ngân hàng"), ("es", "el computer")):
        context = LookupContext(line, counterpart="computer")
        model.show("computer", context, pinned=True, language=language)
        card = model.card()
        assert (card.shows, card.language, card.parts) == (
            Shows.NO_DICTIONARY,
            language,
            (),
        )
    model.show("computer", LookupContext("my computer"), pinned=True, language="en")
    assert model.card().shows is Shows.CHINESE_FOR  # English's: unchanged
    model.show("computer", LookupContext("我的computer"), pinned=True, language="zh")
    assert model.card().shows is Shows.CHINESE_FOR  # a Latin word on a Chinese line
    model.show("computer", LookupContext("computer"), pinned=True)
    assert model.card().shows is Shows.CHINESE_FOR  # a line of no language known


def test_a_word_whose_dictionary_isnt_the_one_in_use_says_so() -> None:
    """The first run asks no language (polyglotic-hq 293): a learner whose
    PC guessed English hovers a Chinese word. Not "not in the dictionary" -
    CC-CEDICT has it, it just isn't the one running - and, pinned, the card
    offers to learn Chinese, which runs it from the next start."""
    model = Lookup(learner(english=True))
    model.show("电脑", CONTEXT, pinned=True, language="zh")
    card = model.card()
    assert (card.shows, card.language) == (Shows.NO_DICTIONARY, "zh")
    model.show("computer", LookupContext("my computer"), pinned=True, language="en")
    assert model.card().shows is Shows.NOT_FOUND  # its own dictionary's: true
    chinese = Lookup(learner())
    chinese.show("xyzzy", LookupContext("xyzzy"), pinned=True, language="en")
    assert chinese.card().shows is not Shows.NO_DICTIONARY  # "No Chinese for it"


def test_a_word_in_a_language_with_no_dictionary_here_says_so() -> None:
    """Not "not in the dictionary", which can't be known (248's 3.3): Thai
    has none yet, nor has Spanish without its pack. A word the learner's
    dictionary does have is still shown, and an English row keeps "Chinese
    for it"."""
    model = Lookup(learner())
    model.show("สวัสดี", LookupContext("สวัสดี"), pinned=True, language="th")
    card = model.card()
    assert (card.shows, card.language) == (Shows.NO_DICTIONARY, "th")
    model.show("casa", LookupContext("Mi casa."), pinned=False, language="es")
    assert model.card().shows is Shows.NO_DICTIONARY
    model.show("电脑", CONTEXT, pinned=True, language="yue")  # Han: CC-CEDICT's
    assert model.card().shows is Shows.ENTRY
    model.show("computer", LookupContext("my computer"), pinned=True, language="en")
    assert model.card().shows is Shows.CHINESE_FOR
    spanish = Lookup(with_spanish())  # the pack here: its own "not found"
    spanish.show("Wallace", LookupContext("Wallace."), pinned=True, language="es")
    assert spanish.card().shows is Shows.NOT_FOUND


def test_a_name_inside_its_sentence_opens_on_the_name_first() -> None:
    """polyglotic-hq 464: the dictionary has "Bill" as the word bill (帐单),
    then the name. Clicked inside its sentence it's the name, as its caption
    counted it; a sentence's first "Bill" is still the word."""
    d = learner(english=True)
    records = [
        EntryRecord("ecdict:bill", "bill", "", "", ("n. 帐单",), 900),
        EntryRecord("ecdict:Bill", "Bill", "", "", ("n. 比尔（男子名）",), None),
    ]
    file = FakeDictionaryFile(
        records,
        forms={"bill": ["ecdict:bill"], "Bill": ["ecdict:bill", "ecdict:Bill"]},
    )
    d.dictionary = EnglishDictionary(file)
    lookup = Lookup(d)
    line = "Then Bill paid the bill"
    lookup.show("Bill", LookupContext(line), pinned=True, at=(5, 9))
    entry = lookup.entry()
    assert entry is not None and entry.headword == "Bill" and entry.is_name
    assert "比尔" in lookup.card().readings[0].senses[0]
    lookup.show("Bill", LookupContext("Bill paid"), pinned=True, at=(0, 4))
    entry = lookup.entry()
    assert entry is not None and entry.headword == "bill"
    lookup.show("Bill", LookupContext(line), pinned=True)  # where: unknown
    entry = lookup.entry()
    assert entry is not None and entry.headword == "bill"
