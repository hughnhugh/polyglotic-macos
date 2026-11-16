"""The dictionary file adapter: what's written is read back the same, in
order, with merges followed - and a file in another format is refused."""

import sqlite3
import threading
from pathlib import Path

import pytest
from tests.lexicon.sample import chinese_sample

RANKS = {"人": 10, "游戏": 500, "这个": 20, "这": 30}

from polyglotic_desktop.adapters.sqlite_dictionary import (
    DictionaryFormatError,
    GuardedDictionary,
    SqliteDictionary,
    write_dictionary,
)
from polyglotic_desktop.core.learning.levels import place
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.lexicon.english import EnglishDictionary
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.ports.dictionary import EntryRecord


def write_sample(path: Path) -> None:
    fake = chinese_sample(frequency_ranks=RANKS)
    write_dictionary(
        path,
        {"dictionary": "cedict"},
        list(fake.by_id.values()),
        fake.forms,
        fake.meaning_words,
        merged={"cedict:merged0000": fake.forms["电脑"][0]},
    )


def test_what_is_written_reads_back_the_same(tmp_path: Path) -> None:
    path = tmp_path / "cedict.sqlite"
    write_sample(path)
    fake = chinese_sample(frequency_ranks=RANKS)
    file = SqliteDictionary(path)
    assert file.info["dictionary"] == "cedict" and file.info["format"] == "1"
    assert sorted(file.headwords()) == sorted(fake.headwords())
    assert file.frequency_ranks() == fake.frequency_ranks() == {
        "人": 10, "遊戲": 500, "游戏": 500, "這個": 20, "这个": 20, "這": 30, "这": 30
    }  # fmt: skip
    for word in ("足", "还", "了", "電腦", "人"):
        assert file.records(word) == fake.records(word)
    assert file.records_by_meaning("game", 10) == fake.records_by_meaning("game", 10)
    # commonest first, as many as asked for
    people = file.records_by_meaning("this", 10)
    assert [r.headword for r in people] == ["这个", "这", "个"]
    assert file.records_by_meaning("this", 1) == people[:1]
    assert file.lemma("running") is None
    file.close()


def test_core_works_the_same_on_the_file(tmp_path: Path) -> None:
    path = tmp_path / "cedict.sqlite"
    write_sample(path)
    on_disk = ChineseDictionary(SqliteDictionary(path))
    in_memory = ChineseDictionary(chinese_sample(frequency_ranks=RANKS))
    assert on_disk.split("我们一起打游戏OK吧") == in_memory.split("我们一起打游戏OK吧")
    assert on_disk.lookup("足") == in_memory.lookup("足")
    assert on_disk.reverse_lookup("games") == in_memory.reverse_lookup("games")


def test_a_merged_entry_id_finds_the_entry_it_became(tmp_path: Path) -> None:
    path = tmp_path / "cedict.sqlite"
    write_sample(path)
    d = ChineseDictionary(SqliteDictionary(path))
    computer = d.lookup("电脑")[0]
    assert d.entry(EntryId("cedict:merged0000")) == computer
    assert d.entry(EntryId("cedict:gone000000")) is None
    assert d.merged_ids() == [EntryId("cedict:merged0000")]  # one query (220)


def test_english_inflections_and_levels(tmp_path: Path) -> None:
    path = tmp_path / "ecdict.sqlite"
    run = EntryRecord("ecdict:run", "run", "", "rʌn", ("v. 跑", "n. 赛跑"), 202)
    hobby = EntryRecord("cedict:hobby", "爱好", "愛好", "ai4 hao4", ("hobby",), 900,
                        (("hsk-2025", 2), ("hsk-2021", 1)))  # fmt: skip
    write_dictionary(
        path,
        {"dictionary": "ecdict"},
        [run, hobby],
        {"run": ["ecdict:run"], "爱好": ["cedict:hobby"]},
        lemmas={"ran": "run", "running": "run"},
    )
    file = SqliteDictionary(path)
    assert (
        EnglishDictionary(file).entry_for_word("ran")
        == EnglishDictionary(file).lookup("run")[0]
    )
    assert file.records("run") == [run]
    assert file.records("爱好") == [hobby]


def test_a_meaning_with_a_line_break_is_refused(tmp_path: Path) -> None:
    bad = EntryRecord("ecdict:x", "x", "", "", ("one\ntwo",))
    with pytest.raises(ValueError, match="line break"):
        write_dictionary(tmp_path / "x.sqlite", {}, [bad], {"x": ["ecdict:x"]})


def test_another_format_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    write_sample(path)
    db = sqlite3.connect(path)
    db.execute("UPDATE info SET value = '0' WHERE key = 'format'")
    db.commit()
    db.close()
    with pytest.raises(DictionaryFormatError, match="format"):
        SqliteDictionary(path)
    not_sqlite = tmp_path / "text.sqlite"
    not_sqlite.write_text("not a database", encoding="utf-8")
    with pytest.raises(DictionaryFormatError):
        SqliteDictionary(not_sqlite)
    with pytest.raises(FileNotFoundError):
        SqliteDictionary(tmp_path / "missing.sqlite")


def test_the_bands_sizes_from_the_file(tmp_path: Path) -> None:
    """Words' bands (polyglotic-hq 163): the ranks each once, and the
    headwords at each level."""
    records = [
        EntryRecord("t:hai", "还", "還", "hai2", ("still",), 40, (("hsk-2025", 1),)),
        EntryRecord("t:huan", "还", "還", "huan2", ("return",), 40, (("hsk-2025", 2),)),
        EntryRecord("t:a", "啊", "啊", "a1", ("ah",), 1500, (("hsk-2025", 1),)),
        EntryRecord("t:b", "吧", "吧", "ba5", ("eh",), None, (("hsk-2021", 1),)),
    ]
    forms = {"还": ["t:hai", "t:huan"], "啊": ["t:a"], "吧": ["t:b"]}
    write_dictionary(tmp_path / "d.sqlite", {}, records, forms)
    file = SqliteDictionary(tmp_path / "d.sqlite")
    assert file.words_ranked(2000) == [40, 1500]
    assert file.words_ranked(1000) == [40]
    assert file.words_at_levels("hsk-2025") == {1: 2, 2: 1}
    assert file.words_at_levels("en-frequency") == {}
    zh = ChineseDictionary(file)
    assert zh.words_in_ranks([(1, 1000), (1001, 2000), (2001, 5000)]) == [1, 1, 0]
    # the words a learning load takes in (polyglotic-hq 324): each headword
    # once, commonest first, by the entry a caption counts it for
    assert file.headwords_ranked(0, 10) == [("还", 40), ("啊", 1500)]
    assert file.headwords_ranked(40, 10) == [("啊", 1500)]
    assert file.headwords_ranked(0, 1) == [("还", 40)]
    assert file.headwords_ranked(1500, 10) == []
    assert sorted(file.headwords_at_levels("hsk-2025"), key=str) == [
        ("啊", 1, 1500),
        ("还", 1, 40),
    ]
    assert file.headwords_at_levels("hsk-2021") == [("吧", 1, None)]
    assert file.headwords_at_levels("en-frequency") == []


def test_the_words_past_a_place_come_in_the_learning_windows_order(
    tmp_path: Path,
) -> None:
    """What a learning load takes in (polyglotic-hq 324): each word once,
    by its place - its frequency rank, or its syllabus level's size where
    that is smaller - so a level's words rare in written text aren't left
    for last. HSK 3.0's levels 1 and 2 hold 300 and 500 words."""
    records = [
        EntryRecord("t:hai", "还", "還", "hai2", ("still",), 40, (("hsk-2025", 1),)),
        EntryRecord("t:huan", "还", "還", "huan2", ("return",), 40, (("hsk-2025", 2),)),
        EntryRecord("t:de", "的", "的", "de5", ("of",), 120, ()),
        EntryRecord("t:a", "啊", "啊", "a1", ("ah",), 1500, (("hsk-2025", 1),)),
        EntryRecord("t:x", "向", "向", "xiang4", ("towards",), 400, ()),
        EntryRecord("t:b", "吧", "吧", "ba5", ("eh",), None, (("hsk-2025", 2),)),
        EntryRecord("t:y", "跃", "躍", "yue4", ("leap",), 2000, ()),
        EntryRecord("t:z", "乙", "乙", "yi3", ("second",), None, ()),
    ]
    forms = {r.headword: [r.entry_id] for r in records[2:]} | {
        "还": ["t:hai", "t:huan"]
    }
    write_dictionary(tmp_path / "d.sqlite", {}, records, forms)
    zh = ChineseDictionary(SqliteDictionary(tmp_path / "d.sqlite"))
    in_order = [(40, "t:hai"), (120, "t:de"), (300, "t:a"), (400, "t:x"), (500, "t:b")]
    in_order.append((2000, "t:y"))

    def past(after: int, limit: int, scheme: str = "hsk-2025") -> list[tuple[int, str]]:
        return [(at, f.entry_id) for at, f in zh.words_past(after, limit, scheme)]

    assert past(0, 10) == in_order
    assert past(120, 10) == in_order[2:]
    assert past(2000, 10) == []
    # read a few at a time, from where the last reading ended: none missed,
    # none twice
    read: list[tuple[int, str]] = []
    while batch := past(read[-1][0] if read else 0, 2):
        read += batch
    assert read == in_order
    # each word's place is the one its facts give (`levels.place`)
    assert all(place(f) == at for at, f in zh.words_past(0, 10, "hsk-2025"))
    # a scheme of frequency cut-offs, or one this file has no levels for:
    # the ranks alone
    assert past(0, 10, "en-frequency") == [
        (40, "t:hai"),
        (120, "t:de"),
        (400, "t:x"),
        (1500, "t:a"),
        (2000, "t:y"),
    ]


def read_from_two_threads(file: SqliteDictionary | GuardedDictionary) -> list[str]:
    """Every entry of the sample read 200 times over from each of two
    threads at once, by ID and by word: what came back wrong."""
    fake = chinese_sample(frequency_ranks=RANKS)
    ids = list(fake.by_id)
    wrong: list[str] = []

    def read(order: list[str]) -> None:
        for _ in range(200):
            for entry_id in order:
                try:
                    found = file.record(entry_id)
                    if found is None or found.entry_id != entry_id:
                        wrong.append(entry_id)
                    words = file.records(fake.by_id[entry_id].headword)
                    if entry_id not in [r.entry_id for r in words]:
                        wrong.append(entry_id)
                except Exception as e:  # noqa: BLE001 - any of them is wrong
                    wrong.append(type(e).__name__)

    threads = [
        threading.Thread(target=read, args=(ids,)),
        threading.Thread(target=read, args=(ids[::-1],)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return wrong


def test_two_threads_reading_at_once_each_get_their_own_answers(tmp_path: Path) -> None:
    """The read ahead reads on the dictionary's thread while the interface
    thread looks words up (polyglotic-hq 212). Through one shared SQLite
    connection, a thread got the other's rows, rows of None and "bad
    parameter or other API misuse" (polyglotic-hq 220)."""
    path = tmp_path / "cedict.sqlite"
    write_sample(path)
    file = SqliteDictionary(path)
    assert read_from_two_threads(file) == []
    file.close()
    with pytest.raises(sqlite3.ProgrammingError):  # closed for every thread
        file.record("cedict:anything")


def test_two_threads_reading_at_once_leave_the_dictionary_in(tmp_path: Path) -> None:
    """The guard took that misuse for a damaged file and left the learner's
    dictionary out for the session: no word marks, every lookup saying the
    file is damaged (polyglotic-hq 220: every time, on CC-CEDICT)."""
    path = tmp_path / "cedict.sqlite"
    write_sample(path)
    guarded = GuardedDictionary(path)
    assert read_from_two_threads(guarded) == []
    assert guarded.problem is None
    guarded.close()


def test_a_forms_own_reading_reads_back_and_an_older_file_has_none(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wiktru.sqlite"
    hand = EntryRecord("wiktru:ruka", "рука", "", "рука́", ("(noun) hand",), 300)
    write_dictionary(
        path,
        {"dictionary": "wiktru"},
        [hand],
        {"рука": ["wiktru:ruka"]},
        lemmas={"руку": "рука"},
        form_readings={"руку": "ру́ку"},
    )
    file = SqliteDictionary(path)
    assert file.form_reading("руку") == "ру́ку" and file.form_reading("рука") == ""
    file.close()
    # a file written before the table (polyglotic-hq 298): no form readings
    db = sqlite3.connect(path)
    db.execute("DROP TABLE form_readings")
    db.commit()
    db.close()
    older = SqliteDictionary(path)
    assert older.form_reading("руку") == "" and older.lemma("руку") == "рука"
    older.close()
    assert GuardedDictionary(tmp_path / "missing.sqlite").form_reading("руку") == ""
