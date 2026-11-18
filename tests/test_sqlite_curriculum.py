"""Our curriculum's set, the histories and named word sets in the learning
file (polyglotic-hq 477, version 10; decision 0219)."""

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from polyglotic_desktop.adapters.sqlite_learning import VERSION, SqliteLearningStore
from polyglotic_desktop.ports.learning import (
    StoredCurriculumWord,
    StoredLineChange,
    StoredSetWord,
    StoredStatus,
    StoredStatusChange,
)

AT = datetime(2026, 11, 18, 4, 30, 15, 250000, tzinfo=UTC)
WORD = StoredCurriculumWord(
    "cedict:a", "in", "heard", AT, 2, date(2026, 11, 18), 3, None
)
RETIRED = StoredCurriculumWord(
    "cedict:b", "retired", "order", AT, 3, date(2026, 11, 17), 4, AT
)
SET_WORD = StoredSetWord("quiet", "cedict:a", ("curriculum", "saved"), AT)


def _filled(path: Path) -> SqliteLearningStore:
    store = SqliteLearningStore(path)
    store.save_status(StoredStatus("cedict:a", "learning", "learner", AT))
    store.save_curriculum_words([WORD, RETIRED])
    store.save_set_words([SET_WORD])
    store.add_status_changes(
        [StoredStatusChange("cedict:a", "new", "learning", "learner", AT)]
    )
    store.add_line_change(StoredLineChange("hsk-2025", 3.5, "picked", AT))
    store.add_line_change(StoredLineChange(None, None, "restored", AT))
    return store


def _rows(path: Path, table: str) -> list[tuple[object, ...]]:
    db = sqlite3.connect(path)
    try:
        return db.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        db.close()


def test_the_set_and_word_sets_come_back_whole_after_reopening(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    _filled(path).close()
    data = SqliteLearningStore(path).load()
    assert sorted(data.curriculum_words) == [WORD, RETIRED]
    assert list(data.set_words) == [SET_WORD]


def test_the_histories_are_kept_in_order(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    _filled(path).close()
    assert [r[1:] for r in _rows(path, "status_history")] == [
        ("cedict:a", "new", "learning", "learner", AT.isoformat())
    ]
    assert [r[1:] for r in _rows(path, "line_history")] == [
        ("hsk-2025", 3.5, "picked", AT.isoformat()),
        (None, None, "restored", AT.isoformat()),
    ]


def test_words_leave_the_set_and_a_word_set(tmp_path: Path) -> None:
    store = _filled(tmp_path / "learning.sqlite")
    store.delete_curriculum_words(["cedict:a"])
    store.delete_set_words("quiet", ["cedict:a"])
    data = store.load()
    assert list(data.curriculum_words) == [RETIRED] and not data.set_words
    store.close()


def test_deleting_learning_data_deletes_all_of_it(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    store = _filled(path)
    store.delete_learning_data()
    store.close()
    for table in ("curriculum_words", "status_history", "line_history", "set_words"):
        assert _rows(path, table) == [], table


def test_a_merged_entry_leaves_the_set_and_word_sets(tmp_path: Path) -> None:
    store = _filled(tmp_path / "learning.sqlite")
    store.forget_entry("cedict:a")
    data = store.load()
    assert list(data.curriculum_words) == [RETIRED] and not data.set_words
    store.close()


def test_a_version_9_file_gains_the_tables_and_keeps_its_data(tmp_path: Path) -> None:
    """0.1.8's first learning file (version 9) opened by this app."""
    path = tmp_path / "learning.sqlite"
    store = SqliteLearningStore(path)
    store.save_status(StoredStatus("cedict:a", "known", "learner", AT))
    store.close()
    db = sqlite3.connect(path)
    for table in ("curriculum_words", "status_history", "line_history", "set_words"):
        db.execute(f"DROP TABLE {table}")
    for column in ("days_heard", "last_heard"):  # version 11's
        db.execute(f"ALTER TABLE exposures DROP COLUMN {column}")
    db.execute("PRAGMA user_version = 9")
    db.commit()
    db.close()

    store = SqliteLearningStore(path)
    assert len(store.load().statuses) == 1
    store.save_curriculum_words([WORD])
    assert list(store.load().curriculum_words) == [WORD]
    store.close()
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone() == (VERSION,)
    db.close()


def test_a_garbled_row_is_left_out_and_kept(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    _filled(path).close()
    db = sqlite3.connect(path)
    db.execute(
        "INSERT INTO curriculum_words VALUES ('cedict:c', 'in', 'heard', 'not a time', "
        "0, NULL, 0, NULL)"
    )
    db.commit()
    db.close()
    data = SqliteLearningStore(path).load()
    assert sorted(data.curriculum_words) == [WORD, RETIRED]
    assert len(_rows(path, "curriculum_words")) == 3
