"""The learning store on a thread of its own: writes return at once, run in
order on one thread, and reads see the writes queued before them."""

import logging
import sqlite3
import threading
import time
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from tests.test_learning_set_aside import filled

from polyglotic_desktop.adapters.background_learning import BackgroundLearningStore
from polyglotic_desktop.adapters.sqlite_learning import SqliteLearningStore
from polyglotic_desktop.ports.learning import (
    LearningDataProblem,
    LearningSnapshot,
    SetAsideLearningData,
    StoredAnkiExport,
    StoredCoverage,
    StoredExposures,
    StoredLevel,
    StoredStatus,
)

AT = datetime(2026, 11, 7, tzinfo=UTC)


def background(path: Path) -> BackgroundLearningStore:
    return BackgroundLearningStore(lambda: SqliteLearningStore(path))


def test_reads_see_the_writes_queued_before_them(tmp_path: Path) -> None:
    store = background(tmp_path / "learning.sqlite")
    store.save_level(StoredLevel("hsk-2025", 2.5))
    store.save_status(StoredStatus("cedict:1", "known", "learner", AT))
    snapshot = store.load()
    assert snapshot.level == StoredLevel("hsk-2025", 2.5)
    assert [s.entry_id for s in snapshot.statuses] == ["cedict:1"]
    store.close()
    again = SqliteLearningStore(tmp_path / "learning.sqlite")
    assert again.load().level == StoredLevel("hsk-2025", 2.5)
    again.close()


def test_what_a_write_was_given_is_copied_before_it_returns(tmp_path: Path) -> None:
    store = background(tmp_path / "learning.sqlite")
    daily = {date(2026, 11, 6): {"cedict:1": 2}}
    store.save_exposures([StoredExposures("cedict:1", 2, 0, 0)], daily)
    daily[date(2026, 11, 6)]["cedict:1"] = 99  # the caller's own, changed after
    store.save_anki_exports(StoredAnkiExport(e, AT) for e in ["cedict:1"])
    assert store.daily_exposures(date(2026, 11, 6)) == {"cedict:1": 2}
    assert [e.entry_id for e in store.load().anki_exports] == ["cedict:1"]
    changes = [StoredCoverage(date(2026, 11, 6), 3, 1, 1)]
    store.add_coverage(change for change in changes)  # a generator: copied
    assert store.load().coverage == changes
    store.close()


def test_writes_run_on_one_other_thread_without_waiting(tmp_path: Path) -> None:
    seen: list[str] = []

    class Slow(SqliteLearningStore):
        def save_level(self, level: StoredLevel) -> None:
            time.sleep(0.05)
            seen.append(threading.current_thread().name)
            super().save_level(level)

    store = BackgroundLearningStore(lambda: Slow(tmp_path / "learning.sqlite"))
    start = time.perf_counter()
    for n in range(4):
        store.save_level(StoredLevel("hsk-2025", n))
    assert time.perf_counter() - start < 0.05  # returned before any was written
    assert store.load().level == StoredLevel("hsk-2025", 3)  # in order
    assert len(set(seen)) == 1 and seen[0] != threading.current_thread().name
    store.close()


def test_a_failed_write_is_logged_and_the_next_goes_on(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class Failing(SqliteLearningStore):
        def delete_word(self, entry_id: str) -> None:
            raise OSError("disk full")

    store = BackgroundLearningStore(lambda: Failing(tmp_path / "learning.sqlite"))
    with caplog.at_level(logging.ERROR):
        store.delete_word("cedict:1")
        store.save_level(StoredLevel("hsk-2025", 1))
        store.flush()
    assert "a learning save failed" in caplog.text
    assert store.load().level == StoredLevel("hsk-2025", 1)
    store.close()


def test_a_write_after_closing_is_logged_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A learning save that came after `close` - at quit, with a lookup or
    the server's learning still arriving - raised an uncaught RuntimeError,
    which the next start offered as a crash to report (polyglotic-hq 203;
    the outbox already logs it)."""
    store = background(tmp_path / "learning.sqlite")
    store.save_level(StoredLevel("hsk-2025", 2.0))
    store.close()
    with caplog.at_level(logging.WARNING):
        store.save_status(StoredStatus("cedict:1", "known", "learner", AT))
        store.delete_learning_data()  # 207: the deletion goes the same way
        store.close()  # twice: nothing more to do
    assert caplog.text.count("came after the store closed") == 2
    again = SqliteLearningStore(tmp_path / "learning.sqlite")
    loaded = again.load()
    assert loaded.level == StoredLevel("hsk-2025", 2.0) and not loaded.statuses
    again.close()


def damage() -> sqlite3.DatabaseError:
    """SQLite's answer for a damaged file, as a query on one raises it."""
    error = sqlite3.DatabaseError("database disk image is malformed")
    error.sqlite_errorname = "SQLITE_CORRUPT"
    return error


def test_a_store_found_damaged_is_set_aside_and_nothing_more_is_saved(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Polyglotic-hq 206: no crash, no error per save - out for the
    session, the file set aside as it was, and `on_damaged` told once."""
    path = tmp_path / "learning.sqlite"
    calls: list[str] = []

    class DamagedLater(SqliteLearningStore):
        def save_status(self, status: StoredStatus) -> None:
            calls.append(status.entry_id)
            if status.entry_id == "cedict:2":
                raise damage()
            super().save_status(status)

    store = BackgroundLearningStore(lambda: DamagedLater(path))
    told: list[SetAsideLearningData | None] = []
    store.on_damaged = told.append
    store.save_status(StoredStatus("cedict:1", "known", "learner", AT))
    store.flush()
    before = path.read_bytes()
    with caplog.at_level(logging.INFO):
        for n in (2, 3, 4):
            store.save_status(StoredStatus(f"cedict:{n}", "known", "learner", AT))
        store.save_level(StoredLevel("hsk-2025", 1))
        assert store.daily_exposures(date(2026, 11, 7)) == {}  # no raise
        assert store.exposure_days() == []
        assert store.days_to_hand_over() == []
    store.close()

    assert calls == ["cedict:1", "cedict:2"]  # nothing tried after it
    assert store.out
    (aside,) = told
    assert aside is not None and aside.problem is LearningDataProblem.DAMAGED
    assert aside.path.read_bytes() == before  # as it was: not written over
    assert not path.exists()  # the next start begins a new one
    assert caplog.text.count("found damaged") == 2  # once, then where it went
    assert "a learning save failed" not in caplog.text


def test_a_read_that_finds_real_damage_answers_nothing(tmp_path: Path) -> None:
    """A page overwritten under an open store: the next read that reaches
    it (past SQLite's cache) fails as damaged."""
    path = tmp_path / "learning.sqlite"
    filled(path)

    class Uncached(SqliteLearningStore):
        def load(self) -> LearningSnapshot:
            self._db.execute("PRAGMA shrink_memory")  # read from the disk
            return super().load()

    store = BackgroundLearningStore(lambda: Uncached(path))
    told: list[SetAsideLearningData | None] = []
    store.on_damaged = told.append
    with path.open("r+b") as file:
        file.seek(4096 * 3)
        file.write(bytes(range(256)) * 16)
    damaged = path.read_bytes()

    snapshot = store.load()

    assert snapshot.statuses == [] and snapshot.saved_words == []
    (aside,) = told
    assert aside is not None and aside.path.read_bytes() == damaged
    store.close()


def test_the_days_to_hand_over_answer_nothing_on_damage(tmp_path: Path) -> None:
    """163's read of the days not handed over yet (at the start, and as a
    day turns) goes through the same guard: a damaged store answers no
    days and is set aside, rather than raising into Learning (polyglotic-hq
    206, 209)."""
    path = tmp_path / "learning.sqlite"

    class DamagedLater(SqliteLearningStore):
        def days_to_hand_over(self) -> Sequence[date]:
            raise damage()

    store = BackgroundLearningStore(lambda: DamagedLater(path))
    told: list[SetAsideLearningData | None] = []
    store.on_damaged = told.append
    store.save_exposures(
        [StoredExposures("cedict:1", 1, 0, 0, date(2026, 11, 7))],
        {date(2026, 11, 7): {"cedict:1": 1}},
    )

    assert store.days_to_hand_over() == []

    assert store.out
    (aside,) = told
    assert aside is not None and aside.problem is LearningDataProblem.DAMAGED
    store.close()


def test_one_that_cant_be_set_aside_is_still_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "learning.sqlite"

    class DamagedLater(SqliteLearningStore):
        def save_level(self, level: StoredLevel) -> None:
            raise damage()

    store = BackgroundLearningStore(lambda: DamagedLater(path))
    told: list[SetAsideLearningData | None] = []
    store.on_damaged = told.append

    def refused(self: Path, target: Path) -> Path:
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "rename", refused)
    store.save_level(StoredLevel("hsk-2025", 1))
    store.flush()
    store.close()

    assert store.out and told == [None]
    assert path.exists()  # left where it was: the next start tries again


def test_deleting_once_out_still_deletes_the_copy_set_aside(tmp_path: Path) -> None:
    """Polyglotic-hq 207: found damaged mid-session, the store is out and
    its file set aside, with the learner's data in it; "Delete learning
    data... also from this PC" then deletes that copy all the same."""
    path = tmp_path / "learning.sqlite"
    filled(path)

    class DamagedLater(SqliteLearningStore):
        def save_level(self, level: StoredLevel) -> None:
            raise damage()

    store = BackgroundLearningStore(lambda: DamagedLater(path))
    store.save_level(StoredLevel("hsk-2025", 1))
    assert store.set_aside_copies() == 1 and store.out

    store.delete_learning_data()
    store.flush()

    assert store.set_aside_copies() == 0
    assert list(tmp_path.iterdir()) == []
    store.close()


def test_a_deletion_that_finds_the_store_damaged_deletes_its_copy(
    tmp_path: Path,
) -> None:
    path = tmp_path / "learning.sqlite"
    filled(path)

    class DamagedOnDeleting(SqliteLearningStore):
        def delete_learning_data(self) -> None:
            raise damage()

    store = BackgroundLearningStore(lambda: DamagedOnDeleting(path))
    told: list[SetAsideLearningData | None] = []
    store.on_damaged = told.append

    store.delete_learning_data()
    store.flush()

    (aside,) = told
    assert store.out and aside is not None and not aside.path.exists()
    assert list(tmp_path.iterdir()) == []
    store.close()
