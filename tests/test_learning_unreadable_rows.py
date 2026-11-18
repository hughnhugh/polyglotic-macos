"""A row SQLite reads but the app can't - a bad time, a status it doesn't
know, a value not of its column's type - is left out at the start, counted
and kept in the file; the rest loads (polyglotic-hq 207). Too many in a
table are a fault in how the app reads them, or a newer app's values: the
store is refused, nothing written. Real SQLite files, the bad values put
in directly; made-up text."""

import logging
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from tests.learning.test_vocabulary import lookup

from polyglotic_desktop.adapters.sqlite_learning import (
    LearningStoreUnreadableError,
    SqliteLearningStore,
    too_many_unreadable,
    unreadable_in,
)
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.ports.learning import (
    StoredAnkiExport,
    StoredCategory,
    StoredCoverage,
    StoredDeckWord,
    StoredExposures,
    StoredLevel,
    StoredListening,
    StoredSavedWord,
    StoredStatus,
)

AT = datetime(2026, 11, 8, 6, 30, tzinfo=UTC)
SENTENCE = "我的电脑又卡了"
STATUSES = 60


def filled(path: Path) -> None:
    """A learning store with something in every table."""
    store = SqliteLearningStore(path)
    store.save_level(StoredLevel("hsk-2025", 3.5))
    store.save_category(StoredCategory("saved", "Saved", "#6fc3ff", 0))
    store.save_category(StoredCategory("tricky", "Tricky", "#ff9f6f", 1))
    for n in range(STATUSES):
        store.save_status(StoredStatus(f"cedict:{n:06d}", "known", "learner", AT))
    for n in range(3):
        store.save_word(
            StoredSavedWord(
                f"cedict:w{n}", "电脑", "電腦", "diàn nǎo", "computer", "saved",
                SENTENCE, "My computer froze again", AT,
            )
        )  # fmt: skip
        store.save_deck_word(
            StoredDeckWord(
                f"cedict:d{n}", "电脑", "電腦", "diàn nǎo", "computer",
                SENTENCE, "My computer froze again", AT,
            )
        )  # fmt: skip
    store.save_anki_exports([StoredAnkiExport(f"cedict:d{n}", AT) for n in range(3)])
    store.save_exposures(
        [
            StoredExposures(f"cedict:{n:06d}", 3, 1, 0, date(2026, 11, 7))
            for n in range(3)
        ],
        {date(2026, 11, 7): {"cedict:000000": 2}},
    )
    # what was heard (polyglotic-hq 163)
    store.add_coverage(
        [StoredCoverage(date(2026, 11, day), 90, 5, 5) for day in (5, 6, 7)]
    )
    store.add_listening(
        [StoredListening(date(2026, 11, day), "video", 600.0) for day in (5, 6, 7)]
    )
    store.close()


GOOD = AT.isoformat()
GARBLED: dict[str, tuple[str, tuple[object, ...]]] = {
    "a status's bad time": (
        "INSERT INTO statuses VALUES (?, ?, ?, ?)",
        ("cedict:bad", "known", "learner", "yesterday-ish"),
    ),
    "a status this app doesn't know": (
        "INSERT INTO statuses VALUES (?, ?, ?, ?)",
        ("cedict:bad", "mastered", "learner", GOOD),
    ),
    "a status's source it doesn't know": (
        "INSERT INTO statuses VALUES (?, ?, ?, ?)",
        ("cedict:bad", "known", "someone", GOOD),
    ),
    "a status's time as bytes": (
        "INSERT INTO statuses VALUES (?, ?, ?, ?)",
        ("cedict:bad", "known", "learner", b"\x00\x01"),
    ),
    "a saved word's bad time": (
        "INSERT INTO saved_words VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("cedict:bad", "a", "a", "a", "a", "saved", SENTENCE, "t", "2026-13-45"),
    ),
    "a saved word's text as a number": (
        "INSERT INTO saved_words VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("cedict:bad", "a", "a", "a", "a", "saved", b"\xff", "t", GOOD),
    ),
    "a deck word's bad time": (
        "INSERT INTO deck_words VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("cedict:bad", "a", "a", "a", "a", SENTENCE, "t", ""),
    ),
    "an export's bad time": (
        "INSERT INTO anki_exports VALUES (?, ?)",
        ("cedict:bad", "never"),
    ),
    "a category's position as text": (
        "INSERT INTO categories VALUES (?, ?, ?, ?)",
        ("bad", "Bad", "#000000", "first"),
    ),
    "an exposure count as text": (
        "INSERT INTO exposures VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("cedict:bad", "lots", 0, 0, None, 0, None),
    ),
    # what was heard (polyglotic-hq 163, 209)
    "an exposure's bad first heard": (
        "INSERT INTO exposures VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("cedict:bad", 1, 0, 0, "last week", 1, None),
    ),
    # the days it was heard on (polyglotic-hq 489)
    "an exposure's days as text": (
        "INSERT INTO exposures VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("cedict:bad", 1, 0, 0, None, "a few", None),
    ),
    "an exposure's bad last heard": (
        "INSERT INTO exposures VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("cedict:bad", 1, 0, 0, None, 1, "yesterday"),
    ),
    "a day's coverage as text": (
        "INSERT INTO daily_coverage VALUES (?, ?, ?, ?)",
        ("2026-11-08", "most", 0, 0),
    ),
    "a coverage day that isn't one": (
        "INSERT INTO daily_coverage VALUES (?, ?, ?, ?)",
        ("someday", 1, 0, 0),
    ),
    "a day's listening as text": (
        "INSERT INTO daily_listening VALUES (?, ?, ?)",
        ("2026-11-08", "video", "an hour"),
    ),
}
TABLE = {name: insert.split()[2] for name, (insert, _) in GARBLED.items()}


def put(path: Path, insert: str, values: tuple[object, ...]) -> None:
    """Straight into the file, as nothing in the app would write it."""
    db = sqlite3.connect(path)
    db.execute(insert, values)
    db.commit()
    db.close()


def rows_in(path: Path, table: str) -> int:
    db = sqlite3.connect(path)
    (count,) = db.execute(f"SELECT count(*) FROM {table}").fetchone()
    db.close()
    return int(count)


@pytest.mark.parametrize("garble", GARBLED)
def test_a_garbled_row_is_left_out_and_the_rest_loads(
    tmp_path: Path, garble: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "learning.sqlite"
    filled(path)
    put(path, *GARBLED[garble])
    table = TABLE[garble]
    before = rows_in(path, table)

    store = SqliteLearningStore(path)
    with caplog.at_level(logging.INFO):
        # what the app does at the start: core's Learning takes it all in
        vocabulary = Vocabulary(store, lookup, "hsk-2025")
    snapshot = store.load()
    store.close()

    assert vocabulary.line is not None
    assert len(snapshot.statuses) == STATUSES
    assert [c.id for c in snapshot.categories] == ["saved", "tricky"]
    assert len(snapshot.saved_words) == len(snapshot.deck_words) == 3
    assert len(snapshot.anki_exports) == len(snapshot.exposures) == 3
    assert {row.first_heard for row in snapshot.exposures} == {date(2026, 11, 7)}
    assert [row.day.day for row in snapshot.coverage] == [5, 6, 7]
    assert [row.day.day for row in snapshot.listening] == [5, 6, 7]
    entry_ids = {
        *(row.entry_id for row in snapshot.statuses),
        *(row.entry_id for row in snapshot.saved_words),
        *(row.entry_id for row in snapshot.deck_words),
        *(row.entry_id for row in snapshot.anki_exports),
        *(row.entry_id for row in snapshot.exposures),
    }
    assert "cedict:bad" not in entry_ids
    assert rows_in(path, table) == before  # kept in the file, as it was
    assert f"1 row(s) that can't be read left out, kept in the file ({table} 1 of" in (
        caplog.text
    )
    assert SENTENCE not in caplog.text and "cedict:bad" not in caplog.text


def test_a_garbled_level_is_left_out(tmp_path: Path) -> None:
    """The level picker asks again, as on a first run."""
    path = tmp_path / "learning.sqlite"
    filled(path)
    db = sqlite3.connect(path)
    db.execute("UPDATE level SET midpoint = 'middling'")
    db.commit()
    db.close()

    store = SqliteLearningStore(path)
    assert store.load().level is None
    store.close()


@pytest.mark.parametrize(
    ("unreadable", "rows", "refused"),
    [
        (0, 0, False),
        (1, 1, False),  # one row, garbled: never worth a dead start
        (2, 2, False),
        (3, 3, True),  # a whole table: a fault in reading, not garbling
        (3, 10, True),
        (3, 60, False),  # 5 %
        (5, 100, False),
        (6, 100, True),
        (50, 1000, False),
        (51, 1000, True),
    ],
)
def test_how_many_unreadable_rows_are_too_many(
    unreadable: int, rows: int, refused: bool
) -> None:
    assert too_many_unreadable(unreadable, rows) is refused


def test_too_many_refuse_the_store_and_nothing_is_written(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Every status in a value this app doesn't know - say a newer app's,
    after moving to an older channel: refused, as a newer app's file is,
    rather than shown as if the learner's words were gone."""
    path = tmp_path / "learning.sqlite"
    filled(path)
    db = sqlite3.connect(path)
    db.execute("UPDATE statuses SET status = 'mastered'")
    db.commit()
    db.close()
    before = path.read_bytes()
    folder = {each.name: each.read_bytes() for each in tmp_path.iterdir()}

    store = SqliteLearningStore(path)
    with (
        caplog.at_level(logging.INFO),
        pytest.raises(LearningStoreUnreadableError) as refused,
    ):
        Vocabulary(store, lookup, "hsk-2025")
    store.close()

    assert (refused.value.table, refused.value.unreadable) == ("statuses", STATUSES)
    assert path.read_bytes() == before
    # the store and the level's copy beside it (decision 0048), as they were
    assert {each.name: each.read_bytes() for each in tmp_path.iterdir()} == folder
    assert (
        f"the learning data is refused: {STATUSES} of {STATUSES} rows in statuses"
        in caplog.text
    )
    assert "mastered" not in caplog.text and "cedict:" not in caplog.text


def test_a_garbled_day_of_daily_counts_is_left_out(tmp_path: Path) -> None:
    """Handed over at the start (`share_finished_days`)."""
    path = tmp_path / "learning.sqlite"
    filled(path)
    put(path, "INSERT INTO daily_exposures VALUES (?, ?, ?)", ("someday", "x", 1))
    put(
        path,
        "INSERT INTO daily_exposures VALUES (?, ?, ?)",
        ("2026-11-07", "cedict:000001", "two"),
    )

    store = SqliteLearningStore(path)
    vocabulary = Vocabulary(store, lookup, "hsk-2025")
    taken = vocabulary.take_finished_exposure_days(date(2026, 11, 8))
    store.close()

    assert taken == {date(2026, 11, 7): {"cedict:000000": 2}}


def test_unreadable_rows_are_counted_for_the_check_without_writing(
    tmp_path: Path,
) -> None:
    """`--check-install`'s numbers: counts per store, read-only."""
    filled(tmp_path / "learning.sqlite")
    put(tmp_path / "learning.sqlite", *GARBLED["a status's bad time"])
    english = tmp_path / "learning-en.sqlite"
    filled(english)
    db = sqlite3.connect(english)
    db.execute("UPDATE anki_exports SET exported_at = 'never'")
    db.commit()
    db.close()
    whole = tmp_path / "learning-xx.sqlite"
    filled(whole)
    (tmp_path / "learning.sqlite.damaged-20261108T063000Z").write_bytes(b"aside")
    before = {each.name: each.read_bytes() for each in tmp_path.iterdir()}

    found = unreadable_in(tmp_path)

    assert found == {
        "learning-en.sqlite": (3, "anki_exports"),
        "learning-xx.sqlite": (0, None),
        "learning.sqlite": (1, None),
    }
    assert {each.name: each.read_bytes() for each in tmp_path.iterdir()} == before
