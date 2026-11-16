"""Zhuyin from the dictionary's tone-marked pinyin (polyglotic-hq 395):
the standard table, and tones as zhuyin marks them."""

import pytest

from polyglotic_desktop.core.lexicon.pinyin import mark_pinyin
from polyglotic_desktop.core.lexicon.zhuyin import split_tone, zhuyin


@pytest.mark.parametrize(
    ("pinyin", "expected"),
    [
        # each tone: the first unmarked, then ˊ ˇ ˋ, the neutral's ˙ before
        ("mā", "ㄇㄚ"),
        ("má", "ㄇㄚˊ"),
        ("mǎ", "ㄇㄚˇ"),
        ("mà", "ㄇㄚˋ"),
        ("ma", "˙ㄇㄚ"),
        ("le", "˙ㄌㄜ"),
        # 刚刚呢, 游戏, 中文, 学习, 女儿, 绿
        ("gāng", "ㄍㄤ"),
        ("ne", "˙ㄋㄜ"),
        ("yóu", "ㄧㄡˊ"),
        ("xì", "ㄒㄧˋ"),
        ("zhōng", "ㄓㄨㄥ"),
        ("wén", "ㄨㄣˊ"),
        ("xué", "ㄒㄩㄝˊ"),
        ("xí", "ㄒㄧˊ"),
        ("nǚ", "ㄋㄩˇ"),
        ("ér", "ㄦˊ"),
        ("lǜ", "ㄌㄩˋ"),
        # the initial alone, j/q/x's u, y- and w- spellings, iu/ui/un
        ("shì", "ㄕˋ"),
        ("zì", "ㄗˋ"),
        ("rì", "ㄖˋ"),
        ("qù", "ㄑㄩˋ"),
        ("juǎn", "ㄐㄩㄢˇ"),
        ("xūn", "ㄒㄩㄣ"),
        ("yī", "ㄧ"),
        ("yǔ", "ㄩˇ"),
        ("yuè", "ㄩㄝˋ"),
        ("yòng", "ㄩㄥˋ"),
        ("wǒ", "ㄨㄛˇ"),
        ("liù", "ㄌㄧㄡˋ"),
        ("duì", "ㄉㄨㄟˋ"),
        ("lùn", "ㄌㄨㄣˋ"),
        ("xióng", "ㄒㄩㄥˊ"),
        ("ài", "ㄞˋ"),
        ("ēn", "ㄣ"),
        ("hǎo", "ㄏㄠˇ"),
        ("chuāng", "ㄔㄨㄤ"),
    ],
)
def test_the_table(pinyin: str, expected: str) -> None:
    assert zhuyin(pinyin) == expected


def test_a_syllable_the_table_doesnt_know_is_kept() -> None:
    for kept in ("hm", "ng", "xx", "Q"):
        assert zhuyin(kept) == kept


def test_from_cc_cedicts_numbered_pinyin() -> None:
    """The way the dictionary gives it: numbered, then marked."""
    marked = mark_pinyin("gang1 gang1 ne5 lu:4 nu:3 r5").split()
    assert [zhuyin(s) for s in marked] == [
        "ㄍㄤ",
        "ㄍㄤ",
        "˙ㄋㄜ",
        "ㄌㄩˋ",
        "ㄋㄩˇ",
        "˙ㄦ",
    ]


def test_split_tone() -> None:
    assert split_tone("Nǚ") == ("nü", 3)
    assert split_tone("le") == ("le", 5)
    assert split_tone("lv4") == ("lü4", 5)  # numbers aren't read: marked pinyin only
