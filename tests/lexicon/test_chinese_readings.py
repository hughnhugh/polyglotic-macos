"""Pinyin for a reading line (polyglotic-hq 364, 369; decision 0155):
`ChineseDictionary.readings` gives a syllable for each Chinese character,
read by the word it is in - on a small sample of real CC-CEDICT lines, and
on the real dictionary (the folder POLYGLOTIC_REAL_DICTIONARIES names, as
CI builds CC-CEDICT): the lone readings 364 judged on FLEURS text."""

import os
from pathlib import Path

import pytest
from tests.lexicon.sample import CEDICT_SAMPLE, chinese_sample

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary

# A character's readings in the order the real file gives them alone (地 dì,
# 只 zhǐ, 重 zhòng first): the sample's few words don't outvote file order.
MORE = """\
銀行 银行 [yin2 hang2] /bank/CL:家[jia1],個|个[ge4]/
行動 行动 [xing2 dong4] /operation; action; to move about; mobile/
行 行 [hang2] /row; line; commercial firm; line of business; profession/
行 行 [xing2] /to walk; to go; to travel; a visit; temporary; makeshift; current; in circulation; to do; to perform; capable; competent; effective; all right; OK!; will do/
結果 结果 [jie1 guo3] /to bear fruit/
結果 结果 [jie2 guo3] /outcome; result; consequence; in the end; as a result/
教授 教授 [jiao1 shou4] /to teach (a subject)/
教授 教授 [jiao4 shou4] /professor/
倒轉 倒转 [dao4 zhuan3] /to make an about-turn; to reverse one's direction, policy, sequence etc; to turn things on their head/
倒轉 倒转 [dao4 zhuan4] /(of time, or a video clip etc) to run in reverse/Taiwan pr. [dao4zhuan3]/
更 更 [geng1] /to change or replace; to experience; one of the five two-hour periods/
更 更 [geng4] /more; even more; further; still; still more/
更新 更新 [geng1 xin1] /to replace the old with new; to renew; to update/
為 为 [wei2] /as (in the capacity of); to take sth as; to act as; to serve as; to behave as; to become; to be; to do; by (in the passive voice)/
為 为 [wei4] /because of; for; to/
以 以 [yi3] /to use; by means of; according to; in order to; because of; at (a certain date or place)/
他 他 [ta1] /he; him/
我 我 [wo3] /I; me; my/
食 食 [shi2] /to eat; food; animal feed; eclipse/
祈禱 祈祷 [qi2 dao3] /to pray; to say one's prayers; prayer/
稱 称 [cheng1] /to weigh; to state; to name; name; appellation; to praise/
地 地 [di4] /earth; ground; field; place; land/CL:片[pian4]/
地 地 [de5] /-ly; structural particle: used before a verb or adjective, linking it to preceding modifying adverbial adjunct/
準確 准确 [zhun3 que4] /accurate; exact; precise/
判斷 判断 [pan4 duan4] /to judge; to determine; judgment/
購物 购物 [gou4 wu4] /shopping/
之一 之一 [zhi1 yi1] /one of (sth); one out of a multitude; one (third, quarter, percent etc)/
三 三 [san1] /three; 3/
只 只 [zhi3] /only; merely; just/
隻 只 [zhi1] /classifier for birds and certain animals, one of a pair, some utensils, vessels etc/
貓 猫 [mao1] /cat/CL:隻|只[zhi1]/
有 有 [you3] /to have; there is; there are; to exist; to be/
長 长 [chang2] /length; long; forever; always; constantly/
長 长 [zhang3] /chief; head; elder; to grow; to develop; to increase; to enhance/
很 很 [hen3] /(adverb of degree); quite; very; awfully/
得 得 [de2] /to obtain; to get; to gain; to catch (a disease); proper; suitable; proud; contented; to allow; to permit; ready; finished/
得 得 [de5] /structural particle: used after a verb (or adjective as main verb), linking it to following phrase indicating effect, degree, possibility etc/
得 得 [dei3] /to have to; must; ought to; to need to/
高 高 [gao1] /high; tall; above average; loud; your (honorific)/
走 走 [zou3] /to walk; to go; to run; to move (of vehicle); to visit; to leave; to go away; to die (euph.); from; through; away (in compound verbs, such as 撤走[che4 zou3])/
就 就 [jiu4] /at once; right away; only; just (emphasis); as early as; already; as soon as; then; in that case/
重 重 [zhong4] /heavy; serious; to attach importance to/
重 重 [chong2] /to repeat; repetition; again; re-; classifier: layer/
寫 写 [xie3] /to write/
稅 税 [shui4] /taxes; duties/
都會 都会 [du1 hui4] /city; metropolis/
都 都 [dou1] /all; both; entirely; (used for emphasis) even; already; (not) at all/
都 都 [du1] /capital city; metropolis/
會 会 [hui4] /can; to be possible; to be able to; will; to be likely to; to be sure to; to assemble; to meet; to gather; to see; union; group; association/CL:個|个[ge4]/
每年 每年 [mei3 nian2] /every year; each year; yearly/
設計 设计 [she4 ji4] /plan; design; to design; to plan/CL:個|个[ge4]/
"""


def dictionary() -> ChineseDictionary:
    ranks = {"人": 10, "游戏": 500, "打游戏": 40000, "都会": 9000, "会": 30, "都": 20}
    return ChineseDictionary(chinese_sample(CEDICT_SAMPLE + MORE, ranks))


def pinyin(text: str) -> str:
    return " ".join(reading.text for reading in dictionary().readings(text))


def test_a_syllable_over_each_chinese_character_and_nothing_over_the_rest() -> None:
    readings = dictionary().readings("这个人打游戏 OK，电脑！")
    text = "这个人打游戏 OK，电脑！"
    assert [(text[r.start : r.end], r.text) for r in readings] == [
        ("这", "zhè"), ("个", "ge"), ("人", "rén"), ("打", "dǎ"), ("游", "yóu"),
        ("戏", "xì"), ("电", "diàn"), ("脑", "nǎo"),
    ]  # fmt: skip
    # a word's last syllable says so: a layout shows the words by it
    assert [r.ends_word for r in readings] == [
        False, True, True, False, False, True, False, True,
    ]  # fmt: skip


def test_a_character_is_read_by_the_word_it_is_in() -> None:
    assert pinyin("银行") == "yín háng"
    assert pinyin("行动") == "xíng dòng"
    assert pinyin("还钱") == "huán qián"
    assert pinyin("还") == "hái"  # alone: still, not "to return"
    assert pinyin("更新") == "gēng xīn"
    assert pinyin("更高") == "gèng gāo"  # alone: more


def test_of_a_words_readings_the_one_that_says_most_then_a_noun_before_a_verb() -> None:
    """The file's order doesn't tell a longer word's readings apart: 结果
    was jiē guǒ, "to bear fruit"."""
    assert pinyin("结果") == "jié guǒ"
    assert pinyin("教授") == "jiào shòu"
    assert pinyin("倒转") == "dào zhuǎn"  # a note before a sense isn't a noun


def test_lone_characters_whose_reading_the_words_around_them_say() -> None:
    assert pinyin("为他祈祷") == "wèi tā qí dǎo"  # for him
    assert pinyin("以人为食") == "yǐ rén wéi shí"  # 以 ... 为: as
    assert pinyin("称为人") == "chēng wéi rén"  # after a verb that takes it
    assert pinyin("准确地判断") == "zhǔn què de pàn duàn"  # the adverb's de
    assert pinyin("购物地之一") == "gòu wù dì zhī yī"  # a place
    assert pinyin("三只猫") == "sān zhī māo"  # the measure word
    assert pinyin("只有猫") == "zhǐ yǒu māo"  # only
    assert pinyin("很长") == "hěn cháng"
    assert pinyin("长得高") == "zhǎng de gāo"  # to grow
    assert pinyin("我得走") == "wǒ děi zǒu"  # must
    assert pinyin("重写") == "chóng xiě"  # again
    assert pinyin("重税") == "zhòng shuì"


def test_two_words_the_split_takes_for_one_are_read_as_the_two() -> None:
    """都会, "a metropolis", is nearly always 都 + 会 in speech."""
    assert pinyin("每年都会设计") == "měi nián dōu huì shè jì"


def test_a_word_the_dictionary_lacks_is_read_character_by_character() -> None:
    readings = dictionary().readings("蛇人㐀")
    assert [r.text for r in readings] == ["shé", "rén"]  # none for 㐀: not known


REAL_DICTIONARIES = "POLYGLOTIC_REAL_DICTIONARIES"

LONE = (
    "更gèng 将jiāng 將jiāng 把bǎ 熟shú 只zhǐ 种zhǒng 種zhǒng 要yào 会huì 會huì "
    "和hé 没méi 沒méi 好hǎo 长cháng 長cháng 行xíng 当dāng 當dāng 为wèi 為wèi "
    "得de 地dì 少shǎo 几jǐ 幾jǐ 还hái 還hái 都dōu 了le 着zhe 著zhe 的de "
    "中zhōng 大dà 给gěi 給gěi 便biàn 数shù 數shù 应yīng 應yīng 相xiāng "
    "重zhòng 间jiān 間jiān 系xì 看kàn 教jiāo 觉jué 覺jué 似sì 处chù 處chù "
    "曾céng 朝cháo 称chēng 稱chēng 传chuán 傳chuán 发fā 發fā 分fēn 供gōng "
    "号hào 號hào 假jiǎ 乐lè 樂lè 量liàng 难nán 難nán 强qiáng 強qiáng 任rèn "
    "散sàn 胜shèng 勝shèng 说shuō 說shuō 台tái 通tōng 兴xīng 興xīng 与yǔ "
    "與yǔ 载zài 載zài 占zhàn 佔zhàn 正zhèng 贾jiǎ 賈jiǎ 薄báo 转zhuǎn "
    "轉zhuǎn 作zuò 谁shéi 誰shéi"
)
"""364's lone readings, each judged in its FLEURS sentences: a character
standing as a word by itself, read as it is alone."""


@pytest.fixture(scope="module")
def real() -> ChineseDictionary:
    folder = os.environ.get(REAL_DICTIONARIES)
    if not folder or not (Path(folder) / "cedict.sqlite").exists():
        pytest.skip(f"{REAL_DICTIONARIES} names no built cedict.sqlite")
    return ChineseDictionary(SqliteDictionary(Path(folder) / "cedict.sqlite"))


def test_a_lone_character_reads_as_judged_on_the_real_dictionary(
    real: ChineseDictionary,
) -> None:
    judged = {pair[0]: pair[1:] for pair in LONE.split()}
    # alone, where no rule of _alone's reads it otherwise; 为 standing last
    # in its clause is wéi ("as"), so it is read before a word
    read = {c: real.readings(f"{c}他" if c in "为為" else c)[0].text for c in judged}
    assert {c: r for c, r in read.items() if r != judged[c]} == {}


def test_sentences_read_as_judged_on_the_real_dictionary(
    real: ChineseDictionary,
) -> None:
    def pinyin(text: str) -> str:
        return " ".join(r.text for r in real.readings(text))

    assert pinyin("银行的结果") == "yín háng de jié guǒ"
    assert pinyin("他是教授") == "tā shì jiào shòu"
    assert pinyin("我们都会去") == "wǒ men dōu huì qù"
    assert pinyin("他不是") == "tā bù shì"  # citation tones, no sandhi
