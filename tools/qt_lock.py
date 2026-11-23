"""The shared Qt lock: one Qt run at a time on the user's PC, started only
with memory to spare (polyglotic-hq 563).

    python -m tools.qt_lock status  # holder, queue and free memory

    with qt_lock.held("pytest tests/ui", say=print) as took:
        ...  # the Qt run

Agents' tests and the UI lab run beside the live server on the user's PC.
On 2026-11-20 two whole-suite runs from one agent, run together, took the
PC to 0.5 GB free; the agents' rule since that morning - a Qt run starts at
3.0 GB free, read twice 20 s apart, and holds `qt.lock` in the folder above
the repos - lived only in wrapper scripts each agent copied
(`projects/551-preview-1-fixes/work/qt_run551.ps1` in polyglotic-hq), and a
run started without one held nothing. So pytest's Qt tests (`tests/
conftest.py`) and the UI lab's command take it themselves.

The lock is the wrappers' own, so both keep out of each other's way: a file
whose one line says whose run it is (`551 2026-11-20 08:55:00 ...`), there
while the run lasts. This one adds `pid=N` at the end, and:

- **Waits** while another run holds it: a file under `STALE_MINUTES` old
  whose process (if it names one) is still running. An older one, or one
  whose process has ended (a run killed before it could delete it), is
  taken over.
- **Waits its turn** (polyglotic-hq 569): runs waiting take numbered
  tickets in `qt.lock.queue` beside the lock - one past the highest there,
  created exclusively, holding the lock's line with `pid=`, touched at
  every look - and the lock goes to the oldest live ticket. Before it, a
  run that looked every 20 s lost the lock to runs that looked every
  second: on 2026-11-20 one agent waited about 35 minutes in all, another
  saw four other holders in 12 minutes. A ticket whose process has ended,
  or untouched for `TICKET_STALE_MINUTES`, is skipped and deleted.
  polyglotic-hq's `qtlock.py` (346's tool) keeps the same lock and queue.
  The agents' wrappers take no ticket: they still take a free lock first.
- **Checks memory before joining the queue:** `START_MB` free at two
  readings `SETTLE_SECONDS` apart. A drop while queued sends the waiter
  back to the memory check without a ticket.
- **Keeps it fresh:** touched every `REFRESH_SECONDS` while held, so a run
  longer than `STALE_MINUTES` isn't taken over (polyglotic-hq 548).
- **Deletes it at the end** - only if the line is still this run's.
- **Lets a run's own children through:** `HELD_ENV` is set while it's held,
  so the UI lab's languages, each its own process, run under their
  parent's lock instead of waiting for it.
- **Runs under its own wrapper:** a wrapper's line (no `pid=`) under
  `STALE_MINUTES` old naming this worktree's project (`wt/551-...`) is the
  wrapper that started this run: it runs under it, taking nothing.
- **Never hangs:** it waits at most `MOST_MINUTES`, then raises `GaveUp`.

Only on the dev PC: off CI (`CI` and `GITHUB_ACTIONS` unset - CI's runs on
this PC order themselves with `tools/ci_lock.py`), on Windows, where the
lock's folder is there (`POLYGLOTIC_QT_LOCK` names another file: the
tests'). Anywhere else the run goes ahead at once, and nothing is said.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

LOCK_FILE = Path.home() / "workspace" / "polyglotic" / "qt.lock"
"""The folder that holds the three repos and the agents' worktrees (`wt/`)."""

HELD_ENV = "POLYGLOTIC_QT_LOCK_HELD"
"""Set while a run holds the lock, to the holder's pid: its children run
under it."""

START_MB = 3072
"""Free memory a run waits for, at both readings."""

STOP_MB = 2048
"""Under this a run that holds the lock should stop (the wrappers killed
theirs here; `too_little_memory`)."""

SETTLE_SECONDS = 20.0
"""Between the two readings: memory that another run has only just let go
of isn't counted on."""

STALE_MINUTES = 15.0
"""A wrapper's lock this old is taken over (theirs isn't kept fresh)."""

REFRESH_SECONDS = 60.0

POLL_SECONDS = 2.0
"""How often a waiting run looks at the lock (and touches its ticket)."""

TICKET_STALE_MINUTES = 5.0
"""A ticket untouched this long is a waiter that hung: skipped."""

MOST_MINUTES = 45.0
"""About three whole-suite runs ahead of this one."""

ROOT = Path(__file__).resolve().parents[1]

_PID = re.compile(r"\bpid=(\d+)\s*$")
_TICKET = re.compile(r"\d{10}\.ticket")


class GaveUp(RuntimeError):
    """The lock or the memory wasn't there within `MOST_MINUTES`."""


def lock_file() -> Path:
    named = os.environ.get("POLYGLOTIC_QT_LOCK")
    return Path(named) if named else LOCK_FILE


def on_the_dev_pc(path: Path | None = None) -> bool:
    """Off CI, on Windows, where the lock's folder is."""
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return False
    return sys.platform == "win32" and (path or lock_file()).parent.is_dir()


def applies(path: Path | None = None) -> bool:
    """Whether a run here takes the lock: on the dev PC, not already under
    a run that holds it (`HELD_ENV`)."""
    return not os.environ.get(HELD_ENV) and on_the_dev_pc(path)


def project(root: Path = ROOT) -> str:
    """Whose run, as the wrappers write it: the worktree's project number
    (`wt/563-qt-lock`: 563), or the checkout's folder name."""
    match = re.match(r"(\d+)-", root.name)
    return match.group(1) if match else root.name


def free_mb() -> int | None:
    """The PC's available memory in MB (Task Manager's "Available"), or
    None where it can't be read."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Status(ctypes.Structure):
        _fields_ = [
            ("dwLength", wintypes.DWORD),
            ("dwMemoryLoad", wintypes.DWORD),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = Status()
    status.dwLength = ctypes.sizeof(Status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return int(status.ullAvailPhys // (1024 * 1024))


def alive(pid: int) -> bool:
    """Whether process `pid` is running. On Windows by asking for its exit
    code - never `os.kill(pid, 0)`, which ends it there (polyglotic-hq 411)."""
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5  # access denied: another account's
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _read(path: Path) -> tuple[str, float] | None:
    """The lock's (or a ticket's) line and its age in minutes, or None if
    there's none."""
    try:
        line = path.read_text(encoding="utf-8-sig", errors="replace").strip()
        age = (time.time() - path.stat().st_mtime) / 60
    except FileNotFoundError:
        return None
    except OSError:
        return ("(unreadable)", 0.0)  # being written: held
    return line, age


def _remove(path: Path) -> None:
    """`path` deleted, tried for about 2 s: on Windows a run reading it at
    that moment makes the delete fail (polyglotic-hq 569's test saw it), and
    a lock or ticket left behind naming a running process holds everyone
    up."""
    for _ in range(100):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.02)
        except OSError:
            return


OWN_WRAPPER = "own wrapper"


def holder(path: Path, root: Path = ROOT) -> str | None:
    """Who holds the lock at `path`: their line; `OWN_WRAPPER` for this
    worktree's own wrapper; or None when it's free or stale."""
    read = _read(path)
    if read is None:
        return None
    line, age = read
    if age >= STALE_MINUTES:
        return None
    pid = _PID.search(line)
    if pid is not None:
        return line if alive(int(pid.group(1))) else None
    whose = line.split(" ", 1)[0]
    return OWN_WRAPPER if whose == project(root) else line


def _take(path: Path, line: str, root: Path) -> bool:
    """The lock made, with `line` in it; False if another run made it
    first. A stale one is removed first."""
    if path.exists() and holder(path, root) is None:
        _remove(path)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
        file.write(line + "\n")
    return True


def _ours(path: Path, line: str) -> bool:
    read = _read(path)
    return read is not None and read[0] == line


def queue(path: Path) -> Path:
    """The folder of tickets for the lock at `path`: `qt.lock.queue`."""
    return path.with_name(path.name + ".queue")


def tickets(path: Path) -> list[Path]:
    """The tickets waiting for the lock at `path`, oldest first."""
    try:
        found = [t for t in queue(path).iterdir() if _TICKET.fullmatch(t.name)]
    except FileNotFoundError:
        return []
    return sorted(found, key=lambda t: t.name)


def ticket_live(ticket: Path) -> bool:
    """A ticket whose run is still waiting: its process running and the
    ticket touched within `TICKET_STALE_MINUTES`. One being written (no
    `pid=` yet) counts for a minute; one that can't be read counts."""
    read = _read(ticket)
    if read is None:
        return False
    line, age = read
    pid = _PID.search(line)
    if pid is None:
        return line == "(unreadable)" or age < 1.0
    return age < TICKET_STALE_MINUTES and alive(int(pid.group(1)))


def _take_ticket(path: Path, line: str, number: int | None = None) -> Path:
    """A ticket at the back of the queue - or at `number` if that's free,
    so a run whose ticket was taken for dead keeps its place."""
    folder = queue(path)
    folder.mkdir(parents=True, exist_ok=True)
    if number is None:
        number = max((int(t.name[:10]) for t in tickets(path)), default=0) + 1
    for _ in range(1000):
        ticket = folder / f"{number:010d}.ticket"
        try:
            fd = os.open(ticket, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            number += 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(line + "\n")
        return ticket
    raise GaveUp(f"qt.lock: no ticket could be made in {folder}")


def _live_tickets(path: Path) -> Iterator[Path]:
    for ticket in tickets(path):
        if ticket_live(ticket):
            yield ticket
        else:
            _remove(ticket)


def _ahead_of(path: Path, mine: Path) -> str | None:
    live = list(_live_tickets(path))
    if live and live[0].name < mine.name:
        read = _read(live[0])
        return read[0] if read is not None and read[0] else "someone"
    return None


def _keep(path: Path, mine: Path, line: str) -> Path:
    """`mine` touched; made again (at its number if it can be) if it went."""
    try:
        os.utime(mine)
    except FileNotFoundError:
        return _take_ticket(path, line, int(mine.name[:10]))
    except OSError:
        pass
    return mine


def _gb(mb: int | None) -> str:
    return "?" if mb is None else f"{mb / 1024:.1f} GB"


def _line(root: Path, what: str) -> str:
    return (
        f"{project(root)} {time.strftime('%Y-%m-%d %H:%M:%S')}"
        f" {' '.join(what.split())} pid={os.getpid()}"
    )


@contextlib.contextmanager
def held(
    what: str,
    *,
    say: Callable[[str], None] = lambda text: print(text, file=sys.stderr, flush=True),
    path: Path | None = None,
    root: Path = ROOT,
    memory: Callable[[], int | None] = free_mb,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    refresh_seconds: float = REFRESH_SECONDS,
) -> Iterator[bool]:
    """Wait for memory before joining the queue for the shared Qt lock.

    Give up the ticket if memory drops while queued. Yield False when the
    lock does not apply or the worktree's own wrapper already holds it.
    Raise GaveUp on timeout.
    """
    path = path or lock_file()
    if not applies(path):
        yield False
        return
    if holder(path, root) == OWN_WRAPPER:
        yield False
        return
    started = clock()
    said = ""

    def waited_too_long(waiting: str) -> None:
        if clock() - started >= MOST_MINUTES * 60:
            raise GaveUp(
                f"qt.lock: gave up after {MOST_MINUTES:g} min: {waiting}."
                " Try again later, or ask Claude."
            )

    mine = None
    under_wrapper = False
    try:
        while True:
            whose = holder(path, root)
            if whose == OWN_WRAPPER:
                under_wrapper = True
                break
            free = memory()
            if mine is None and (free is None or free >= START_MB):
                sleep(SETTLE_SECONDS)
                free = memory()
            if free is not None and free < START_MB:
                if mine is not None:
                    _remove(mine)
                    mine = None
                waiting = (
                    f"{_gb(free)} free of the {_gb(START_MB)} a Qt run starts with"
                )
                waited_too_long(waiting)
                if said != "memory":
                    say(f"qt.lock: waiting - {waiting}")
                    said = "memory"
                sleep(POLL_SECONDS)
                continue
            if mine is None:
                waits_as = _line(root, what)
                mine = _take_ticket(path, waits_as)
                whose = holder(path, root)
                if whose == OWN_WRAPPER:
                    under_wrapper = True
                    break
            mine = _keep(path, mine, waits_as)
            ahead = _ahead_of(path, mine)
            line = _line(root, what)
            if whose is None and ahead is None and _take(path, line, root):
                break
            if not whose and ahead is not None:
                waiting = f"{ahead} is ahead in the queue ({queue(path)})"
            else:
                waiting = f"another Qt run holds {path} ({whose or 'just taken'})"
            waited_too_long(waiting)
            if (whose or ahead) != said:  # once for each, not at every look
                say(f"qt.lock: waiting - {waiting}")
                said = whose or ahead or ""
            sleep(POLL_SECONDS)
    finally:
        if mine is not None:
            _remove(mine)
    if under_wrapper:
        yield False
        return
    stop = threading.Event()

    def keep_fresh() -> None:
        while not stop.wait(refresh_seconds):
            if _ours(path, line):
                with contextlib.suppress(OSError):
                    os.utime(path)

    fresh = threading.Thread(target=keep_fresh, name="qt.lock fresh", daemon=True)
    fresh.start()
    before = os.environ.get(HELD_ENV)
    try:
        say(f"qt.lock: held after {clock() - started:.0f} s ({_gb(free)} free): {path}")
        os.environ[HELD_ENV] = str(os.getpid())
        yield True
    finally:
        stop.set()
        fresh.join(5)
        if before is None:
            os.environ.pop(HELD_ENV, None)
        else:
            os.environ[HELD_ENV] = before
        if _ours(path, line):
            _remove(path)


def too_little_memory(memory: Callable[[], int | None] = free_mb) -> str | None:
    """Why a run holding the lock should stop now - under `STOP_MB` free -
    or None."""
    free = memory()
    if free is None or free >= STOP_MB:
        return None
    return (
        f"qt.lock: the PC has {_gb(free)} free, under the {_gb(STOP_MB)} a Qt run"
        " stops at (the live server runs beside it) - run again when it's back"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the shared Qt lock.")
    parser.add_argument(
        "action", choices=["status"], help="show the holder, queue and free memory"
    )
    parser.parse_args()
    path = lock_file()
    whose = holder(path, ROOT)
    if whose == OWN_WRAPPER:
        read = _read(path)
        whose = read[0] if read is not None else None
    print(f"Holder: {whose or 'none'}")
    print(f"Free memory: {_gb(free_mb())}")
    print("Queue:")
    for ticket in _live_tickets(path):
        read = _read(ticket)
        if read is not None:
            line, refreshed = read
            try:
                info = ticket.stat()
            except FileNotFoundError:
                continue
            except OSError:
                print(f"  {ticket.name} (unreadable)")
                continue
            age = (
                max(time.time() - getattr(info, "st_birthtime", info.st_mtime), 0) / 60
            )
            print(
                f"  {ticket.name} (age {age:.1f} min, "
                f"refreshed {max(refreshed, 0):.1f} min ago) {line}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
