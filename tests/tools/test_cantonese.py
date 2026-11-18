"""The Cantonese pack's build (polyglotic-hq 371 and 450, decision 0160):
its sources read, each word's everyday Jyutping first, CC-Canto's meanings
before CC-CEDICT's, and ranks from speech and writing - writing only as far
as speech bears it out (polyglotic-hq 467)."""

import zipfile
from collections import Counter
from collections.abc import Collection
from pathlib import Path

import pytest
from tools.dictionaries import cantonese
from tools.dictionaries.cedict import CedictLine
from tools.dictionaries.packs import CANTONESE_RANKS, Draft, cantonese_draft

CANTO_LINES = [
    "# CC-Canto",
    "係 係 [xi4] {hai6} /(Cantonese) to be/to connect/",
    "嘅 嘅 [kai3] {ge3} /possessive marker/",
    "嘅 慨 [kai3] {koi3} /(final particle) surprise/",
    "三 三 [san1] {saam1} /1. three 2. (slang) love affair/ # adapted from cc-cedict",
    "佢哋 渠哋 [qu2 di4] {keoi5 dei6} /(pronoun) they/",
    "空 空 [kong1] {hung1} ",
    "四 四 [si4] {sei3} /(slang) labourer/",
]


def test_cc_cantos_lines_are_read_with_their_notes_and_numbered_senses() -> None:
    lines = list(cantonese.parse(CANTO_LINES))
    assert [line.traditional for line in lines] == [
        "係",
        "嘅",
        "嘅",
        "三",
        "佢哋",
        "空",
        "四",
    ]
    assert lines[3].meanings == ("three", "(slang) love affair")
    assert lines[4].jyutping == "keoi5 dei6"
    assert lines[5].meanings == ()


def test_jyutpings_tones_are_raised() -> None:
    assert cantonese.raised("keoi5 dei6") == "keoi⁵ dei⁶"
    assert cantonese.is_jyutping("hai6") and not cantonese.is_jyutping("AA ji1")


def rime(path: Path, rows: list[str]) -> Path:
    path.write_text(
        "# Rime dictionary\n---\nname: x\n...\n\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_the_everyday_reading_is_rimes(tmp_path: Path) -> None:
    """A word's reading from the word list (of two, the one its characters
    weigh more); a character's, its weightiest - none given is the full
    weight, so 嘅 is ge3, not koi3 (CC-Canto's own order)."""
    words = cantonese.read_rime_words(
        rime(
            tmp_path / "w.yaml",
            ["銀行\tngan4 hong4", "吖嗱\taa1 laa4", "吖嗱\taa1 naa4"],
        )
    )
    chars = cantonese.read_rime_chars(
        rime(
            tmp_path / "c.yaml",
            ["嘅\tge3", "嘅\tkoi3\t3%", "吖\taa1", "嗱\tlaa4\t3%", "嗱\tnaa4"],
        )
    )
    everyday = cantonese.Everyday(words, chars)
    assert everyday("銀行") == "ngan4 hong4"
    assert everyday("吖嗱") == "aa1 naa4"
    assert everyday("嘅") == "ge3"
    assert everyday("嘅嗱") == "ge3 naa4"  # character by character
    assert everyday("睇") is None


def test_hkcancor_counts_its_own_words(tmp_path: Path) -> None:
    path = tmp_path / "hkcancor.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("utf8/", "")
        archive.writestr(
            "utf8/FC-001_v",
            "<sent_tag>\n\t有/v1/jau5/\n\t真係/d/zan1hai6/\n\t。/w/VQ1/\n\t有/v1/jau5/\n",
        )
    assert cantonese.hkcancor_counts(path) == {"有": 2, "真係": 1}


def reads(table: dict[str, str]) -> cantonese.ReadsEveryday:
    """An everyday reading by `table`, of the readings given if any."""

    def everyday(form: str, among: Collection[str] | None = None) -> str | None:
        reading = table.get(form)
        return reading if among is None or reading in among else None

    return everyday


def cedict_line(trad: str, simp: str, pinyin: str, *meanings: str) -> CedictLine:
    return CedictLine(trad, simp, pinyin, meanings)


def draft() -> Draft:
    readings = {
        ("係", "系", "xi4"): ["hai6"],
        ("系", "系", "xi4"): ["hai6"],
        ("行", "行", "xing2"): ["hang4", "haang4"],
        ("行", "行", "hang2"): ["hong4"],
        ("銀行", "银行", "yinhang2"): ["ngan4 hong4"],
    }
    lines = [
        cedict_line("係", "系", "xi4", "to connect", "to be (literary)"),
        cedict_line("系", "系", "xi4", "system"),
        cedict_line("行", "行", "hang2", "row", "line"),
        cedict_line("行", "行", "xing2", "to walk", "to go"),
        cedict_line("銀行", "银行", "yin2 hang2", "bank"),
        cedict_line("嘅", "嘅", "kai3", "variant of 慨[kai3]"),
        cedict_line("𠮶", "𠮶", "ge3", "that"),  # no reading anywhere: left out
        cedict_line("四", "四", "si4", "four", "4"),
        cedict_line("四", "四", "Si4", "surname Si"),
        cedict_line("的", "的", "de5", "of; ~'s (possessive particle)"),
    ]
    readings |= {
        ("四", "四", "si4"): ["sei3"],
        ("四", "四", "Si4"): ["sei3"],
        ("的", "的", "de5"): ["dik1"],
    }
    usual = {
        "係": "hai6",
        "嘅": "ge3",
        "行": "haang4",
        "銀行": "ngan4 hong4",
        "四": "sei3",
        "的": "dik1",
    }
    return cantonese_draft(
        list(cantonese.parse(CANTO_LINES)),
        readings,
        lines,
        reads(usual),
        spoken={"係": 0.04, "嘅": 0.02},
        written={"银行": 0.002, "系": 0.001, "的": 0.06},
        # 10,000 words said: 銀行 once, 的 not at all
        said=cantonese.Said(Counter({"銀行": 1}), 10_000),
        senses={},
        own={},
    )


def test_a_forms_everyday_reading_comes_first_and_cc_canto_before_cc_cedict() -> None:
    d = draft()
    by_key = {e.key: e for e in d.entries}

    def shown(form: str) -> list[tuple[str, str]]:
        return [(by_key[k].reading, by_key[k].meanings[0]) for k in d.forms[form]]

    # CC-Canto's 係 has CC-CEDICT's reading: CC-CEDICT's entry is left to it
    assert shown("係") == [("hai⁶", "(Cantonese) to be")]
    # ge3 (everyday) before koi3; CC-CEDICT's 嘅 has no reading in the
    # readings file, so rime's everyday ge3 - which CC-Canto has already
    assert shown("嘅") == [
        ("ge³", "possessive marker"),
        ("koi³", "(final particle) surprise"),
    ]
    # rime's haang4 is among the readings file's: the walk; the row after
    assert shown("行") == [("haang⁴", "to walk"), ("hong⁴", "row")]
    assert "𠮶" not in d.forms


def test_a_simplified_form_finds_its_word_unless_it_is_a_word_itself() -> None:
    d = draft()
    by_key = {e.key: e for e in d.entries}
    assert [by_key[k].headword for k in d.forms["银行"]] == ["銀行"]
    assert [by_key[k].headword for k in d.forms["系"]] == ["系"]  # not 係
    assert [by_key[k].headword for k in d.forms["渠哋"]] == ["佢哋"]


def test_ranks_average_speech_and_writing() -> None:
    counted = draft().counted[CANTONESE_RANKS]
    # CC-Canto writes 係 as its own Simplified form: written Chinese's 系 (a
    # Mandarin "system" as much as 係) isn't counted for it
    assert counted["係"] == 0.02
    assert counted["嘅"] == 0.01  # Cantonese's own: speech alone
    assert counted["銀行"] == 0.001  # by its Simplified form, 银行
    assert "佢哋" not in counted
    assert draft().keep_unranked


def test_a_word_written_far_more_than_it_is_said_ranks_by_speech() -> None:
    """的 is Mandarin's commonest word, not Cantonese's (polyglotic-hq 467):
    written 0.06 of the time and never said in 10,000 words, it counts in
    writing only as if said once - far below 銀行, which speech bears out."""
    counted = draft().counted[CANTONESE_RANKS]
    assert counted["的"] == pytest.approx((0 + 1 / 10_000) / 2)
    assert counted["的"] < counted["銀行"] < counted["嘅"]


def test_said_bounds_only_what_speech_doesnt_bear_out() -> None:
    said = cantonese.Said(Counter({"被": 15}), 100_000)
    # 被 is said 15 times: written 0.003 is under 50 times (15 + 1) / 100,000
    assert said.written("被", 0.003) == 0.003
    # 他 is never said: written 0.005 is 500 times (0 + 1) / 100,000
    assert said.written("他", 0.005) == pytest.approx(1 / 100_000)


def test_said_counts_runs_of_hkcancors_words_and_the_captions_words() -> None:
    utterances = [
        cantonese.Utterance("a", ("有", "一", "個", "人", "。"), ("",) * 5),
        cantonese.Utterance("b", ("一個", "被"), ("", "")),
    ]
    said = cantonese.said(utterances, ["被告被關入監獄，OK"], {"一個", "被告", "監獄"})
    # 一 + 個 is a run of HKCanCor's words that a dictionary has whole
    assert said.counts["一個"] == 2
    assert said.counts["一"] == 1 and "有一" not in said.counts
    # the caption cut into the pack's forms: 被告 / 被 / 關 / 入 / 監獄
    assert said.counts["被"] == 2 and said.counts["被告"] == 1
    assert said.total == 6 + 5  # HKCanCor's Chinese words, then the caption's


def test_hkcancor_is_read_as_utterances_with_each_words_jyutping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "hkcancor.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "utf8/FC-001_v",
            "<info>\n1-TN-R011\n</info>\n<sent>\n<sent_tag>\n\t有/v1/jau5/\n"
            "\t官司/n/gun1si1/\n\t。/w/VQ1/\n</sent_tag>\n</sent>\n"
            "<sent_tag>\n\t會/vu/wui5/\n</sent_tag>\n",
        )
    utterances = cantonese.hkcancor_utterances(path)
    assert [u.words for u in utterances] == [("有", "官司", "。"), ("會",)]
    assert utterances[0].readings == ("jau5", "gun1 si1", "")
    assert cantonese.heard_readings(utterances) == {
        "有": Counter({"jau5": 1}),
        "官司": Counter({"gun1 si1": 1}),
        "會": Counter({"wui5": 1}),
    }


def test_a_word_is_read_as_hkcancors_speakers_mostly_say_it() -> None:
    """會 is wui5 ("will") 9 times in 10, though rime-cantonese weighs the
    literary wui6 first (polyglotic-hq 467)."""
    chars = {
        "會": {"wui6": 100.0, "wui5": 100.0, "wui2": 5.0},
        "上": {"soeng6": 100.0},
    }
    heard = {
        "會": Counter({"wui5": 9, "wui6": 1}),
        "上": Counter({"soeng5": 6, "soeng6": 4}),  # rime hasn't soeng5 for 上
        "返": Counter({"faan1": 3}),  # too few
    }
    rime = cantonese.Everyday({"會": ["wui6"]}, chars)
    everyday = cantonese.Everyday({"會": ["wui6"]}, chars, heard)
    assert rime("會") == "wui6"
    assert everyday("會") == "wui5"
    assert everyday("上") == "soeng6"
    assert everyday("返") is None  # no reading in rime either
    # of the readings a word's entries have: 會's entries are read wui6 and
    # wui2 only, so rime-cantonese's choice stands
    assert everyday("會", {"wui6", "wui2"}) == "wui6"
    assert everyday("會", {"wui5", "wui6"}) == "wui5"
    assert everyday("會", {"wui2"}) is None


def test_cc_cedicts_meaning_comes_first_where_cc_canto_only_adds_slang() -> None:
    """四: CC-Canto has only "(slang) labourer", CC-CEDICT "four" with the
    same reading - both are kept, "four" first; CC-CEDICT's surname entry
    only points elsewhere, so it is left out (polyglotic-hq 461 and 467)."""
    d = draft()
    by_key = {e.key: e for e in d.entries}
    assert [by_key[k].meanings[0] for k in d.forms["四"]] == [
        "four",
        "(slang) labourer",
    ]


def test_the_commonest_words_open_on_the_meanings_a_learner_hears() -> None:
    """The by-hand table and the pack's own meanings (polyglotic-hq 467):
    行 opens on its row entry's "line" (read the everyday way too), with an
    own meaning before it; a meaning no entry has stops the build."""
    lines = [
        cedict_line("行", "行", "xing2", "to walk", "to go"),
        cedict_line("行", "行", "hang2", "row", "line"),
    ]
    readings = {("行", "行", "xing2"): ["haang4"], ("行", "行", "hang2"): ["haang4"]}

    def build(senses: dict[str, tuple[str, ...]]) -> Draft:
        return cantonese_draft(
            [],
            readings,
            lines,
            reads({"行": "haang4"}),
            spoken={},
            written={},
            said=cantonese.Said(Counter(), 1),
            senses=senses,
            own={"行": ("to go (Cantonese)",)},
        )

    d = build({"行": ("line", "row")})
    by_key = {e.key: e for e in d.entries}
    assert [by_key[k].meanings for k in d.forms["行"]] == [
        ("to go (Cantonese)", "line", "row"),
        ("to walk", "to go"),
    ]
    with pytest.raises(ValueError, match="行"):
        build({"行": ("to run",)})


def test_an_entry_merged_from_several_lines_is_placed_by_all_its_meanings() -> None:
    """CC-Canto's 曾 has a line of only "Chinese surname" before its line of
    "once": the merged entry isn't a surname's, so it stays before
    CC-CEDICT's "great-"; and the line CC-Canto starts with a part of speech
    comes after the plain one (polyglotic-hq 467)."""
    canto = list(
        cantonese.parse(
            [
                "曾 曾 [ceng2] {cang4} /(noun) Chinese surname/",
                "曾 曾 [ceng2] {cang4} /once/already/",
            ]
        )
    )
    lines = [cedict_line("曾", "曾", "zeng1", "great- (grandfather etc)")]
    d = cantonese_draft(
        canto,
        {("曾", "曾", "zeng1"): ["cang4"]},
        lines,
        reads({"曾": "cang4"}),
        spoken={},
        written={},
        said=cantonese.Said(Counter(), 1),
        senses={},
        own={},
    )
    by_key = {e.key: e for e in d.entries}
    assert [by_key[k].meanings for k in d.forms["曾"]] == [
        ("once", "already", "(noun) Chinese surname"),
        ("great- (grandfather etc)",),
    ]


def test_cc_cantos_tagged_line_comes_after_its_plain_line() -> None:
    """法: CC-Canto's own line "(noun) 1. The short form of France" was the
    card's first meaning; the line adapted from CC-CEDICT ("law") now is
    (polyglotic-hq 467). Lines all plain or all tagged keep their order."""
    tagged = ("(noun) 1. The short form of France",)
    plain = ("law", "method")
    assert cantonese.one_entry([tagged, plain]) == (*plain, *tagged)
    assert cantonese.one_entry([plain, ("law", "way")]) == ("law", "method", "way")


def test_a_variant_opens_on_its_word_and_isnt_ranked_by_writing() -> None:
    """瞭解 only says "variant of 了解": its card opens on 了解's meanings,
    then its own; and 尒 ("variant of 爾") isn't ranked by Simplified 尔's
    written share (polyglotic-hq 467)."""
    lines = [
        cedict_line("瞭解", "了解", "liao3 jie3", "variant of 了解[liao3 jie3]"),
        cedict_line("了解", "了解", "liao3 jie3", "to understand"),
        cedict_line("尒", "尔", "er3", "variant of 爾|尔[er3]"),
        cedict_line("爾", "尔", "er3", "you"),
    ]
    readings = {
        ("瞭解", "了解", "liao3jie3"): ["liu5 gaai2"],
        ("了解", "了解", "liao3jie3"): ["liu5 gaai2"],
        ("尒", "尔", "er3"): ["ji5"],
        ("爾", "尔", "er3"): ["ji5"],
    }
    d = cantonese_draft(
        [],
        readings,
        lines,
        reads({}),
        spoken={},
        written={"尔": 0.001},
        said=cantonese.Said(Counter({"爾": 100}), 1000),
        senses={},
        own={},
    )
    by_key = {e.key: e for e in d.entries}
    assert [by_key[k].meanings[0] for k in d.forms["瞭解"]] == [
        "to understand",
        "variant of 了解[liao3 jie3]",
    ]
    counted = d.counted[CANTONESE_RANKS]
    assert "尒" not in counted and counted["爾"] == 0.0005


def test_the_packs_own_meaning_goes_on_the_words_own_entry() -> None:
    """晒 ("all", after a verb) only says "variant of 曬" in CC-CEDICT: the
    pack's own meaning goes on 晒's entry, not on 曬's (polyglotic-hq 467)."""
    lines = [
        cedict_line("晒", "晒", "shai4", "variant of 曬|晒[shai4]"),
        cedict_line("曬", "晒", "shai4", "to dry in the sun"),
    ]
    readings = {
        ("晒", "晒", "shai4"): ["saai3"],
        ("曬", "晒", "shai4"): ["saai3"],
    }
    d = cantonese_draft(
        [],
        readings,
        lines,
        reads({}),
        spoken={},
        written={},
        said=cantonese.Said(Counter(), 1),
        senses={},
        own={"晒": ("all; completely",)},
    )
    by_key = {e.key: e for e in d.entries}
    assert [by_key[k].meanings for k in d.forms["晒"]] == [
        ("all; completely", "variant of 曬|晒[shai4]")
    ]
    assert [by_key[k].meanings for k in d.forms["曬"]] == [("to dry in the sun",)]
