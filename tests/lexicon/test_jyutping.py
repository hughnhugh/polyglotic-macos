"""Jyutping over Cantonese, from its pack (polyglotic-hq 450, decision
0160): each word as its everyday entry reads it, a syllable a character -
a word the pack hasn't got whole, character by character."""

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.han import HanSplit
from polyglotic_desktop.core.lexicon.jyutping import JyutpingReader, syllables_of
from polyglotic_desktop.ports.dictionary import EntryRecord

RECORDS = [
    EntryRecord("canto:1", "銀行", "", "ngan⁴ hong⁴", ("bank",), 789),
    EntryRecord("canto:2", "行", "", "haang⁴", ("to walk",), 257),
    EntryRecord("canto:3", "行", "", "hong⁴", ("row",), 257),
    EntryRecord("canto:4", "銀", "", "ngan⁴", ("silver",), 2000),
    EntryRecord("canto:5", "去", "", "heoi³", ("to go",), 30),
    EntryRecord("canto:6", "AA制", "", "AA zai³", ("going Dutch",), None),
    EntryRecord("canto:7", "制", "", "zai³", ("system",), 900),
    EntryRecord("canto:8", "睇", "", "tai²", ("to look",), 40),
]


def reader() -> JyutpingReader:
    forms: dict[str, list[str]] = {}
    for r in RECORDS:
        forms.setdefault(r.headword, []).append(r.entry_id)
    file = FakeDictionaryFile(RECORDS, forms)
    return JyutpingReader(BasicDictionary(file, HanSplit(file), "yue"))


def read(text: str) -> list[tuple[str, str, bool]]:
    return [
        (text[r.start : r.end], r.text, r.ends_word) for r in reader().readings(text)
    ]


def test_a_character_is_read_by_the_word_it_is_in() -> None:
    """行 is hong4 in 銀行 (bank), haang4 alone (to walk): its first entry."""
    assert read("去銀行") == [
        ("去", "heoi³", True),
        ("銀", "ngan⁴", False),
        ("行", "hong⁴", True),
    ]
    assert read("行") == [("行", "haang⁴", True)]


def test_nothing_over_what_isnt_a_chinese_character() -> None:
    assert read("睇 OK, 5 次") == [("睇", "tai²", True)]


def test_a_reading_that_isnt_all_jyutping_is_read_by_its_characters() -> None:
    """CC-Canto writes AA制's AA in letters: 制 is still read, the letters
    aren't."""
    assert syllables_of("AA zai³") is None and syllables_of("hai⁶") == ["hai⁶"]
    assert read("睇AA制") == [("睇", "tai²", True), ("制", "zai³", True)]


def test_a_character_the_pack_hasnt_got_has_no_reading() -> None:
    assert read("佢去") == [("去", "heoi³", True)]
