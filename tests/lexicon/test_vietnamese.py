"""Vietnamese's word split (polyglotic-hq 325, decision 0121): a caption's
syllables joined into the dictionary's words - fewest, then commonest."""

from collections.abc import Iterable, Mapping

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.lexicon.vietnamese import VietnameseSplit, key, runs
from polyglotic_desktop.ports.dictionary import EntryRecord

WORDS: dict[str, int | None] = {
    "học sinh": 900,
    "học": 300,
    "sinh": 2000,
    "sinh viên": 1500,
    "có thể": 40,
    "có": 5,
    "thể": 4000,
    "chỉ": 120,
    "chỉ thực": 30000,
    "thực hiện": 600,
    "hiện": 3000,
    "Việt Nam": 400,
    "đi": 20,
}


def vietnamese(words: Mapping[str, int | None]) -> FakeDictionaryFile:
    records = [
        EntryRecord(f"wiktvi:{n}", word, "", "", ("a meaning",), rank)
        for n, (word, rank) in enumerate(words.items())
    ]
    return FakeDictionaryFile(records, {r.headword: [r.entry_id] for r in records})


def said(text: str, split: VietnameseSplit) -> list[str]:
    return [text[w.start : w.end] for w in split.words(text)]


def test_syllables_join_into_the_dictionarys_words() -> None:
    split = VietnameseSplit(vietnamese(WORDS))
    assert said("Các học sinh có thể đi.", split) == [
        "Các",
        "học sinh",
        "có thể",
        "đi",
    ]
    # a word the dictionary hasn't got is its syllables
    assert said("học sinh giỏi", split) == ["học sinh", "giỏi"]


def test_a_word_never_crosses_punctuation_or_a_line() -> None:
    split = VietnameseSplit(vietnamese(WORDS))
    assert said("Có, thể", split) == ["Có", "thể"]
    assert said("học\nsinh", split) == ["học", "sinh"]
    assert [len(r) for r in runs("học sinh, có thể 3 đi")] == [2, 2, 1]


def test_among_as_few_words_the_commoner_win() -> None:
    """ "chỉ thực hiện" is two words either way; "thực hiện" (to carry
    out) is far commoner than "chỉ thực". Without ranks the longer first
    word would win - the miss 325 found on its hand-checked lines."""
    assert said("chỉ thực hiện", VietnameseSplit(vietnamese(WORDS))) == [
        "chỉ",
        "thực hiện",
    ]
    unranked = dict.fromkeys(WORDS, None)
    assert said("chỉ thực hiện", VietnameseSplit(vietnamese(unranked))) == [
        "chỉ thực",
        "hiện",
    ]


def test_capitals_and_spelling_variants_of_spaces_match() -> None:
    split = VietnameseSplit(vietnamese(WORDS))
    assert said("Học sinh ở VIỆT NAM", split) == ["Học sinh", "ở", "VIỆT NAM"]
    assert said("học  sinh", split) == ["học  sinh"]  # two spaces
    assert key(" Việt  Nam ") == "việt nam"
    # composed and decomposed letters are one key
    assert key("học sinh".replace("ọ", "ọ")) == "học sinh"


class CountingFile(FakeDictionaryFile):
    def __init__(self, words: Mapping[str, int | None]) -> None:
        base = vietnamese(words)
        super().__init__(list(base.by_id.values()), base.forms)
        self.reads = 0

    def headwords(self) -> Iterable[str]:
        self.reads += 1
        return super().headwords()


def test_the_dictionarys_words_are_read_once_at_the_first_split() -> None:
    file = CountingFile(WORDS)
    split = VietnameseSplit(file)
    assert file.reads == 0  # nothing at start
    split.words("học sinh")
    split.words("có thể")
    assert file.reads == 1
