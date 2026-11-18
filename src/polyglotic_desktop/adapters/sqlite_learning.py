"""The learner's own learning data on this PC: one SQLite file (why:
decision 0010).

`SqliteLearningStore` implements the `LearningStore` port for core's
Learning: the level, explicit word statuses, categories, saved words
(with their source sentences), exposure counts and the daily counts kept
for opt-in sharing. Every change is written at once, so closing the app -
or a crash - loses nothing already shown.

The file's schema version is SQLite's `user_version`. A newer app adds to
it with one migration per version (`_MIGRATIONS`); an older app refuses a
file from a newer one rather than damage it.

`open_learning_store` is how the app opens it (polyglotic-hq 206): a file
that can't be read - a folder in its place, cut off, overwritten in
places, not SQLite, not learning data - is renamed aside, never deleted or
written over, and a new one started, rather than the app failing to
start. A file from a newer app is still refused. What the server keeps -
statuses and saved words - comes back by the connection's sync; what was
only on this PC stays in the file set aside. One found damaged after the
start - a save or a read failing - is set aside then (`set_aside_now`),
and the next start begins a new one. Each file set aside holds a copy of
the learner's data, so the learner deleting their learning data on this
PC deletes those too (`delete_set_aside`, polyglotic-hq 207).

A row SQLite reads but this app can't - a value not of its column's type,
a time or a status it can't parse - is left out of `load` and counted,
and stays in the file (polyglotic-hq 207): a garbled row never stops the
start. More of a table's rows than a few garbled ones explain
(`too_many_unreadable`) is a fault in how this app reads them, or a newer
app's values: the store is refused as a newer app's is, with nothing
written, rather than shown to the learner as if those rows were gone.

What the learner deletes or replaces - a saved word, a category, a deck
word, a sentence, a category's name - leaves none of its text readable in
the file or its write-ahead log, at once (polyglotic-hq 213): SQLite's
`secure_delete` zeroes it, and a checkpoint after that write copies the
log into the file and empties it (`_scrub`). A caption's counts never
wait on a checkpoint. Another program reading the file can keep that
checkpoint from finishing until it lets go; then it's tried again after
each write and at close (polyglotic-hq 237).

The level is kept twice (decision 0048, polyglotic-hq 237): in the store,
and in a small file beside it (`level_file`: `learning-level.json` beside
`learning.sqlite`), written with every change of level. A store started
again after one was set aside takes the level from that file, so the
learner isn't asked it again before anything says why; a store with a
level writes it there when the file's is missing or different (the first
start of an app with this). It never leaves the PC, and like the level in
the store it stays when the learner deletes their learning data.

Tables:
- `level`: one row - the scheme and the curve's midpoint.
- `statuses`: entry ID -> status, source, when set (UTC, ISO 8601).
- `categories`: id, name, colour, position.
- `saved_words`: entry ID -> headword, traditional, reading, meaning,
  category, source sentence and its translation, when saved.
- `deck_words`: entry ID -> the text and the line (with its translation)
  a word went into the deck with, and when (version 2).
- `anki_exports`: entry ID -> when it was last written to an Anki file
  (version 2).
- `exposures`: entry ID -> heard, heard by you, heard in the deck.
- `daily_exposures`: (UTC date, entry ID) -> captions heard in from what
  the PC played; for opt-in sharing (D3b sends them).
- `daily_coverage`: UTC date -> the tokens of its finished captions that
  were known, in the deck and new (version 3); never sent.
- `daily_listening`: (UTC date, source category) -> seconds of listening
  with captions on (version 4); never sent.
- version 5: `exposures.first_heard` (the UTC day an entry was first
  heard; NULL before), and `handed_over_days`: the days whose daily counts
  were handed over for sharing - kept 8 weeks, not deleted at once
  (decision 0041).
- version 6: `load_words`: entry ID -> a word of the learning load - its
  standing, stage, meetings, whether added by hand, its place, and when it
  entered, last counted and graduated (polyglotic-hq 324, decision 0117);
  never sent.
- version 7: `anki_csv_exports`: entry ID -> when it was last written to a
  CSV file; `anki_exports` is the deck file's from then on - each kind of
  file remembers its own exports (polyglotic-hq 368). It starts as a copy
  of `anki_exports`: which kind wrote a word before is unknown, so both
  remember it, as "only words not exported yet" did.
- version 8: `lookups`: entry ID -> how often the word was looked up on
  this PC, pinned (a click) and on hover, when last, and how many pinned
  lookups since the learner last said they know it (polyglotic-hq 373,
  DECISIONS #176 (c), (d)); never sent - the server already gets each
  lookup as an entry ID and a time. It starts with one pinned lookup for
  every word a pinned lookup had turned back to new (a status "new" whose
  source is "estimated": the only lookups kept before).
- version 9: `saved_sentences`: id -> a saved sentence - what was said,
  its translation and that translation's language, its parts (each
  clause's text, links and speaker, as JSON: `_parts_json`), its category
  (shared with saved words: deleting a category deletes its sentences)
  and when it was saved (polyglotic-hq 459, decision 0216); never sent.
- version 10 (polyglotic-hq 477, decision 0219; never sent):
  `curriculum_words`: entry ID -> a word of our curriculum's active set -
  in it or retired, why it came, when it entered, the days it was met on
  and the last, the sittings it sat, when it retired; `status_history`
  and `line_history`: every change of a word's status (before, after, who,
  when) and every move of the known line, appended in order and never
  changed (474's store hooks); `set_words`: (set name, entry ID) -> a
  word of a named word set with its sources and when added - the quiet
  view's chosen words, `quiet`.
- version 11 (polyglotic-hq 489, decision 0226; never sent):
  `exposures.days_heard` and `exposures.last_heard` - the separate days
  a word was heard on from what the PC played, and the last of them (the
  learner's own day), for how well each word is known. Filled in from
  the daily counts still kept (the last 8 weeks, UTC days), and at least
  1 for a word heard.
"""

from __future__ import annotations

import contextlib
import functools
import glob
import json
import logging
import os
import re
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from types import TracebackType
from typing import Concatenate, TypeVar

from polyglotic_desktop.core.learning.statuses import StatusSource
from polyglotic_desktop.core.shared import WordStatus
from polyglotic_desktop.ports.learning import (
    LearningDataProblem,
    LearningSnapshot,
    SetAsideLearningData,
    StoredAnkiExport,
    StoredCategory,
    StoredCoverage,
    StoredCurriculumWord,
    StoredDeckWord,
    StoredExposures,
    StoredLevel,
    StoredLineChange,
    StoredListening,
    StoredLoadWord,
    StoredLookups,
    StoredSavedWord,
    StoredSentence,
    StoredSentencePart,
    StoredSetWord,
    StoredStatus,
    StoredStatusChange,
)

_MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (  # version 1
        """CREATE TABLE level (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            scheme TEXT NOT NULL,
            midpoint REAL NOT NULL
        )""",
        """CREATE TABLE statuses (
            entry_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source TEXT NOT NULL,
            at TEXT NOT NULL
        ) WITHOUT ROWID""",
        """CREATE TABLE categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            position INTEGER NOT NULL
        ) WITHOUT ROWID""",
        """CREATE TABLE saved_words (
            entry_id TEXT PRIMARY KEY,
            headword TEXT NOT NULL,
            traditional TEXT NOT NULL,
            reading TEXT NOT NULL,
            meaning TEXT NOT NULL,
            category_id TEXT NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
            source_sentence TEXT NOT NULL,
            source_translation TEXT NOT NULL,
            saved_at TEXT NOT NULL
        ) WITHOUT ROWID""",
        """CREATE TABLE exposures (
            entry_id TEXT PRIMARY KEY,
            heard INTEGER NOT NULL,
            heard_by_you INTEGER NOT NULL,
            heard_in_deck INTEGER NOT NULL
        ) WITHOUT ROWID""",
        """CREATE TABLE daily_exposures (
            day TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (day, entry_id)
        ) WITHOUT ROWID""",
    ),
    (  # version 2: the line a word went into the deck with; Anki exports
        """CREATE TABLE deck_words (
            entry_id TEXT PRIMARY KEY,
            headword TEXT NOT NULL,
            traditional TEXT NOT NULL,
            reading TEXT NOT NULL,
            meaning TEXT NOT NULL,
            sentence TEXT NOT NULL,
            translation TEXT NOT NULL,
            learned_at TEXT NOT NULL
        ) WITHOUT ROWID""",
        """CREATE TABLE anki_exports (
            entry_id TEXT PRIMARY KEY,
            exported_at TEXT NOT NULL
        ) WITHOUT ROWID""",
    ),
    (  # version 3: each day's coverage (polyglotic-hq project 163)
        """CREATE TABLE daily_coverage (
            day TEXT PRIMARY KEY,
            known INTEGER NOT NULL,
            deck INTEGER NOT NULL,
            new INTEGER NOT NULL
        ) WITHOUT ROWID""",
    ),
    (  # version 4: each day's listening, by source category (project 163)
        """CREATE TABLE daily_listening (
            day TEXT NOT NULL,
            category TEXT NOT NULL,
            seconds REAL NOT NULL,
            PRIMARY KEY (day, category)
        ) WITHOUT ROWID""",
    ),
    (  # version 5: first heard; daily counts kept once handed over (0041)
        "ALTER TABLE exposures ADD COLUMN first_heard TEXT",
        """CREATE TABLE handed_over_days (
            day TEXT PRIMARY KEY
        ) WITHOUT ROWID""",
    ),
    (  # version 6: the learning load's words (polyglotic-hq 324, 0117)
        """CREATE TABLE load_words (
            entry_id TEXT PRIMARY KEY,
            standing TEXT NOT NULL,
            stage INTEGER NOT NULL,
            meetings INTEGER NOT NULL,
            by_hand INTEGER NOT NULL,
            place INTEGER,
            entered_at TEXT NOT NULL,
            last_met TEXT,
            graduated_at TEXT
        ) WITHOUT ROWID""",
    ),
    (  # version 7: a CSV's exports apart from a deck file's (polyglotic-hq 368)
        """CREATE TABLE anki_csv_exports (
            entry_id TEXT PRIMARY KEY,
            exported_at TEXT NOT NULL
        ) WITHOUT ROWID""",
        "INSERT INTO anki_csv_exports SELECT entry_id, exported_at FROM anki_exports",
    ),
    (  # version 8: lookups kept, with counts and the last time (373)
        """CREATE TABLE lookups (
            entry_id TEXT PRIMARY KEY,
            pinned INTEGER NOT NULL,
            hovered INTEGER NOT NULL,
            last_at TEXT NOT NULL,
            pinned_since_known INTEGER NOT NULL
        ) WITHOUT ROWID""",
        (
            "INSERT INTO lookups SELECT entry_id, 1, 0, at, 0 FROM statuses"
            " WHERE source = 'estimated' AND status = 'new'"
        ),
    ),
    (  # version 9: saved sentences (polyglotic-hq 459, decision 0216)
        """CREATE TABLE saved_sentences (
            id TEXT PRIMARY KEY,
            original TEXT NOT NULL,
            translation TEXT NOT NULL,
            parts TEXT NOT NULL,
            translation_language TEXT NOT NULL,
            category_id TEXT NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
            saved_at TEXT NOT NULL
        ) WITHOUT ROWID""",
    ),
    (  # version 10: our curriculum, the histories, word sets (477, 0219)
        """CREATE TABLE curriculum_words (
            entry_id TEXT PRIMARY KEY,
            standing TEXT NOT NULL,
            came TEXT NOT NULL,
            entered_at TEXT NOT NULL,
            days_met INTEGER NOT NULL,
            last_day TEXT,
            sittings INTEGER NOT NULL,
            retired_at TEXT
        ) WITHOUT ROWID""",
        """CREATE TABLE status_history (
            id INTEGER PRIMARY KEY,
            entry_id TEXT NOT NULL,
            before TEXT NOT NULL,
            after TEXT NOT NULL,
            source TEXT NOT NULL,
            at TEXT NOT NULL
        )""",
        """CREATE TABLE line_history (
            id INTEGER PRIMARY KEY,
            scheme TEXT,
            midpoint REAL,
            source TEXT NOT NULL,
            at TEXT NOT NULL
        )""",
        """CREATE TABLE set_words (
            name TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            sources TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (name, entry_id)
        ) WITHOUT ROWID""",
    ),
    (  # version 11: the days a word was heard on (polyglotic-hq 489, 0226)
        "ALTER TABLE exposures ADD COLUMN days_heard INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE exposures ADD COLUMN last_heard TEXT",
        (
            "UPDATE exposures SET"
            " days_heard = MAX(heard > 0, (SELECT COUNT(*) FROM daily_exposures d"
            " WHERE d.entry_id = exposures.entry_id AND d.count > 0)),"
            " last_heard = (SELECT MAX(day) FROM daily_exposures d"
            " WHERE d.entry_id = exposures.entry_id AND d.count > 0)"
        ),
        "UPDATE exposures SET last_heard = first_heard WHERE last_heard IS NULL",
    ),
)
VERSION = len(_MIGRATIONS)
_TABLES = tuple(
    frozenset(re.findall(r"CREATE TABLE (\w+)", " ".join(migration)))
    for migration in _MIGRATIONS
)
"""The tables each version adds."""
_COLUMNS = tuple(
    frozenset(re.findall(r"ALTER TABLE (\w+) ADD COLUMN (\w+)", " ".join(migration)))
    for migration in _MIGRATIONS
)
"""The columns each version adds to a table it didn't create, as (table,
column): version 5's `exposures.first_heard` (polyglotic-hq 163, 209)."""
_DAMAGED = frozenset({"SQLITE_NOTADB", "SQLITE_CORRUPT"})
"""SQLite's answers for a file that isn't a database, or is damaged."""
KEEP_SET_ASIDE = 3
"""Files set aside kept per learning store, the newest: an older one goes
when a newer is set aside, so a file damaged at every start can't fill the
disk."""
_ANKI_TABLES = {"deck": "anki_exports", "csv": "anki_csv_exports"}
"""Where each kind of Anki file's exports are kept (`StoredAnkiExport.kind`)."""
UNREADABLE_AT_MOST = 2
UNREADABLE_SHARE = 0.05
"""Rows of a table that can't be read, left out at the start: up to
`UNREADABLE_AT_MOST`, or up to `UNREADABLE_SHARE` of the table's rows if
that's more. Beyond it the store is refused (`too_many_unreadable`)."""

log = logging.getLogger(__name__)


class LearningStoreFormatError(Exception):
    """The file was written by a newer version of the app: refused, and
    left as it is (RELEASING.md)."""


class LearningStoreDamagedError(Exception):
    """The file can't be read as a learning store - `problem` says why."""

    def __init__(self, problem: LearningDataProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


class LearningStoreUnreadableError(Exception):
    """More of a table's rows can't be read than a few garbled ones explain
    (`too_many_unreadable`): refused, nothing written, and left as it is
    (polyglotic-hq 207). Says how many, never what they hold."""

    def __init__(self, table: str, unreadable: int, rows: int) -> None:
        super().__init__(f"{unreadable} of {rows} rows in {table} can't be read")
        self.table = table
        self.unreadable = unreadable
        self.rows = rows


class _Transaction:
    """BEGIN ... COMMIT, or ROLLBACK on an error. The connection is in
    autocommit mode, so any single statement is its own transaction."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def __enter__(self) -> None:
        self._db.execute("BEGIN")

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self._db.execute("ROLLBACK" if kind else "COMMIT")


def _then_scrub[**Args, Result](
    write: Callable[Concatenate[SqliteLearningStore, Args], Result],
) -> Callable[Concatenate[SqliteLearningStore, Args], Result]:
    """A write to the store, then the checkpoint `_scrub` still owes, if it
    owes one: tried after each write until another program lets go of the
    file (polyglotic-hq 237). It never waits, so a caption's counts don't
    either."""

    @functools.wraps(write)
    def written(
        store: SqliteLearningStore, *args: Args.args, **kwargs: Args.kwargs
    ) -> Result:
        result = write(store, *args, **kwargs)
        if store._scrub_owed:
            store._scrub()
        return result

    return written


class SqliteLearningStore:
    """The learning store at `path`, created if missing (":memory:" for
    one that's never written to disk). Use it from the thread that
    opened it."""

    def __init__(self, path: Path | str) -> None:
        """Raises `LearningStoreFormatError` for a newer app's file,
        `LearningStoreDamagedError` for one that can't be read as a learning
        store - each left as it was found - and SQLite's own error for a
        file that's locked or out of reach (not the file's fault)."""
        self.set_aside: SetAsideLearningData | None = None
        """The file found here before, if it couldn't be read
        (`open_learning_store`)."""
        self.created = False
        """This open started the store: there was nothing in it."""
        self._scrub_owed = False
        """A checkpoint after the learner's text went (`_scrub`) couldn't
        finish: another program held the file."""
        self._path = path
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                raise LearningStoreDamagedError(LearningDataProblem.FOLDER)
        self._db = sqlite3.connect(path, isolation_level=None)
        try:
            version = self._check()
            self.created = version == 0
            self._db.execute("PRAGMA foreign_keys = ON")
            # what a delete or a replace frees is written over with zeros,
            # freed pages too (not FAST: it leaves those) - `_scrub`
            self._db.execute("PRAGMA secure_delete = ON")
            self._db.execute("PRAGMA journal_mode = WAL")
            self._migrate(version)
            self._follow_level_file()
        except sqlite3.DatabaseError as e:
            self._close_as_found()
            if is_damage(e):
                raise LearningStoreDamagedError(LearningDataProblem.DAMAGED) from e
            raise  # locked, out of reach, a disk error: not the file's fault
        except BaseException:
            self._close_as_found()
            raise

    def _check(self) -> int:
        """The file's version, once it's known to be whole and a learning
        store - read only, before anything is written. The version first:
        it's read from the header alone, while SQLite's check reads the
        schema, which a newer SQLite may have written in a form this one
        calls damaged."""
        db = self._db
        (version,) = db.execute("PRAGMA user_version").fetchone()
        if version > VERSION:
            raise LearningStoreFormatError(_newer(version))
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise LearningStoreDamagedError(LearningDataProblem.DAMAGED)
        tables = {
            name
            for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        wanted = frozenset().union(*_TABLES[: max(version, 0)])
        if version < 0 or not wanted <= tables or (version == 0 and tables):
            raise LearningStoreDamagedError(LearningDataProblem.NOT_LEARNING_DATA)
        for table, column in frozenset().union(*_COLUMNS[: max(version, 0)]):
            # a column a version added, missing: every load would fail on
            # it (a missing table is caught above)
            if column not in {
                name for _, name, *_ in db.execute(f"PRAGMA table_info({table})")
            }:
                raise LearningStoreDamagedError(LearningDataProblem.NOT_LEARNING_DATA)
        return int(version)

    def _close_as_found(self) -> None:
        """Closed without writing: a file that couldn't be opened is kept
        as it was, its write-ahead log too (not checkpointed into it)."""
        with contextlib.suppress(sqlite3.Error):
            self._db.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
        self._db.close()

    def _migrate(self, version: int) -> None:
        """Every migration the file lacks, in one transaction: a new store's
        nine are one write to the disk, not nine, and one that fails leaves
        the file as it was found. A pack language's learning data is made
        as its pack opens, the interface waiting for it: on a Ryzen 5 5600X
        a new store took 22 ms on a quiet PC (12 of them the commits) and
        45 ms beside other work; in one transaction, 13 (polyglotic-hq 509)."""
        if version == VERSION:
            return
        with _Transaction(self._db):
            for number in range(version, VERSION):
                for statement in _MIGRATIONS[number]:
                    self._db.execute(statement)
            self._db.execute(f"PRAGMA user_version = {VERSION}")

    def _follow_level_file(self) -> None:
        """The level and its copy beside the store agree (decision 0048):
        a store with no level - new, or started again after one was set
        aside - takes the copy's; one whose level reads writes it to the
        copy when that's missing or different. A level row that can't be
        read is left for `load` to count, and the copy as it is."""
        if not isinstance(self._path, Path):
            return
        rows = self._db.execute("SELECT scheme, midpoint FROM level").fetchall()
        kept = read_level_file(self._path)
        if not rows:
            if kept is not None:
                self._insert_level(kept)
                log.info("the level was taken from the copy beside the learning data")
            return
        try:
            stored = _level(rows[0])
        except (TypeError, ValueError):
            return
        if stored != kept:
            _write_level_file(self._path, stored)

    def close(self) -> None:
        """A checkpoint still owed (`_scrub`) is tried once more first."""
        if self._scrub_owed:
            with contextlib.suppress(sqlite3.Error):
                self._scrub()
            if self._scrub_owed:
                log.warning(
                    "the learning data's log is still read by another program"
                    " at close: emptied once that program lets go of it"
                )
        self._db.close()

    def _scrub(self) -> None:
        """The learner's text was just deleted or written over (polyglotic-hq
        213). `secure_delete` has zeroed it in the page, but the file keeps
        the page as it was until a checkpoint, and the write-ahead log keeps
        earlier copies until written over: the log is copied into the file
        and emptied, so none of it stays readable in either while the app
        runs. Only after such a write - never a caption's counts.

        The checkpoint never waits. Another program reading the file - the
        app has this one connection to it, and `unreadable_in`'s immutable
        reader takes no locks - can hold an older snapshot, and the checkpoint can't finish until it
        lets go: SQLite answers `busy` (polyglotic-hq 237, from 226's Low 2;
        waiting, it held the learning thread 5 s and then gave up silently).
        Then it's owed, and tried again after each write (`_then_scrub`)
        and at close, until it finishes."""
        (waited,) = self._db.execute("PRAGMA busy_timeout").fetchone()
        self._db.execute("PRAGMA busy_timeout = 0")
        try:
            busy, frames, copied = self._db.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)"
            ).fetchone()
        finally:
            self._db.execute(f"PRAGMA busy_timeout = {int(waited)}")
        owed = bool(busy) or frames != copied
        if owed and not self._scrub_owed:
            log.info(
                "the learning data's log couldn't be emptied yet: another"
                " program is reading the file; tried again after each write"
            )
        self._scrub_owed = owed

    def _has(self, table: str, entry_id: str) -> bool:
        return (
            self._db.execute(
                f"SELECT 1 FROM {table} WHERE entry_id = ?", (entry_id,)
            ).fetchone()
            is not None
        )

    def set_aside_now(self) -> SetAsideLearningData | None:
        """Found damaged after the start (`is_damage`): closed as it is, and
        renamed aside with its WAL files as at a start; the next start
        begins a new one. None for a store in memory. Raises `OSError` if it
        can't be renamed - it's left where it is, closed."""
        self._close_as_found()
        if not isinstance(self._path, Path):
            return None
        aside = _set_aside(self._path)
        log.warning("the learning data was found damaged: set aside as %s", aside.name)
        _keep_newest(self._path)
        self.set_aside = SetAsideLearningData(aside, LearningDataProblem.DAMAGED)
        return self.set_aside

    # -- reading ----------------------------------------------------------------------

    def load(self) -> LearningSnapshot:
        """Everything stored that can be read. A row that can't be is left
        out, kept in the file, and logged by count (polyglotic-hq 207);
        `LearningStoreUnreadableError` if a table has too many of them."""
        snapshot, tally = _read(self._db)
        for table, (unreadable, rows) in tally.items():
            if too_many_unreadable(unreadable, rows):
                log.error(
                    "the learning data is refused: %d of %d rows in %s can't be"
                    " read, more than garbled rows explain - a fault in how this"
                    " app reads them, or a newer app's values. Nothing is written;"
                    " the file is left as it is",
                    unreadable,
                    rows,
                    table,
                )
                raise LearningStoreUnreadableError(table, unreadable, rows)
        if left_out := _left_out(tally):
            log.warning(
                "the learning data: %d row(s) that can't be read left out, kept"
                " in the file (%s)",
                sum(unreadable for unreadable, _ in tally.values()),
                left_out,
            )
        return snapshot

    def daily_exposures(self, day: date) -> Mapping[str, int]:
        return dict(
            self._db.execute(
                "SELECT entry_id, count FROM daily_exposures "
                "WHERE day = ? AND count != 0 AND typeof(count) = 'integer'",
                (day.isoformat(),),
            )
        )

    def exposure_days(self) -> Sequence[date]:
        days: list[date] = []
        unreadable = 0
        for (day,) in self._db.execute(
            "SELECT DISTINCT day FROM daily_exposures ORDER BY day"
        ):
            try:
                days.append(date.fromisoformat(_text(day)))
            except (ValueError, TypeError):
                unreadable += 1  # left in the file, as at the start (207)
        if unreadable:
            log.warning(
                "daily counts: %d day(s) that can't be read left out", unreadable
            )
        return days

    def days_to_hand_over(self) -> Sequence[date]:
        days: list[date] = []
        unreadable = 0
        for (day,) in self._db.execute(
            "SELECT DISTINCT day FROM daily_exposures WHERE day NOT IN "
            "(SELECT day FROM handed_over_days) ORDER BY day"
        ):
            try:
                days.append(_day(day))
            except (ValueError, TypeError):
                unreadable += 1  # left in the file, as `exposure_days` does (207)
        if unreadable:
            log.warning(
                "daily counts to hand over: %d day(s) that can't be read left out",
                unreadable,
            )
        return days

    def saved_sentences(self) -> Sequence[StoredSentence]:
        """Read apart from `load`, when first wanted (polyglotic-hq 459): a
        row that can't be read is left out, kept in the file, and logged by
        count - however many, since nothing here is written back from what
        was read."""
        kept: list[StoredSentence] = []
        unreadable = 0
        for row in self._db.execute(
            "SELECT id, original, translation, parts, translation_language, "
            "category_id, saved_at FROM saved_sentences"
        ):
            try:
                kept.append(_sentence(row))
            except (ValueError, TypeError):
                unreadable += 1
        if unreadable:
            log.warning(
                "saved sentences: %d of %d that can't be read left out, kept in"
                " the file",
                unreadable,
                unreadable + len(kept),
            )
        return kept

    # -- writing ----------------------------------------------------------------------

    @_then_scrub
    def save_level(self, level: StoredLevel) -> None:
        self._insert_level(level)
        if isinstance(self._path, Path):
            _write_level_file(self._path, level)  # decision 0048

    @_then_scrub
    def clear_level(self) -> None:
        """The level gone from the store and from its copy beside it, so a
        store started again doesn't take the copy's (decision 0048)."""
        self._db.execute("DELETE FROM level")
        if isinstance(self._path, Path):
            try:
                level_file(self._path).unlink(missing_ok=True)
            except OSError as error:
                log.warning(
                    "the level's copy couldn't be removed (%s)", type(error).__name__
                )

    def _insert_level(self, level: StoredLevel) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO level VALUES (1, ?, ?)",
            (level.scheme, level.midpoint),
        )

    @_then_scrub
    def save_status(self, status: StoredStatus) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO statuses VALUES (?, ?, ?, ?)",
            (status.entry_id, status.status, status.source, status.at.isoformat()),
        )

    @_then_scrub
    def save_category(self, category: StoredCategory) -> None:
        old = self._db.execute(
            "SELECT name FROM categories WHERE id = ?", (category.id,)
        ).fetchone()
        # not INSERT OR REPLACE: replacing a row deletes it first, and its
        # saved words with it
        self._db.execute(
            "INSERT INTO categories VALUES (?, ?, ?, ?) ON CONFLICT (id) DO UPDATE "
            "SET name = excluded.name, color = excluded.color, "
            "position = excluded.position",
            (category.id, category.name, category.color, category.position),
        )
        if old is not None and old[0] != category.name:
            self._scrub()  # renamed: the old name goes

    @_then_scrub
    def delete_category(self, category_id: str) -> None:
        # its saved words go with it (ON DELETE CASCADE)
        if self._db.execute(
            "DELETE FROM categories WHERE id = ?", (category_id,)
        ).rowcount:
            self._scrub()

    @_then_scrub
    def save_word(self, word: StoredSavedWord) -> None:
        replacing = self._has("saved_words", word.entry_id)
        self._db.execute(
            "INSERT OR REPLACE INTO saved_words VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                word.entry_id,
                word.headword,
                word.traditional,
                word.reading,
                word.meaning,
                word.category_id,
                word.source_sentence,
                word.source_translation,
                word.saved_at.isoformat(),
            ),
        )
        if replacing:
            self._scrub()  # its old sentence goes

    @_then_scrub
    def delete_word(self, entry_id: str) -> None:
        if self._db.execute(
            "DELETE FROM saved_words WHERE entry_id = ?", (entry_id,)
        ).rowcount:
            self._scrub()

    @_then_scrub
    def save_sentence(self, sentence: StoredSentence) -> None:
        replacing = (
            self._db.execute(
                "SELECT 1 FROM saved_sentences WHERE id = ?", (sentence.id,)
            ).fetchone()
            is not None
        )
        self._db.execute(
            "INSERT OR REPLACE INTO saved_sentences VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sentence.id,
                sentence.original,
                sentence.translation,
                _parts_json(sentence.parts),
                sentence.translation_language,
                sentence.category_id,
                sentence.saved_at.isoformat(),
            ),
        )
        if replacing:
            self._scrub()  # its old text goes

    @_then_scrub
    def delete_sentence(self, sentence_id: str) -> None:
        if self._db.execute(
            "DELETE FROM saved_sentences WHERE id = ?", (sentence_id,)
        ).rowcount:
            self._scrub()

    @_then_scrub
    def save_deck_word(self, word: StoredDeckWord) -> None:
        replacing = self._has("deck_words", word.entry_id)
        self._db.execute(
            "INSERT OR REPLACE INTO deck_words VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                word.entry_id,
                word.headword,
                word.traditional,
                word.reading,
                word.meaning,
                word.sentence,
                word.translation,
                word.learned_at.isoformat(),
            ),
        )
        if replacing:
            self._scrub()  # its old line goes

    @_then_scrub
    def delete_deck_word(self, entry_id: str) -> None:
        if self._db.execute(
            "DELETE FROM deck_words WHERE entry_id = ?", (entry_id,)
        ).rowcount:
            self._scrub()

    @_then_scrub
    def save_anki_exports(self, exports: Iterable[StoredAnkiExport]) -> None:
        # each kind of file in its own table (368): the deck file's, the CSV's
        rows = [(_ANKI_TABLES.get(e.kind), e) for e in exports]
        with _Transaction(self._db):
            for table in _ANKI_TABLES.values():
                self._db.executemany(
                    f"INSERT OR REPLACE INTO {table} VALUES (?, ?)",
                    [
                        (e.entry_id, e.exported_at.isoformat())
                        for t, e in rows
                        if t == table
                    ],
                )

    @_then_scrub
    def save_load_words(self, words: Sequence[StoredLoadWord]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT OR REPLACE INTO load_words VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        w.entry_id,
                        w.standing,
                        w.stage,
                        w.meetings,
                        int(w.by_hand),
                        w.place,
                        w.entered_at.isoformat(),
                        w.last_met.isoformat() if w.last_met else None,
                        w.graduated_at.isoformat() if w.graduated_at else None,
                    )
                    for w in words
                ],
            )

    @_then_scrub
    def save_curriculum_words(self, words: Sequence[StoredCurriculumWord]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT OR REPLACE INTO curriculum_words VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        w.entry_id,
                        w.standing,
                        w.came,
                        w.entered_at.isoformat(),
                        w.days_met,
                        w.last_day.isoformat() if w.last_day else None,
                        w.sittings,
                        w.retired_at.isoformat() if w.retired_at else None,
                    )
                    for w in words
                ],
            )

    @_then_scrub
    def delete_curriculum_words(self, entry_ids: Sequence[str]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "DELETE FROM curriculum_words WHERE entry_id = ?",
                [(entry_id,) for entry_id in entry_ids],
            )

    def add_status_changes(self, changes: Sequence[StoredStatusChange]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT INTO status_history (entry_id, before, after, source, at) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (c.entry_id, c.before, c.after, c.source, c.at.isoformat())
                    for c in changes
                ],
            )

    def add_line_change(self, change: StoredLineChange) -> None:
        self._db.execute(
            "INSERT INTO line_history (scheme, midpoint, source, at) VALUES (?, ?, ?, ?)",
            (change.scheme, change.midpoint, change.source, change.at.isoformat()),
        )

    def status_changes(self) -> Sequence[StoredStatusChange]:
        found: list[StoredStatusChange] = []
        for entry_id, before, after, source, at in self._db.execute(
            "SELECT entry_id, before, after, source, at FROM status_history ORDER BY id"
        ):
            try:
                found.append(
                    StoredStatusChange(
                        _text(entry_id),
                        _text(before),
                        _text(after),
                        _text(source),
                        _time(at),
                    )
                )
            except (ValueError, TypeError):
                continue  # left in the file, as at the start (207)
        return found

    def line_changes(self) -> Sequence[StoredLineChange]:
        found: list[StoredLineChange] = []
        for scheme, midpoint, source, at in self._db.execute(
            "SELECT scheme, midpoint, source, at FROM line_history ORDER BY id"
        ):
            try:
                found.append(
                    StoredLineChange(
                        None if scheme is None else _text(scheme),
                        None if midpoint is None else float(midpoint),
                        _text(source),
                        _time(at),
                    )
                )
            except (ValueError, TypeError):
                continue
        return found

    @_then_scrub
    def save_set_words(self, words: Sequence[StoredSetWord]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT OR REPLACE INTO set_words VALUES (?, ?, ?, ?)",
                [
                    (w.name, w.entry_id, ",".join(w.sources), w.added_at.isoformat())
                    for w in words
                ],
            )

    @_then_scrub
    def delete_set_words(self, name: str, entry_ids: Sequence[str]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "DELETE FROM set_words WHERE name = ? AND entry_id = ?",
                [(name, entry_id) for entry_id in entry_ids],
            )

    @_then_scrub
    def save_lookups(self, lookups: StoredLookups) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO lookups VALUES (?, ?, ?, ?, ?)",
            (
                lookups.entry_id,
                lookups.pinned,
                lookups.hovered,
                lookups.last_at.isoformat(),
                lookups.pinned_since_known,
            ),
        )

    @_then_scrub
    def delete_load_words(self, entry_ids: Sequence[str]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "DELETE FROM load_words WHERE entry_id = ?",
                [(entry_id,) for entry_id in entry_ids],
            )

    @_then_scrub
    def forget_entry(self, entry_id: str) -> None:
        deleted = 0
        with _Transaction(self._db):
            for table in (
                "statuses",
                "saved_words",
                "exposures",
                "deck_words",
                "anki_exports",
                "anki_csv_exports",
                "load_words",
                "lookups",
                "curriculum_words",
                "set_words",
            ):
                deleted += self._db.execute(
                    f"DELETE FROM {table} WHERE entry_id = ?", (entry_id,)
                ).rowcount
        if deleted:
            self._scrub()

    @_then_scrub
    def save_exposures(
        self, counts: Sequence[StoredExposures], daily: Mapping[date, Mapping[str, int]]
    ) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT OR REPLACE INTO exposures VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.entry_id,
                        c.heard,
                        c.heard_by_you,
                        c.heard_in_deck,
                        c.first_heard.isoformat() if c.first_heard else None,
                        c.days_heard,
                        c.last_heard.isoformat() if c.last_heard else None,
                    )
                    for c in counts
                ],
            )
            self._db.executemany(
                "INSERT INTO daily_exposures VALUES (?, ?, ?) "
                "ON CONFLICT (day, entry_id) DO UPDATE SET count = count + excluded.count",
                [
                    (day.isoformat(), entry_id, delta)
                    for day, changes in daily.items()
                    for entry_id, delta in changes.items()
                ],
            )

    @_then_scrub
    def mark_handed_over(self, days: Iterable[date]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT OR IGNORE INTO handed_over_days VALUES (?)",
                [(day.isoformat(),) for day in days],
            )

    @_then_scrub
    def forget_daily_exposures(self, days: Iterable[date]) -> None:
        kept = [(day.isoformat(),) for day in days]
        with _Transaction(self._db):
            for table in ("daily_exposures", "handed_over_days"):
                self._db.executemany(f"DELETE FROM {table} WHERE day = ?", kept)

    @_then_scrub
    def add_coverage(self, changes: Iterable[StoredCoverage]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT INTO daily_coverage VALUES (?, ?, ?, ?) "
                "ON CONFLICT (day) DO UPDATE SET known = known + excluded.known, "
                "deck = deck + excluded.deck, new = new + excluded.new",
                [(c.day.isoformat(), c.known, c.deck, c.new) for c in changes],
            )

    @_then_scrub
    def add_listening(self, listened: Iterable[StoredListening]) -> None:
        with _Transaction(self._db):
            self._db.executemany(
                "INSERT INTO daily_listening VALUES (?, ?, ?) "
                "ON CONFLICT (day, category) DO UPDATE "
                "SET seconds = seconds + excluded.seconds",
                [(e.day.isoformat(), e.category, e.seconds) for e in listened],
            )

    def delete_learning_data(self) -> None:
        with _Transaction(self._db):
            for table in (
                "statuses",
                "saved_words",
                "saved_sentences",
                "deck_words",
                "anki_exports",
                "anki_csv_exports",
                "exposures",
                "daily_exposures",
                "daily_coverage",
                "daily_listening",
                "handed_over_days",
                "load_words",
                "lookups",
                "curriculum_words",
                "status_history",
                "line_history",
                "set_words",
            ):
                self._db.execute(f"DELETE FROM {table}")
        self.delete_set_aside()
        # a deleted row's text stays in the file's free space, and in the
        # write-ahead log, until written over: the file is rewritten
        # without it and the log emptied, so none of it can be read back
        # (polyglotic-hq 207; about 6 ms for a 4 MB store)
        self._db.execute("VACUUM")
        self._scrub()

    # -- the files set aside from it (polyglotic-hq 206, 207) ---------------------------

    def set_aside_copies(self) -> list[Path]:
        """The files set aside from this store, beside it, oldest first - not
        their WAL files, nor a folder set aside; none for a store in memory.
        Only listed, never opened; works once the store is out too."""
        if not isinstance(self._path, Path):
            return []
        return [
            each
            for each in _set_aside_from(self._path)
            if each.is_file() and not each.name.endswith(_WAL_FILES)
        ]

    def delete_set_aside(self) -> int:
        """Deletes the files set aside from this store, with their WAL files
        - the learner deleted their learning data on this PC, and each holds
        a copy of it (polyglotic-hq 207). A folder set aside is kept: what's
        in it may not be the app's. Another language's store's files are
        its own. Returns how many were deleted; one that can't be (in use)
        is logged by its name and kept. Works once the store is out too."""
        if not isinstance(self._path, Path):
            return 0
        deleted = kept = 0
        for each in _set_aside_from(self._path):
            if not each.is_file():
                continue
            try:
                each.unlink()
            except OSError as error:
                kept += 1
                log.warning(
                    "a learning data file set aside couldn't be deleted (%s): %s",
                    type(error).__name__,
                    each.name,
                )
            else:
                deleted += not each.name.endswith(_WAL_FILES)
        if deleted or kept:
            log.info(
                "learning data deleted: %d file(s) set aside deleted, %d kept",
                deleted,
                kept,
            )
        return deleted


def is_damage(error: BaseException) -> bool:
    """SQLite saying the file is damaged, or isn't a database - not that
    it's busy, out of reach or out of room."""
    return (
        isinstance(error, sqlite3.DatabaseError)
        and getattr(error, "sqlite_errorname", None) in _DAMAGED
    )


def delete_learning_data_at(path: Path) -> bool:
    """Empties the learning store at `path` - one no app has open - and
    deletes the copies set aside from it, as `delete_learning_data` does
    for an open one; the level and the categories
    stay. False, logged, when it couldn't be: from a newer app
    (`LearningStoreFormatError`), in use, out of reach."""
    try:
        store = open_learning_store(path)
    except (
        LearningStoreFormatError,
        LearningStoreDamagedError,
        OSError,
        sqlite3.Error,
    ) as error:
        log.warning(
            "the learning data in %s couldn't be deleted: %s",
            path.name,
            type(error).__name__,
        )
        return False
    try:
        store.delete_learning_data()  # and the copies set aside
    except (OSError, sqlite3.Error) as error:
        log.warning(
            "the learning data in %s couldn't be deleted: %s",
            path.name,
            type(error).__name__,
        )
        return False
    finally:
        store.close()
    return True


def open_learning_store(path: Path) -> SqliteLearningStore:
    """The learning store at `path`, created if missing. One that can't be
    read (`LearningStoreDamagedError`) is renamed aside with its WAL files,
    `learning.sqlite.damaged-<this PC's time and offset>` - never deleted or written over -
    and a new one started; the store's `set_aside` says where it went and
    why. Of the files set aside, the newest `KEEP_SET_ASIDE` are kept.

    A file from a newer app (`LearningStoreFormatError`) is raised as it
    is: setting it aside would hide the learner's words from the app they
    go back to. So is one that's locked or out of reach (not the file's
    fault), and a damaged one that can't be renamed - it's never replaced."""
    try:
        return SqliteLearningStore(path)
    except LearningStoreDamagedError as damaged:
        problem = damaged.problem
        try:
            aside = _set_aside(path)
        except OSError as error:
            log.warning(
                "the learning data couldn't be read (%s), nor set aside (%s)",
                problem.value,
                type(error).__name__,
            )
            raise damaged from error
    log.warning(
        "the learning data couldn't be read (%s): set aside as %s, a new one started",
        problem.value,
        aside.name,
    )
    store = SqliteLearningStore(path)
    store.set_aside = SetAsideLearningData(aside, problem)
    _keep_newest(path)
    return store


def level_file(path: Path) -> Path:
    """Where the level is kept beside the store at `path`, as well as in
    it (decision 0048): `learning-level.json` beside `learning.sqlite`."""
    return path.with_name(f"{path.stem}-level.json")


def read_level_file(path: Path) -> StoredLevel | None:
    """The level kept beside the store at `path`; None when there's none,
    or it can't be read (said in the log by its kind only)."""
    file = level_file(path)
    try:
        data = json.loads(file.read_text("utf-8"))
        return StoredLevel(_text(data["scheme"]), float(_number(data["midpoint"])))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError) as error:
        log.warning("the level's copy couldn't be read (%s)", type(error).__name__)
        return None


def _write_level_file(path: Path, level: StoredLevel) -> None:
    """The level beside the store, whole or not at all: written to a
    temporary file, then put in place. A failure is said in the log by its
    kind; the store still has the level."""
    file = level_file(path)
    temporary = file.with_name(f"{file.name}.tmp")
    try:
        temporary.write_text(
            json.dumps({"scheme": level.scheme, "midpoint": level.midpoint}), "utf-8"
        )
        os.replace(temporary, file)
    except OSError as error:
        log.warning("the level's copy couldn't be written (%s)", type(error).__name__)
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)


_WAL_FILES = ("-wal", "-shm")


def _set_aside(path: Path) -> Path:
    """`path`, with its WAL files, renamed `<name>.damaged-<time>` - this
    PC's time with its offset, as the settings file's (Home's banner names
    it; a UTC time read as yesterday in Australia - polyglotic-hq 203) -
    `-2`, `-3`... after it if that's taken, so nothing is written over. The
    WAL files go first: one left beside a new store would be read into it.
    A rename that fails puts back what had moved, and raises."""
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    aside = path.with_name(f"{path.name}.damaged-{stamp}")
    count = 1
    while any(_with(aside, end).exists() for end in ("", *_WAL_FILES)):
        count += 1
        aside = path.with_name(f"{path.name}.damaged-{stamp}-{count}")
    moved: list[tuple[Path, Path]] = []
    try:
        for end in (*_WAL_FILES, ""):
            old = _with(path, end)
            if old.exists():
                old.rename(_with(aside, end))
                moved.append((old, _with(aside, end)))
    except OSError:
        for old, new in reversed(moved):
            with contextlib.suppress(OSError):
                new.rename(old)
        raise
    return aside


def _set_aside_from(path: Path) -> list[Path]:
    """Everything set aside from the store at `path` - files, their WAL
    files and folders - oldest first, by the time in each name
    (`_set_aside_when`)."""
    return sorted(
        path.parent.glob(f"{glob.escape(path.name)}.damaged-*"),
        key=lambda each: _set_aside_when(each.name),
    )


def _keep_newest(path: Path) -> None:
    """The files set aside from `path` beyond the newest `KEEP_SET_ASIDE`
    removed, with their WAL files. A folder set aside is never removed:
    what's in it may not be the app's."""
    found = [
        each
        for each in _set_aside_from(path)
        if each.is_file() and not each.name.endswith(_WAL_FILES)
    ]
    for old in found[:-KEEP_SET_ASIDE]:
        for end in ("", *_WAL_FILES):
            with contextlib.suppress(OSError):
                _with(old, end).unlink(missing_ok=True)
        log.info("an older learning data file set aside removed: %s", old.name)


def set_aside_in(folder: Path) -> list[str]:
    """The names of the learning data files set aside in `folder` (its
    learning stores' - every language's), oldest first; not their WAL
    files. Only listed, never opened."""
    return sorted(
        (
            each.name
            for each in folder.glob("learning*.sqlite.damaged-*")
            if not each.name.endswith(_WAL_FILES)
        ),
        key=_set_aside_when,
    )


def unreadable_in(folder: Path) -> dict[str, tuple[int, str | None]]:
    """Per learning store in `folder` (every language's), the rows the
    start leaves out because they can't be read, and the table that has too
    many if it would be refused (polyglotic-hq 207) - counts only, never
    what they hold. Opened read-only and as unchanging (SQLite's
    `immutable`): nothing is written, migrated or made beside it, not even
    WAL files. A store the app is writing meanwhile is counted as of its
    last checkpoint. One that can't be read this way (damaged, from a newer
    or an older app) is left out: the start deals with it."""
    found: dict[str, tuple[int, str | None]] = {}
    for path in sorted(folder.glob("learning*.sqlite")):
        if not path.is_file():
            continue
        try:
            db = sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)
        except sqlite3.Error:
            continue
        try:
            (version,) = db.execute("PRAGMA user_version").fetchone()
            if version != VERSION:
                continue
            _, tally = _read(db)
        except sqlite3.Error:
            continue
        finally:
            db.close()
        refused = next(
            (
                table
                for table, (unreadable, rows) in tally.items()
                if too_many_unreadable(unreadable, rows)
            ),
            None,
        )
        found[path.name] = (sum(n for n, _ in tally.values()), refused)
    return found


_STAMP = re.compile(r"\.damaged-(\d{8}T\d{6}(?:Z|[+-]\d{4}))(?:-(\d+))?$")


def _set_aside_when(name: str) -> tuple[datetime, int]:
    """When a file was set aside, from its name - the oldest are removed
    first. Names carry this PC's time and offset (UTC's before polyglotic-hq
    203), so as text they don't sort by time across the two, a clock change
    or a move between time zones. A name that doesn't say counts as oldest."""
    found = _STAMP.search(name)
    if found is None:
        return datetime.min.replace(tzinfo=UTC), 0
    at = datetime.strptime(found.group(1).replace("Z", "+0000"), "%Y%m%dT%H%M%S%z")
    return at, int(found.group(2) or 1)


def _with(path: Path, end: str) -> Path:
    return path.with_name(path.name + end)


def _newer(version: int) -> str:
    return f"learning data version {version}; this app reads up to {VERSION}"


def too_many_unreadable(unreadable: int, rows: int) -> bool:
    """More of a table's `rows` can't be read than a few garbled ones
    explain: over `UNREADABLE_AT_MOST`, and over `UNREADABLE_SHARE` of
    them. A whole table of 3 or more is too many; 1 or 2 rows never are."""
    return unreadable > max(UNREADABLE_AT_MOST, UNREADABLE_SHARE * rows)


_Tally = dict[str, tuple[int, int]]
"""Per table: the rows that couldn't be read, of how many."""
_Row = TypeVar("_Row")


def _read(db: sqlite3.Connection) -> tuple[LearningSnapshot, _Tally]:
    """Every row that can be read, and per table how many couldn't."""
    tally: _Tally = {}

    def rows(
        table: str, columns: str, parse: Callable[[tuple[object, ...]], _Row]
    ) -> list[_Row]:
        kept: list[_Row] = []
        unreadable = 0
        for row in db.execute(f"SELECT {columns} FROM {table}"):
            try:
                kept.append(parse(row))
            except (ValueError, TypeError):
                unreadable += 1
        tally[table] = (unreadable, unreadable + len(kept))
        return kept

    level = rows("level", "scheme, midpoint", _level)
    snapshot = LearningSnapshot(
        level=level[0] if level else None,
        statuses=rows("statuses", "entry_id, status, source, at", _status),
        categories=sorted(
            rows("categories", "id, name, color, position", _category),
            key=lambda category: category.position,
        ),
        saved_words=rows(
            "saved_words",
            "entry_id, headword, traditional, reading, meaning, category_id, "
            "source_sentence, source_translation, saved_at",
            _saved_word,
        ),
        exposures=_read_exposures(db, tally),
        deck_words=rows(
            "deck_words",
            "entry_id, headword, traditional, reading, meaning, sentence, "
            "translation, learned_at",
            _deck_word,
        ),
        anki_exports=[
            *rows("anki_exports", "entry_id, exported_at", _anki_export),
            *rows("anki_csv_exports", "entry_id, exported_at", _anki_csv_export),
        ],
        coverage=sorted(
            rows("daily_coverage", "day, known, deck, new", _coverage),
            key=lambda each: each.day,
        ),
        listening=sorted(
            rows("daily_listening", "day, category, seconds", _listening),
            key=lambda each: (each.day, each.category),
        ),
        load_words=rows(
            "load_words",
            "entry_id, standing, stage, meetings, by_hand, place, entered_at, "
            "last_met, graduated_at",
            _load_word,
        ),
        lookups=rows(
            "lookups",
            "entry_id, pinned, hovered, last_at, pinned_since_known",
            _lookups,
        ),
        curriculum_words=rows(
            "curriculum_words",
            "entry_id, standing, came, entered_at, days_met, last_day, sittings, "
            "retired_at",
            _curriculum_word,
        ),
        set_words=rows("set_words", "name, entry_id, sources, added_at", _set_word),
    )
    return snapshot, tally


def _left_out(tally: _Tally) -> str:
    """`statuses 2 of 300, saved_words 1 of 40` - counts only."""
    return ", ".join(
        f"{table} {unreadable} of {rows}"
        for table, (unreadable, rows) in tally.items()
        if unreadable
    )


# Each row's values, checked: one not of its column's type (SQLite keeps
# what it's given), or a time or status this app can't parse, raises
# ValueError or TypeError - and the row is left out (polyglotic-hq 207).


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("not text")
    return value


def _whole(value: object) -> int:
    if not isinstance(value, int):
        raise TypeError("not a whole number")
    return value


def _number(value: object) -> float:
    if not isinstance(value, int | float):
        raise TypeError("not a number")
    return value


def _time(value: object) -> datetime:
    return datetime.fromisoformat(_text(value))


def _level(row: tuple[object, ...]) -> StoredLevel:
    scheme, midpoint = row
    return StoredLevel(_text(scheme), _number(midpoint))


_STATUSES = frozenset(status.value for status in WordStatus)
_SOURCES = frozenset(source.value for source in StatusSource)


def _status(row: tuple[object, ...]) -> StoredStatus:
    # the commonest rows, so checked inline (polyglotic-hq 207: 40,000 of
    # them load in about 10 ms more than unchecked)
    entry_id, status, source, at = row
    if (
        type(entry_id) is not str
        or type(status) is not str
        or type(source) is not str
        or status not in _STATUSES
        or source not in _SOURCES
    ):
        raise ValueError("not a status this app knows")
    return StoredStatus(entry_id, status, source, _time(at))


def _category(row: tuple[object, ...]) -> StoredCategory:
    category_id, name, color, position = row
    return StoredCategory(
        _text(category_id), _text(name), _text(color), _whole(position)
    )


def _saved_word(row: tuple[object, ...]) -> StoredSavedWord:
    *text, saved_at = row
    (
        entry_id,
        headword,
        traditional,
        reading,
        meaning,
        category,
        sentence,
        translation,
    ) = (_text(value) for value in text)
    return StoredSavedWord(
        entry_id,
        headword,
        traditional,
        reading,
        meaning,
        category,
        sentence,
        translation,
        _time(saved_at),
    )


def _parts_json(parts: Sequence[StoredSentencePart]) -> str:
    """A saved sentence's parts as the text of its `parts` column: a list
    of `[original, translation, speaker, [[o start, o end, t start, t end,
    key], ...]]` (`_parts` reads it)."""
    return json.dumps(
        [
            [p.original, p.translation, p.speaker, [list(link) for link in p.links]]
            for p in parts
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _parts(value: object) -> tuple[StoredSentencePart, ...]:
    """`_parts_json`'s text read back - ValueError or TypeError for any
    value not of its shape (the row is left out, 207)."""
    parts = json.loads(_text(value))
    if not isinstance(parts, list):
        raise TypeError("not a list of parts")
    found = []
    for part in parts:
        original, translation, speaker, links = part
        found.append(
            StoredSentencePart(
                _text(original),
                _text(translation),
                tuple(_link(link) for link in links),
                _text(speaker),
            )
        )
    return tuple(found)


def _link(value: object) -> tuple[int, int, int, int, bool]:
    if not isinstance(value, list) or len(value) != 5:
        raise TypeError("not a link")
    o_start, o_end, t_start, t_end, key = value
    if not isinstance(key, bool):
        raise TypeError("not a link")
    return _whole(o_start), _whole(o_end), _whole(t_start), _whole(t_end), key


def _sentence(row: tuple[object, ...]) -> StoredSentence:
    sentence_id, original, translation, parts, language, category, saved_at = row
    return StoredSentence(
        _text(sentence_id),
        _text(original),
        _text(translation),
        _parts(parts),
        _text(language),
        _text(category),
        _time(saved_at),
    )


def _read_exposures(db: sqlite3.Connection, tally: _Tally) -> list[StoredExposures]:
    """The exposure counts that can be read, the rest counted in `tally`
    like every table's. The one table with a row for every word met -
    30,000 for a long-time learner, all read before the window shows - so
    its rows are checked here in the loop, with no call a row, and each
    day is parsed once. With the records as named tuples, the start's
    read of a learner of 30,000 words met went from about 137 ms to 115
    (polyglotic-hq 314)."""
    kept: list[StoredExposures] = []
    unreadable = 0
    # None for words heard before version 5 (polyglotic-hq 163)
    days: dict[object, date | None] = {None: None}
    for (
        entry_id,
        heard,
        heard_by_you,
        heard_in_deck,
        first_heard,
        days_heard,
        last_heard,
    ) in db.execute(
        "SELECT entry_id, heard, heard_by_you, heard_in_deck, first_heard,"
        " days_heard, last_heard FROM exposures"
    ):
        if (
            type(entry_id) is not str
            or type(heard) is not int
            or type(heard_by_you) is not int
            or type(heard_in_deck) is not int
            or type(days_heard) is not int
        ):
            unreadable += 1
            continue
        try:
            if first_heard in days:
                day = days[first_heard]
            else:
                day = days[first_heard] = _day(first_heard)
            if last_heard in days:
                last = days[last_heard]
            else:
                last = days[last_heard] = _day(last_heard)
        except (ValueError, TypeError):
            unreadable += 1
            continue
        kept.append(
            StoredExposures(
                entry_id, heard, heard_by_you, heard_in_deck, day, days_heard, last
            )
        )
    tally["exposures"] = (unreadable, unreadable + len(kept))
    return kept


def _load_word(row: tuple[object, ...]) -> StoredLoadWord:
    entry_id, standing, stage, meetings, by_hand, place, entered, met, graduated = row
    return StoredLoadWord(
        _text(entry_id),
        _text(standing),
        _whole(stage),
        _whole(meetings),
        bool(_whole(by_hand)),
        None if place is None else _whole(place),
        _time(entered),
        None if met is None else _time(met),
        None if graduated is None else _time(graduated),
    )


def _curriculum_word(row: tuple[object, ...]) -> StoredCurriculumWord:
    entry_id, standing, came, entered, days, last, sittings, retired = row
    return StoredCurriculumWord(
        _text(entry_id),
        _text(standing),
        _text(came),
        _time(entered),
        _whole(days),
        None if last is None else _day(last),
        _whole(sittings),
        None if retired is None else _time(retired),
    )


def _set_word(row: tuple[object, ...]) -> StoredSetWord:
    name, entry_id, sources, added = row
    found = _text(sources)
    return StoredSetWord(
        _text(name),
        _text(entry_id),
        tuple(found.split(",")) if found else (),
        _time(added),
    )


def _lookups(row: tuple[object, ...]) -> StoredLookups:
    entry_id, pinned, hovered, last, since = row
    return StoredLookups(
        _text(entry_id), _whole(pinned), _whole(hovered), _time(last), _whole(since)
    )


def _deck_word(row: tuple[object, ...]) -> StoredDeckWord:
    *text, at = row
    (
        entry_id,
        headword,
        traditional,
        reading,
        meaning,
        sentence,
        translation,
    ) = (_text(value) for value in text)
    return StoredDeckWord(
        entry_id,
        headword,
        traditional,
        reading,
        meaning,
        sentence,
        translation,
        _time(at),
    )


def _day(value: object) -> date:
    return date.fromisoformat(_text(value))


def _coverage(row: tuple[object, ...]) -> StoredCoverage:
    day, known, deck, new = row
    return StoredCoverage(_day(day), _whole(known), _whole(deck), _whole(new))


def _listening(row: tuple[object, ...]) -> StoredListening:
    day, category, seconds = row
    return StoredListening(_day(day), _text(category), _number(seconds))


def _anki_export(row: tuple[object, ...]) -> StoredAnkiExport:
    entry_id, at = row
    return StoredAnkiExport(_text(entry_id), _time(at), "deck")


def _anki_csv_export(row: tuple[object, ...]) -> StoredAnkiExport:
    entry_id, at = row
    return StoredAnkiExport(_text(entry_id), _time(at), "csv")
