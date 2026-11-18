"""Names in Chinese captions stay names (polyglotic-hq 496, DECISIONS #214's
note): a foreign name the dictionary hasn't got, cut into pieces by the
word split (杜|瓦|尔, 米|勒), and a word a translation writes by its sound
(万里 of 黄万里, "Huang Wanli") are names - neither coloured by how well
they're known nor lit blue in the quiet view."""

from tests.lexicon.sample import chinese_sample

from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary, as_names

NAMES = """\
杜 杜 [du4] /birchleaf pear; to stop/
瓦 瓦 [wa3] /roof tile/
尔 尔 [er3] /thus; so/
米 米 [mi3] /rice; meter/
勒 勒 [le4] /to rein in/
已婚 已婚 [yi3 hun1] /married/
留下 留下 [liu2 xia4] /to leave behind/
黄 黄 [huang2] /yellow/
黃 黄 [Huang2] /surname Huang/
萬里 万里 [wan4 li3] /far away/
萬 万 [wan4] /ten thousand/
裡 里 [li3] /inside/
是 是 [shi4] /is; are/
黨 党 [dang3] /party; association/
查 查 [cha2] /to check/
高 高 [gao1] /tall/
幾 几 [ji3] /a few/
呂 吕 [Lu:3] /surname Lü/
"""
RANKS = {
    "杜": 7779,
    "瓦": 2597,
    "尔": 2242,
    "米": 154,
    "勒": 4201,
    "已婚": 22001,
    "留下": 1531,
    "黄": 705,
    "万里": 7998,
    "万": 300,
    "里": 71,
    "是": 2,
    "党": 296,
    "查": 2443,
    "高": 100,
    "几": 200,
}
"""The real pack's ranks (CC-CEDICT with jieba's, 2026-11-15)."""


def dictionary() -> ChineseDictionary:
    return ChineseDictionary(chinese_sample(NAMES, RANKS))


def names(text: str) -> list[str]:
    return [
        text[w.start : w.end]
        for w in dictionary().words_in(text, "hsk-2025")
        if w.entry.is_name
    ]


def test_a_foreign_name_cut_into_pieces_is_a_name_in_each() -> None:
    # 杜瓦尔 (Duval) and 米勒 (Miller), as 489's FLEURS caption cut them
    assert names("杜瓦尔已婚") == ["杜", "瓦", "尔"]
    assert names("米勒留下") == ["米", "勒"]


def test_common_sound_characters_side_by_side_stay_words() -> None:
    assert names("几米高") == []  # "a few metres tall": no rare piece
    assert names("查查") == []  # "have a look": one character said again
    assert names("米是高") == []  # not side by side


def test_a_word_its_translation_writes_by_its_sound_is_a_name() -> None:
    found = dictionary().named_by_sound(
        "黄万里是党",
        [(0, 1, "Huang"), (1, 3, "Wanli's"), (3, 4, "is"), (4, 5, "Party")],
    )
    assert found == {(0, 1), (1, 3)}


def test_a_link_to_the_whole_name_or_its_sound_in_small_letters() -> None:
    d = dictionary()
    assert d.named_by_sound("黄万里", [(1, 3, "Huang Wanli")]) == {(1, 3)}
    assert d.named_by_sound("万里", [(0, 2, "wanli")]) == set()  # not capitalised
    assert d.named_by_sound("万里", [(0, 2, "far away")]) == set()
    assert d.named_by_sound("吕", [(0, 1, "Lü")]) == {(0, 1)}
    assert d.named_by_sound("吕", [(0, 1, "Lv")]) == {(0, 1)}


def test_a_link_over_a_names_pieces_makes_each_a_name() -> None:
    d = dictionary()
    words = d.words_in("黄万里是", "hsk-2025")
    named = as_names(words, d.named_by_sound("黄万里是", [(0, 3, "Huang Wanli")]))
    assert [w.entry.is_name for w in named] == [True, True, False]
