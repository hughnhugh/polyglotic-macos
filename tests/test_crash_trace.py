"""The crash trace (polyglotic-hq 997): a fatal error - one no Python
`except` can catch, as an access violation inside Qt is - leaves every
thread's Python stack in `logs/crash.log`, file, line and function only,
never a value; earlier runs' traces are kept, a few, and the file stays
out of what a report attaches."""

import faulthandler
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from polyglotic_desktop.adapters.app_log import read_log
from polyglotic_desktop.adapters.crash_trace import CRASH_TRACE_NAME, CrashTrace

CANARY = "CANARY-caption-zebra"


@pytest.fixture(autouse=True)
def pytests_own_trace_kept() -> Iterator[None]:
    """pytest's faulthandler on again after a test's own `stop`."""
    was = faulthandler.is_enabled()
    yield
    if was and not faulthandler.is_enabled() and sys.__stderr__ is not None:
        faulthandler.enable(sys.__stderr__, all_threads=True)


CRASHES = textwrap.dedent(
    f"""
    import faulthandler, sys, threading
    from pathlib import Path
    from polyglotic_desktop.adapters.crash_trace import CrashTrace

    CrashTrace(Path(sys.argv[1])).start()
    waiting = threading.Event()

    def another_thread_waits():
        waiting.wait()

    threading.Thread(target=another_thread_waits, daemon=True).start()

    def deep_in_the_app():
        caption = "{CANARY}"  # a value: never in the trace
        faulthandler._sigsegv()  # as a fault inside Qt: nothing catches it
        return caption

    deep_in_the_app()
    """
)


def crashed(folder: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", CRASHES, str(folder)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_fatal_error_leaves_every_threads_python_stack(tmp_path: Path) -> None:
    done = crashed(tmp_path)
    assert done.returncode != 0  # it did crash
    trace = (tmp_path / CRASH_TRACE_NAME).read_text("utf-8", errors="replace")
    assert "Segmentation fault" in trace  # Windows and Linux both name it so
    assert "in deep_in_the_app" in trace  # where it was, by function and line
    assert "line " in trace
    assert "in another_thread_waits" in trace  # every thread, not only its own
    assert CANARY not in trace  # names and lines only: no value


def test_the_last_runs_trace_is_kept_and_an_empty_one_used_again(
    tmp_path: Path,
) -> None:
    crashed(tmp_path)
    first = (tmp_path / CRASH_TRACE_NAME).read_text("utf-8", errors="replace")
    trace = CrashTrace(tmp_path)
    assert trace.start()
    trace.stop()
    assert (tmp_path / f"{CRASH_TRACE_NAME}.1").read_text(
        "utf-8", errors="replace"
    ) == first
    assert (tmp_path / CRASH_TRACE_NAME).read_text("utf-8") == ""
    assert trace.start()  # this run left nothing: its file is used again
    trace.stop()
    assert not (tmp_path / f"{CRASH_TRACE_NAME}.2").exists()


def test_only_so_many_traces_are_kept(tmp_path: Path) -> None:
    trace = CrashTrace(tmp_path, files=3)
    for n in range(5):
        (tmp_path / CRASH_TRACE_NAME).write_text(f"run {n}\n", "utf-8")
        assert trace.start()
        trace.stop()
    kept = sorted(p.name for p in tmp_path.iterdir())
    assert kept == [CRASH_TRACE_NAME, f"{CRASH_TRACE_NAME}.1", f"{CRASH_TRACE_NAME}.2"]
    assert (tmp_path / f"{CRASH_TRACE_NAME}.1").read_text("utf-8") == "run 4\n"
    assert (tmp_path / f"{CRASH_TRACE_NAME}.2").read_text("utf-8") == "run 3\n"


def test_a_run_that_writes_too_much_starts_its_file_again(tmp_path: Path) -> None:
    trace = CrashTrace(tmp_path, most=100)
    assert trace.start()
    try:
        trace.keep_small()  # empty: kept
        assert not (tmp_path / f"{CRASH_TRACE_NAME}.1").exists()
        assert trace._stream is not None
        trace._stream.write("Windows fatal exception: code 0x8001010d\n" * 10)
        trace._stream.flush()
        trace.keep_small()
        assert (tmp_path / f"{CRASH_TRACE_NAME}.1").stat().st_size > 100
        assert (tmp_path / CRASH_TRACE_NAME).stat().st_size == 0
    finally:
        trace.stop()


def test_a_report_never_attaches_the_trace(tmp_path: Path) -> None:
    """Until the founder decides it may (RULES #28): the log only."""
    (tmp_path / "polyglotic.log").write_text("the app's own line\n", "utf-8")
    crashed(tmp_path)
    attached = read_log(tmp_path) or ""
    assert "the app's own line" in attached
    assert "deep_in_the_app" not in attached
