"""A word's readings in the order people use them (polyglotic-hq 366): the
word card shows the first, a caption's word counts for it, and the pinyin of
a phrase reads it. CC-CEDICT's file order puts the rarer reading first for
many words with several (结果 jiē guǒ, "to bear fruit", before jié guǒ,
"result"), and the reading most words use isn't a character's reading alone
(更 gēng, as in 更新, before gèng, "more").

On real CC-CEDICT lines; on the real dictionary - the folder
POLYGLOTIC_REAL_DICTIONARIES names, as CI builds CC-CEDICT - every reading
put first by hand is one the word has, and the words measured in 366 read
as judged there."""

import os
from pathlib import Path

import pytest
from tests.lexicon.sample import chinese_sample

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.chinese import (
    EVERYDAY_READINGS,
    ChineseDictionary,
)

LINES = """\
出來 出来 [chu1 lai2] /to come out/to appear/to arise/
出來 出来 [chu5 lai5] /(after a verb, indicates coming out, completion of an action, or ability to discern or detect)/
地方 地方 [di4 fang1] /region/regional (away from the central administration)/local/
地方 地方 [di4 fang5] /place; location; area; space; territory/aspect; part/CL:處|处[chu4]/
好處 好处 [hao3 chu3] /easy to get along with/
好處 好处 [hao3 chu5] /benefit; advantage; merit/gain; profit/also pr. [hao3chu4]/
將 将 [jiang1] /will/shall/to use/to take/to checkmate/just a short while ago/(introduces object of main verb, used in the same way as 把[ba3])/
將 将 [jiang4] /(bound form) a general/(literary) to command; to lead/(Chinese chess) general (on the black side, equivalent to a king in Western chess)/
將軍 将军 [jiang1 jun1] /general; high-ranking military officer/
大將 大将 [da4 jiang4] /a general or admiral/
將領 将领 [jiang4 ling3] /high-ranking military officer/
教授 教授 [jiao1 shou4] /to teach (a subject)/
教授 教授 [jiao4 shou4] /professor/
更 更 [geng1] /to change or replace/to experience/one of the five two-hour periods into which the night was formerly divided/watch (e.g. of a sentry or guard)/
更 更 [geng4] /more/even more/further/still/still more/
更新 更新 [geng1 xin1] /to replace the old with new; to renew; to update/
變更 变更 [bian4 geng1] /to change; to alter; to modify/
東西 东西 [dong1 xi1] /east and west/
東西 东西 [dong1 xi5] /thing/stuff/person/CL:個|个[ge4],件[jian4]/
結果 结果 [jie1 guo3] /to bear fruit/
結果 结果 [jie2 guo3] /outcome; result; consequence/in the end; as a result/to kill; to dispatch/
老公 老公 [lao3 gong1] /(coll.) husband/
老公 老公 [lao3 gong5] /(coll.) eunuch/see also 老公[lao3 gong1]/
重點 重点 [chong2 dian3] /to recount (e.g. results of election)/to re-evaluate/
重點 重点 [zhong4 dian3] /important point; main point; focus/key (project etc)/to focus on; to put the emphasis on/
生意 生意 [sheng1 yi4] /life force/vitality/
生意 生意 [sheng1 yi5] /business/CL:筆|笔[bi3]/
"""


def first(word: str) -> str:
    return ChineseDictionary(chinese_sample(LINES)).lookup(word)[0].reading


def test_a_word_s_everyday_reading_comes_before_a_rarer_one() -> None:
    assert first("结果") == "jié guǒ"  # "result", not "to bear fruit"
    assert first("教授") == "jiào shòu"  # "professor", not "to teach"
    assert first("重点") == "zhòng diǎn"  # not "to recount"
    assert first("好处") == "hǎo chu"  # "benefit", more senses
    assert first("东西") == "dōng xi"  # "thing", more senses
    assert first("地方") == "dì fang"  # "place"
    assert first("結果") == "jié guǒ"  # the traditional form too


def test_what_isn_t_a_sense_doesn_t_count_as_one() -> None:
    assert first("老公") == "lǎo gōng"  # "husband": a "see also" isn't a sense
    assert first("出来") == "chū lái"  # a verb's ending in brackets names nothing


def test_a_reading_put_first_by_hand() -> None:
    assert first("生意") == "shēng yi"  # "business", though as many senses


def test_a_character_alone_reads_as_it_does_alone() -> None:
    assert first("更") == "gèng"  # though gēng is in 更新 and 变更
    assert first("将") == "jiāng"  # though jiàng is in more words


def test_a_meaning_s_words_still_find_every_reading() -> None:
    d = ChineseDictionary(chinese_sample(LINES))
    assert [e.reading for e in d.lookup("结果")] == ["jié guǒ", "jiē guǒ"]


REAL_DICTIONARIES = "POLYGLOTIC_REAL_DICTIONARIES"

JUDGED = {
    "结果": "jié guǒ", "教授": "jiào shòu", "重点": "zhòng diǎn",
    "好处": "hǎo chu", "东西": "dōng xi", "便宜": "pián yi", "故事": "gù shi",
    "告诉": "gào su", "大夫": "dài fu", "地方": "dì fang", "老公": "lǎo gōng",
    "出来": "chū lái", "过来": "guò lái", "尽量": "jǐn liàng", "更": "gèng",
    "将": "jiāng", "把": "bǎ", "还": "hái", "为": "wèi", "应": "yīng",
}  # fmt: skip
"""Words 366 judged by hand, read first on the real dictionary."""


@pytest.fixture(scope="module")
def real() -> ChineseDictionary:
    folder = os.environ.get(REAL_DICTIONARIES)
    if not folder or not (Path(folder) / "cedict.sqlite").exists():
        pytest.skip(f"{REAL_DICTIONARIES} names no built cedict.sqlite")
    return ChineseDictionary(SqliteDictionary(Path(folder) / "cedict.sqlite"))


def test_every_reading_put_first_by_hand_is_one_the_word_has(
    real: ChineseDictionary,
) -> None:
    for form, reading in EVERYDAY_READINGS.items():
        assert real.lookup(form)[0].reading == reading, form


def test_the_judged_words_read_first_as_judged(real: ChineseDictionary) -> None:
    assert {w: real.lookup(w)[0].reading for w in JUDGED} == JUDGED
