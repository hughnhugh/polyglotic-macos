"""The dictionary files: one SQLite file per dictionary (why: decision 0009).

`SqliteDictionary` reads one for core (the `DictionaryFile` port), and
`GuardedDictionary` reads the learner's without ever stopping the app
(polyglotic-hq 199); `write_dictionary` writes one, for
`tools/dictionaries`. They live here so the format has one owner. The files are plain, unlocked SQLite, as the
sources' share-alike licences require: anyone can open them.

Tables:
- `info`: the dictionary's name, format version, sources and their versions,
  and what its frequency ranks mean (`RANKS`).
- `entries`: one row per entry - entry ID, headword, traditional form,
  reading as the source gives it, meanings (one per line), frequency rank,
  levels (`scheme:level` pairs, space-separated).
- `forms`: written form -> entries, in order (everyday reading first).
- `meaning_words`: English word -> the entries whose meanings use it, as
  entry numbers packed 4 bytes each (little-endian), commonest first
  (reverse lookup; Chinese only). Packed, CC-CEDICT's 727,000 pairs take
  about 3MB; one row per pair took 8MB more.
- `lemmas`: inflected form -> its headword (English only).
- `merged`: old entry ID -> the entry ID it was merged into (decision 0007).
- `form_readings`: written form -> how that form itself is said, where the
  dictionary marks it apart from its entries' headwords (Russian's stress:
  "руку" is "ру́ку"). Added in format 1 (polyglotic-hq 298): an older app
  ignores it, and a file without it has no form readings.
- `sense_classes`: reviewed class masks by entry number and gloss ordinal.
  Optional and versioned separately within format 1.
- `sense_prefixes`: lengths of redundant labels in the legacy gloss text,
  for display alongside the optional typed classes.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import threading
from array import array
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from polyglotic_desktop.ports.dictionary import DictionaryProblem, EntryRecord
from polyglotic_desktop.ports.word_classes import SenseClasses, WordClass

log = logging.getLogger(__name__)

FORMAT = "1"

RANKS = "1"
"""What a file's frequency ranks mean, as its `info` says it under "ranks"
(decision 0120): each entry's `frequency_rank` is its word's place, 1 the
commonest, by the lists `info` names under "frequency_source" - a
headword's entries share one rank, so a rank is a word; an inflected form
counts for its lemma's entry; None where the lists never met the word (a
name, a rare word). "ranked_entries" says how many entries have one. A file
without "ranks" (built before polyglotic-hq 325) has ranks if any entry has
one, and a basic pack's then counted entries, not words."""

SCHEMA = """
CREATE TABLE info (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE entries (
    n INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    headword TEXT NOT NULL,
    traditional TEXT NOT NULL,
    reading TEXT NOT NULL,
    meanings TEXT NOT NULL,
    frequency_rank INTEGER,
    levels TEXT NOT NULL
);
CREATE TABLE forms (
    form TEXT NOT NULL, position INTEGER NOT NULL, n INTEGER NOT NULL,
    PRIMARY KEY (form, position)
) WITHOUT ROWID;
CREATE TABLE meaning_words (word TEXT PRIMARY KEY, entries BLOB NOT NULL) WITHOUT ROWID;
CREATE TABLE lemmas (form TEXT PRIMARY KEY, lemma TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE merged (old_id TEXT PRIMARY KEY, id TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE form_readings (form TEXT PRIMARY KEY, reading TEXT NOT NULL) WITHOUT ROWID;
"""

SENSE_CLASSES_VERSION = "1"
_CLASS_BITS = {cls: 1 << index for index, cls in enumerate(WordClass)}
_ALL_CLASSES = sum(_CLASS_BITS.values())
_SENSE_CLASSES_SCHEMA = f"""
CREATE TABLE sense_classes (
    n INTEGER NOT NULL REFERENCES entries(n),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    classes INTEGER NOT NULL CHECK (classes BETWEEN 0 AND {_ALL_CLASSES}),
    PRIMARY KEY (n, ordinal)
) WITHOUT ROWID
"""
_SENSE_PREFIXES_SCHEMA = """
CREATE TABLE sense_prefixes (
    n INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    length INTEGER NOT NULL CHECK (length > 0),
    PRIMARY KEY (n, ordinal),
    FOREIGN KEY (n, ordinal) REFERENCES sense_classes(n, ordinal)
) WITHOUT ROWID
"""
_QUERY_CHUNK = 500  # parameters per query, within SQLite's variable limit

_OWN_FIRST = (
    "entries e JOIN forms f ON f.form = e.headword AND f.n = e.n AND f.position = 0"
)
"""The entries that are the first for their own headword: the one a
caption counts the word for (`records(headword)[0]`)."""

_COLUMNS = (
    "e.id, e.headword, e.traditional, e.reading, e.meanings, e.frequency_rank, e.levels"
)


def _pack(numbers: list[int]) -> bytes:
    packed = array("I", numbers)  # 4 bytes on every platform we build for
    if sys.byteorder == "big":
        packed.byteswap()
    return packed.tobytes()


def _unpack(data: bytes) -> list[int]:
    packed = array("I")
    packed.frombytes(data)
    if sys.byteorder == "big":
        packed.byteswap()
    return packed.tolist()


class DictionaryFormatError(Exception):
    """The file isn't a dictionary file this app version can read."""


class DictionaryDamaged(DictionaryFormatError):
    """The file isn't readable as SQLite: cut off, overwritten, or not a
    dictionary file at all."""


def _record(row: tuple[str, str, str, str, str, int | None, str]) -> EntryRecord:
    entry_id, headword, traditional, reading, meanings, rank, levels = row
    pairs = []
    for pair in levels.split():
        scheme, _, level = pair.rpartition(":")
        pairs.append((scheme, int(level)))
    return EntryRecord(
        entry_id=entry_id,
        headword=headword,
        traditional=traditional,
        reading=reading,
        meanings=tuple(meanings.split("\n")) if meanings else (),
        frequency_rank=rank,
        levels=tuple(pairs),
    )


class SqliteDictionary:
    """One dictionary file, opened read-only. Safe to open on a background
    thread and use from several at once: each thread reads through a
    connection of its own (`_db`) - two threads sharing one got each
    other's rows, rows of None and "bad parameter or other API misuse"
    (polyglotic-hq 220: 8,578 wrong answers in 40,000 reads, as the read
    ahead and the interface thread read at the start)."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        self._uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        self._local = threading.local()
        self._opened: list[sqlite3.Connection] = []
        self._opening = threading.Lock()
        self._closed = False
        try:
            self.info = dict(self._db.execute("SELECT key, value FROM info"))
        except sqlite3.DatabaseError as e:
            self.close()
            raise DictionaryDamaged(f"{path.name}: {e}") from e
        if self.info.get("format") != FORMAT:
            self.close()
            raise DictionaryFormatError(
                f"{path.name}: format {self.info.get('format')!r}, expected {FORMAT!r}"
            )
        self._form_readings = bool(
            self._db.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'form_readings'"
            ).fetchone()
        )  # a file written before 298 hasn't the table
        self._sense_classes = False
        self._sense_prefixes = False
        if self.info.get("sense_classes_version") == SENSE_CLASSES_VERSION:
            try:
                found = self._db.execute(
                    "SELECT n, ordinal, classes FROM sense_classes LIMIT 1"
                ).fetchone()
            except sqlite3.DatabaseError:
                pass  # the optional extension cannot invalidate the base dictionary
            else:
                self._sense_classes = found is not None
                try:
                    self._db.execute(
                        "SELECT n, ordinal, length FROM sense_prefixes LIMIT 0"
                    )
                except sqlite3.DatabaseError:
                    pass
                else:
                    self._sense_prefixes = True

    @property
    def has_sense_classes(self) -> bool:
        return self._sense_classes

    @property
    def _db(self) -> sqlite3.Connection:
        """This thread's connection to the file, opened when it first reads.
        Each is only ever used by its own thread; `close` closes them all."""
        db: sqlite3.Connection | None = getattr(self._local, "db", None)
        if db is None:
            # check_same_thread off only so that `close` can close it from
            # whichever thread closes the file
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

    def headwords(self) -> Iterable[str]:
        return [
            form
            for (form,) in self._db.execute("SELECT form FROM forms WHERE position = 0")
        ]

    def frequency_ranks(self) -> Mapping[str, int]:
        return dict(
            self._db.execute(
                "SELECT f.form, MIN(e.frequency_rank) FROM forms f "
                "JOIN entries e ON e.n = f.n WHERE e.frequency_rank IS NOT NULL "
                "GROUP BY f.form"
            )
        )

    def records(self, word: str) -> Sequence[EntryRecord]:
        rows = self._db.execute(
            f"SELECT e.n, {_COLUMNS} FROM forms f JOIN entries e ON e.n = f.n "
            "WHERE f.form = ? ORDER BY f.position",
            (word,),
        ).fetchall()
        found = self._records(rows)
        return [found[row[0]] for row in rows]

    def _records(self, rows: Iterable[tuple]) -> dict[int, EntryRecord]:
        found = {n: _record(tuple(rest)) for n, *rest in rows}
        if not self._sense_classes:
            return found
        classes: dict[int, list[SenseClasses]] = {}
        prefixes: dict[int, list[int]] = {}
        columns = "s.n, s.ordinal, s.classes"
        table = "sense_classes AS s"
        if self._sense_prefixes:
            columns += ", p.length"
            table += " LEFT JOIN sense_prefixes AS p USING (n, ordinal)"
        else:
            columns += ", NULL"
        numbers = list(found)
        for start in range(0, len(numbers), _QUERY_CHUNK):
            chunk = numbers[start : start + _QUERY_CHUNK]
            marks = ", ".join("?" * len(chunk))
            for n, ordinal, mask, prefix in self._db.execute(
                f"SELECT {columns} FROM {table} WHERE s.n IN ({marks})",
                chunk,
            ):
                count = len(found[n].meanings)
                if (
                    isinstance(ordinal, int)
                    and 0 <= ordinal < count
                    and isinstance(mask, int)
                    and 0 <= mask <= _ALL_CLASSES
                ):
                    if n not in classes:
                        classes[n] = [None] * count
                    classes[n][ordinal] = tuple(
                        cls for cls, bit in _CLASS_BITS.items() if mask & bit
                    )
                    if isinstance(prefix, int) and 0 < prefix < len(
                        found[n].meanings[ordinal]
                    ):
                        if n not in prefixes:
                            prefixes[n] = [0] * count
                        prefixes[n][ordinal] = prefix
        for n, labels in classes.items():
            found[n] = replace(
                found[n],
                sense_classes=tuple(labels),
                sense_prefixes=tuple(prefixes.get(n, ())),
            )
        return found

    def records_by_meaning(
        self, english_word: str, limit: int
    ) -> Sequence[EntryRecord]:
        row = self._db.execute(
            "SELECT entries FROM meaning_words WHERE word = ?", (english_word,)
        ).fetchone()
        if row is None:
            return []
        numbers = _unpack(row[0])[:limit]
        found: dict[int, EntryRecord] = {}
        for start in range(0, len(numbers), _QUERY_CHUNK):
            chunk = numbers[start : start + _QUERY_CHUNK]
            marks = ", ".join("?" * len(chunk))
            query = f"SELECT e.n, {_COLUMNS} FROM entries e WHERE e.n IN ({marks})"
            found.update(self._records(self._db.execute(query, chunk)))
        return [found[n] for n in numbers if n in found]

    def lemma(self, word: str) -> str | None:
        row = self._db.execute(
            "SELECT lemma FROM lemmas WHERE form = ?", (word,)
        ).fetchone()
        return row[0] if row else None

    def form_reading(self, word: str) -> str:
        if not self._form_readings:
            return ""
        row = self._db.execute(
            "SELECT reading FROM form_readings WHERE form = ?", (word,)
        ).fetchone()
        return str(row[0]) if row else ""

    def record(self, entry_id: str) -> EntryRecord | None:
        query = f"SELECT e.n, {_COLUMNS} FROM entries e WHERE e.id = ?"
        row = self._db.execute(query, (entry_id,)).fetchone()
        if row is None:
            merged = self._db.execute(
                "SELECT id FROM merged WHERE old_id = ?", (entry_id,)
            ).fetchone()
            if merged:
                row = self._db.execute(query, (merged[0],)).fetchone()
        return self._records([row])[row[0]] if row else None

    def merged_ids(self) -> Sequence[str]:
        return [old for (old,) in self._db.execute("SELECT old_id FROM merged")]

    def words_ranked(self, last: int) -> Sequence[int]:
        return [
            rank
            for (rank,) in self._db.execute(
                "SELECT DISTINCT frequency_rank FROM entries "
                "WHERE frequency_rank <= ? ORDER BY frequency_rank",
                (last,),
            )
        ]

    def headwords_ranked(self, after: int, limit: int) -> Sequence[tuple[str, int]]:
        return list(
            self._db.execute(
                f"SELECT e.headword, e.frequency_rank FROM {_OWN_FIRST} "
                "WHERE e.frequency_rank > ? ORDER BY e.frequency_rank, e.n LIMIT ?",
                (after, limit),
            )
        )

    def headwords_at_levels(self, scheme: str) -> Sequence[tuple[str, int, int | None]]:
        prefix = f"{scheme}:"
        found = []
        for headword, levels, rank in self._db.execute(
            f"SELECT e.headword, e.levels, e.frequency_rank FROM {_OWN_FIRST} "
            "WHERE instr(e.levels, ?) > 0",
            (prefix,),
        ):
            for pair in levels.split():
                if pair.startswith(prefix):
                    found.append((headword, int(pair.removeprefix(prefix)), rank))
        return found

    def words_at_levels(self, scheme: str) -> Mapping[int, int]:
        prefix = f"{scheme}:"
        headwords: dict[int, set[str]] = {}
        for headword, levels in self._db.execute(
            "SELECT headword, levels FROM entries WHERE instr(levels, ?) > 0",
            (prefix,),
        ):
            for pair in levels.split():
                if pair.startswith(prefix):
                    level = int(pair.removeprefix(prefix))
                    headwords.setdefault(level, set()).add(headword)
        return {level: len(found) for level, found in sorted(headwords.items())}


class GuardedDictionary:
    """The learner's dictionary file, which never stops the app (a
    `DictionaryFile`; polyglotic-hq 199). A file that can't be opened -
    missing, cut off, the wrong format, unreadable - leaves the dictionary
    *out*: every query answers nothing (no entries, no forms), so captions
    run without word marks or counting, and lookups say why (`problem`).

    A file that opens but fails a query later - a page in the middle that
    can't be read - goes out then, for the rest of the session: a damaged
    file's other answers can't be trusted either (a word split on half its
    words would count the wrong words), and every later query would fail
    the same way. `on_problem` hears of it once, on the thread whose query
    failed. The reason is logged once, content-free: the file's name, the
    problem and the error's type - never per lookup."""

    def __init__(self, path: Path) -> None:
        self.name = path.name
        self.problem: DictionaryProblem | None = None
        self.on_problem: Callable[[DictionaryProblem], None] | None = None
        """Told once when the dictionary goes out after it opened (`main`:
        the learning tools' `dictionary_out`). From any thread."""
        self._file: SqliteDictionary | None = None
        self._going_out = threading.Lock()
        try:
            self._file = SqliteDictionary(path)
        except FileNotFoundError as e:
            self._out(DictionaryProblem.MISSING, e)
        except DictionaryDamaged as e:
            self._out(DictionaryProblem.DAMAGED, e)
        except DictionaryFormatError as e:
            self._out(DictionaryProblem.WRONG_FORMAT, e)
        except (OSError, sqlite3.Error) as e:  # sqlite3: "unable to open"
            self._out(DictionaryProblem.UNREADABLE, e)

    def _out(self, problem: DictionaryProblem, error: Exception) -> None:
        with self._going_out:  # two threads' failing queries: told once
            if self.problem is not None:
                return
            self.problem = problem
        log.warning(
            "Dictionary %s left out: %s (%s)",
            self.name,
            problem.value,
            type(error).__name__,
        )
        if self.on_problem is not None:
            self.on_problem(problem)

    def _ask[T](self, query: Callable[[SqliteDictionary], T], nothing: T) -> T:
        """`query`'s answer from the file - `nothing` while it's out, or if
        the file fails it (then it's out)."""
        if self._file is None or self.problem is not None:
            return nothing
        try:
            return query(self._file)
        except (sqlite3.Error, ValueError) as e:  # ValueError: a garbled row
            self._out(DictionaryProblem.DAMAGED, e)
            return nothing

    def close(self) -> None:
        if self._file is not None:
            self._file.close()

    @property
    def has_sense_classes(self) -> bool:
        return self._ask(lambda file: file.has_sense_classes, False)

    def headwords(self) -> Iterable[str]:
        return self._ask(lambda file: file.headwords(), [])

    def frequency_ranks(self) -> Mapping[str, int]:
        return self._ask(lambda file: file.frequency_ranks(), {})

    def records(self, word: str) -> Sequence[EntryRecord]:
        return self._ask(lambda file: file.records(word), [])

    def records_by_meaning(
        self, english_word: str, limit: int
    ) -> Sequence[EntryRecord]:
        return self._ask(lambda file: file.records_by_meaning(english_word, limit), [])

    def lemma(self, word: str) -> str | None:
        return self._ask(lambda file: file.lemma(word), None)

    def form_reading(self, word: str) -> str:
        return self._ask(lambda file: file.form_reading(word), "")

    def record(self, entry_id: str) -> EntryRecord | None:
        return self._ask(lambda file: file.record(entry_id), None)

    def merged_ids(self) -> Sequence[str]:
        return self._ask(lambda file: file.merged_ids(), [])

    def words_ranked(self, last: int) -> Sequence[int]:
        return self._ask(lambda file: file.words_ranked(last), [])

    def headwords_ranked(self, after: int, limit: int) -> Sequence[tuple[str, int]]:
        return self._ask(lambda file: file.headwords_ranked(after, limit), [])

    def headwords_at_levels(self, scheme: str) -> Sequence[tuple[str, int, int | None]]:
        return self._ask(lambda file: file.headwords_at_levels(scheme), [])

    def words_at_levels(self, scheme: str) -> Mapping[int, int]:
        return self._ask(lambda file: file.words_at_levels(scheme), {})


def write_dictionary(
    path: Path,
    info: Mapping[str, str],
    records: Sequence[EntryRecord],
    forms: Mapping[str, Sequence[str]],
    meaning_words: Mapping[str, Iterable[str]] | None = None,
    lemmas: Mapping[str, str] | None = None,
    merged: Mapping[str, str] | None = None,
    form_readings: Mapping[str, str] | None = None,
    *,
    with_sense_classes: bool = False,
) -> None:
    """Writes a new dictionary file at `path` (replacing any). `forms` maps
    each written form to entry IDs in order; `meaning_words` maps English
    words to entry IDs (stored commonest first); `merged` maps old entry IDs
    to current ones; `form_readings` maps written forms to how each is
    said."""
    with_prefixes = False
    for record in records:
        if any("\n" in m for m in record.meanings):
            raise ValueError(f"{record.entry_id}: a meaning with a line break")
        if record.sense_classes:
            with_sense_classes = True
            if len(record.sense_classes) != len(record.meanings):
                raise ValueError(
                    f"{record.entry_id}: classes must follow the stored glosses"
                )
            if any(
                cls not in _CLASS_BITS
                for labels in record.sense_classes
                for cls in labels or ()
            ):
                raise ValueError(f"{record.entry_id}: invalid sense class")
        if record.sense_prefixes:
            with_prefixes = True
            if (
                len(record.sense_prefixes) != len(record.meanings)
                or not record.sense_classes
                or any(
                    prefix and (labels is None or not 0 < prefix < len(gloss))
                    for prefix, gloss, labels in zip(
                        record.sense_prefixes,
                        record.meanings,
                        record.sense_classes,
                        strict=True,
                    )
                )
            ):
                raise ValueError(f"{record.entry_id}: invalid legacy sense prefix")
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA)
        db.execute("BEGIN")
        info = {
            key: value for key, value in info.items() if key != "sense_classes_version"
        }
        if with_sense_classes:
            db.execute(_SENSE_CLASSES_SCHEMA)
            info = {**info, "sense_classes_version": SENSE_CLASSES_VERSION}
        if with_prefixes:
            db.execute(_SENSE_PREFIXES_SCHEMA)
        db.executemany(
            "INSERT INTO info VALUES (?, ?)", sorted({**info, "format": FORMAT}.items())
        )
        number = {r.entry_id: n for n, r in enumerate(records, start=1)}
        db.executemany(
            "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (
                    number[r.entry_id],
                    r.entry_id,
                    r.headword,
                    r.traditional,
                    r.reading,
                    "\n".join(r.meanings),
                    r.frequency_rank,
                    " ".join(f"{scheme}:{level}" for scheme, level in r.levels),
                )
                for r in records
            ),
        )
        db.executemany(
            "INSERT INTO forms VALUES (?, ?, ?)",
            (
                (form, position, number[entry_id])
                for form, ids in forms.items()
                for position, entry_id in enumerate(ids)
            ),
        )
        if with_sense_classes:
            db.executemany(
                "INSERT INTO sense_classes VALUES (?, ?, ?)",
                (
                    (
                        number[r.entry_id],
                        ordinal,
                        sum(_CLASS_BITS[cls] for cls in set(labels)),
                    )
                    for r in records
                    for ordinal, labels in enumerate(r.sense_classes)
                    if labels is not None
                ),
            )
        if with_prefixes:
            db.executemany(
                "INSERT INTO sense_prefixes VALUES (?, ?, ?)",
                (
                    (number[r.entry_id], ordinal, prefix)
                    for r in records
                    for ordinal, prefix in enumerate(r.sense_prefixes)
                    if prefix
                ),
            )
        rank = {r.entry_id: r.frequency_rank for r in records}

        def commonest_first(entry_id: str) -> tuple[bool, int, int]:
            return (rank[entry_id] is None, rank[entry_id] or 0, number[entry_id])

        db.executemany(
            "INSERT INTO meaning_words VALUES (?, ?)",
            (
                (
                    word,
                    _pack([number[i] for i in sorted(set(ids), key=commonest_first)]),
                )
                for word, ids in sorted((meaning_words or {}).items())
            ),
        )
        db.executemany(
            "INSERT INTO lemmas VALUES (?, ?)", sorted((lemmas or {}).items())
        )
        db.executemany(
            "INSERT INTO merged VALUES (?, ?)", sorted((merged or {}).items())
        )
        db.executemany(
            "INSERT INTO form_readings VALUES (?, ?)",
            sorted((form_readings or {}).items()),
        )
        db.commit()
        db.execute("VACUUM")
    finally:
        db.close()


def add_info(path: Path, values: Mapping[str, str]) -> None:
    """Adds facts measured on a written file to its `info` (the build's
    coverage probe), replacing any of the same name."""
    db = sqlite3.connect(path)
    try:
        db.executemany(
            "INSERT OR REPLACE INTO info VALUES (?, ?)", sorted(values.items())
        )
        db.commit()
    finally:
        db.close()
