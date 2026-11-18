"""A basic dictionary's lookups (decision 0035), through fakes of the
dictionary file and the word split: the order a caption's word is looked
up in, and the words in a line."""

from collections.abc import Sequence

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.lexicon.basic import BasicDictionary, absent
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.ports.dictionary import EntryRecord
from polyglotic_desktop.ports.word_split import SplitWord


def record(entry_id: str, headword: str, meaning: str, rank: int = 1) -> EntryRecord:
    return EntryRecord(entry_id, headword, "", "", (meaning,), rank)


SPANISH = FakeDictionaryFile(
    [
        record("wiktes:casa", "casa", "house", 300),
        record("wiktes:casar", "casar", "to marry", 2000),
        record("wiktes:saber", "saber", "to know", 160),
        record("wiktes:venir", "venir", "to come", 270),
        record("wiktes:vengar", "vengar", "to avenge", 9000),
        record("wiktes:Darwin", "Darwin", "(name) a surname", 8000),
        record("wiktes:Navidad", "Navidad", "(noun) Christmas", 3000),
    ],
    {
        "casa": ["wiktes:casa"],
        "casar": ["wiktes:casar"],
        "saber": ["wiktes:saber"],
        "venir": ["wiktes:venir"],
        "vengar": ["wiktes:vengar"],
        "Darwin": ["wiktes:Darwin"],
        "Navidad": ["wiktes:Navidad"],
    },
    lemmas={"supe": "saber", "vengo": "venir"},
)


class FakeSplit:
    """Words by spaces; `table` gives each word's analysis."""

    def __init__(self, table: dict[str, SplitWord] | None = None) -> None:
        self.table = table or {}

    def words(self, text: str) -> Sequence[SplitWord]:
        out, at = [], 0
        for word in text.split():
            start = text.index(word, at)
            at = start + len(word)
            seen = self.table.get(word, SplitWord(0, 0))
            out.append(SplitWord(start, at, seen.lemmas, seen.guesses, seen.content))
        return out


def heads(dictionary: BasicDictionary, word: str) -> list[str]:
    return [e.headword for e in dictionary.lookup(word)]


def test_the_packs_own_forms_come_before_the_analysers_guess() -> None:
    split = FakeSplit({"vengo": SplitWord(0, 0, guesses=("vengar",))})
    spanish = BasicDictionary(SPANISH, split, "es")
    assert heads(spanish, "vengo") == ["venir"]  # Wiktionary's, not simplemma's
    assert heads(spanish, "supe") == ["saber"]
    assert heads(spanish, "Casa") == ["casa"]  # lower case too
    assert spanish.lookup("nada") == []


def test_a_guess_is_tried_when_the_pack_knows_nothing_better() -> None:
    split = FakeSplit({"casándose": SplitWord(0, 0, guesses=("casar",))})
    assert heads(BasicDictionary(SPANISH, split, "es"), "casándose") == ["casar"]


def test_the_first_guess_that_finds_anything_is_the_one_shown() -> None:
    """Guesses come likeliest first (simplemma's lemma, then the word
    without a clitic): a later, far-fetched one isn't shown beside it - and
    a guess that is an inflected form finds its lemma (polyglotic-hq 380)."""
    split = FakeSplit({"casándose": SplitWord(0, 0, guesses=("casar", "casa"))})
    assert heads(BasicDictionary(SPANISH, split, "es"), "casándose") == ["casar"]
    split = FakeSplit({"lesupe": SplitWord(0, 0, guesses=("nada", "supe", "casa"))})
    assert heads(BasicDictionary(SPANISH, split, "es"), "lesupe") == ["saber"]


def test_an_analysers_lemma_in_context_comes_before_the_word_itself() -> None:
    japanese = FakeDictionaryFile(
        [
            record("jmdict:suru", "する", "to do", 27),
            record("jmdict:shi", "し", "four"),
        ],
        {"する": ["jmdict:suru"], "し": ["jmdict:shi"]},
    )
    split = FakeSplit({"し": SplitWord(0, 0, lemmas=("する",), content=True)})
    assert heads(BasicDictionary(japanese, split, "ja"), "し") == ["する", "し"]


def test_words_in_a_line_count_for_their_entries() -> None:
    split = FakeSplit({"vengo": SplitWord(0, 0, guesses=("vengar",))})
    spanish = BasicDictionary(SPANISH, split, "es")
    words = spanish.words_in("vengo a casa de Darwin", "es-frequency")
    assert [(w.start, w.end, w.entry.entry_id) for w in words] == [
        (0, 5, "wiktes:venir"),
        (8, 12, "wiktes:casa"),
        (16, 22, "wiktes:Darwin"),
    ]
    assert words[2].entry.is_name  # the pack says so: "(name) a surname"
    assert spanish.word_at("vengo a casa", 9) == (8, 12)
    assert spanish.word_at("vengo a casa", 5) is None
    assert spanish.entry(words[0].entry.entry_id) == spanish.lookup("venir")[0]


def test_a_phrase_is_looked_up_as_written() -> None:
    spanish = BasicDictionary(SPANISH, FakeSplit(), "es")
    assert spanish.lookup("a casa") == []


def test_a_forms_own_reading_is_found_as_written_or_in_lower_case() -> None:
    russian = BasicDictionary(
        FakeDictionaryFile(
            [record("wiktru:ruka", "рука", "hand")],
            {"рука": ["wiktru:ruka"]},
            lemmas={"руку": "рука"},
            form_readings={"руку": "ру́ку"},
        ),
        FakeSplit(),
        "ru",
    )
    assert russian.form_reading("руку") == russian.form_reading("Руку") == "ру́ку"
    assert russian.form_reading("рука") == ""


def test_a_name_is_what_the_pack_says_not_a_capital() -> None:
    """German writes nouns with a capital: they had all been names, so no
    German noun was ever pointed out as new (polyglotic-hq 380). A pack's
    name is an entry whose meanings are all "(name) ..."."""
    spanish = BasicDictionary(SPANISH, FakeSplit(), "es")
    assert [e.is_name for e in spanish.lookup("Navidad")] == [False]
    assert [e.is_name for e in spanish.lookup("Darwin")] == [True]


# -- a pack as a learner's dictionary (decision 0175; polyglotic-hq 391) -----


def test_a_pack_answers_what_learning_asks_of_a_learners_dictionary() -> None:
    spanish = BasicDictionary(SPANISH, FakeSplit(), "es")
    casa = spanish.lookup("casa")[0]
    facts = spanish.facts(casa.entry_id, "en-frequency")
    assert facts is not None
    assert (facts.frequency_rank, facts.level, facts.is_name) == (300, 1, False)
    assert spanish.facts(EntryId("wiktes:gone"), "en-frequency") is None
    # the sizes of Words' bands: by rank
    assert spanish.words_in_ranks([(1, 1000), (1001, 5000), (5001, 10000)]) == [
        3,
        2,
        2,
    ]
    assert spanish.words_at_levels("en-frequency") == {}  # ranks, not levels
    assert spanish.merged_ids() == []


def test_a_packs_words_come_in_order_of_rank_for_a_learning_load() -> None:
    spanish = BasicDictionary(SPANISH, FakeSplit(), "es")
    past = spanish.words_past(200, 3, "en-frequency")
    assert [(rank, facts.entry_id) for rank, facts in past] == [
        (270, "wiktes:venir"),
        (300, "wiktes:casa"),
        (2000, "wiktes:casar"),
    ]
    assert spanish.words_past(9000, 5, "en-frequency") == []


def test_a_pack_that_is_not_here_finds_nothing() -> None:
    gone = absent("es")
    assert gone.language == "es"
    assert gone.lookup("casa") == [] and gone.entry(EntryId("wiktes:casa")) is None
    assert gone.words_in("vengo a casa", "en-frequency") == []
    assert gone.word_at("casa", 1) is None
    assert gone.words_past(0, 10, "en-frequency") == []
    assert gone.words_in_ranks([(1, 1000)]) == [0]
    assert gone.merged_ids() == [] and gone.form_reading("casa") == ""


class FrenchMeanings:
    """A stand-in meanings file: a pack's meanings in French (decision 0234)."""

    def meanings(self, entry_id: str) -> tuple[str, ...] | None:
        return {"wiktes:casa": ("(noun) maison",)}.get(entry_id)


def test_a_packs_entry_in_the_learners_meanings_file_is_shown_in_their_language() -> (
    None
):
    spanish = BasicDictionary(SPANISH, FakeSplit(), "es")
    spanish.explain_in(FrenchMeanings())
    assert spanish.lookup("casa")[0].meanings == ("(noun) maison",)
    assert spanish.lookup("supe")[0].meanings == ("to know",)  # not in the file
    entry = spanish.entry(EntryId("wiktes:casa"))
    assert entry is not None and entry.meanings == ("(noun) maison",)
