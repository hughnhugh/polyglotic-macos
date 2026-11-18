"""Stress marks over Russian (polyglotic-hq 511; 370 measured the data): an
acute over each word's stressed vowel, from the Russian pack's stressed
forms and headwords - none for a word of one vowel, one written with ё, or
one the pack stresses two ways. A made-up pack, as the build writes it."""

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.adapters.spaced_split import SpacedSplit
from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.stress import MARK, StressReader, stressed_at
from polyglotic_desktop.ports.dictionary import EntryRecord

RUSSIAN = FakeDictionaryFile(
    [
        EntryRecord("wiktru:1", "молоко", "", "молоко́", ("milk",), 900),
        EntryRecord("wiktru:2", "рука", "", "рука́", ("hand",), 300),
        EntryRecord("wiktru:3", "ещё", "", "ещё", ("still",), 50),
        EntryRecord("wiktru:4", "дом", "", "до́м", ("house",), 200),
    ],
    {
        "молоко": ["wiktru:1"],
        "рука": ["wiktru:2"],
        "ещё": ["wiktru:3"],
        "еще": ["wiktru:3"],
        "дом": ["wiktru:4"],
        "руку": ["wiktru:2"],
        "руки": ["wiktru:2"],
    },
    form_readings={"руку": "ру́ку", "руки": "руки́, ру́ки"},
)


def marks(text: str) -> list[str]:
    """`text` with each mark the reader gives written in after its vowel."""
    reader = StressReader(BasicDictionary(RUSSIAN, SpacedSplit("ru"), "ru"))
    found = reader.readings(text)
    assert all(r.text == MARK and r.end == r.start + 1 for r in found)
    out = list(text)
    for r in reversed(found):
        out.insert(r.end, "́")
    return "".join(out).split()


def test_the_stressed_vowel_of_a_headword_and_an_inflected_form() -> None:
    """The stress moves as a word inflects: рука́, but ру́ку."""
    assert marks("Молоко рука руку") == ["Молоко́", "рука́", "ру́ку"]


def test_no_mark_where_none_is_needed_or_known() -> None:
    # one vowel; written with ё; stressed two ways; not in the pack
    assert marks("дом ещё руки Москва") == ["дом", "ещё", "руки", "Москва"]


def test_a_yo_written_as_e_is_its_stress() -> None:
    """Most Russian text writes ещё as еще: the ё is where its stress is."""
    assert marks("еще") == ["еще́"]


def test_where_a_reading_puts_the_stress() -> None:
    assert stressed_at("руку", "ру́ку") == 1
    assert stressed_at("еще", "ещё") == 2
    assert stressed_at("творог", "тво́ро́г") is None  # said either way
    assert stressed_at("рука", "ру́ку") is None  # another word's spelling
