"""The dictionary build (decision 0009), end to end on small fixtures in
the sources' real formats: fetching with checksums, CC-CEDICT with jieba
ranks and both HSK schemes, ECDICT cut with inflections, the credits."""

import dataclasses
import gzip
import hashlib
import sys
import zipfile
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from tests.lexicon.sample import CEDICT_SAMPLE
from tests.tools.wordfreq_data import msgpack
from tools.dictionaries import build, ecdict, sources, treebanks
from tools.dictionaries.entry_ids import Registry, default_id

from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.lexicon.entries import (
    ENGLISH_FREQUENCY,
    HSK_2021,
    HSK_2025,
)
from polyglotic_desktop.core.shared import Level

JIEBA = (
    "的 318825 uj\n人 120000 n\n电脑 4000 n\n游戏 3000 n\n这个 9000 r\n不在词典 99 x\n"
)
HSK_2025_WORDS = "word\tlevel\n人\t1\n电脑\t1\n游戏\t3\n北京\t1\n还\t1\n不在词典\t2\n"
HSK_2021_WORDS = "word\tlevel\n人\t1\n电脑\t1\n游戏\t2\n还\t1\n还\t3\n"

HEADER = "word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,exchange,detail,audio"
SECRET = "COLLINS-ONLY"  # must never reach the file
ECDICT_CSV = "\n".join(
    [
        HEADER,
        f'run,rʌn,,"v. 跑\\nn. 赛跑",,{SECRET},{SECRET},zk gk,208,202,p:ran/i:running/d:run/0:run/1:d/3:runs,,',
        "ran,ræn,,run的过去式,,,,,0,0,0:run/1:p,,",
        "running,ˈrʌnɪŋ,,n. 赛跑,,,,gk,3269,3252,0:run/1:i,,",
        "leave,liːv,,v. 离开,,,,zk,300,280,p:left/d:left/i:leaving/3:leaves,,",
        "left,left,,a. 左边的,,,,zk,1045,771,0:leave/1:dp,,",
        "English,ˈɪŋɡlɪʃ,,n. 英语,,,,zk,1974,1900,,,",
        "procrastinate,,,v. 拖延,,,,gre,0,0,,,",
        "obscurity,,,n. 无名,,,,,0,0,,,",
        "'tween,twi:n,,prep. [诗歌用语] = between,,,,,0,0,,,",
        "",
    ]
)


# Centibels below 1 -> words: "run" is 10^-2.5 of all words, "ran" 10^-3...
# CMUdict, cut down: the words the wordfreq sample ranks (polyglotic-hq 511)
CMUDICT_SAMPLE = """english IH1 NG G L IH0 SH
left L EH1 F T
procrastinate P R OW0 K R AE1 S T AH0 N EY2 T
run R AH1 N
running R AH1 N IH0 NG
runs R AH1 N Z
"""
WORDFREQ_BUCKETS = {
    250: ["run", "english"],
    300: ["ran", "running", "leave"],
    350: ["left"],
    500: ["procrastinate"],
}


# Open English WordNet's WN-LMF, cut down: "run" as a noun (listed first,
# as the file's order has it) and a verb, "leave", and "procrastinate".
OEWN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource xmlns:dc="https://globalwordnet.github.io/schemas/dc/">
  <Lexicon id="oewn" label="Open English Wordnet" language="en" version="2025+">
    <LexicalEntry id="oewn-run-n">
      <Lemma writtenForm="run" partOfSpeech="n"/>
      <Sense id="oewn-run__1.04.00.." synset="oewn-1-n"/>
    </LexicalEntry>
    <LexicalEntry id="oewn-run-v">
      <Lemma writtenForm="run" partOfSpeech="v"/>
      <Form writtenForm="ran"/>
      <Sense id="oewn-run__2.38.00.." synset="oewn-2-v"/>
      <Sense id="oewn-run__2.38.04.." synset="oewn-3-v"/>
    </LexicalEntry>
    <LexicalEntry id="oewn-leave-v">
      <Lemma writtenForm="leave" partOfSpeech="v"/>
      <Sense id="oewn-leave__2.38.00.." synset="oewn-4-v"/>
    </LexicalEntry>
    <LexicalEntry id="oewn-procrastinate-v">
      <Lemma writtenForm="procrastinate" partOfSpeech="v"/>
      <Sense id="oewn-procrastinate__2.42.00.." synset="oewn-5-v"/>
    </LexicalEntry>
    <Synset id="oewn-1-n" partOfSpeech="n">
      <Definition>a score in baseball made by a runner touching all four bases</Definition>
    </Synset>
    <Synset id="oewn-2-v" partOfSpeech="v">
      <Definition>move fast by using one&apos;s feet; with one foot off the ground</Definition>
      <Example>Don&apos;t run - you&apos;ll be out of breath</Example>
    </Synset>
    <Synset id="oewn-3-v" partOfSpeech="v">
      <Definition>flee; take to one&apos;s heels</Definition>
    </Synset>
    <Synset id="oewn-4-v" partOfSpeech="v">
      <Definition>go away from a place</Definition>
      <Example>At what time does your train leave?</Example>
    </Synset>
    <Synset id="oewn-5-v" partOfSpeech="v">
      <Definition>postpone doing what one should be doing</Definition>
    </Synset>
  </Lexicon>
</LexicalResource>
"""
# UD English-EWT, cut down: "run" a verb three times, a noun once.
EWT = "".join(
    f"# sent_id = {n}\n"
    + "\t".join((str(1), form, lemma, tag, *"__0", "root", *"__"))
    + "\n\n"
    for n, (form, lemma, tag) in enumerate(
        [("run", "run", "VERB"), ("ran", "run", "VERB"), ("runs", "run", "VERB")]
        + [("run", "run", "NOUN"), ("left", "leave", "VERB")]
    )
)


def fixture_sources(folder: Path) -> dict[str, sources.Source]:
    """The sources as files under `folder`, pinned to their checksums."""
    folder.mkdir()
    (folder / "cedict.txt.gz").write_bytes(gzip.compress(CEDICT_SAMPLE.encode("utf-8")))
    (folder / "jieba.txt").write_text(JIEBA, encoding="utf-8")
    with zipfile.ZipFile(folder / "hsk30.whl", "w") as wheel:
        wheel.writestr("hsk30/data/hsk2025_words.tsv", HSK_2025_WORDS)
        wheel.writestr("hsk30/data/hsk30_words.tsv", HSK_2021_WORDS)
        wheel.writestr("hsk30/__init__.py", "raise SystemExit('never run')\n")
    (folder / "ecdict.csv").write_text(ECDICT_CSV, encoding="utf-8")
    buckets: list[object] = [WORDFREQ_BUCKETS.get(i, []) for i in range(800)]
    data = msgpack([{"format": "cB", "version": 1}, *buckets])
    with zipfile.ZipFile(folder / "wordfreq.whl", "w") as wheel:
        wheel.writestr("wordfreq/data/large_en.msgpack.gz", gzip.compress(data))
    (folder / "oewn.xml.gz").write_bytes(gzip.compress(OEWN_XML.encode("utf-8")))
    for ewt in treebanks.of("en"):
        (folder / f"{ewt.name}.conllu").write_text(EWT, encoding="utf-8")
    (folder / "cmudict.dict").write_text(CMUDICT_SAMPLE, encoding="utf-8")
    pinned = {}
    for real, name in (
        (sources.CEDICT, "cedict.txt.gz"),
        (sources.JIEBA, "jieba.txt"),
        (sources.HSK30, "hsk30.whl"),
        (sources.ECDICT, "ecdict.csv"),
        (sources.WORDFREQ, "wordfreq.whl"),
        (sources.OEWN, "oewn.xml.gz"),
        (sources.CMUDICT, "cmudict.dict"),
        *((ewt, f"{ewt.name}.conllu") for ewt in treebanks.of("en")),
    ):
        path = folder / name
        pinned[real.name] = dataclasses.replace(
            real,
            url=path.resolve().as_uri(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            filename=f"fetched-{name}",
        )
    return pinned


def built(tmp_path: Path, monkeypatch: MonkeyPatch, *options: str) -> Path:
    pinned = fixture_sources(tmp_path / "upstream")
    ewt = {s.name for s in treebanks.of("en")}
    monkeypatch.setattr(
        build, "SOURCES", tuple(s for s in pinned.values() if s.name not in ewt)
    )
    monkeypatch.setattr(build, "TREEBANKS", tuple(pinned[name] for name in sorted(ewt)))
    monkeypatch.setattr(build, "REGISTRY", tmp_path / "registry")
    (tmp_path / "registry").mkdir()
    out = tmp_path / "out"
    args = ["--sources", str(tmp_path / "downloads"), "--out", str(out), *options]
    assert build.main(args) == 0
    return out


def test_fetch_checks_the_pinned_checksum(tmp_path: Path) -> None:
    pinned = fixture_sources(tmp_path / "upstream")
    path = sources.fetch(pinned["jieba"], tmp_path / "downloads")
    assert path.read_text(encoding="utf-8") == JIEBA
    assert sources.fetch(pinned["jieba"], tmp_path / "downloads") == path  # kept
    wrong = dataclasses.replace(pinned["jieba"], sha256="0" * 64, filename="other.txt")
    with pytest.raises(sources.ChecksumError):
        sources.fetch(wrong, tmp_path / "downloads")
    assert not (tmp_path / "downloads" / "other.txt").exists()


def test_the_chinese_dictionary_has_ranks_both_hsk_schemes_and_names(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    file = SqliteDictionary(built(tmp_path, monkeypatch) / "cedict.sqlite")
    d = ChineseDictionary(file)
    computer = d.lookup("电脑")[0]
    assert computer.entry_id == default_id("cedict", "電腦 电脑 [dian4 nao3]")
    assert computer.frequency_rank == 3  # 人, 这个, then 电脑 (的 isn't in the sample)
    game = d.lookup("游戏")[0]
    assert game.level_in(HSK_2025) == 3 and game.level_in(HSK_2021) == 2
    assert game.is_at_or_below(Level("hsk-2021", 2))
    assert not game.is_at_or_below(Level("hsk-2025", 2))
    # Listed twice in the 2021 table: the lower level. Both readings of 还
    # get it: the lists give no pinyin.
    assert [e.level_in(HSK_2021) for e in d.lookup("还")] == [1, 1]
    beijing = d.lookup("北京")[0]
    assert beijing.is_name and beijing.level_in(HSK_2025) == 1  # the only entry
    assert d.split("我们一起打游戏") == [(0, 1), (1, 2), (2, 3), (3, 4), (4, 7)]
    assert d.reverse_lookup("computer")[0] == computer
    assert file.info["dictionary"] == "cedict" and "jieba" in file.info["sources"]


def test_the_english_dictionary_is_cut_with_inflections_and_ranks(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    path = built(tmp_path, monkeypatch) / "ecdict.sqlite"
    d = EnglishDictionary(SqliteDictionary(path))
    run = d.lookup("run")[0]
    assert run.meanings == ("v. 跑", "n. 赛跑") and run.reading == "rʌn"
    assert d.entry_for_word("ran") == run and d.entry_for_word("running") == run
    assert d.entry_for_word("left") == d.lookup("leave")[0]
    assert [e.headword for e in d.lookup("left")] == ["leave", "left"]
    # wordfreq ranks: an entry counts its inflected forms - run (+ran,
    # running) before English; leave (+left) before running and left.
    words = ("run", "English", "leave", "running", "left", "procrastinate")
    ranks = {w: d.lookup(w)[-1].frequency_rank for w in words}
    assert list(ranks.values()) == [1, 2, 3, 4, 5, 6]
    assert run.level_in(ENGLISH_FREQUENCY) == 1
    assert d.lookup("obscurity") == []  # cut: no rank, no exam list
    assert d.lookup("ran")[0] == run  # no entry of its own: only "run的过去式"
    assert d.lookup("English")[0].is_name
    assert SECRET.encode() not in path.read_bytes()


def test_the_english_dictionary_in_english_has_the_same_entries_in_english(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """`ecdict-en.sqlite` (polyglotic-hq 447, decision 0211): ECDICT's
    entries, IDs, inflections and ranks with English meanings - so a word
    saved in either is the same word - our own where WordNet has none,
    WordNet's verb first for "run" (the treebank's commoner use)."""
    out = built(tmp_path, monkeypatch)
    chinese = SqliteDictionary(out / "ecdict.sqlite")
    file = SqliteDictionary(out / "ecdict-en.sqlite")
    try:
        zh, en = EnglishDictionary(chinese), EnglishDictionary(file)
        for word in ("run", "ran", "left", "English", "procrastinate", "'tween"):
            assert [
                (e.entry_id, e.headword, e.frequency_rank) for e in en.lookup(word)
            ] == [
                (e.entry_id, e.headword, e.frequency_rank) for e in zh.lookup(word)
            ], word
        run = en.lookup("run")[0]
        assert run.meanings == (
            "(verb) move fast by using one's feet: \"Don't run - you'll be out of breath\"",
            "(verb) flee; take to one's heels",  # too short to cut
            "(noun) a score in baseball made by a runner touching all four bases",
        )
        assert en.lookup("ran")[0] == run
        assert (
            en.lookup("leave")[0].meanings[0].startswith("(verb) go away from a place")
        )
        # "left" has an entry of its own: what it is a form of
        assert en.lookup("left")[1].meanings == (
            "(verb) past tense and past participle of leave",
        )
        assert file.info["meanings"] == "en" and "oewn" in file.info["sources"]
        assert SECRET.encode() not in (out / "ecdict-en.sqlite").read_bytes()
    finally:
        chinese.close()
        file.close()


def test_the_english_dictionaries_respell_the_commonest_words(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """511: the reading line over English reads how a word sounds (471's
    respelling, KAY-oss) as the English dictionary's form reading - in
    both English files; a word CMUdict hasn't got has none."""
    out = built(tmp_path, monkeypatch)
    for name in ("ecdict.sqlite", "ecdict-en.sqlite"):
        file = SqliteDictionary(out / name)
        try:
            assert file.form_reading("procrastinate") == "proh-KRAS-tuh-nayt"
            assert file.form_reading("running") == "RUN-ing"
            assert file.form_reading("runs") == "RUNZ"  # a form wordfreq lacks
            assert file.form_reading("ran") == ""  # not in CMUdict
        finally:
            file.close()


def test_credits_name_every_source_with_its_licence(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    text = (built(tmp_path, monkeypatch) / "CREDITS.md").read_text(encoding="utf-8")
    for source in sources.SOURCES:
        assert source.title in text and source.notice in text
    assert "SUBTLEX is freely available data" in text
    assert "CC BY-SA 4.0" in text and "Permission is hereby granted" in text
    # Open English WordNet: CC BY, and Princeton WordNet's notice with it
    assert "UD_English-EWT" in text and "Princeton University" in text


def test_the_build_is_repeatable(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    out = built(tmp_path, monkeypatch)
    first = {p.name: p.read_bytes() for p in out.iterdir()}
    assert (
        build.main(["--sources", str(tmp_path / "downloads"), "--out", str(out)]) == 0
    )
    assert {p.name: p.read_bytes() for p in out.iterdir()} == first


def test_one_dictionary_alone_from_its_own_sources(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """`--only cedict`: CI's start gate needs CC-CEDICT alone, without
    ECDICT's and wordfreq's downloads (polyglotic-hq 229)."""
    out = built(tmp_path, monkeypatch, "--only", "cedict")

    assert sorted(p.name for p in out.glob("*.sqlite")) == ["cedict.sqlite"]
    assert sorted(p.name for p in (tmp_path / "downloads").iterdir()) == [
        "fetched-cedict.txt.gz",
        "fetched-hsk30.whl",
        "fetched-jieba.txt",
    ]
    file = SqliteDictionary(out / "cedict.sqlite")
    try:
        assert file.info["dictionary"] == "cedict"
    finally:
        file.close()


def test_the_ecdict_cut_and_frequency_ranks() -> None:
    rows = [
        ecdict.EcdictRow("a", "", ("x",), (), bnc=5, frq=0, exchange={}),
        ecdict.EcdictRow("b", "", ("x",), (), bnc=9, frq=2, exchange={}),
        ecdict.EcdictRow("c", "", ("x",), ("cet4",), bnc=0, frq=0, exchange={}),
        ecdict.EcdictRow("d", "", (), ("cet4",), bnc=1, frq=1, exchange={}),
    ]
    assert [r.word for r in ecdict.cut(rows)] == ["a", "b", "c"]  # d: no meanings
    assert ecdict.frequency_ranks(ecdict.cut(rows)) == {"b": 1, "a": 2}


def _row(word: str, rank: int, meaning: str, **exchange: str) -> ecdict.EcdictRow:
    return ecdict.EcdictRow(word, "", (meaning,), (), rank, rank, exchange)


def test_a_form_opens_on_the_likelier_of_its_lemmas() -> None:
    """ECDICT's "does" says "0:doe" (the deer's plural), and "do" lists it:
    the card opened on "doe" (polyglotic-hq 447's top-200 check). A lemma
    that lists the form wins over the form's own "0:" when it's commoner,
    the form is its regular inflection, and a verb for a verb's form -
    unless the form's own meaning names its "0:" (polyglotic-hq 462)."""
    rows = [
        _row("do", 18, "v. 做", **{"3": "does"}),
        _row("doe", 9309, "n. 母鹿", s="does"),
        _row("does", 0, "v. 做（do的第三人称单数形式）", **{"0": "doe"}),
        # "fee" lists "feeding" (wrongly): not its regular -ing
        _row("fee", 1618, "vt. 付费给", i="feeding"),
        _row("feed", 1317, "v. 喂", i="feeding"),
        _row("feeding", 10712, "n. 饲养", **{"0": "feed"}),
        # "ting" lists "tinged" too, but is rarer than "tinge"
        _row("ting", 21626, "v. 发叮叮声", p="tinged"),
        _row("tinge", 14082, "vt. 染", p="tinged"),
        _row("tinged", 0, "a. 淡色的", **{"0": "tinge"}),
        # "bath" is commoner and lists "bathed", but isn't a verb
        _row("bath", 2551, "n. 沐浴", p="bathed"),
        _row("bathe", 7550, "vt. 沐浴", p="bathed"),
        _row("bathed", 0, "a. 沐浴的", **{"0": "bathe"}),
        # "palled" says it's pall's
        _row("pal", 5020, "vi. 结为朋友", p="palled"),
        _row("pall", 20025, "vi. 生厌", p="palled"),
        _row("palled", 0, "v. 生厌( pall的过去式 )", **{"0": "pall"}),
        _row("ruin", 2000, "vt. 毁灭", p="ruined"),
        _row("ruine", 30000, "n. 废墟", p="ruined"),
        _row("ruined", 10136, "a. 毁灭的", **{"0": "ruine"}),
        _row("be", 2, "v. 是", **{"3": "is"}),
        _row("AM", 1192, "be的单数第一人称"),
    ]
    kept = {row.word for row in ecdict.cut(rows)}
    lemmas = ecdict.lemmas(rows, kept)
    assert lemmas["does"] == "do"
    assert lemmas["ruined"] == "ruin"
    assert lemmas["feeding"] == "feed"
    assert lemmas["tinged"] == "tinge"
    assert lemmas["bathed"] == "bathe"
    assert lemmas["palled"] == "pall"
    # ECDICT has "am" only as "AM": it's be's
    assert lemmas["am"] == "be" and lemmas["is"] == "be"


def test_the_regular_forms_of_a_lemma() -> None:
    assert "does" in ecdict.regular_forms("do", "3")
    assert "watches" in ecdict.regular_forms("watch", "3")
    assert "cities" in ecdict.regular_forms("city", "s")
    assert "analyses" in ecdict.regular_forms("analysis", "s")
    assert {"loved"} <= ecdict.regular_forms("love", "p")
    assert {"stopped", "panicked"} <= (
        ecdict.regular_forms("stop", "d") | ecdict.regular_forms("panic", "d")
    )
    assert "carried" in ecdict.regular_forms("carry", "p")
    assert {"making", "dying", "stopping"} <= (
        ecdict.regular_forms("make", "i")
        | ecdict.regular_forms("die", "i")
        | ecdict.regular_forms("stop", "i")
    )
    assert "feeding" not in ecdict.regular_forms("fee", "i")
    assert {"bigger", "biggest", "nicer", "happiest"} <= (
        ecdict.regular_forms("big", "r")
        | ecdict.regular_forms("big", "t")
        | ecdict.regular_forms("nice", "r")
        | ecdict.regular_forms("happy", "t")
    )


def test_update_ids_reads_ecdict_too(tmp_path: Path) -> None:
    from tools.dictionaries import update_ids

    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    old.write_text(ECDICT_CSV.replace("English,", "english,"), encoding="utf-8")
    new.write_text(ECDICT_CSV, encoding="utf-8")
    registry = tmp_path / "ecdict.tsv"
    assert (
        update_ids.main(["ecdict", str(old), str(new), "--registry", str(registry)])
        == 0
    )
    assert Registry.load(registry, "ecdict").ids == {
        "English": default_id("ecdict", "english")
    }


def test_english_ranks_can_come_from_ecdict_instead(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    out = built(tmp_path, monkeypatch, "--english-frequency", "ecdict")
    file = SqliteDictionary(out / "ecdict.sqlite")
    d = EnglishDictionary(file)
    assert d.lookup("run")[0].frequency_rank == 1
    assert d.lookup("procrastinate")[0].frequency_rank is None  # kept: on an exam list
    assert file.info["frequency_source"] == "ecdict"
    assert file.info["licence"] == "MIT"


def test_the_everyday_meaning_comes_first_and_capitals_are_found_in_lower_case(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """polyglotic-hq 463's top-500 check of `ecdict.sqlite`: "can" opened
    on 装罐 ("to can", as in tins) - ECDICT's own order - though English
    uses it as an auxiliary; "tv" was in neither dictionary (ECDICT has
    only "TV"); "number" opened on numb (ECDICT: numb's comparative)."""
    this = sys.modules[__name__]
    rows = [
        HEADER,
        'can,kæn,,"vt. 装罐\\nn. 罐头, 容器\\naux. 能, 可以",,,,zk,70,60,p:canned/d:canned/i:canning/3:cans/s:cans,,',
        'TV,,,"电视\\n[计] 电视, 转移向量",,,,,900,800,,,',
        "numb,nʌm,,a. 麻木的,,,,gk,12639,9317,d:numbed/r:number,,",
        'number,,,"n. 数, 数字\\nvt. 数",,,,zk,143,204,0:numb/1:r/s:numbers,,',
        "",
    ]
    monkeypatch.setattr(this, "ECDICT_CSV", "\n".join(rows))
    monkeypatch.setattr(this, "WORDFREQ_BUCKETS", {250: ["can", "number"], 300: ["tv"]})
    sentences = [("can", "can", "AUX")] * 3 + [("tv", "tv", "NOUN")]
    monkeypatch.setattr(
        this,
        "EWT",
        "".join(
            f"# sent_id = {n}\n"
            + "\t".join((str(1), form, lemma, tag, *"__0", "root", *"__"))
            + "\n\n"
            for n, (form, lemma, tag) in enumerate(sentences)
        ),
    )
    out = built(tmp_path, monkeypatch)
    for name in ("ecdict.sqlite", "ecdict-en.sqlite"):
        file = SqliteDictionary(out / name)
        try:
            d = EnglishDictionary(file)
            assert [e.headword for e in d.lookup("tv")] == ["TV"], name
            assert [e.headword for e in d.lookup("TV")] == ["TV"], name
            assert d.lookup("number")[0].headword == "number", name
            if name == "ecdict.sqlite":
                assert d.lookup("can")[0].meanings == (
                    "aux. 能, 可以",
                    "vt. 装罐",
                    "n. 罐头, 容器",
                )
                assert d.lookup("number")[0].meanings[0] == "n. 数, 数字"
        finally:
            file.close()


def test_a_word_ecdict_makes_a_form_of_another_is_not_one() -> None:
    """ECDICT's "number" says "0:numb" (numb's comparative), and numb lists
    it: the card for "number" opened on 麻木的 (polyglotic-hq 463)."""
    rows = [
        _row("numb", 9317, "a. 麻木的", r="number"),
        _row("number", 143, "n. 数", **{"0": "numb", "1": "r"}),
        _row("good", 50, "a. 好的", r="better"),
        _row("better", 452, "a. 较好的", **{"0": "good", "1": "r"}),
    ]
    lemmas = ecdict.lemmas(rows, {row.word for row in ecdict.cut(rows)})
    assert "number" not in lemmas
    assert lemmas["better"] == "good"


def test_words_ecdict_has_only_in_capitals_are_found_in_lower_case() -> None:
    kept = {"TV", "OK", "UK", "ALICE"}
    found = ecdict.lower_case_forms(kept)
    assert found["tv"] == "TV" and found["ok"] == "OK" and found["uk"] == "UK"
    assert "alice" not in found  # ALICE is a computing term, not Alice
    assert ecdict.lower_case_forms({"TV", "tv"}) == {}  # "tv" has its own


def test_given_names_are_names_and_a_bit_is_not_a_bite(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """polyglotic-hq 464's top-500 check: "John" opened john, 厕所
    ("toilet"), as ECDICT has no "John"; "mary" (玛丽（女子名）) was a word,
    counted as heard; "bit" opened bite (咬) and counted for it; "evening"
    opened even. In both dictionaries."""
    this = sys.modules[__name__]
    rows = [
        HEADER,
        "john,dʒɒn,,n. 厕所,,,,,30000,30000,,,",
        'bill,bɪl,,"n. 帐单\\nvt. 开帐单",,,,zk,900,900,,,',
        "mary,ˈmεəri,,n. 玛丽（女子名）,,,,,2000,2000,,,",
        "shortlist,,,n. 候选人名单,,,,,9000,9000,,,",
        "bite,baɪt,,v. 咬,,,,zk,2000,2000,p:bit/d:bitten/3:bites,,",
        "bit,bɪt,,n. 少量,,,,zk,400,400,0:bite/1:p,,",
        "even,ˈiːvn,,adv. 甚至,,,,zk,100,100,i:evening,,",
        "evening,ˈiːvnɪŋ,,n. 傍晚,,,,zk,500,500,0:even/1:i,,",
        "",
    ]
    monkeypatch.setattr(this, "ECDICT_CSV", "\n".join(rows))
    monkeypatch.setattr(
        this,
        "WORDFREQ_BUCKETS",
        {250: ["bit", "even"], 300: ["bill", "evening"], 350: ["bite", "mary"]},
    )
    out = built(tmp_path, monkeypatch)
    for name in ("ecdict.sqlite", "ecdict-en.sqlite"):
        file = SqliteDictionary(out / name)
        try:
            d = EnglishDictionary(file)
            john = d.lookup("John")
            assert [e.headword for e in john] == ["John"], name
            assert john[0].is_name and john[0].reading == "dʒɒn"
            assert [e.headword for e in d.lookup("Bill")] == ["bill", "Bill"], name
            bill = d.lookup("Bill", inside=True)
            assert [e.headword for e in bill] == ["Bill", "bill"], name
            assert [e.headword for e in d.lookup("mary")] == ["Mary"], name
            assert d.lookup("mary")[0].is_name
            assert d.lookup("mary")[0].entry_id == default_id("ecdict", "mary")
            assert not d.lookup("shortlist")[0].is_name  # 候选人名单 isn't 人名
            assert [e.headword for e in d.lookup("bit")] == ["bit", "bite"], name
            assert d.entry_for_word("bit") == d.lookup("bit")[0]
            assert [e.headword for e in d.lookup("evening")] == ["evening"], name
            if name == "ecdict.sqlite":
                assert john[0].meanings == ("n. 约翰（男子名）",)
                assert bill[0].meanings == ("n. 比尔（男子名）",)
            else:
                assert john[0].meanings == ("(name) a man's name",)
                assert d.lookup("mary")[0].meanings[0] == "(name) a woman's name"
        finally:
            file.close()
