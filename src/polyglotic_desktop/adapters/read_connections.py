"""A read-only SQLite file read from several threads at once: a connection
per thread, and none closed while a query is under way on it (the pack and
meanings files; polyglotic-hq 220, 995)."""

from __future__ import annotations

import functools
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Concatenate, Protocol


class ReadConnections:
    """One file's connections, one for each thread that reads it.

    Each thread reads through a connection of its own: two threads sharing
    one got each other's rows, rows of None and "bad parameter or other API
    misuse" (polyglotic-hq 220).

    And a connection is closed only while no query is under way on it.
    Closing one on another thread mid-query ends the whole process with an
    access violation (0xC0000005) in Python's sqlite3: the query goes on to
    read the connection's handle, which the close has just cleared
    (polyglotic-hq 995, on CPython 3.12.10 and SQLite 3.49.1). A replaced
    pack is closed 2 s after the swap (`main.PACK_OLD_CLOSED_AFTER_MS`),
    and the app's quit closes every pack, while other threads may still be
    reading them. So `close` closes the idle connections at once and leaves
    each busy one to its own thread, which closes it as its query ends -
    never waiting for it, so the interface thread doesn't stall either."""

    def __init__(self, uri: str) -> None:
        self._uri = uri
        self._local = threading.local()
        self._lock = threading.Lock()
        self._under_way: dict[sqlite3.Connection, int] = {}
        """Every connection open: the queries under way on it (0: idle). Only
        its own thread changes its count; `close` takes the idle ones."""
        self._closed = False

    @contextmanager
    def reading(self) -> Iterator[sqlite3.Connection]:
        """This thread's connection - opened as it first reads - for the
        queries in the block, which `close` won't close under them. Nests.
        `sqlite3.ProgrammingError` once the file is closed."""
        db: sqlite3.Connection | None = getattr(self._local, "db", None)
        fresh = db is None
        if db is None:
            # check_same_thread off only so that `close` can close an idle
            # connection from whichever thread closes the file
            db = sqlite3.connect(self._uri, uri=True, check_same_thread=False)
        with self._lock:
            opened = not self._closed
            if opened:
                self._under_way[db] = self._under_way.get(db, 0) + 1
        if not opened:
            if fresh:
                db.close()
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        self._local.db = db
        try:
            yield db
        finally:
            with self._lock:
                left = self._under_way[db] - 1
                last = left == 0 and self._closed
                if last:
                    del self._under_way[db]
                else:
                    self._under_way[db] = left
            if last:  # the file was closed while this ran: closed now, here
                db.close()

    def current(self) -> sqlite3.Connection:
        """This thread's connection, inside `reading` (RuntimeError outside:
        a query there could be closed under)."""
        db: sqlite3.Connection | None = getattr(self._local, "db", None)
        if db is None or not self._under_way.get(db):
            raise RuntimeError("a query outside ReadConnections.reading")
        return db

    def close(self) -> None:
        """Closed for every thread: the idle connections now, each busy one
        by its own thread as its query ends. Further reads raise."""
        with self._lock:
            self._closed = True
            idle = [db for db, n in self._under_way.items() if n == 0]
            for db in idle:
                del self._under_way[db]
        for db in idle:
            db.close()


class _Reader(Protocol):
    _connections: ReadConnections


def reads[R: _Reader, **P, T](
    method: Callable[Concatenate[R, P], T],
) -> Callable[Concatenate[R, P], T]:
    """A reader's method whose queries (through `current`) run inside
    `reading`, so the file isn't closed under them."""

    @functools.wraps(method)
    def read(self: R, *args: P.args, **kwargs: P.kwargs) -> T:
        with self._connections.reading():
            return method(self, *args, **kwargs)

    return read
