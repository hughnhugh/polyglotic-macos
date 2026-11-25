"""Meanings files: a dictionary's meanings in one more language (decisions
0133 and 0234; polyglotic-hq 326, 341 and 510).

A dictionary is built once, with the meanings its source has (ECDICT's in
Chinese and our English, Wiktionary's packs in English). Each other
language a learner may read gets a small file beside it, a rider,
`<dictionary>-<language>-<version>.meanings`, keyed by entry ID: the
meanings people wrote in that language (Wiktionary's translation tables,
another edition of Wiktionary). The dictionary's own file doesn't change,
so its format stays what older apps read; an app from before these files
never looks at them.

A row may say a machine made it. Only the language pairs approved in
`APPROVED_MACHINE_MEANINGS` are exposed, with an internal marker which core
turns into the learner-facing label required by DECISIONS #110. All other
machine-made rows remain absent.

Plain, unlocked SQLite, as the sources' share-alike licences require.
Tables:
- `info`: `kind` ("meanings"), `format`, the dictionary's name, its
  language, `meanings_language`, `version`, the sources and their
  licences, how many rows there are and how many a machine made.
- `meanings`: entry ID -> its meanings (one per line) and whether a
  machine made them.

`SqliteMeanings` reads one for core (the `MeaningsFile` port); it is safe
from several threads, each through its own connection, as
`SqliteDictionary` is. `MeaningsShelf` holds the ones open now, by
dictionary, for the dictionaries to read through (`view`) while a newer
one replaces an older. `write_meanings` writes one, for `tools/dictionaries`.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

FORMAT = "1"
KIND = "meanings"
SUFFIX = ".meanings"
MACHINE_MARKER = "\x1emachine-made\x1f"
APPROVED_MACHINE_MEANINGS = frozenset(
    {
        ("ja", "zh"),
        ("ja", "zh_TW"),
    }
)
"""Machine-made riders the user approved on 2026-11-24 (DECISIONS #171 Q2)."""

SCHEMA = """
CREATE TABLE info (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE meanings (
    id TEXT PRIMARY KEY,
    senses TEXT NOT NULL,
    machine INTEGER NOT NULL
) WITHOUT ROWID;
"""


class NotAMeaningsFile(Exception):
    """The file isn't a meanings file this app reads: damaged, another kind
    of file, or a newer format. Says which, never its contents."""


class SqliteMeanings:
    """One meanings file, opened read-only."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        self._uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        self._local = threading.local()
        self._opened: list[sqlite3.Connection] = []
        self._opening = threading.Lock()
        self._closed = False
        try:
            self.info: dict[str, str] = dict(
                self._db.execute("SELECT key, value FROM info")
            )
        except sqlite3.DatabaseError as e:
            self.close()
            raise NotAMeaningsFile(f"{path.name}: {type(e).__name__}") from None
        if self.info.get("kind") != KIND or self.info.get("format") != FORMAT:
            self.close()
            raise NotAMeaningsFile(
                f"{path.name}: {self.info.get('kind')!r} "
                f"format {self.info.get('format')!r}"
            )

    @property
    def _db(self) -> sqlite3.Connection:
        db: sqlite3.Connection | None = getattr(self._local, "db", None)
        if db is None:
            db = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
            with self._opening:
                if self._closed:
                    db.close()
                    raise sqlite3.ProgrammingError(
                        "Cannot operate on a closed database."
                    )
                self._opened.append(db)
            self._local.db = db
        return db

    def close(self) -> None:
        with self._opening:
            self._closed = True
            opened, self._opened = self._opened, []
        for db in opened:
            db.close()

    def meanings(self, entry_id: str) -> tuple[str, ...] | None:
        """The entry's meanings - None if the file has none for it, only a
        machine's (see the module), or can no longer be read (closed,
        gone): the dictionary's own are shown."""
        try:
            row = self._db.execute(
                "SELECT senses, machine FROM meanings WHERE id = ?",
                (entry_id,),
            ).fetchone()
        except sqlite3.Error:
            return None
        if row is None or not row[0]:
            return None
        machine = bool(row[1])
        pair = (self.info.get("language"), self.info.get("meanings_language"))
        if machine and pair not in APPROVED_MACHINE_MEANINGS:
            return None
        marker = MACHINE_MARKER if machine else ""
        return tuple(marker + sense for sense in row[0].split("\n"))


class ConvertedMeanings:
    """A rider converted to the learner's Chinese script on read.

    This is used only when the requested Japanese rider is absent and its
    approved other-script rider is present.  The marker is metadata and is
    deliberately kept outside conversion.
    """

    def __init__(self, source: SqliteMeanings, convert: Callable[[str], str]) -> None:
        self.source = source
        self.info = source.info
        self._convert = convert

    def meanings(self, entry_id: str) -> tuple[str, ...] | None:
        found = self.source.meanings(entry_id)
        if found is None:
            return None
        return tuple(
            MACHINE_MARKER + self._convert(value.removeprefix(MACHINE_MARKER))
            if value.startswith(MACHINE_MARKER)
            else self._convert(value)
            for value in found
        )

    def close(self) -> None:
        self.source.close()


def meanings_beside(
    folders: Sequence[Path], dictionary: str, language: str
) -> SqliteMeanings | None:
    """`dictionary`'s meanings file in `language` from `folders` (the packs'
    folder, then the installer's): the newest by its `version` that opens
    and says it is that dictionary's in that language. None: there is none
    this app reads - the dictionary's own meanings are shown."""
    best: tuple[tuple[int, ...], SqliteMeanings] | None = None
    for folder in folders:
        found = sorted(folder.glob(f"{dictionary}-{language}*{SUFFIX}"))
        for path in found if folder.is_dir() else ():
            try:
                file = SqliteMeanings(path)
            except (NotAMeaningsFile, OSError):
                continue
            info = file.info
            try:
                version = tuple(int(n) for n in info.get("version", "0").split("."))
            except ValueError:
                version = (0,)
            wrong = (info.get("dictionary"), info.get("meanings_language")) != (
                dictionary,
                language,
            )
            if wrong or (best is not None and best[0] >= version):
                file.close()
                continue
            if best is not None:
                best[1].close()
            best = (version, file)
    return best[1] if best is not None else None


class MeaningsShelf:
    """The meanings files open now, one per dictionary at most: set from
    the interface thread (`put`), read from any through a dictionary's
    `view` - which reads whichever file is on the shelf at the time, so a
    newer file arriving reaches every dictionary at once."""

    def __init__(self) -> None:
        self._held: dict[str, SqliteMeanings] = {}

    def put(
        self, dictionary: str, file: SqliteMeanings | None
    ) -> SqliteMeanings | None:
        """`dictionary`'s meanings from now on (None: its own); the file it
        replaces, for the caller to close once lookups under way are done."""
        old = self._held.pop(dictionary, None)
        if file is not None:
            self._held[dictionary] = file
        return old

    def held(self, dictionary: str) -> SqliteMeanings | None:
        return self._held.get(dictionary)

    def view(self, dictionary: str) -> ShelfView:
        """What `dictionary` reads its other meanings through."""
        return ShelfView(self, dictionary)

    def close(self) -> None:
        held, self._held = self._held, {}
        for file in held.values():
            file.close()


class ShelfView:
    """One dictionary's meanings, whichever file the shelf has for it now
    (the `MeaningsFile` port)."""

    def __init__(self, shelf: MeaningsShelf, dictionary: str) -> None:
        self._shelf = shelf
        self._dictionary = dictionary

    def meanings(self, entry_id: str) -> tuple[str, ...] | None:
        file = self._shelf.held(self._dictionary)
        return file.meanings(entry_id) if file is not None else None


def write_meanings(
    path: Path,
    info: Mapping[str, str],
    rows: Iterable[tuple[str, Sequence[str], bool]],
) -> None:
    """Writes a new meanings file at `path` (replacing any): each entry ID
    with its meanings and whether a machine made them, in ID order so a
    build is the same byte for byte. Entries without meanings are left out."""
    kept = sorted(
        (entry_id, tuple(senses), machine)
        for entry_id, senses, machine in rows
        if senses
    )
    for entry_id, senses, _ in kept:
        if any("\n" in sense or not sense for sense in senses):
            raise ValueError(f"{entry_id}: an empty meaning or one with a line break")
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA)
        made = sum(1 for _, _, machine in kept if machine)
        facts = {
            **info,
            "kind": KIND,
            "format": FORMAT,
            "entries": str(len(kept)),
            "machine_made": str(made),
        }
        db.executemany("INSERT INTO info VALUES (?, ?)", sorted(facts.items()))
        db.executemany(
            "INSERT INTO meanings VALUES (?, ?, ?)",
            (
                (entry_id, "\n".join(senses), int(machine))
                for entry_id, senses, machine in kept
            ),
        )
        db.commit()
        db.execute("VACUUM")
    finally:
        db.close()
