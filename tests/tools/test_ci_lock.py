"""`tools/ci_lock.py`: CI's timing steps run alone on the PC the Windows
runners share (polyglotic-hq 312) - a step held alone waits for shared
ones and keeps new ones waiting; shared steps run side by side; the
step's exit code is kept; the lock never fails a step."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools import ci_lock

WINDOWS = pytest.mark.skipif(sys.platform != "win32", reason="Windows' LockFileEx")


def step(how: str, lock: Path, code: str = "", *options: str) -> subprocess.Popen[str]:
    """`python -m tools.ci_lock HOW [OPTIONS] -- python -c CODE`, as a CI
    step runs it."""
    return subprocess.Popen(
        [sys.executable, "-m", "tools.ci_lock", how, *options, "--"]
        + [sys.executable, "-c", code],
        env=dict(os.environ, POLYGLOTIC_CI_LOCK=str(lock)),
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        text=True,
    )


def holding(lock: Path) -> subprocess.Popen[bytes]:
    """A step holding the lock alone for a minute, its output not kept (its
    own command would keep the pipe open after it's killed)."""
    return subprocess.Popen(
        [sys.executable, "-m", "tools.ci_lock", "alone", "--"]
        + [sys.executable, "-c", "import time; time.sleep(60)"],
        env=dict(os.environ, POLYGLOTIC_CI_LOCK=str(lock)),
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.DEVNULL,
    )


@WINDOWS
def test_a_step_held_alone_waits_for_a_shared_one(tmp_path: Path) -> None:
    lock = tmp_path / "steps.lock"
    with ci_lock.held(alone=False, path=lock):
        timing = step("alone", lock)
        time.sleep(1.5)
        assert timing.poll() is None  # waiting
    out, _ = timing.communicate(timeout=30)
    assert timing.returncode == 0
    assert "ci_lock: alone, after" in out


@WINDOWS
def test_a_shared_step_that_comes_while_one_waits_alone_waits_behind_it(
    tmp_path: Path,
) -> None:
    """polyglotic-hq 344: the start with real windows waited 10 minutes and
    gave up (2026-11-14 11:56-12:06 UTC): shared steps that started while it
    waited took the lock beside the ones running, so it never came free. A
    shared step that comes later now waits for the alone one."""
    lock = tmp_path / "steps.lock"
    stamp = "import time; print('at', time.time())"
    with ci_lock.held(alone=False, path=lock):  # the other runner's pytest
        timing = step("alone", lock, stamp)
        time.sleep(1.5)  # waiting for the pytest
        assert timing.poll() is None
        later = step("shared", lock, stamp)  # the next heavy step starts
        time.sleep(1.5)
        assert later.poll() is None  # behind the timing step, not beside the pytest
    timed, _ = timing.communicate(timeout=30)
    after, _ = later.communicate(timeout=30)
    assert timing.returncode == 0 and later.returncode == 0
    assert "ci_lock: alone, after" in timed and "ci_lock: shared, after" in after

    def at(out: str) -> float:
        return float(
            next(line for line in out.splitlines() if line.startswith("at "))[3:]
        )

    assert at(timed) <= at(after)


@WINDOWS
def test_shared_steps_run_side_by_side(tmp_path: Path) -> None:
    lock = tmp_path / "steps.lock"
    with ci_lock.held(alone=False, path=lock):
        other = step("shared", lock)
        out, _ = other.communicate(timeout=30)
    assert other.returncode == 0 and "ci_lock: shared, after 0 s" in out


@WINDOWS
def test_a_shared_step_waits_while_one_is_held_alone(tmp_path: Path) -> None:
    lock = tmp_path / "steps.lock"
    with ci_lock.held(alone=True, path=lock):
        heavy = step("shared", lock)
        time.sleep(1.5)
        assert heavy.poll() is None
    heavy.communicate(timeout=30)
    assert heavy.returncode == 0


def test_the_steps_own_exit_code_is_kept(tmp_path: Path) -> None:
    done = step("alone", tmp_path / "steps.lock", "raise SystemExit(3)")
    done.communicate(timeout=30)
    assert done.returncode == 3


def test_a_lock_that_cant_be_had_runs_the_step_unlocked(tmp_path: Path) -> None:
    folder = tmp_path / "a-folder"  # a folder can't be opened as the lock
    folder.mkdir()
    done = step("alone", folder)
    out, _ = done.communicate(timeout=30)
    assert done.returncode == 0 and "ci_lock: unlocked" in out


@WINDOWS
def test_a_step_held_alone_gives_up_with_a_clear_line_not_a_hung_job(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "steps.lock"
    with ci_lock.held(alone=False, path=lock):
        timing = step("alone", lock, "print('ran')", "--most-minutes", "0.02")
        out, _ = timing.communicate(timeout=30)
    assert timing.returncode == 1 and "ran" not in out
    assert "ci_lock: gave up after 0.02 min: other CI steps held" in out


@WINDOWS
def test_a_jobs_own_wait_replaces_the_default_and_the_flag_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 999: the UI lab's walks gave up after the default 10
    minutes while a Checks (Windows) run held the PC shared; the lab's job
    names a longer wait once, for every step it locks."""
    lock = tmp_path / "steps.lock"
    monkeypatch.setenv(ci_lock.MINUTES_VARIABLE, "0.02")
    with ci_lock.held(alone=False, path=lock):
        timing = step("alone", lock, "print('ran')")
        out, _ = timing.communicate(timeout=30)
        assert "ci_lock: gave up after 0.02 min" in out
        flagged = step("alone", lock, "print('ran')", "--most-minutes", "0.03")
        out, _ = flagged.communicate(timeout=30)
        assert "ci_lock: gave up after 0.03 min" in out


@WINDOWS
def test_a_shared_step_that_waited_too_long_runs_unlocked(tmp_path: Path) -> None:
    lock = tmp_path / "steps.lock"
    with ci_lock.held(alone=True, path=lock):
        heavy = step("shared", lock, "print('ran')", "--most-minutes", "0.02")
        out, _ = heavy.communicate(timeout=30)
    assert heavy.returncode == 0 and "ran" in out and "gave up" in out


@WINDOWS
def test_a_lock_is_let_go_when_its_process_is_killed(tmp_path: Path) -> None:
    """A cancelled job's lock: Windows releases it with the process."""
    lock = tmp_path / "steps.lock"
    holder = holding(lock)
    time.sleep(1.5)  # it holds the lock now
    holder.kill()  # as a cancelled job's step is; its command may live on
    holder.wait(timeout=30)
    with ci_lock.held(alone=True, path=lock, most_minutes=0.1) as said:
        assert said.startswith("alone")


def test_off_ci_the_lock_is_taken_only_if_it_is_here(tmp_path: Path) -> None:
    lock = tmp_path / "polyglotic-ci" / "steps.lock"
    done = step("shared", lock, "", "--if-present")
    out, _ = done.communicate(timeout=30)
    assert done.returncode == 0
    assert (
        "ci_lock: unlocked: " + ("no " if sys.platform == "win32" else "not Windows")
        in out
    )
    assert not lock.parent.exists()  # never made off CI


def _alive(pid: int) -> bool:
    """Whether process `pid` is still running (Windows)."""
    import ctypes

    # getattr: WinDLL exists on Windows only (mypy --platform linux/darwin)
    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)  # noqa: B009
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _end(pid: int) -> None:
    """Our own test process `pid` ended, if it's still there (by its PID)."""
    import ctypes

    # getattr: WinDLL exists on Windows only (mypy --platform linux/darwin)
    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)  # noqa: B009
    handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
    if handle:
        kernel32.TerminateProcess(handle, 1)
        kernel32.CloseHandle(handle)


@WINDOWS
@pytest.mark.parametrize("ends", ["killed", "on its own"])
def test_what_a_step_started_ends_with_it(tmp_path: Path, ends: str) -> None:
    """polyglotic-hq 344: a cancelled job left the language walk's Pythons
    running, holding the runner's work folder, and every job after it on
    that runner failed at checkout (2026-11-15). As CI runs it - `python`
    through the venv's launcher, a command that starts a child of its own -
    the child ends with the step: killed, as a cancel does, or left behind
    by a command that ended."""
    pid_file = tmp_path / "child.pid"
    child = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    command = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        + ("time.sleep(60)" if ends == "killed" else "time.sleep(3)")
    )
    started = step("shared", tmp_path / "steps.lock", command)
    try:
        deadline = time.monotonic() + 20
        while not pid_file.exists() or not pid_file.read_text():
            assert time.monotonic() < deadline, "the child never started"
            time.sleep(0.1)
        pid = int(pid_file.read_text())
        assert _alive(pid)
        if ends == "killed":
            started.kill()  # the step's own process, as a cancel ends it
        started.communicate(timeout=30)
        deadline = time.monotonic() + 10
        while _alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _alive(pid), "the step's child outlived it"
    finally:
        if pid_file.exists() and pid_file.read_text():
            _end(int(pid_file.read_text()))
        if started.poll() is None:
            started.kill()
