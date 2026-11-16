"""The learner's dictionary file never stops the app (polyglotic-hq 199,
184's QA item 21): a file that's missing, cut off, of another format or
unreadable leaves the dictionary out - every query answers nothing, and
`problem` says why - with the reason logged once, content-free. One that
opens but fails a query later goes out then, for the session, told once."""

import logging
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.test_sqlite_dictionary import write_sample

from polyglotic_desktop.adapters import sqlite_dictionary
from polyglotic_desktop.adapters.sqlite_dictionary import (
    GuardedDictionary,
    SqliteDictionary,
)
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.shared import EntryFacts, EntryId
from polyglotic_desktop.ports.dictionary import DictionaryProblem

# the sample's words, which must never reach the log
WORDS = ("电脑", "游戏", "computer")


def cut_off(path: Path, keep: int) -> Path:
    """`path` written whole, then cut to its first `keep` bytes - as 184's
    QA cut `cedict.sqlite` to 3 MB."""
    write_sample(path)
    path.write_bytes(path.read_bytes()[:keep])
    return path


def damaged_inside(path: Path, table: str = "forms") -> Path:
    """`path` written whole, then `table`'s first page overwritten: it opens
    (its `info` is whole) and some queries answer, but one that reads that
    page fails - as a file cut off or overwritten after its first pages
    does (164's top next 2)."""
    write_sample(path)
    db = sqlite3.connect(path)
    size = db.execute("PRAGMA page_size").fetchone()[0]
    (root,) = db.execute(
        "SELECT rootpage FROM sqlite_master WHERE name = ?", (table,)
    ).fetchone()
    db.close()
    data = bytearray(path.read_bytes())
    data[(root - 1) * size : root * size] = bytes([0xFF]) * size
    path.write_bytes(bytes(data))
    return path


def not_a_database(path: Path) -> Path:
    path.write_bytes(b"not a database " * 400)
    return path


def other_format(path: Path) -> Path:
    write_sample(path)
    db = sqlite3.connect(path)
    db.execute("UPDATE info SET value = '0' WHERE key = 'format'")
    db.commit()
    db.close()
    return path


def answers_nothing(file: GuardedDictionary) -> bool:
    return (
        list(file.headwords()) == []
        and dict(file.frequency_ranks()) == {}
        and list(file.records("电脑")) == []
        and list(file.records_by_meaning("computer", 10)) == []
        and file.lemma("running") is None
        and file.record("cedict:x") is None
        and list(file.merged_ids()) == []
        and list(file.words_ranked(1000)) == []
        and list(file.headwords_ranked(0, 10)) == []
        and list(file.headwords_at_levels("hsk-2025")) == []
        and dict(file.words_at_levels("hsk-2025")) == {}
    )


@pytest.mark.parametrize(
    ("make", "problem"),
    [
        (lambda path: path, DictionaryProblem.MISSING),
        (lambda path: cut_off(path, 8192), DictionaryProblem.DAMAGED),
        (not_a_database, DictionaryProblem.DAMAGED),
        (other_format, DictionaryProblem.WRONG_FORMAT),
    ],
    ids=["missing", "cut off", "not a database", "another format"],
)  # fmt: skip
def test_a_file_that_cant_be_opened_leaves_the_dictionary_out(
    tmp_path: Path, make: Callable[[Path], object], problem: DictionaryProblem
) -> None:
    path = tmp_path / "cedict.sqlite"
    make(path)

    file = GuardedDictionary(path)

    assert file.problem is problem
    assert answers_nothing(file)
    file.close()


def test_unreadable_when_the_pc_wont_open_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cedict.sqlite"
    write_sample(path)

    def refused(self: SqliteDictionary, path: Path) -> None:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(SqliteDictionary, "__init__", refused)
    assert GuardedDictionary(path).problem is DictionaryProblem.UNREADABLE

    def sqlite_refused(self: SqliteDictionary, path: Path) -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(SqliteDictionary, "__init__", sqlite_refused)
    assert GuardedDictionary(path).problem is DictionaryProblem.UNREADABLE


def test_a_whole_file_answers_as_the_file_does(tmp_path: Path) -> None:
    path = tmp_path / "cedict.sqlite"
    write_sample(path)
    whole = SqliteDictionary(path)

    file = GuardedDictionary(path)

    assert file.problem is None
    assert sorted(file.headwords()) == sorted(whole.headwords())
    assert file.records("电脑") == whole.records("电脑")
    assert file.record("cedict:merged0000") == whole.record("cedict:merged0000")
    assert list(file.merged_ids()) == list(whole.merged_ids()) == ["cedict:merged0000"]
    # Words' bands (polyglotic-hq 163, 209)
    assert list(file.words_ranked(1000)) == list(whole.words_ranked(1000))
    assert list(file.words_ranked(1000))  # the sample has ranked words
    assert list(file.headwords_ranked(0, 5)) == list(whole.headwords_ranked(0, 5))
    assert list(file.headwords_at_levels("hsk-2025")) == list(
        whole.headwords_at_levels("hsk-2025")
    )
    assert dict(file.words_at_levels("hsk-2025")) == dict(
        whole.words_at_levels("hsk-2025")
    )
    file.close()
    whole.close()


def test_the_reason_is_logged_once_and_content_free(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=sqlite_dictionary.__name__)
    file = GuardedDictionary(cut_off(tmp_path / "cedict.sqlite", 8192))
    for word in WORDS:
        file.records(word)  # lookups while it's out add nothing to the log

    said = [r.getMessage() for r in caplog.records]
    assert said == ["Dictionary cedict.sqlite left out: damaged (DictionaryDamaged)"]
    assert not any(word in line for line in said for word in WORDS)


def test_the_word_split_reads_nothing_and_finds_no_words(tmp_path: Path) -> None:
    """Out, the word split has no words: captions' words are neither
    marked nor counted - none is taken for a word it isn't."""
    dictionary = ChineseDictionary(GuardedDictionary(tmp_path / "cedict.sqlite"))
    dictionary.prepare()
    assert dictionary.ready
    assert dictionary.words_in("我的电脑又卡了", "hsk-2025") == []
    assert dictionary.lookup("电脑") == []


@pytest.mark.parametrize("out", [False, True], ids=["whole", "out"])
def test_while_its_out_nothing_heard_is_counted(tmp_path: Path, out: bool) -> None:
    """199's suggestion for 163's counting (polyglotic-hq 209): a finished
    caption heard while the dictionary is out leaves coverage, words met
    and first heard empty - and Words' band sizes answer none - rather than
    counting words it can't know. The whole file, beside it, counts them."""
    path = tmp_path / "cedict.sqlite"
    if not out:
        write_sample(path)
    dictionary = ChineseDictionary(GuardedDictionary(path))
    dictionary.prepare()

    def facts(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        entry = dictionary.entry(entry_id)
        return entry.facts(scheme) if entry else None

    clock = Clock(datetime(2026, 11, 8, 9, 0, tzinfo=UTC))
    vocabulary = Vocabulary(MemoryLearningStore(), facts, "hsk-2025", clock)
    words = dictionary.words_in("我的电脑又卡了", "hsk-2025")
    vocabulary.caption_finished("c1", words, by_you=False)

    heard = (
        vocabulary.coverage().tokens,
        len(vocabulary.met_words()),
        vocabulary.new_words(),
    )
    if out:
        assert words == [] and heard == (0, 0, 0)
        assert dictionary.words_in_ranks([(1, 1000), (1001, 2000)]) == [0, 0]
        assert dict(dictionary.words_at_levels("hsk-2025")) == {}
    else:
        assert words and all(n > 0 for n in heard)


def test_a_query_that_fails_puts_it_out_for_the_session(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A lookup on a page that can't be read answers nothing - it raised
    `sqlite3.DatabaseError` into the card before - and the dictionary is
    out from then on, even for what it could still read: told once, logged
    once, never per lookup."""
    caplog.set_level(logging.WARNING, logger=sqlite_dictionary.__name__)
    file = GuardedDictionary(damaged_inside(tmp_path / "cedict.sqlite"))
    told: list[DictionaryProblem] = []
    file.on_problem = told.append
    assert file.problem is None  # it opened
    assert file.record("cedict:merged0000") is not None  # a page it can read

    assert file.records("电脑") == []

    assert file.problem is DictionaryProblem.DAMAGED
    for word in WORDS:
        file.records(word)
    assert answers_nothing(file)
    assert told == [DictionaryProblem.DAMAGED]
    said = [r.getMessage() for r in caplog.records]
    assert said == ["Dictionary cedict.sqlite left out: damaged (DatabaseError)"]


def test_two_threads_failing_at_once_tell_it_once(tmp_path: Path) -> None:
    """The word split's read on its thread and a lookup on the interface
    thread can meet the damage together."""
    file = GuardedDictionary(damaged_inside(tmp_path / "cedict.sqlite"))
    told: list[DictionaryProblem] = []
    file.on_problem = told.append
    start = threading.Barrier(4)

    def look_up() -> None:
        start.wait()
        file.frequency_ranks()

    threads = [threading.Thread(target=look_up) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert told == [DictionaryProblem.DAMAGED]
