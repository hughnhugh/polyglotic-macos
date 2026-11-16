"""What waits to be sent to the server, and the user's consent choices: one SQLite file.

`SqliteOutbox` implements two ports for the connection: `Outbox` (learning
events, consent, usage events and daily exposure counts kept until the
server has them - the offline buffer) and `ConsentStore` (the user's
choices, newest last). Every change is written at once, so closing the app
or a crash loses nothing waiting. Kept apart from the learner's own data
(decision 0010's file): this is the connection's, and holds nothing but
entry IDs, times, counts and the tracking plan's properties.

In the app it's used from one thread of its own, `BackgroundOutbox`
(adapters/background_outbox.py), so the interface never waits on its
disk; the harness and tests use it directly, from any thread - one
connection shared under a lock. Items dropped for room, or for a kind
forgotten, are logged by count and kind - never what they held.

`open_outbox` is how the app opens it: a file that can't be read is set
aside and a fresh one started, rather than the app failing to start
(polyglotic-hq project 042, Medium 4).

Tables (schema version in SQLite's `user_version`, as in
`sqlite_learning`):
- `waiting`: kind, id, body (JSON), in the order added.
- `notes`: key -> value (the learning sync cursor, ...); `dropped` counts
  items dropped for room.
- `consent`: every choice, with its id and time, and the tester agreement
  accepted with it (version and time; empty before version 2).
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from polyglotic_desktop.ports.consent import Agreement, ConsentChoice
from polyglotic_desktop.ports.outbox import Waiting

_MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (  # version 1
        """CREATE TABLE waiting (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            id TEXT NOT NULL UNIQUE,
            body TEXT NOT NULL
        )""",
        "CREATE INDEX waiting_kind ON waiting (kind, seq)",
        """CREATE TABLE notes (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID""",
        """CREATE TABLE consent (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            at TEXT NOT NULL,
            usage INTEGER NOT NULL,
            crashes INTEGER NOT NULL,
            exposures INTEGER NOT NULL
        )""",
    ),
    (  # version 2: the tester agreement accepted with each choice (185)
        "ALTER TABLE consent ADD COLUMN agreement TEXT",
        "ALTER TABLE consent ADD COLUMN agreement_at TEXT",
    ),
)
VERSION = len(_MIGRATIONS)
_DROPPED = "dropped"
_UNREADABLE = frozenset({"SQLITE_NOTADB", "SQLITE_CORRUPT"})
"""SQLite's answers for a file that isn't a database, or is damaged."""

log = logging.getLogger(__name__)


class OutboxFormatError(Exception):
    """The file can't be read as an outbox: it was written by a newer
    version of the app, or isn't SQLite, or is damaged."""


class SqliteOutbox:
    """The outbox at `path`, created if missing (":memory:" for one that's
    never written to disk)."""

    def __init__(self, path: Path | str) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        try:
            self._db.execute("PRAGMA journal_mode = WAL")
            self._migrate()
        except OutboxFormatError:
            self._db.close()
            raise
        except sqlite3.DatabaseError as e:
            self._db.close()
            if getattr(e, "sqlite_errorname", None) in _UNREADABLE:
                raise OutboxFormatError("not SQLite, or damaged") from e
            raise  # locked, out of reach, a disk error: not the file's fault

    def _migrate(self) -> None:
        (version,) = self._db.execute("PRAGMA user_version").fetchone()
        if version > VERSION:
            raise OutboxFormatError(
                f"outbox version {version}; this app reads up to {VERSION}"
            )
        for number in range(version, VERSION):
            self._db.execute("BEGIN")
            for statement in _MIGRATIONS[number]:
                self._db.execute(statement)
            self._db.execute(f"PRAGMA user_version = {number + 1}")
            self._db.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- Outbox ---------------------------------------------------------------------

    def add(self, item: Waiting, keep: int) -> None:
        with self._lock:
            db = self._db
            db.execute("BEGIN")
            try:
                db.execute(
                    "INSERT OR IGNORE INTO waiting (kind, id, body) VALUES (?, ?, ?)",
                    (item.kind, item.id, item.body),
                )
                (count,) = db.execute(
                    "SELECT COUNT(*) FROM waiting WHERE kind = ?", (item.kind,)
                ).fetchone()
                over = max(0, count - keep)
                if over:
                    db.execute(
                        "DELETE FROM waiting WHERE seq IN (SELECT seq FROM waiting "
                        "WHERE kind = ? ORDER BY seq LIMIT ?)",
                        (item.kind, over),
                    )
                    db.execute(
                        "INSERT INTO notes VALUES (?, ?) ON CONFLICT (key) "
                        "DO UPDATE SET value = CAST(value AS INTEGER) + ?",
                        (_DROPPED, str(over), over),
                    )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        if over:
            log.warning("the outbox is full: %d %s item(s) dropped", over, item.kind)

    def waiting(self) -> Sequence[Waiting]:
        with self._lock:
            return [
                Waiting(kind, item_id, body)
                for kind, item_id, body in self._db.execute(
                    "SELECT kind, id, body FROM waiting ORDER BY seq"
                )
            ]

    def remove(self, ids: Iterable[str]) -> None:
        with self._lock:
            self._db.executemany(
                "DELETE FROM waiting WHERE id = ?", [(i,) for i in ids]
            )

    def remove_kind(self, kind: str) -> None:
        with self._lock:
            count = self._db.execute(
                "DELETE FROM waiting WHERE kind = ?", (kind,)
            ).rowcount
        if count:
            log.info("%d waiting %s item(s) dropped", count, kind)

    def dropped(self) -> int:
        value = self.note(_DROPPED)
        return int(value) if value else 0

    def note(self, key: str) -> str | None:
        with self._lock:
            row = self._db.execute(
                "SELECT value FROM notes WHERE key = ?", (key,)
            ).fetchone()
        return str(row[0]) if row else None

    def save_note(self, key: str, value: str | None) -> None:
        with self._lock:
            if value is None:
                self._db.execute("DELETE FROM notes WHERE key = ?", (key,))
            else:
                self._db.execute(
                    "INSERT OR REPLACE INTO notes VALUES (?, ?)", (key, value)
                )

    # -- ConsentStore ---------------------------------------------------------------

    def consent(self) -> ConsentChoice | None:
        with self._lock:
            row = self._db.execute(
                "SELECT id, at, usage, crashes, exposures, agreement, agreement_at "
                "FROM consent ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        choice_id, at, usage, crashes, exposures, agreement, agreement_at = row
        return ConsentChoice(
            choice_id,
            datetime.fromisoformat(at),
            bool(usage),
            bool(crashes),
            bool(exposures),
            Agreement(agreement, datetime.fromisoformat(agreement_at))
            if agreement and agreement_at
            else None,
        )

    def save_consent(self, choice: ConsentChoice) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO consent (id, at, usage, crashes, exposures, "
                "agreement, agreement_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    choice.id,
                    choice.at.isoformat(),
                    choice.usage,
                    choice.crashes,
                    choice.exposures,
                    choice.agreement.version if choice.agreement else None,
                    choice.agreement.at.isoformat() if choice.agreement else None,
                ),
            )


def open_outbox(path: Path) -> SqliteOutbox:
    """The outbox at `path`, created if missing. One that can't be read (an
    `OutboxFormatError`: not SQLite, damaged, or written by a newer app -
    after moving to an older channel, say) is renamed aside with its WAL
    files, `outbox.unreadable-<time>.sqlite`, and a fresh one started: it's
    only a buffer of what waits for the server. What waited is lost; the
    consent choices are asked again (the first-run screen), and learning
    syncs from the start. A file that's locked or out of reach is raised as
    it is - setting it aside wouldn't help."""
    try:
        return SqliteOutbox(path)
    except OutboxFormatError as e:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        aside = path.with_name(f"{path.stem}.unreadable-{stamp}{path.suffix}")
        for suffix in ("", "-wal", "-shm"):
            old = path.with_name(path.name + suffix)
            if old.exists():
                old.replace(aside.with_name(aside.name + suffix))
        log.warning(
            "the outbox couldn't be read (%s): set aside as %s, a fresh one started",
            e,
            aside.name,
        )
        return SqliteOutbox(path)
