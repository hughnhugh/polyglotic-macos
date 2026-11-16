"""A learning data file that can't be read is set aside, never deleted or
written over, and a new one started (adapters.sqlite_learning's
`open_learning_store`, polyglotic-hq 206); a newer app's file is still
refused, left as it is."""

import logging
import shutil
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.learning.fakes import Clock, words_of
from tests.learning.test_vocabulary import ENTRIES, LINE, eid, lookup
from tests.stopped_clock import AFTER_MIDNIGHT_IN_MELBOURNE, stopped_at

from polyglotic_desktop.adapters import sqlite_learning
from polyglotic_desktop.adapters.sqlite_learning import (
    KEEP_SET_ASIDE,
    VERSION,
    LearningStoreDamagedError,
    LearningStoreFormatError,
    SqliteLearningStore,
    open_learning_store,
    set_aside_in,
)
from polyglotic_desktop.core.learning.vocabulary import EntryText, Vocabulary
from polyglotic_desktop.core.shared import (
    LearningEvent,
    WordSaved,
    WordStatus,
    WordStatusChanged,
)
from polyglotic_desktop.ports.learning import (
    LearningDataProblem,
    StoredCategory,
    StoredSavedWord,
    StoredStatus,
)

AT = datetime(2026, 11, 8, 6, 30, tzinfo=UTC)
SENTENCE = "我的电脑又卡了"


def filled(path: Path) -> None:
    """A learning store with a saved word, its sentence, and enough
    statuses to fill several pages."""
    store = SqliteLearningStore(path)
    store.save_category(StoredCategory("saved", "Saved", "#6fc3ff", 0))
    store.save_word(
        StoredSavedWord(
            "cedict:a", "电脑", "電腦", "diàn nǎo", "computer", "saved",
            SENTENCE, "My computer froze again", AT,
        )
    )  # fmt: skip
    for n in range(400):
        store.save_status(StoredStatus(f"cedict:{n:06d}", "known", "learner", AT))
    store.close()


def a_folder(path: Path) -> None:
    path.mkdir()
    (path / "something.txt").write_text("kept")


def cut_off(path: Path) -> None:
    filled(path)
    with path.open("r+b") as file:
        file.truncate(path.stat().st_size // 2)


def overwritten_in_places(path: Path) -> None:
    filled(path)
    with path.open("r+b") as file:
        file.seek(4096 * 3)
        file.write(bytes(range(256)) * 16)


def not_sqlite(path: Path) -> None:
    path.write_bytes(b"not a database at all, just some bytes" * 200)


def another_sqlite_file(path: Path) -> None:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE forms (form TEXT, entry_id TEXT)")
    db.commit()
    db.close()


def a_table_missing(path: Path) -> None:
    filled(path)
    db = sqlite3.connect(path)
    db.execute("DROP TABLE deck_words")
    db.commit()
    db.close()


def a_table_of_163s_missing(path: Path) -> None:
    """Version 4's listening table (polyglotic-hq 163, 209)."""
    filled(path)
    db = sqlite3.connect(path)
    db.execute("DROP TABLE daily_listening")
    db.commit()
    db.close()


def first_heard_missing(path: Path) -> None:
    """Version 5 adds a column, not a table: a file at version 5 without it
    failed every load, and so the start (polyglotic-hq 209)."""
    filled(path)
    db = sqlite3.connect(path)
    db.execute("ALTER TABLE exposures DROP COLUMN first_heard")
    db.commit()
    db.close()


DAMAGE: dict[str, tuple[Callable[[Path], None], LearningDataProblem]] = {
    "a folder": (a_folder, LearningDataProblem.FOLDER),
    "cut off": (cut_off, LearningDataProblem.DAMAGED),
    "overwritten in places": (overwritten_in_places, LearningDataProblem.DAMAGED),
    "not SQLite": (not_sqlite, LearningDataProblem.DAMAGED),
    "another SQLite file": (another_sqlite_file, LearningDataProblem.NOT_LEARNING_DATA),
    "a table missing": (a_table_missing, LearningDataProblem.NOT_LEARNING_DATA),
    "a table of 163's missing": (
        a_table_of_163s_missing,
        LearningDataProblem.NOT_LEARNING_DATA,
    ),
    "first heard missing": (first_heard_missing, LearningDataProblem.NOT_LEARNING_DATA),
}


def contents(path: Path) -> dict[str, bytes]:
    """Every file at `path` (a file, or a folder's), by name."""
    if path.is_dir():
        return {each.name: each.read_bytes() for each in path.iterdir()}
    return {path.name: path.read_bytes()}


@pytest.mark.parametrize("damage", DAMAGE)
def test_a_file_that_cant_be_read_is_set_aside_and_a_new_one_started(
    tmp_path: Path, damage: str
) -> None:
    path = tmp_path / "learning.sqlite"
    make, problem = DAMAGE[damage]
    make(path)
    before = list(contents(path).values())
    with pytest.raises(LearningStoreDamagedError):
        SqliteLearningStore(path).close()  # what failed the start before

    store = open_learning_store(path)

    assert store.set_aside is not None
    assert store.set_aside.problem is problem
    aside = store.set_aside.path
    assert aside.parent == tmp_path
    assert aside.name.startswith("learning.sqlite.damaged-")
    # kept as it was: not deleted, not written over
    assert list(contents(aside).values()) == before
    assert store.created
    snapshot = store.load()
    assert not (snapshot.statuses or snapshot.saved_words or snapshot.categories)
    store.save_status(StoredStatus("cedict:b", "learning", "learner", AT))
    store.close()
    again = SqliteLearningStore(path)
    assert [s.entry_id for s in again.load().statuses] == ["cedict:b"]
    assert again.set_aside is None and not again.created
    again.close()


def test_one_set_aside_starts_again_at_the_latest_version_and_fills(
    tmp_path: Path,
) -> None:
    """163's versions 3-5 against 206's set-aside (polyglotic-hq 209): the
    new store is created at the latest version, with each day's coverage,
    listening and first heard; what the server keeps syncs into it; and
    what's heard after is counted and kept. What stays on the PC alone
    (coverage, listening, first heard, daily counts) starts again empty:
    the server never had it."""
    path = tmp_path / "learning.sqlite"
    overwritten_in_places(path)
    clock = Clock(datetime(2026, 11, 8, 9, 0, tzinfo=UTC))

    store = open_learning_store(path)
    assert store.set_aside is not None and store.created
    version = sqlite3.connect(path)
    assert version.execute("PRAGMA user_version").fetchone() == (VERSION,)
    version.close()
    vocabulary = Vocabulary(store, lookup, "hsk-2025", clock)
    resynced: list[LearningEvent] = [
        WordStatusChanged(eid("酸奶"), WordStatus.KNOWN, AT),
        WordSaved(eid("榴莲"), AT),
    ]
    assert vocabulary.apply_from_server(resynced, describe) == 2
    vocabulary.caption_finished("c1", words_of(LINE, ENTRIES), by_you=False)
    vocabulary.listened("video")
    clock.advance(seconds=30)
    vocabulary.caption_finished("c2", words_of(LINE, ENTRIES), by_you=False)
    vocabulary.listened("video")
    store.close()

    again = SqliteLearningStore(path)
    snapshot = again.load()
    again.close()
    assert [s.entry_id for s in snapshot.statuses] == [eid("酸奶")]
    assert [w.entry_id for w in snapshot.saved_words] == [eid("榴莲")]
    today = clock().date()
    assert [c.day for c in snapshot.coverage] == [today]
    assert sum(c.known + c.deck + c.new for c in snapshot.coverage) > 0
    assert [(each.day, each.category, each.seconds) for each in snapshot.listening] == [
        (today, "video", 30.0)
    ]
    assert snapshot.exposures
    assert {e.first_heard for e in snapshot.exposures} == {today}


def describe(entry_id: str) -> EntryText | None:
    return (
        EntryText("榴莲", "榴槤", "liú lián", "durian")
        if entry_id == eid("榴莲")
        else None
    )


def test_a_whole_file_opens_as_it_is(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    filled(path)
    store = open_learning_store(path)
    assert store.set_aside is None and not store.created
    assert len(store.load().statuses) == 400
    store.close()
    assert set_aside_in(tmp_path) == []


def test_a_new_store_is_created(tmp_path: Path) -> None:
    store = open_learning_store(tmp_path / "learning.sqlite")
    assert store.created and store.set_aside is None
    store.close()


def test_the_reason_is_logged_without_what_the_file_holds(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "learning.sqlite"
    overwritten_in_places(path)
    with caplog.at_level(logging.INFO, logger=sqlite_learning.__name__):
        store = open_learning_store(path)
    store.close()
    assert store.set_aside is not None
    said = caplog.text
    assert "couldn't be read (damaged)" in said
    assert store.set_aside.path.name in said
    assert str(tmp_path) not in said  # file names only: a path holds the user's
    assert SENTENCE not in said and "电脑" not in said


@pytest.mark.parametrize("unparseable", [False, True])
def test_a_newer_apps_file_is_still_refused_and_left_as_it_is(
    tmp_path: Path, unparseable: bool
) -> None:
    """Told apart from a damaged one - even when a newer SQLite wrote a
    schema this one can't read, which SQLite itself calls malformed."""
    path = tmp_path / "learning.sqlite"
    filled(path)
    db = sqlite3.connect(path)
    if unparseable:
        db.execute("PRAGMA writable_schema = ON")
        db.execute(
            "INSERT INTO sqlite_master VALUES ('table', 'later', 'later', 0,"
            " 'CREATE TABLE later (a SOMETHING NEW (((')"
        )
    db.execute(f"PRAGMA user_version = {VERSION + 1}")
    db.commit()
    db.close()
    before = path.read_bytes()

    with pytest.raises(LearningStoreFormatError, match="version"):
        open_learning_store(path)

    assert path.read_bytes() == before
    assert set_aside_in(tmp_path) == []


def test_its_wal_files_go_with_it_unchanged(tmp_path: Path) -> None:
    """As a crash leaves them: the file and its write-ahead log. The log
    isn't written into the file, and none is left beside the new one."""
    live = tmp_path / "live" / "learning.sqlite"
    live.parent.mkdir()
    filled(live)  # written into the file itself as it closed
    store = SqliteLearningStore(live)
    for n in range(20):  # these only in its log
        store.save_status(StoredStatus(f"cedict:zz{n:04d}", "known", "learner", AT))
    path = tmp_path / "learning.sqlite"
    for end in ("", "-wal", "-shm"):
        shutil.copyfile(f"{live}{end}", f"{path}{end}")
    store.close()
    with path.open("r+b") as file:  # pages the log doesn't hold, gone
        file.truncate(path.stat().st_size // 2)
    before = {end: Path(f"{path}{end}").read_bytes() for end in ("", "-wal")}
    assert before["-wal"]

    new = open_learning_store(path)

    assert new.set_aside is not None
    aside = new.set_aside.path
    for end, data in before.items():
        assert Path(f"{aside}{end}").read_bytes() == data
    assert new.load().statuses == []  # nothing of the old log read into it
    new.close()


def test_only_the_newest_few_are_kept_and_never_a_folder(tmp_path: Path) -> None:
    path = tmp_path / "learning.sqlite"
    older = [
        tmp_path / f"learning.sqlite.damaged-2025010{n}T000000Z" for n in range(1, 4)
    ]
    for each in older:
        each.write_bytes(b"old")
    Path(f"{older[0]}-wal").write_bytes(b"its log")
    folder = tmp_path / "learning.sqlite.damaged-20240101T000000Z"
    folder.mkdir()
    english = tmp_path / "learning-en.sqlite.damaged-20200101T000000Z"
    english.write_bytes(b"another language's")
    not_sqlite(path)

    store = open_learning_store(path)
    store.close()

    assert store.set_aside is not None
    kept = sorted(p.name for p in tmp_path.glob("learning.sqlite.damaged-*"))
    assert kept == sorted(
        [folder.name, older[1].name, older[2].name, store.set_aside.path.name]
    )
    assert len(
        [p for p in tmp_path.glob("learning.sqlite.damaged-*") if p.is_file()]
    ) == (KEEP_SET_ASIDE)
    assert english.exists()
    assert set_aside_in(tmp_path) == sorted(
        [english.name, folder.name, older[1].name, older[2].name]
        + [store.set_aside.path.name]
    )


def test_set_aside_in_this_pcs_time_and_the_oldest_by_time_go_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Home's banner names the file: named in UTC it read as yesterday in
    Australia (polyglotic-hq 203, as the settings file's). With this PC's
    time and offset the names don't sort as text by time - across a clock
    change, a move between time zones, or the UTC names from before - so
    the oldest kept go by the time in the name."""
    names = [  # oldest first: 09:00, 10:00, 11:00 and 12:00 UTC on 2025-01-08
        "learning.sqlite.damaged-20250108T090000Z",
        "learning.sqlite.damaged-20250108T050000-0500",
        "learning.sqlite.damaged-20250108T220000+1100",
        "learning.sqlite.damaged-20250108T060000-0600",
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"old")
    path = tmp_path / "learning.sqlite"
    not_sqlite(path)

    # the clock stopped: a "today" read after the name was made was the next
    # day when the PC's midnight fell between (polyglotic-hq 344)
    now = AFTER_MIDNIGHT_IN_MELBOURNE
    monkeypatch.setattr(sqlite_learning, "datetime", stopped_at(now))
    store = open_learning_store(path)
    store.close()

    assert store.set_aside is not None
    new = store.set_aside.path.name
    here = now.astimezone()  # this PC's time and offset
    assert new == f"learning.sqlite.damaged-{here:%Y%m%dT%H%M%S%z}"
    kept = {p.name for p in tmp_path.glob("learning.sqlite.damaged-*")}
    assert kept == {names[2], names[3], new}  # the two oldest by time went
    assert set_aside_in(tmp_path) == [names[2], names[3], new]


def test_a_name_taken_is_never_written_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Fixed(datetime):
        @classmethod
        def now(cls, tz: object = None) -> "Fixed":
            return cls(2026, 11, 8, 6, 30, tzinfo=UTC)

    monkeypatch.setattr(sqlite_learning, "datetime", Fixed)
    stamp = Fixed.now().astimezone().strftime("%Y%m%dT%H%M%S%z")  # this PC's time
    taken = tmp_path / f"learning.sqlite.damaged-{stamp}"
    taken.write_bytes(b"set aside a moment ago")
    path = tmp_path / "learning.sqlite"
    not_sqlite(path)

    store = open_learning_store(path)
    store.close()

    assert store.set_aside is not None
    assert store.set_aside.path.name == f"learning.sqlite.damaged-{stamp}-2"
    assert taken.read_bytes() == b"set aside a moment ago"


def test_one_that_cant_be_renamed_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "learning.sqlite"
    not_sqlite(path)
    before = path.read_bytes()

    def refused(self: Path, target: Path) -> Path:
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "rename", refused)
    with pytest.raises(LearningStoreDamagedError):
        open_learning_store(path)

    assert path.read_bytes() == before
    assert set_aside_in(tmp_path) == []


def test_a_locked_file_is_raised_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not the file's fault: setting it aside wouldn't help."""
    path = tmp_path / "learning.sqlite"
    filled(path)
    before = path.read_bytes()

    def locked(self: SqliteLearningStore) -> int:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(SqliteLearningStore, "_check", locked)
    with pytest.raises(sqlite3.OperationalError):
        open_learning_store(path)

    assert path.read_bytes() == before
    assert set_aside_in(tmp_path) == []


def test_deleting_the_learning_data_deletes_the_copies_set_aside(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Polyglotic-hq 207: each copy set aside holds the learner's sentences,
    so "Delete learning data... also from this PC" deletes them, with their
    WAL files - only this store's. A folder set aside, another language's
    copies and the outbox's and settings' files set aside stay."""
    path = tmp_path / "learning.sqlite"
    overwritten_in_places(path)  # a real copy: the sentence is in it
    open_learning_store(path).close()
    taken = tmp_path / "learning.sqlite.damaged-20261101T000000Z-2"
    filled(taken)
    Path(f"{taken}-wal").write_bytes(SENTENCE.encode())
    Path(f"{taken}-shm").write_bytes(b"its index")
    orphan_log = tmp_path / "learning.sqlite.damaged-20261102T000000Z-wal"
    orphan_log.write_bytes(SENTENCE.encode())
    folder = tmp_path / "learning.sqlite.damaged-20240101T000000Z"
    a_folder(folder)
    kept = {
        name: tmp_path / name
        for name in (
            "learning-en.sqlite.damaged-20261101T000000Z",
            "outbox.unreadable-20261101T000000Z.sqlite",
            "settings.unreadable-20261101T000000Z.json",
        )
    }
    for each in kept.values():
        each.write_bytes(b"not ours to delete")
    store = SqliteLearningStore(path)
    assert len(store.set_aside_copies()) == 2

    with caplog.at_level(logging.INFO):
        store.delete_learning_data()

    assert store.set_aside_copies() == []
    left = sorted(each.name for each in tmp_path.iterdir())
    assert left == sorted(
        ["learning.sqlite", "learning.sqlite-wal", "learning.sqlite-shm"]
        + [folder.name, *kept]
    )
    assert (folder / "something.txt").read_text() == "kept"
    assert "2 file(s) set aside deleted, 0 kept" in caplog.text
    assert SENTENCE not in caplog.text
    store.close()


def test_a_copy_that_cant_be_deleted_is_kept_and_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "learning.sqlite"
    copy = tmp_path / "learning.sqlite.damaged-20261101T000000Z"
    copy.write_bytes(b"in use")
    store = SqliteLearningStore(path)

    def in_use(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "unlink", in_use)
    with caplog.at_level(logging.INFO):
        assert store.delete_set_aside() == 0
    store.close()

    assert copy.exists()
    assert "couldn't be deleted (PermissionError): " + copy.name in caplog.text
    assert "0 file(s) set aside deleted, 1 kept" in caplog.text


def test_a_store_in_memory_has_nothing_set_aside() -> None:
    store = SqliteLearningStore(":memory:")
    assert store.set_aside_copies() == []
    store.delete_learning_data()
    store.close()
