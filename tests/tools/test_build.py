"""The dictionary build (decision 0009), end to end on small fixtures in
the sources' real formats: fetching with checksums, CC-CEDICT with jieba
ranks and both HSK schemes, ECDICT cut with inflections, the credits."""

import dataclasses
import gzip
import hashlib
import zipfile
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from tests.lexicon.sample import CEDICT_SAMPLE
from tests.tools.wordfreq_data import msgpack
from tools.dictionaries import build, ecdict, sources
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
WORDFREQ_BUCKETS = {
    250: ["run", "english"],
    300: ["ran", "running", "leave"],
    350: ["left"],
    500: ["procrastinate"],
}


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
    pinned = {}
    for real, name in (
        (sources.CEDICT, "cedict.txt.gz"),
        (sources.JIEBA, "jieba.txt"),
        (sources.HSK30, "hsk30.whl"),
        (sources.ECDICT, "ecdict.csv"),
        (sources.WORDFREQ, "wordfreq.whl"),
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
    monkeypatch.setattr(build, "SOURCES", tuple(pinned.values()))
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


def test_credits_name_every_source_with_its_licence(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    text = (built(tmp_path, monkeypatch) / "CREDITS.md").read_text(encoding="utf-8")
    for source in sources.SOURCES:
        assert source.title in text and source.notice in text
    assert "SUBTLEX is freely available data" in text
    assert "CC BY-SA 4.0" in text and "Permission is hereby granted" in text


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
