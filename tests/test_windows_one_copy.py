"""The lock the one copy holds, as Windows keeps it (`platform/windows/
one_copy.py`, polyglotic-hq 310, decision 0101): a named mutex. Held in
another process - the copy that runs, here a small stand-in - it's never
stale: ended, crashed or killed, that process leaves nothing behind."""

import os
import subprocess
import sys
import time
import uuid
from functools import partial
from pathlib import Path

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.main import os_adapters
from polyglotic_desktop.platform.windows.one_copy import NamedMutex, let_to_front
from polyglotic_desktop.ui import one_copy

ROOT = Path(__file__).resolve().parents[1]
HOLDS = """
import sys, time
from polyglotic_desktop.platform.windows.one_copy import NamedMutex
print(NamedMutex(sys.argv[1]).take(), flush=True)
time.sleep(float(sys.argv[2]))
"""


@pytest.fixture
def name() -> str:
    return f"Polyglotic-test-310-{uuid.uuid4().hex}"


def _held_elsewhere(name: str, seconds: float) -> subprocess.Popen[str]:
    """Another process holding `name`'s lock for `seconds`, then ending."""
    run = subprocess.Popen(
        [sys.executable, "-c", HOLDS, name, str(seconds)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert run.stdout is not None
    assert run.stdout.readline().strip() == "True"
    return run


def test_the_first_holds_it_and_a_second_doesnt_until_its_let_go(name: str) -> None:
    first, second = NamedMutex(name), NamedMutex(name)
    try:
        assert first.take()
        assert first.take()  # still this copy's
        assert not second.take()
        assert not second.take()  # asking again doesn't keep it alive
        first.release()
        assert second.take()
    finally:
        first.release()
        second.release()


def test_two_names_are_two_locks(name: str) -> None:
    one, other = NamedMutex(name), NamedMutex(name + "-other")
    try:
        assert one.take() and other.take()
    finally:
        one.release()
        other.release()


def test_held_by_another_process_until_it_ends(name: str) -> None:
    holder = _held_elsewhere(name, 30)
    lock = NamedMutex(name)
    try:
        assert not lock.take()
    finally:
        holder.kill()  # TerminateProcess: as a crash, or Task Manager's End task
        holder.communicate()
    assert lock.take()  # nothing stale
    lock.release()


def test_a_copy_on_its_way_out_is_waited_for_then_this_one_runs(name: str) -> None:
    """The updater's restart, or a start just after Quit: the old copy holds
    the lock a moment longer and no longer answers; the new start waits
    for it, then runs - the real lock, the real asking."""
    holder = _held_elsewhere(name, 1.5)
    lock = NamedMutex(name)
    try:
        began = time.monotonic()
        asked = partial(one_copy.ask_to_show, name, lambda pid: None)
        started = one_copy.start(lock.take, asked, show=True)
        assert started is one_copy.Start.RUNS
        assert 0.5 < time.monotonic() - began < one_copy.WAIT_SEC
    finally:
        lock.release()
        holder.kill()
        holder.communicate()


def test_a_name_windows_refuses_runs_rather_than_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    r"""No backslash may follow `Local\`: Windows refuses the name, and the
    copy runs, as it did before the lock (said in the log)."""
    lock = NamedMutex("Polyglotic-test-310\\not-a-name")
    assert lock.take()
    assert "running regardless" in caplog.text
    lock.release()


def test_letting_a_process_to_the_front_never_fails() -> None:
    """Refused quietly where this process may not hand it on - a test's
    process isn't the one in front."""
    let_to_front(os.getpid())
    let_to_front(0)


def test_windows_gives_main_the_lock_and_the_front() -> None:
    found = os_adapters("win32")
    assert found.copy_lock is NamedMutex
    assert found.let_to_front is let_to_front
