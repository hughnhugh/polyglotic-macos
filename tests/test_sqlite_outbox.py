"""The outbox and consent choices in SQLite (adapters/sqlite_outbox.py)."""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from polyglotic_desktop.adapters.sqlite_outbox import (
    OutboxFormatError,
    SqliteOutbox,
    open_outbox,
)
from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ports.outbox import Waiting

AT = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)


def item(kind: str, n: int) -> Waiting:
    return Waiting(kind, f"{kind}-{n}", f'{{"n": {n}}}')


def test_waiting_in_order_and_forgotten() -> None:
    outbox = SqliteOutbox(":memory:")
    for n in range(3):
        outbox.add(item("learning", n), keep=10)
    outbox.add(item("usage", 0), keep=10)
    outbox.add(item("learning", 0), keep=10)  # the same id again: ignored
    assert [w.id for w in outbox.waiting()] == [
        "learning-0",
        "learning-1",
        "learning-2",
        "usage-0",
    ]
    outbox.remove(["learning-1"])
    outbox.remove_kind("learning")
    assert [w.id for w in outbox.waiting()] == ["usage-0"]


def test_bounded_per_kind_oldest_first(caplog: pytest.LogCaptureFixture) -> None:
    outbox = SqliteOutbox(":memory:")
    outbox.add(item("usage", 0), keep=2)
    for n in range(4):
        with caplog.at_level(logging.WARNING):
            outbox.add(item("learning", n), keep=2)
        assert outbox.dropped() == max(0, n - 1)
    assert [w.id for w in outbox.waiting()] == ["usage-0", "learning-2", "learning-3"]
    assert caplog.text.count("the outbox is full: 1 learning item(s) dropped") == 2


def test_notes_and_consent_survive_reopening(tmp_path: Path) -> None:
    path = tmp_path / "Polyglotic" / "outbox.sqlite"
    outbox = SqliteOutbox(path)
    assert outbox.consent() is None and outbox.note("cursor") is None
    outbox.save_note("cursor", "1234")
    outbox.save_consent(ConsentChoice("a", AT, True, False, False))
    outbox.save_consent(ConsentChoice("b", AT, False, False, True))
    outbox.add(item("consent", 1), keep=5)
    outbox.close()
    again = SqliteOutbox(path)
    assert again.note("cursor") == "1234"
    assert again.consent() == ConsentChoice("b", AT, False, False, True)
    assert [w.id for w in again.waiting()] == ["consent-1"]
    again.save_note("cursor", None)
    assert again.note("cursor") is None


def test_the_agreement_accepted_is_kept_with_the_choice(tmp_path: Path) -> None:
    # polyglotic-hq 185: which tester agreement this PC accepted, and when
    path = tmp_path / "outbox.sqlite"
    outbox = SqliteOutbox(path)
    agreed = Agreement("tester-2026-11-08", AT)
    outbox.save_consent(ConsentChoice("a", AT, True, False, False, agreed))
    outbox.close()
    assert SqliteOutbox(path).consent() == ConsentChoice(
        "a", AT, True, False, False, agreed
    )


def test_an_outbox_from_before_the_agreement_keeps_its_choice(tmp_path: Path) -> None:
    # version 1's file (the app before 185): its choice is read as having no
    # agreement, so the app asks for one at start
    path = tmp_path / "outbox.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE consent (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT "
            "NOT NULL UNIQUE, at TEXT NOT NULL, usage INTEGER NOT NULL, crashes "
            "INTEGER NOT NULL, exposures INTEGER NOT NULL)"
        )
        db.execute(
            "CREATE TABLE waiting (seq INTEGER PRIMARY KEY, kind TEXT, id TEXT, body TEXT)"
        )
        db.execute("CREATE TABLE notes (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute(
            "INSERT INTO consent (id, at, usage, crashes, exposures) VALUES (?, ?, 1, 0, 0)",
            ("old", AT.isoformat()),
        )
        db.execute("PRAGMA user_version = 1")
    db.close()
    assert SqliteOutbox(path).consent() == ConsentChoice("old", AT, True, False, False)


def test_a_file_from_a_newer_app_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version = 99")
    with pytest.raises(OutboxFormatError):
        SqliteOutbox(path)


def test_a_file_that_isnt_sqlite_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite"
    path.write_bytes(b"not a database at all, " * 100)
    with pytest.raises(OutboxFormatError):
        SqliteOutbox(path)


@pytest.mark.parametrize("newer", [False, True])
def test_an_unreadable_outbox_is_set_aside_and_a_fresh_one_started(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, newer: bool
) -> None:
    """It's only a buffer: a damaged file, or one from a newer app, mustn't
    stop the app starting (project 042, Medium 4). Kept aside, not deleted;
    the fresh one never reads the old one's write-ahead log; logged without
    its contents."""
    path = tmp_path / "outbox.sqlite"
    if newer:
        db = sqlite3.connect(path)
        db.execute("PRAGMA user_version = 99")
        db.close()
    else:
        path.write_bytes(b"not a database at all, " * 100)
    broken = path.read_bytes()
    (tmp_path / "outbox.sqlite-wal").write_bytes(b"an old write-ahead log")

    with caplog.at_level(logging.WARNING):
        outbox = open_outbox(path)

    outbox.add(item("learning", 1), keep=10)
    assert [w.id for w in outbox.waiting()] == ["learning-1"]
    assert outbox.consent() is None  # asked again
    (aside,) = tmp_path.glob("outbox.unreadable-*.sqlite")
    assert aside.read_bytes() == broken
    wal = tmp_path / "outbox.sqlite-wal"  # SQLite removed it, or it went aside
    assert not wal.exists() or wal.read_bytes() != b"an old write-ahead log"
    assert "set aside as outbox.unreadable-" in caplog.text
    assert "not a database at all" not in caplog.text


def test_a_readable_outbox_is_opened_as_it_is(tmp_path: Path) -> None:
    path = tmp_path / "outbox.sqlite"
    SqliteOutbox(path).add(item("learning", 1), keep=10)
    assert [w.id for w in open_outbox(path).waiting()] == ["learning-1"]
    assert not list(tmp_path.glob("outbox.unreadable-*"))


def test_an_outbox_out_of_reach_isnt_set_aside(tmp_path: Path) -> None:
    """A folder where the file should be: SQLite can't open it, which isn't
    the file's fault - raised as it is, nothing moved."""
    path = tmp_path / "outbox.sqlite"
    path.mkdir()
    with pytest.raises(sqlite3.OperationalError):
        open_outbox(path)
    assert path.is_dir()
    assert not list(tmp_path.glob("outbox.unreadable-*"))
