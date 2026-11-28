"""A pack or meanings file closed while another thread's query is under way
on it: the query finishes and the process lives (polyglotic-hq 995).

The app closes a replaced pack on the interface thread 2 s after the swap
(`main.PACK_OLD_CLOSED_AFTER_MS`), and every pack at its quit, while other
threads (the pack warmer, a pack learner opening, Learning's reads) may
still be reading them. Closing a connection under another thread's query
ended the whole process with an access violation in Python's sqlite3. Each
case runs in a child process, since that failure is a crash, not an
exception: the reader's query is held inside SQLite (a progress handler on
its connection) while the main thread closes the file."""

import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from tests.test_sqlite_dictionary import write_sample

from polyglotic_desktop.adapters.meanings_file import SqliteMeanings, write_meanings
from polyglotic_desktop.adapters.read_connections import ReadConnections
from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary

CLOSED_UNDER_A_QUERY = r"""
import sqlite3, sys, threading
from pathlib import Path

kind, path = sys.argv[1], Path(sys.argv[2])
inside, release = threading.Event(), threading.Event()
made = []
connect = sqlite3.connect

def gate():  # the reader's query, held inside SQLite until released
    if not inside.is_set():
        inside.set()
        release.wait(10)
    return 0

def gated_connect(*args, **kwargs):
    db = connect(*args, **kwargs)
    made.append(db)
    if threading.current_thread().name == "reader":
        db.set_progress_handler(gate, 1)
    return db

sqlite3.connect = gated_connect  # the readers connect through it, per thread
if kind == "dictionary":
    from polyglotic_desktop.adapters.sqlite_dictionary import SqliteDictionary
    file = SqliteDictionary(path)
    query = lambda: file.records("人")  # a lookup under way
else:
    from polyglotic_desktop.adapters.meanings_file import SqliteMeanings
    file = SqliteMeanings(path)
    query = lambda: file.meanings("x:1")
answer = []
reader = threading.Thread(target=lambda: answer.append(query()), name="reader")
reader.start()
assert inside.wait(10), "the reader's query never started"
threading.Timer(0.3, release.set).start()  # the query goes on after the close
file.close()  # the interface thread closing a replaced file
reader.join(10)
assert not reader.is_alive(), "the reader never finished"
closed = 0
for db in made:
    try:
        db.execute("SELECT 1")
    except sqlite3.ProgrammingError:
        closed += 1
print("survived", bool(answer and answer[0]), closed, len(made))
"""


def write_meanings_sample(path: Path) -> None:
    write_meanings(
        path, {"dictionary": "x", "language": "x"}, [("x:1", ("one",), False)]
    )


@pytest.mark.parametrize("kind", ["dictionary", "meanings"])
def test_a_file_closed_under_another_threads_query_lets_it_finish(
    tmp_path: Path, kind: str
) -> None:
    path = tmp_path / ("cedict.sqlite" if kind == "dictionary" else "x.meanings")
    if kind == "dictionary":
        write_sample(path)
    else:
        write_meanings_sample(path)
    done = subprocess.run(
        [sys.executable, "-c", CLOSED_UNDER_A_QUERY, kind, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    # before 995: the reader crashed (Windows 0xC0000005, -11 elsewhere)
    assert done.returncode == 0, (done.returncode, done.stderr[-800:])
    # the query got its answer, and every connection was closed after it:
    # the opening one at once, the reader's by its own thread as it ended
    assert done.stdout.split() == ["survived", "True", "2", "2"], done.stdout


def test_close_closes_idle_connections_at_once_and_reads_then_refuse(
    tmp_path: Path,
) -> None:
    """An idle thread's connection is closed by whichever thread closes the
    file, so Windows can delete it (polyglotic-hq 441); a read after the
    close is refused on every thread, as before."""
    path = tmp_path / "cedict.sqlite"
    write_sample(path)
    file = SqliteDictionary(path)
    opened: list[sqlite3.Connection] = []

    def read() -> None:
        with file._connections.reading() as db:
            opened.append(db)
        file.records("人")

    thread = threading.Thread(target=read)
    thread.start()
    thread.join()
    file.close()
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")  # closed here, not by its thread
    with pytest.raises(sqlite3.ProgrammingError):
        file.records("人")
    if sys.platform == "win32":
        path.unlink()  # nothing holds it


def test_readings_nest_and_the_last_one_out_closes_a_closed_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "x.meanings"
    write_meanings_sample(path)
    SqliteMeanings(path).close()
    connections = ReadConnections(f"{path.resolve().as_uri()}?mode=ro&immutable=1")
    with connections.reading() as outer:
        with connections.reading() as inner:
            assert inner is outer
            connections.close()  # under two queries: left open
            assert inner.execute("SELECT count(*) FROM meanings").fetchone() == (1,)
        assert outer.execute("SELECT 1").fetchone() == (1,)  # still under one
    with pytest.raises(sqlite3.ProgrammingError):
        outer.execute("SELECT 1")  # the last one out closed it
    with pytest.raises(sqlite3.ProgrammingError), connections.reading():
        pass
    with pytest.raises(RuntimeError):
        connections.current()  # outside a reading
