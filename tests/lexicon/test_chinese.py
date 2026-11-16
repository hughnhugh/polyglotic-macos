"""Chinese lookups (core.lexicon.chinese), with the proof of concept's
tests brought across (vc-translator `test_dictionary.py`): tone marks,
the word split (chengyu kept whole), the word under a character, parts,
English to Chinese, and everyday readings first - on a small sample of
real CC-CEDICT lines, through a fake dictionary file."""

import threading
from collections.abc import Iterable, Mapping

from pytest import MonkeyPatch
from tests.lexicon.sample import chinese_sample, phrases_sample
from tools.dictionaries.entry_ids import default_id

from polyglotic_desktop.core.lexicon import chinese
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary, has_han
from polyglotic_desktop.core.lexicon.pinyin import mark_pinyin
from polyglotic_desktop.core.shared import EntryId


def dictionary() -> ChineseDictionary:
    ranks = {"人": 10, "游戏": 500, "打游戏": 40000}
    return ChineseDictionary(chinese_sample(frequency_ranks=ranks))


def words(text: str) -> list[str]:
    return [text[a:b] for a, b in dictionary().split(text)]


def test_numbered_pinyin_gets_tone_marks() -> None:
    assert mark_pinyin("dian4 nao3") == "diàn nǎo"
    assert mark_pinyin("nu:3 lu:4") == "nǚ lǜ"
    assert mark_pinyin("xiong2 gui4 liu2 hou4") == "xióng guì liú hòu"  # the last vowel
    assert mark_pinyin("Bei3 jing1 r5 m2") == "Běi jīng r m"


def test_lookups_in_either_script_with_idioms_and_names_flagged() -> None:
    d = dictionary()
    assert [e.reading for e in d.lookup("电脑")] == ["diàn nǎo"]
    assert d.lookup("電腦") == d.lookup("电脑")
    assert d.lookup("画蛇添足")[0].idiom and not d.lookup("电脑")[0].idiom
    assert d.lookup("北京")[0].is_name and not d.lookup("电脑")[0].is_name
    assert d.lookup("电脑")[0].entry_id == default_id(
        "cedict", "電腦 电脑 [dian4 nao3]"
    )


def test_lines_split_into_the_fewest_most_even_words() -> None:
    assert words("他画蛇添足了") == ["他", "画蛇添足", "了"]
    assert words("研究生命起源") == ["研究", "生命", "起源"]
    assert words("这个人") == ["这个", "人"]
    assert words("我们一起打游戏OK吧！") == [
        "我",
        "们",
        "一",
        "起",
        "打游戏",
        "OK",
        "吧",
        "！",
    ]
    assert words("用電腦") == ["用", "電腦"]


def test_ties_between_equally_short_even_splits_go_to_the_commoner_words() -> None:
    # 是非常简单: 是非|常 and 是|非常 are both two words of 2 and 1 characters;
    # 非常 is far commoner than 是非. Likewise 中|看到, 对|地球, 不|公平 (project 039).
    lines = """\
是 是 [shi4] /is; are; am; yes; to be/
非 非 [fei1] /to not be; not; wrong/
常 常 [chang2] /always; ever; often/
是非 是非 [shi4 fei1] /right and wrong; quarrel/
非常 非常 [fei1 chang2] /very; very much; unusual/
簡單 简单 [jian3 dan1] /simple/
的 的 [de5] /of; ~'s (possessive particle)/
不 不 [bu4] /(negative prefix); not; no/
公 公 [gong1] /public; collectively owned/
平 平 [ping2] /flat; level; equal/
不公 不公 [bu4 gong1] /unjust; unfair/
公平 公平 [gong1 ping2] /fair; impartial/
"""
    ranks = {
        "是": 3,
        "非常": 120,
        "是非": 9000,
        "常": 400,
        "不": 5,
        "公平": 900,
        "不公": 20000,
    }
    with_ranks = ChineseDictionary(chinese_sample(lines, frequency_ranks=ranks))
    assert ["是非常简单的"[a:b] for a, b in with_ranks.split("是非常简单的")] == [
        "是",
        "非常",
        "简单",
        "的",
    ]
    assert ["不公平"[a:b] for a, b in with_ranks.split("不公平")] == ["不", "公平"]
    # a word the frequency source doesn't rank counts as rare, and without
    # ranks the longer earlier word still wins the tie
    without = ChineseDictionary(chinese_sample(lines))
    assert ["不公平"[a:b] for a, b in without.split("不公平")] == ["不公", "平"]
    # ranks on only some of the words still decide a tie (人 is ranked, 个人 isn't)
    assert words("这个人") == ["这个", "人"]


def test_a_phrase_of_two_common_words_is_split_into_them() -> None:
    # polyglotic-hq 359 (decision 0151): CC-CEDICT's 中的 ("to hit the
    # target") has no frequency rank, yet as one word it beat 中 + 的 on the
    # fewest-words rule - 生活中的 read "to hit the target"; 有了 ("to be
    # pregnant") likewise. Kept whole: a name (马里, Mali), an idiom, a word
    # HSK lists (有的, "some"), and one with a part past COMMON_PARTS (沧龙).
    d = ChineseDictionary(phrases_sample())

    def split(text: str, d: ChineseDictionary = d) -> list[str]:
        return [text[a:b] for a, b in d.split(text)]

    assert split("生活中的人") == ["生活", "中", "的", "人"]
    assert split("有了人") == ["有", "了", "人"]
    assert split("有的人") == ["有的", "人"]
    assert split("去马里") == ["去", "马里"]
    assert split("自由自在") == ["自由自在"]
    assert split("沧龙") == ["沧龙"]
    assert d.is_word("中的") and d.lookup("中的")  # still looked up as itself
    # without ranks nothing is common: the split is as before
    without = ChineseDictionary(phrases_sample(ranked=False))
    assert split("生活中的", without) == ["生活", "中的"]


def test_the_word_under_a_character_the_parts_of_a_word_and_pinyin_for_a_phrase() -> (
    None
):
    d = dictionary()
    assert d.word_at("他画蛇添足了", 3) == (1, 5)
    assert d.word_at("OK电脑", 0) is None and d.word_at("电脑", 5) is None
    assert d.parts("打游戏") == ["游戏"]
    assert d.pinyin_of("电脑游戏") == "diàn nǎo yóu xì"
    assert has_han("OK电脑") and not has_han("OK")


NAMES = """德克薩斯 德克萨斯 [De2 ke4 sa4 si1] /Texas, US state/
薩斯 萨斯 [sa4 si1] /SARS/
北京大學 北京大学 [Bei3 jing1 Da4 xue2] /Peking University/
北京 北京 [Bei3 jing1] /Beijing/
大學 大学 [da4 xue2] /university/
奧巴馬 奥巴马 [Ao4 ba1 ma3] /Barack Obama/
巴馬 巴马 [Ba1 ma3] /Bama county/
電腦遊戲 电脑游戏 [dian4 nao3 you2 xi4] /computer game/
遊戲 游戏 [you2 xi4] /game/
上海話 上海话 [Shang4 hai3 hua4] /Shanghainese/
上海 上海 [Shang4 hai3] /Shanghai/
"""


def test_a_names_parts_are_never_cut_out_of_its_sound_spelling() -> None:
    """346's validation loop: the card's "Inside this word" for 德克萨斯
    (Texas) showed 萨斯 as SARS. A part of a name is shown only where it is
    one of the name's own units (CC-CEDICT capitalises each), and never
    cut out of a unit spelt by sound."""
    d = ChineseDictionary(chinese_sample(NAMES))
    assert d.parts("德克萨斯") == []
    assert d.parts("德克萨斯州") == ["德克萨斯"]  # not found: still no 萨斯
    assert d.parts("奥巴马") == []
    assert d.parts("北京大学") == ["北京", "大学"]  # a name of two units
    assert d.parts("上海话") == ["上海"]  # a name, not spelt by sound
    assert d.parts("电脑游戏") == ["游戏"]  # not a name: as before


def test_english_to_chinese() -> None:
    d = dictionary()
    assert [e.headword for e in d.reverse_lookup("games")][:1] == ["游戏"]
    assert d.reverse_lookup("play games")[0].headword == "打游戏"  # "to play a game"
    assert d.reverse_lookup("computers")[0].headword == "电脑"
    assert [e.headword for e in d.reverse_lookup("Beijing")] == ["北京"]
    assert [e.headword for e in d.reverse_lookup("a person")][:1] == ["人"]
    assert d.reverse_lookup("xyzzy") == []


def test_everyday_readings_first() -> None:
    d = dictionary()
    assert [e.reading for e in d.lookup("足")] == ["zú", "jù"]  # zú is in more words
    assert d.lookup("还")[0].reading == "hái"  # though huán is in more
    assert [e.reading for e in d.lookup("了")] == ["le", "liǎo"]  # "variant of" last


def test_an_entry_by_its_id() -> None:
    d = dictionary()
    computer = d.lookup("电脑")[0]
    assert d.entry(computer.entry_id) == computer
    assert d.entry(EntryId("cedict:0000000000")) is None


def test_reverse_lookup_ranks_only_the_commonest_candidates(
    monkeypatch: MonkeyPatch,
) -> None:
    # "to" is in about 35,000 CC-CEDICT meanings; ranking them all took 2s.
    d = ChineseDictionary(chinese_sample(frequency_ranks={"这个": 20, "这": 30}))
    assert [e.headword for e in d.reverse_lookup("this")] == ["这个", "这", "个"]
    monkeypatch.setattr(chinese, "REVERSE_CANDIDATES", 1)
    assert [e.headword for e in d.reverse_lookup("this")] == ["这个"]


def test_opening_reads_nothing_and_prepare_reads_the_split_once(
    monkeypatch: MonkeyPatch,
) -> None:
    """polyglotic-hq project 110: the word split's ~0.2 s of reading waits
    for `prepare` (main runs it off the interface thread once the window
    shows) - or for the first split, which then reads it there."""
    file = chinese_sample()
    reads: list[str] = []
    headwords, ranks = file.headwords, file.frequency_ranks

    def counted_headwords() -> Iterable[str]:
        reads.append("words")
        return headwords()

    def counted_ranks() -> Mapping[str, int]:
        reads.append("ranks")
        return ranks()

    monkeypatch.setattr(file, "headwords", counted_headwords)
    monkeypatch.setattr(file, "frequency_ranks", counted_ranks)
    found = ChineseDictionary(file)
    assert reads == []
    found.prepare()
    found.prepare()
    assert reads == ["ranks", "words"]
    unprepared = ChineseDictionary(file)
    assert unprepared.is_word("北京")
    assert reads == ["ranks", "words", "ranks", "words"]


def test_the_split_data_is_read_once_however_many_threads_ask() -> None:
    """`prepare` runs off the interface thread at start (polyglotic-hq 136):
    a caller on another thread meanwhile waits for it rather than reading
    the headwords again, and `ready` says when the split can answer."""
    file = chinese_sample()
    reads: list[str] = []
    original = file.headwords

    def counted() -> Iterable[str]:
        reads.append("headwords")
        return original()

    file.headwords = counted  # type: ignore[method-assign]
    d = ChineseDictionary(file)
    assert not d.ready
    threads = [threading.Thread(target=d.prepare) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert d.ready
    assert reads == ["headwords"]
    assert words("打游戏") == ["打游戏"]  # and the split works as before


def test_hangul_and_other_scripts_past_the_unified_ideographs_arent_han() -> None:
    """The compatibility block was once written from a character that
    looks like U+F900 but is U+8C48: Hangul, Yi and the private use area
    were then "Chinese", and a Korean word was looked up in CC-CEDICT
    (polyglotic-hq 337)."""
    assert not any(chinese.is_han(c) for c in "은행에가요")  # Hangul syllables
    assert not chinese.is_han("ꀀ")  # Yi
    assert not chinese.is_han("")  # private use
    assert not any(chinese.is_han(c) for c in "ひらカタ")  # kana
    assert not has_han("은행에 가요 OK")
    for char in ("㐀", "豈", "鿿", "豈", "﫿", "\U00020000", "〇"):
        assert chinese.is_han(char), hex(ord(char))
    assert has_han("我们") and has_han("用iPhone打")
