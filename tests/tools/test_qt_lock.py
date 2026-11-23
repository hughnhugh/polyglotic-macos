"""`tools/qt_lock.py`: a Qt run on the user's PC waits for the shared
`qt.lock` and 3.0 GB free, holds the lock as the agents' wrappers write it,
keeps it fresh, and deletes only its own (polyglotic-hq 563). Each test
has its own lock file, memory and clock: none waits, and none touches the
PC's real lock."""

import contextlib
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tools import qt_lock

ROOT = Path("wt") / "563-qt-lock"


class Run:
    """A run's surroundings: its lock file, the PC's free memory at each
    reading, a clock that moves only when it sleeps, and what it said."""

    def __init__(self, folder: Path, free: list[int] | None = None) -> None:
        self.lock = folder / "qt.lock"
        self.free = list(free or [])
        self.now = 0.0
        self.sleeps: list[float] = []
        self.said: list[str] = []
        self.on_sleep: list[object] = []

    def memory(self) -> int:
        return self.free.pop(0) if self.free else 8000

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        if self.on_sleep:
            action = self.on_sleep.pop(0)
            if callable(action):
                action()

    def held(
        self, what: str = "pytest tests/ui"
    ) -> contextlib.AbstractContextManager[bool]:
        return qt_lock.held(
            what,
            say=self.said.append,
            path=self.lock,
            root=ROOT,
            memory=self.memory,
            sleep=self.sleep,
            clock=lambda: self.now,
        )


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Run]:
    """On the dev PC as far as the lock knows, outside any run that holds
    it (this test run may hold the real one)."""
    monkeypatch.setattr(qt_lock, "applies", lambda path=None: True)
    monkeypatch.delenv(qt_lock.HELD_ENV, raising=False)
    yield Run(tmp_path)


def a_finished_pid() -> int:
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    return finished.pid


def written(lock: Path, line: str, minutes_ago: float = 0.0) -> None:
    lock.write_text(line + "\n", encoding="utf-8")
    then = time.time() - minutes_ago * 60
    os.utime(lock, (then, then))


def test_a_free_lock_is_taken_written_as_the_wrappers_write_it_and_deleted_after(
    run: Run,
) -> None:
    with run.held("pytest  tests/ui\ttests/ui_next") as took:
        line = run.lock.read_text(encoding="utf-8").strip()
        held_by = os.environ.get(qt_lock.HELD_ENV)
    assert took is True
    assert re.fullmatch(
        r"563 \d{4}-\d\d-\d\d \d\d:\d\d:\d\d pytest tests/ui tests/ui_next"
        rf" pid={os.getpid()}",
        line,
    ), line
    assert held_by == str(os.getpid())  # its children run under it
    assert run.sleeps == [qt_lock.SETTLE_SECONDS]  # two readings, 20 s apart
    assert not run.lock.exists()
    assert qt_lock.HELD_ENV not in os.environ


def test_it_waits_while_another_running_run_holds_it(run: Run) -> None:
    other = f"554 2026-11-20 20:23:17 pytest tests pid={os.getpid()}"  # running
    written(run.lock, other)
    run.on_sleep = [None, None, run.lock.unlink]  # settle, then two queue polls
    with run.held() as took:
        assert run.lock.read_text(encoding="utf-8").startswith("563 ")
    assert took is True
    assert (
        run.said[0] == f"qt.lock: waiting - another Qt run holds {run.lock} ({other})"
    )
    assert run.sleeps == [qt_lock.SETTLE_SECONDS] + [qt_lock.POLL_SECONDS] * 2


def test_a_lock_whose_run_has_ended_is_taken_over(run: Run) -> None:
    written(run.lock, f"554 2026-11-20 20:23:17 pytest tests pid={a_finished_pid()}")
    with run.held() as took:
        assert run.lock.read_text(encoding="utf-8").startswith("563 ")
    assert took is True
    assert not any(said.startswith("qt.lock: waiting -") for said in run.said)


def test_a_wrappers_lock_is_waited_for_until_it_is_fifteen_minutes_old(
    run: Run,
) -> None:
    wrapper = "551 2026-11-20 08:55:00 tests/ui_next"  # no pid: the wrapper's own
    written(run.lock, wrapper, minutes_ago=14)
    assert qt_lock.holder(run.lock, ROOT) == wrapper
    written(run.lock, wrapper, minutes_ago=16)
    assert qt_lock.holder(run.lock, ROOT) is None
    with run.held() as took:
        assert run.lock.read_text(encoding="utf-8").startswith("563 ")
    assert took is True


def test_under_its_own_worktrees_wrapper_it_runs_without_taking_or_deleting_it(
    run: Run,
) -> None:
    wrapper = "563 2026-11-20 20:40:00 -m pytest tests/ui"
    written(run.lock, wrapper)
    with run.held() as took:
        pass
    assert took is False
    assert run.lock.read_text(encoding="utf-8").strip() == wrapper
    assert run.sleeps == []


def test_a_memory_waiter_leaves_the_lock_and_queue_open(run: Run) -> None:
    run.free = [4000, 2900, 4000, 4000]

    def another_run() -> None:
        assert qt_lock.tickets(run.lock) == []
        assert not run.lock.exists()
        with qt_lock.held(
            "other", path=run.lock, memory=lambda: 8000, sleep=lambda _: None
        ) as took:
            assert took

    run.on_sleep = [None, another_run]
    with run.held() as took:
        assert took
    assert run.said[0] == (
        "qt.lock: waiting - 2.8 GB free of the 3.0 GB a Qt run starts with"
    )
    assert run.sleeps == [
        qt_lock.SETTLE_SECONDS,
        qt_lock.POLL_SECONDS,
        qt_lock.SETTLE_SECONDS,
    ]


def test_a_queued_run_gives_back_its_ticket_if_memory_drops(run: Run) -> None:
    written(run.lock, f"other 2026-11-20 22:00:00 pid={os.getpid()}")
    run.free = [4000, 4000, 2900, 4000, 4000]

    def queued() -> None:
        assert len(qt_lock.tickets(run.lock)) == 1

    def left_queue() -> None:
        assert qt_lock.tickets(run.lock) == []
        run.lock.unlink()

    run.on_sleep = [None, queued, left_queue]
    with run.held() as took:
        assert took


def test_it_says_why_it_waits_once_not_at_every_reading(run: Run) -> None:
    run.free = [1900, 2000, 2200, 2300, 4000, 4000]
    with run.held():
        pass
    assert [s for s in run.said if s.startswith("qt.lock: waiting -")] == [
        "qt.lock: waiting - 1.9 GB free of the 3.0 GB a Qt run starts with"
    ]


def test_it_lets_go_when_it_gives_up_waiting_for_memory(run: Run) -> None:
    run.free = [1000] * (int(qt_lock.MOST_MINUTES * 60 / qt_lock.POLL_SECONDS) + 1)
    with pytest.raises(qt_lock.GaveUp, match="1.0 GB free of the 3.0 GB"), run.held():
        pytest.fail("ran without the memory")
    assert not run.lock.exists()


def test_it_gives_up_after_45_minutes_instead_of_hanging(run: Run) -> None:
    written(run.lock, f"554 2026-11-20 20:23:17 pytest tests pid={os.getpid()}")
    with pytest.raises(qt_lock.GaveUp, match="gave up after 45 min"), run.held():
        pytest.fail("ran without the lock")
    assert run.now >= qt_lock.MOST_MINUTES * 60
    assert run.lock.read_text(encoding="utf-8").startswith("554 ")
    assert qt_lock.tickets(run.lock) == []  # its place in the queue let go too


def test_it_deletes_only_its_own_line(run: Run) -> None:
    other = f"554 2026-11-20 20:50:00 pytest tests pid={os.getpid()}"
    with run.held():
        written(run.lock, other)  # taken over meanwhile
    assert run.lock.read_text(encoding="utf-8").strip() == other


def test_the_lock_is_kept_fresh_while_held(run: Run) -> None:
    with qt_lock.held(
        "pytest tests/ui",
        say=run.said.append,
        path=run.lock,
        root=ROOT,
        memory=run.memory,
        sleep=run.sleep,
        clock=lambda: run.now,
        refresh_seconds=0.05,
    ):
        old = time.time() - 10 * 60
        os.utime(run.lock, (old, old))
        deadline = time.monotonic() + 5
        while time.time() - run.lock.stat().st_mtime > 60:
            assert time.monotonic() < deadline, "never touched"
            time.sleep(0.05)


def test_a_run_on_ci_or_under_a_held_lock_takes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "qt.lock"
    for name in ("CI", "GITHUB_ACTIONS", qt_lock.HELD_ENV):
        for other in ("CI", "GITHUB_ACTIONS", qt_lock.HELD_ENV):
            monkeypatch.delenv(other, raising=False)
        monkeypatch.setenv(name, "1")
        assert not qt_lock.applies(lock), name
        never = lambda seconds: pytest.fail("it waited")
        with qt_lock.held("pytest", path=lock, sleep=never) as took:
            assert took is False
        assert not lock.exists()


@pytest.mark.windows_only
def test_on_the_dev_pc_where_the_locks_folder_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("CI", "GITHUB_ACTIONS", qt_lock.HELD_ENV):
        monkeypatch.delenv(name, raising=False)
    assert qt_lock.applies(tmp_path / "qt.lock")
    assert not qt_lock.applies(tmp_path / "not here" / "qt.lock")


def test_a_run_holding_it_stops_under_2_gb_free() -> None:
    assert qt_lock.too_little_memory(lambda: 1900) == (
        "qt.lock: the PC has 1.9 GB free, under the 2.0 GB a Qt run stops at"
        " (the live server runs beside it) - run again when it's back"
    )
    assert qt_lock.too_little_memory(lambda: 2048) is None
    assert qt_lock.too_little_memory(lambda: None) is None


def test_a_process_is_alive_until_it_ends() -> None:
    assert qt_lock.alive(os.getpid())
    assert not qt_lock.alive(a_finished_pid())


def test_whose_run_is_the_worktrees_project_or_the_checkouts_name() -> None:
    assert qt_lock.project(Path("wt") / "563-qt-lock") == "563"
    assert qt_lock.project(Path("polyglotic-desktop")) == "polyglotic-desktop"


# The queue (polyglotic-hq 569): runs waiting take numbered tickets beside
# the lock, and the lock goes to the oldest live one, whatever their poll
# rates. polyglotic-hq's qtlock.py keeps the same format.

WAITER = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from tools import qt_lock
qt_lock.applies = lambda path=None: True
qt_lock.POLL_SECONDS = float(sys.argv[4])
qt_lock.SETTLE_SECONDS = 0.0
with qt_lock.held("pytest", say=lambda text: None, path=Path(sys.argv[2]),
                  memory=lambda: 8000):
    with open(sys.argv[5], "a", encoding="ascii") as order:
        order.write(sys.argv[3] + "\\n")
    time.sleep(0.3)
"""


def removed(path: Path) -> None:
    """Deleted, though a waiter may be reading it (Windows refuses then)."""
    for _ in range(200):
        try:
            path.unlink()
            return
        except PermissionError:
            time.sleep(0.01)
    pytest.fail(f"{path} couldn't be deleted")


def a_ticket(lock: Path, number: int, line: str, minutes_ago: float = 0.0) -> Path:
    ticket = qt_lock.queue(lock) / f"{number:010d}.ticket"
    ticket.parent.mkdir(parents=True, exist_ok=True)
    written(ticket, line, minutes_ago)
    return ticket


def test_three_runs_that_look_at_different_rates_get_it_in_the_order_they_came(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "qt.lock"
    order = tmp_path / "order.txt"
    written(lock, f"554 2026-11-20 22:00:00 pytest tests pid={os.getpid()}")
    env = {k: v for k, v in os.environ.items() if k != qt_lock.HELD_ENV}
    waiters: list[subprocess.Popen[bytes]] = []
    try:
        # the slowest looker came first: before 569 the quickest took it
        for count, (name, poll) in enumerate(
            (("slow", 1.5), ("mid", 0.4), ("fast", 0.02)), 1
        ):
            waiters.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-c",
                        WAITER,
                        str(qt_lock.ROOT),
                        str(lock),
                        name,
                        str(poll),
                        str(order),
                    ],
                    env=env,
                )
            )
            deadline = time.monotonic() + 30
            while len(qt_lock.tickets(lock)) < count:
                assert time.monotonic() < deadline, f"{name} took no ticket"
                time.sleep(0.02)
        removed(lock)  # the run holding it ends
        for waiter in waiters:
            assert waiter.wait(timeout=60) == 0
    finally:
        for waiter in waiters:
            if waiter.poll() is None:
                waiter.kill()
                waiter.wait()
    assert order.read_text(encoding="ascii").split() == ["slow", "mid", "fast"]
    assert qt_lock.tickets(lock) == []
    assert not lock.exists()


def test_a_run_waits_behind_a_live_ticket_and_says_whose(run: Run) -> None:
    ahead = f"552 2026-11-20 22:00:00 tests/ui pid={os.getpid()}"
    first = a_ticket(run.lock, 7, ahead)
    run.on_sleep = [None, first.unlink]  # settle, then the other run takes it
    with run.held() as took:
        assert run.lock.read_text(encoding="utf-8").startswith("563 ")
    assert took is True
    assert run.said[0] == (
        f"qt.lock: waiting - {ahead} is ahead in the queue ({qt_lock.queue(run.lock)})"
    )
    assert run.sleeps == [qt_lock.SETTLE_SECONDS, qt_lock.POLL_SECONDS]
    assert qt_lock.tickets(run.lock) == []  # its own went when it took the lock


def test_dead_tickets_ahead_are_skipped_and_deleted(run: Run) -> None:
    ended = a_ticket(run.lock, 1, f"552 2026-11-20 pytest pid={a_finished_pid()}")
    hung = a_ticket(run.lock, 2, f"553 2026-11-20 pytest pid={os.getpid()}", 6)
    never_written = a_ticket(run.lock, 3, "", minutes_ago=2)
    with run.held() as took:
        pass
    assert took is True
    assert not any(said.startswith("qt.lock: waiting -") for said in run.said)
    assert not ended.exists()
    assert not hung.exists()
    assert not never_written.exists()


def test_a_ticket_being_written_or_touched_lately_is_live(tmp_path: Path) -> None:
    lock = tmp_path / "qt.lock"
    assert qt_lock.ticket_live(a_ticket(lock, 1, ""))
    assert qt_lock.ticket_live(a_ticket(lock, 2, f"552 x pid={os.getpid()}", 4))
    assert not qt_lock.ticket_live(a_ticket(lock, 3, f"552 x pid={os.getpid()}", 6))


def test_tickets_are_numbered_past_the_highest_and_a_lost_one_keeps_its_place(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "qt.lock"
    a_ticket(lock, 41, f"552 x pid={os.getpid()}")
    mine = qt_lock._take_ticket(lock, f"563 x pid={os.getpid()}")
    assert mine.name == "0000000042.ticket"
    mine.unlink()  # taken for dead by another run
    assert qt_lock._keep(lock, mine, f"563 x pid={os.getpid()}") == mine
    assert mine.exists()


def test_the_old_one_line_lock_is_still_held(run: Run) -> None:
    """polyglotic-hq's qtlock.py before 569 and the wrappers write no pid."""
    old = "553 2026-11-20 21:40:00"
    written(run.lock, old, minutes_ago=14)
    run.on_sleep = [None, run.lock.unlink]
    with run.held() as took:
        pass
    assert took is True
    assert run.said[0] == f"qt.lock: waiting - another Qt run holds {run.lock} ({old})"


def test_help_does_not_join_the_queue(
    run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["qt_lock.py", "--help"])
    monkeypatch.setattr(qt_lock, "lock_file", lambda: run.lock)
    monkeypatch.setattr(qt_lock, "free_mb", lambda: pytest.fail("read memory"))
    with pytest.raises(SystemExit) as raised:
        qt_lock.main()
    assert raised.value.code == 0
    assert "usage:" in capsys.readouterr().out
    assert not qt_lock.queue(run.lock).exists()
    assert not run.lock.exists()


def test_status_shows_holder_memory_and_live_tickets_without_joining(
    run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pid = os.getpid()
    written(run.lock, f"holder 2026-11-20 22:00:00 pid={pid}")
    live = a_ticket(run.lock, 1, f"live 2026-11-20 22:00:00 pid={pid}", 2)
    dead = a_ticket(run.lock, 2, "dead 2026-11-20 22:00:00 pid=123")
    monkeypatch.setattr(sys, "argv", ["qt_lock.py", "status"])
    monkeypatch.setattr(qt_lock, "lock_file", lambda: run.lock)
    monkeypatch.setattr(qt_lock, "free_mb", lambda: 8192)
    monkeypatch.setattr(qt_lock, "alive", lambda candidate: candidate == pid)
    assert qt_lock.main() == 0
    out = capsys.readouterr().out
    assert "Holder: holder " in out
    assert "Free memory: 8.0 GB" in out
    assert f"{live.name} (age " in out
    assert "refreshed 2.0 min ago" in out
    assert dead.name not in out
    assert qt_lock.tickets(run.lock) == [live]
