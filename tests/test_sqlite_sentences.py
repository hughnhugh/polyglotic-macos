"""Saved sentences in the learning file (polyglotic-hq 459, version 9)."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polyglotic_desktop.adapters.sqlite_learning import VERSION, SqliteLearningStore
from polyglotic_desktop.ports.learning import (
    StoredCategory,
    StoredSentence,
    StoredSentencePart,
    StoredStatus,
)

AT = datetime(2026, 11, 17, 4, 30, 15, 250000, tzinfo=UTC)


def _sentence(n: int, category: str = "saved", text: str = "") -> StoredSentence:
    original = text or f"我们去吃饭吧 {n}"
    return StoredSentence(
        f"s{n}",
        original + " 好吗",
        f"Let's go and eat {n}. OK?",
        (
            StoredSentencePart(original, f"Let's go and eat {n}.", ((4, 6, 13, 16, True),), "Discord"),
            StoredSentencePart("好吗", "OK?", (), "You"),
        ),
        "en",
        category,
        AT,
    )  # fmt: skip


def _store(path: Path) -> SqliteLearningStore:
    store = SqliteLearningStore(path)
    store.save_category(StoredCategory("saved", "Saved", "#6fc3ff", 0))
    store.save_category(StoredCategory("trip", "Trip", "#ff7a9a", 1))
    return store


def test_a_saved_sentence_comes_back_whole_after_reopening(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    store = _store(path)
    store.save_sentence(_sentence(1))
    store.close()
    again = SqliteLearningStore(path)
    assert again.saved_sentences() == [_sentence(1)]
    again.delete_sentence("s1")
    assert again.saved_sentences() == []
    again.close()


def test_sentences_go_with_their_category_and_with_the_learning_data(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "learning.sqlite")
    store.save_sentence(_sentence(1, "trip"))
    store.save_sentence(_sentence(2, "saved"))
    store.delete_category("trip")
    assert [s.id for s in store.saved_sentences()] == ["s2"]
    store.delete_learning_data()
    data = store.load()
    assert store.saved_sentences() == [] and len(data.categories) == 1
    store.close()


def _delete(store: SqliteLearningStore) -> None:
    store.delete_sentence("s0")


def _replace(store: SqliteLearningStore) -> None:
    store.save_sentence(_sentence(0, "saved", "换了一句"))


def _delete_its_category(store: SqliteLearningStore) -> None:
    store.delete_category("trip")


def _delete_everything(store: SqliteLearningStore) -> None:
    store.delete_learning_data()


@pytest.mark.parametrize(
    "remove", [_delete, _replace, _delete_its_category, _delete_everything]
)
def test_a_deleted_sentence_leaves_none_of_its_text_readable(
    tmp_path: Path, remove: Callable[[SqliteLearningStore], None]
) -> None:
    """As a saved word's line (polyglotic-hq 213): gone from the file and
    its write-ahead log at once, not left in free space."""
    path = tmp_path / "learning.sqlite"
    store = _store(path)
    store.save_sentence(_sentence(0, "trip", "GONE1 " + "长" * 600))
    for n in range(1, 30):
        store.save_sentence(_sentence(n, "saved", f"KEPT{n}"))
    store.close()

    store = SqliteLearningStore(path)
    remove(store)
    on_disk = {each.name: each.read_bytes() for each in tmp_path.iterdir()}
    store.close()
    for name, held in on_disk.items():
        assert b"GONE1" not in held, name
        assert ("长" * 50).encode() not in held, name
    assert b"GONE1" not in path.read_bytes()


def test_a_version_8_file_gains_saved_sentences_and_keeps_its_data(
    tmp_path: Path,
) -> None:
    """0.1.7's learning file (version 8) opened by this app."""
    path = tmp_path / "learning.sqlite"
    store = _store(path)
    store.save_status(StoredStatus("cedict:a", "known", "learner", AT))
    store.close()
    db = sqlite3.connect(path)
    db.execute("DROP TABLE saved_sentences")
    for table in ("curriculum_words", "status_history", "line_history", "set_words"):
        db.execute(f"DROP TABLE {table}")  # version 10's
    for column in ("days_heard", "last_heard"):  # version 11's
        db.execute(f"ALTER TABLE exposures DROP COLUMN {column}")
    db.execute("PRAGMA user_version = 8")
    db.commit()
    db.close()

    store = SqliteLearningStore(path)
    data = store.load()
    assert store.saved_sentences() == [] and len(data.statuses) == 1
    store.save_sentence(_sentence(1))
    assert len(store.saved_sentences()) == 1
    store.close()
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone() == (VERSION,)
    db.close()


@pytest.mark.parametrize(
    "parts",
    [
        "not json",
        '{"a": 1}',
        '[["only", "three", "items"]]',
        '[["a", "b", "c", [[0, 1, 0, 1]]]]',
        '[["a", "b", "c", [[0, 1, 0, 1, "yes"]]]]',
        '[[1, "b", "c", []]]',
    ],
)
def test_a_garbled_sentence_is_left_out_and_kept(tmp_path: Path, parts: str) -> None:
    """A row this app can't read stays in the file and out of the load
    (polyglotic-hq 207), never stopping the start."""
    path = tmp_path / "learning.sqlite"
    store = _store(path)
    for n in range(1, 60):
        store.save_sentence(_sentence(n))
    store.close()
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO saved_sentences VALUES ('bad', 'a', 'b', ?, 'en', 'saved', ?)",
        (parts, AT.isoformat()),
    )
    db.commit()
    db.close()
    store = SqliteLearningStore(path)
    assert len(store.saved_sentences()) == 59
    store.close()
    db = sqlite3.connect(path)
    assert db.execute("SELECT count(*) FROM saved_sentences").fetchone() == (60,)
    db.close()
