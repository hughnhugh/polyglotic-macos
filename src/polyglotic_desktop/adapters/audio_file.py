"""Audio files: a language's words recorded ahead of time, so a word can
be said on a PC with no voice for its language (decision 0133;
polyglotic-hq 341).

Windows says a word only in the voices a PC has, and most PCs have their
own language's alone. So the commonest words of a pack are spoken once, by
an open speech model we run ourselves (`tools.dictionaries.audio`), and
shipped beside the pack as `<dictionary>-<version>.audio`: the word looked
up never leaves the PC, and nothing runs on the server while a learner
listens. A word the file hasn't got is said by a Windows voice if the PC
has one (`platform.recorded_voices`).

Plain, unlocked SQLite. Tables:
- `info`: `kind` ("audio"), `format`, the dictionary's name, its language
  and the voice's BCP 47 tag, `version`, the model and voice that spoke and
  their licences, `codec` ("ogg-opus"), how many words.
- `head`: one row - the start every clip shares (an Ogg Opus stream's two
  header pages, about 870 bytes: a third of a short word's file, kept once).
- `clips`: written word -> the rest of its Ogg Opus stream. `head` and a
  clip joined are a whole `.opus` file.

`SqliteAudio` reads one - from any thread, one at a time; `write_audio`
writes one, for `tools/dictionaries`.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

FORMAT = "1"
KIND = "audio"
SUFFIX = ".audio"
CODEC = "ogg-opus"
PAGE_SIZE = 65536
"""SQLite's largest page, so clips of a few kB share pages (`write_audio`)."""

SCHEMA = """
CREATE TABLE info (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE head (data BLOB NOT NULL);
CREATE TABLE clips (word TEXT PRIMARY KEY, sound BLOB NOT NULL);
"""


class NotAnAudioFile(Exception):
    """The file isn't an audio file this app reads: damaged, another kind
    of file, a newer format or another codec. Says which, never its
    contents."""


class SqliteAudio:
    """One audio file, opened read-only."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = sqlite3.connect(
            uri, uri=True, check_same_thread=False
        )
        try:
            self.info: dict[str, str] = dict(
                self._db.execute("SELECT key, value FROM info")
            )
            head = self._db.execute("SELECT data FROM head").fetchone()
        except sqlite3.DatabaseError as e:
            self.close()
            raise NotAnAudioFile(f"{path.name}: {type(e).__name__}") from None
        facts = (self.info.get("kind"), self.info.get("format"), self.info.get("codec"))
        if facts != (KIND, FORMAT, CODEC) or head is None:
            self.close()
            raise NotAnAudioFile(f"{path.name}: {facts!r}")
        self._head = bytes(head[0])
        self.size = path.stat().st_size
        """The file's bytes on this PC (Learning says them)."""

    def close(self) -> None:
        with self._lock:
            db, self._db = self._db, None
        if db is not None:
            db.close()

    def clip(self, word: str) -> bytes | None:
        """`word`'s recording as a whole Ogg Opus file - as written, else in
        lower case - or None: not recorded (or the file closed, or gone)."""
        with self._lock:
            if self._db is None:
                return None
            try:
                for form in dict.fromkeys((word, word.lower())):
                    row = self._db.execute(
                        "SELECT sound FROM clips WHERE word = ?", (form,)
                    ).fetchone()
                    if row is not None:
                        return self._head + bytes(row[0])
            except sqlite3.Error:
                return None
        return None


def write_audio(
    path: Path,
    info: Mapping[str, str],
    head: bytes,
    clips: Iterable[tuple[str, bytes]],
) -> None:
    """Writes a new audio file at `path` (replacing any): the clips' shared
    start, and each word's own part, in word order so a build is the same
    byte for byte."""
    kept = sorted(clips)
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    try:
        # A clip is ~2.6 kB: on SQLite's default 4 kB pages each one fills a
        # page of its own, and 10,000 words took 40 MB for 26 MB of sound
        # (polyglotic-hq 405). On 64 kB pages the file is the sound and ~5 %.
        db.execute(f"PRAGMA page_size = {PAGE_SIZE}")
        db.executescript(SCHEMA)
        facts = {
            **info,
            "kind": KIND,
            "format": FORMAT,
            "codec": CODEC,
            "words": str(len(kept)),
        }
        db.executemany("INSERT INTO info VALUES (?, ?)", sorted(facts.items()))
        db.execute("INSERT INTO head VALUES (?)", (head,))
        db.executemany("INSERT INTO clips VALUES (?, ?)", kept)
        db.commit()
        db.execute("VACUUM")
    finally:
        db.close()


def audio_beside(folders: Sequence[Path], dictionary: str) -> SqliteAudio | None:
    """`dictionary`'s audio file from `folders` (the packs' folder, then the
    installer's): the newest by its `version` that opens and says it is
    that dictionary's. None: there is none this app reads."""
    best: tuple[tuple[int, ...], SqliteAudio] | None = None
    for folder in folders:
        found = sorted(folder.glob(f"{dictionary}*{SUFFIX}"))
        for path in found if folder.is_dir() else ():
            try:
                file = SqliteAudio(path)
            except (NotAnAudioFile, OSError):
                continue
            try:
                version = tuple(
                    int(n) for n in file.info.get("version", "0").split(".")
                )
            except ValueError:
                version = (0,)
            wrong = file.info.get("dictionary") != dictionary
            if wrong or (best is not None and best[0] >= version):
                file.close()
                continue
            if best is not None:
                best[1].close()
            best = (version, file)
    return best[1] if best is not None else None
