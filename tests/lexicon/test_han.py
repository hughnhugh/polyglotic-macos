"""The word split `han` (polyglotic-hq 450, decision 0160): a Cantonese
caption, written without spaces, cut into the pack's words - its own words
whole, as few as possible, a phrase of two common words left to them."""

from collections.abc import Mapping

from tests.lexicon.sample import FakeDictionaryFile

from polyglotic_desktop.core.lexicon.basic import BasicDictionary
from polyglotic_desktop.core.lexicon.han import HanSplit
from polyglotic_desktop.ports.dictionary import EntryRecord

WORDS: dict[str, int | None] = {
    "佢": 9,
    "哋": 900,
    "佢哋": 120,
    "而": 400,
    "家": 300,
    "而家": 88,
    "喺": 75,
    "銀": 2000,
    "行": 257,
    "銀行": 789,
    "同": 50,
    "埋": 600,
    "同埋": 117,
    "你": 5,
    "嘅": 16,
    "你嘅": None,  # a phrase: 你 + 嘅, both common
    "總裁": 9000,
    "行政": 1500,
    "行政總裁": None,  # unranked, but 總裁 isn't among the commonest
    "研究": 500,
    "研究生": 4000,
    "生命": 700,
    "命": 1500,
    "生": 200,
    "起源": 3000,
}


def canto_file(words: Mapping[str, int | None]) -> FakeDictionaryFile:
    records = [
        EntryRecord(f"canto:{n}", word, "", "", ("a meaning",), rank)
        for n, (word, rank) in enumerate(words.items())
    ]
    return FakeDictionaryFile(records, {r.headword: [r.entry_id] for r in records})


def said(text: str, split: HanSplit) -> list[str]:
    return [text[w.start : w.end] for w in split.words(text)]


def test_cantonese_words_stay_whole() -> None:
    """371: CC-CEDICT's split cut 佢哋 and 同埋 in two; the pack's words
    keep them whole."""
    split = HanSplit(canto_file(WORDS))
    assert said("佢哋而家喺銀行同埋你", split) == [
        "佢哋",
        "而家",
        "喺",
        "銀行",
        "同埋",
        "你",
    ]


def test_the_most_evenly_sized_cut_wins_a_tie() -> None:
    split = HanSplit(canto_file(WORDS))
    assert said("研究生命起源", split) == ["研究", "生命", "起源"]


def test_a_phrase_of_two_common_words_is_left_to_them() -> None:
    """你嘅 ("your") has no rank, and 你 and 嘅 are both among the
    commonest: two words, so each is looked up and linked as itself. 行政總裁
    has none either, but 總裁 is rare: it stays one word."""
    split = HanSplit(canto_file(WORDS))
    assert said("你嘅", split) == ["你", "嘅"]
    assert said("行政總裁", split) == ["行政總裁"]


def test_other_scripts_are_words_of_their_own_and_punctuation_none() -> None:
    split = HanSplit(canto_file(WORDS))
    assert said("用iPhone同埋你，5 個", split) == ["用", "iPhone", "同埋", "你", "個"]
    assert said("", split) == []


def test_a_character_the_pack_hasnt_got_is_a_word_alone() -> None:
    split = HanSplit(canto_file(WORDS))
    assert said("佢哋睇", split) == ["佢哋", "睇"]


def test_the_basic_dictionary_finds_a_lines_words_by_it() -> None:
    file = canto_file(WORDS)
    dictionary = BasicDictionary(file, HanSplit(file), "yue")
    text = "佢哋喺銀行"
    assert [text[a:b] for a, b in dictionary.words(text)] == ["佢哋", "喺", "銀行"]
    assert dictionary.word_at(text, 1) == (0, 2)
    assert [e.headword for e in dictionary.lookup("佢哋")] == ["佢哋"]
