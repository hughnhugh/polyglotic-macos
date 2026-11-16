"""The user's settings in a JSON file (the `SettingsStore` port).

One small file - a few dozen values - written whole on every change, to a
temporary file first and then moved over the old one, so a crash mid-write
leaves the old settings, never half of them. A missing or unreadable file
gives no settings (the defaults), not an error. `main` chooses the path:
`settings.json` in Polyglotic's folder in the user's local app data,
not the install folder, which updates replace.

Several parts of the app write the file (today's `Settings`, the new
interface's caption windows and transcripts), each its own keys beside the
others', so each reads it again just before saving. The store keeps what
it last read or saved, and answers with that when the file can't be read
for a moment (gone, locked, half-written by something else): every writer
then builds on the newest state, not on a copy of its own from before
another's save (polyglotic-hq project 128, 2026-11-07). Before anything
was read or saved, an unreadable file still gives no settings.

Nothing waits on the disk from the interface thread (polyglotic-hq project
136, 2026-11-07: every click on a setting read and wrote the file there,
90-126 ms a time under load): `save` keeps the values and hands the write
to a thread of its own, one write for however many saves arrive while it
runs; `load` answers from what's kept while the file is unchanged since it
was last read or written (one `stat`), and reads it only when another
program changed it. `close` (at quit) waits for the last write, so nothing
saved is lost.

A file that isn't JSON at the start (corrupt, or edited by hand) is set
aside, renamed beside the settings with the time, and the app starts from
the defaults - `set_aside` says so, for the interface to tell the user once
(133's item 10: it was reset without a word and then overwritten).

Settings hold no caption text and nothing personal beyond the user's
choices (languages, which app to listen to, overlay positions).
"""

import contextlib
import json
import logging
import os
import threading
from collections.abc import Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


class JsonSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.set_aside: Path | None = None
        """A file that wasn't JSON when first read, kept under this name."""
        self._known: dict[str, object] | None = None
        """What was last read or saved, if anything was."""
        self._seen: tuple[int, int] | None = None
        """The file's (mtime_ns, size) as last read or written: unchanged,
        `_known` is what it holds."""
        self._unsaved = False
        """The last write failed: `_known` is newer than the file."""
        self._pending = False
        """A write is queued or running; `_known` is newer than the file."""
        self._lock = threading.Lock()
        self._writer = ThreadPoolExecutor(1, thread_name_prefix="settings")
        self._last: Future[None] | None = None
        self._closed = False

    def load(self) -> dict[str, object]:
        with self._lock:
            known = self._known
            if known is not None and (self._pending or self._unsaved):
                # newer than the file: every writer builds on it, and the next
                # write that works writes it all (polyglotic-hq 133)
                return dict(known)
            seen = self._seen
        try:
            stamp = _stamp(self.path)
        except OSError:
            stamp = None
        if known is not None and stamp is not None and stamp == seen:
            return dict(known)  # unchanged since: not read again
        return self._read(known)

    def _read(self, known: dict[str, object] | None) -> dict[str, object]:
        try:
            with self.path.open(encoding="utf-8") as f:
                values = json.load(f)
            stamp = _stamp(self.path)
        except FileNotFoundError:
            problem = None
        except (OSError, ValueError) as error:
            problem = type(error).__name__
        else:
            if not isinstance(values, dict):
                problem = "NotAMapping"
            else:
                with self._lock:
                    self._known, self._seen = dict(values), stamp
                return dict(values)
        if known is not None:
            log.warning(
                "settings not read (%s), keeping what was last read or saved",
                problem or "no file",
            )
            return dict(known)
        if problem in ("JSONDecodeError", "NotAMapping"):
            self._set_aside(problem)
        elif problem is not None:
            log.warning("settings not read, using the defaults: %s", problem)
        return {}

    def _set_aside(self, problem: str) -> None:
        """The file isn't settings: renamed beside the settings, with the
        time, and never written over. Nothing read yet - the start. The time
        is this PC's, with its offset: Home's banner names the file, and a
        UTC time read as yesterday in Australia (polyglotic-hq 184, 203)."""
        stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
        aside = self.path.with_name(
            f"{self.path.stem}.unreadable-{stamp}{self.path.suffix}"
        )
        try:
            os.replace(self.path, aside)
        except OSError as error:
            log.warning(
                "settings not read (%s), using the defaults; the file couldn't be"
                " set aside (%s)",
                problem,
                type(error).__name__,
            )
            return
        self.set_aside = aside
        log.warning(
            "settings not read (%s), using the defaults; the file is kept as %s",
            problem,
            aside.name,
        )

    def save(self, values: Mapping[str, object]) -> None:
        """Kept at once, and written whole on the store's own thread - or,
        if the file can't be written (read-only, or held by another
        program), kept here and written with the next save that works: the
        app goes on with them either way, never an error (polyglotic-hq
        133: a read-only file made every change an uncaught error and a
        crash report). After `close`, written here and now."""
        with self._lock:
            self._known = dict(values)
            if self._closed:
                self._pending = True
                flush = True
            elif self._pending:
                return
            else:
                self._pending = True
                flush = False
                self._last = self._writer.submit(self._flush)
        if flush:
            self._flush()

    def flush(self) -> None:
        """Waits until every save so far is on disk (or failed and kept)."""
        last = self._last
        if last is not None:
            last.result()

    def close(self) -> None:
        """At quit: the last write finished, the thread ended."""
        with self._lock:
            self._closed = True
        self.flush()
        self._writer.shutdown(wait=True)

    # -- on the writing thread ------------------------------------------------------------

    def _flush(self) -> None:
        while True:
            with self._lock:
                values = self._known
            assert values is not None
            self._write(values)
            with self._lock:
                if self._known is values:  # no save since: done
                    self._pending = False
                    return

    def _write(self, values: dict[str, object]) -> None:
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as f:
                json.dump(values, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.path)
            stamp = _stamp(self.path)
        except Exception as error:  # noqa: BLE001 - a value JSON can't hold too (142)
            with self._lock:
                first = not self._unsaved
                self._unsaved = True
            if first:
                log.warning(
                    "settings not saved (%s): kept until they can be",
                    type(error).__name__,
                )
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            return
        with self._lock:
            self._seen = stamp
            again, self._unsaved = self._unsaved, False
        if again:
            log.info("settings saved again")


class ReadOnlySettings:
    """The settings file read as it is, never written or set aside: for a
    start that found another copy running, which owns the file
    (polyglotic-hq 310) - its interface language, to say so in."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, object]:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return values if isinstance(values, dict) else {}

    def save(self, values: Mapping[str, object]) -> None:
        """Nothing is written."""


def _stamp(path: Path) -> tuple[int, int]:
    found = os.stat(path)
    return found.st_mtime_ns, found.st_size
