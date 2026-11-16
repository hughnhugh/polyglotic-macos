"""The checkpoint after a delete (adapters.sqlite_learning's `_scrub`,
polyglotic-hq 213) when another program is reading the file (polyglotic-hq
237, from 226's Low 2, `work/p226_secure_delete.py`): SQLite answered
`busy`, nothing read the answer, and the deleted sentence stayed in the
write-ahead log through later writes - and the checkpoint held the learning
thread 5 s before giving up. Now it never waits, and is tried again after
each write and at close, until it finishes."""

import logging
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore
from polyglotic_desktop.ports.learning import (
    StoredCategory,
    StoredExposures,
    StoredSavedWord,
)

AT = datetime(2026, 11, 8, 6, 30, tzinfo=UTC)
GONE = b"HELDREADER_SENTENCE_PLUGH"


def saved(entry: str, sentence: str) -> StoredSavedWord:
    return StoredSavedWord(
        entry, "词", "詞", "cí", "a word", "c1", sentence, "In English", AT
    )


def readable(folder: Path, text: bytes) -> list[str]:
    """The store's files - and its log - in which `text` can be read."""
    return [
        each.name
        for each in sorted(folder.glob("learning.sqlite*"))
        if text in each.read_bytes()
    ]


@contextmanager
def another_program_reading(path: Path) -> Iterator[None]:
    """A second SQLite client holding a read snapshot, as a backup or a
    database browser can."""
    reader = sqlite3.connect(path, isolation_level=None)
    reader.execute("BEGIN")
    reader.execute("SELECT count(*) FROM saved_words").fetchall()
    try:
        yield
    finally:
        reader.execute("COMMIT")
        reader.close()


def a_store_with_the_sentence(path: Path) -> SqliteLearningStore:
    store = SqliteLearningStore(path)
    store.save_category(StoredCategory("c1", "Cat", "#ff0000", 0))
    store.save_word(saved("e1", "kept"))
    store.save_word(saved("e5", GONE.decode()))
    return store


def test_a_checkpoint_kept_busy_is_tried_again_at_the_next_write(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "learning.sqlite"
    store = a_store_with_the_sentence(path)
    with caplog.at_level(logging.INFO), another_program_reading(path):
        started = time.perf_counter()
        store.delete_word("e5")
        assert time.perf_counter() - started < 1.0  # never waits (5 s before)
        assert readable(tmp_path, GONE)  # can't go while it's read
        store.save_exposures(  # a caption's counts, while it's still read
            [StoredExposures("e1", 1, 0, 0)], {date(2026, 11, 8): {"e1": 1}}
        )
        assert time.perf_counter() - started < 1.0  # nor do they
    assert readable(tmp_path, GONE)  # the reader has gone; nothing written since
    store.save_category(StoredCategory("c3", "x", "#0000ff", 2))  # a plain write
    assert readable(tmp_path, GONE) == []
    assert (tmp_path / "learning.sqlite-wal").stat().st_size == 0  # emptied
    store.close()
    assert "another program is reading the file" in caplog.text
    assert "PLUGH" not in caplog.text


def test_a_checkpoint_kept_busy_is_tried_again_at_close(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    store = a_store_with_the_sentence(path)
    with another_program_reading(path):
        store.delete_word("e5")
    store.close()  # no write between: the close tries it
    assert readable(tmp_path, GONE) == []
    assert SqliteLearningStore(path).load().saved_words[0].entry_id == "e1"


def test_a_reader_still_there_at_close_is_said(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Nothing more the app can do: the log is emptied by the last of the
    file's connections to close - the other program's, here."""
    path = tmp_path / "learning.sqlite"
    store = a_store_with_the_sentence(path)
    with another_program_reading(path):
        store.delete_word("e5")
        with caplog.at_level(logging.WARNING):
            store.close()
        assert readable(tmp_path, GONE)
    assert "still read by another program at close" in caplog.text
    assert readable(tmp_path, GONE) == []  # it let go, and closed last


def test_with_no_other_reader_nothing_is_owed(tmp_path: Path) -> None:
    """213's case: the checkpoint finishes at once, and a caption's counts
    after it don't checkpoint (the log grows, as SQLite's own)."""
    path = tmp_path / "learning.sqlite"
    store = a_store_with_the_sentence(path)
    store.delete_word("e5")
    assert readable(tmp_path, GONE) == []
    store.save_exposures(
        [StoredExposures("e1", 1, 0, 0)], {date(2026, 11, 8): {"e1": 1}}
    )
    assert (tmp_path / "learning.sqlite-wal").stat().st_size > 0
    store.close()
