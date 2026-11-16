"""Mandarin in Traditional characters (polyglotic-hq 375; decision 0164):
the converter keeps one character for one and takes the longest phrase,
the shipped table is OpenCC's in Taiwan's forms, and a converted line
splits and counts its words as the Simplified one did."""

import pytest
from tests.lexicon.sample import chinese_sample

from polyglotic_desktop.adapters.traditional_table import TABLE, read_table
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.traditional import TableError, TraditionalChinese

SMALL = {"发": "發", "头发": "頭髮", "干": "幹", "干净": "乾淨", "若干": "若干"}


def test_the_longest_phrase_wins_then_the_character() -> None:
    convert = TraditionalChinese(SMALL).convert
    assert convert("头发") == "頭髮"  # hair
    assert convert("发") == "發"  # alone: to send out
    assert convert("干净") == "乾淨" and convert("干") == "幹"
    assert convert("若干") == "若干"  # a phrase that stays keeps 干 from 幹


def test_every_character_stays_one_character() -> None:
    convert = TraditionalChinese(SMALL).convert
    for text in ("我的头发", "Hi 头发 OK", "", "abc", "头\U00020000发", "干干净净"):
        assert len(convert(text)) == len(text)
    assert convert("Hi 头发, OK") == "Hi 頭髮, OK"  # only Chinese characters change


def test_phrases_never_reach_across_other_text() -> None:
    assert TraditionalChinese(SMALL).convert("头 发") == "头 發"


def test_a_table_that_changes_a_length_is_refused() -> None:
    with pytest.raises(TableError):
        TraditionalChinese({"么": "麼麼"})


def test_simplified_of_takes_each_written_form_back() -> None:
    back = TraditionalChinese(SMALL).simplified_of()
    assert back["發"] == back["髮"] == "发"
    assert back["乾"] == "干" and back["幹"] == "干"
    assert "若" not in back  # unchanged characters aren't listed


def test_the_shipped_table_is_opencc_in_taiwans_forms() -> None:
    table = read_table()
    assert len(table) > 50_000
    assert all(len(s) == len(t) for s, t in table.items())
    assert (
        TABLE.with_name("OpenCC-LICENSE.txt")
        .read_text("utf-8")
        .startswith("Apache License")
    )
    convert = TraditionalChinese(table).convert
    assert convert("我的头发长了，经济发展很快。") == "我的頭髮長了，經濟發展很快。"
    # Taiwan's (and CC-CEDICT's) 為 裡 著, not OpenCC's own 爲 裏 着
    assert convert("因为这里等着") == "因為這裡等著"
    assert convert("一公里") == "一公里"  # a phrase keeps 里


CEDICT = """\
布滿 布满 [bu4 man3] /to be covered with/
布 布 [bu4] /cloth/
佈 布 [bu4] /to announce; to spread/
滿 满 [man3] /full/
宣布 宣布 [xuan1 bu4] /to declare; to announce/
宣佈 宣布 [xuan1 bu4] /variant of 宣布[xuan1 bu4]/
了 了 [le5] /(completed action marker)/
"""
OPENCC = {"布满": "佈滿", "满": "滿", "宣布": "宣佈"}  # OpenCC's 佈 isn't CC-CEDICT's


def test_a_converted_line_splits_as_its_simplified_one() -> None:
    dictionary = ChineseDictionary(chinese_sample(CEDICT))
    converter = TraditionalChinese(OPENCC)
    line = "布满了"
    shown = converter.convert(line)
    assert shown == "佈滿了"
    assert dictionary.split(shown) == [(0, 1), (1, 2), (2, 3)]  # 佈滿 isn't a form
    dictionary.read_traditional(converter.simplified_of())
    assert dictionary.split(shown) == dictionary.split(line) == [(0, 2), (2, 3)]
    assert dictionary.lookup("佈滿") == dictionary.lookup("布满")


def test_a_converted_word_counts_for_the_entry_its_simplified_one_does() -> None:
    """宣佈 is only "variant of 宣布" in CC-CEDICT: a learner who knows 宣布
    meets the word they know, not a variant of it."""
    dictionary = ChineseDictionary(chinese_sample(CEDICT))
    converter = TraditionalChinese(OPENCC)
    assert dictionary.lookup("宣佈")[0].variant_only
    dictionary.read_traditional(converter.simplified_of())
    simplified = dictionary.words_in("宣布了", "hsk-2025")
    shown = dictionary.words_in(converter.convert("宣布了"), "hsk-2025")
    assert [w.entry.entry_id for w in shown] == [w.entry.entry_id for w in simplified]
    assert not dictionary.lookup("宣佈")[0].variant_only


def test_simplified_lines_split_as_before_once_traditional_is_read() -> None:
    dictionary = ChineseDictionary(chinese_sample(CEDICT))
    before = dictionary.split("宣布布满了"), dictionary.lookup("布")
    dictionary.read_traditional(TraditionalChinese(OPENCC).simplified_of())
    assert (dictionary.split("宣布布满了"), dictionary.lookup("布")) == before


def test_a_reading_line_follows_the_forms_told_and_forgotten() -> None:
    """442: Traditional is told after the start's first readings (the
    converter's table is read on a thread of its own) and forgotten when
    switched off - a reading worked out before either isn't kept past it."""
    dictionary = ChineseDictionary(chinese_sample("你 你 [ni3] /you/\n"))

    def read(text: str) -> list[str]:
        return [r.text for r in dictionary.readings(text)]

    assert read("妳") == []  # Taiwan's 你: not a form CC-CEDICT has
    dictionary.read_traditional({"妳": "你"})
    assert read("妳") == ["nǐ"]
    dictionary.read_traditional({})
    assert read("妳") == []
