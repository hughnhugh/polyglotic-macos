"""`tools/ci_memory.py`: a Linux CI step's memory against its runner
container's cap (polyglotic-hq 344, 350) - its peak said every time, and a
kill for memory named with the step. A stand-in cgroup folder here."""

import os
import subprocess
import sys
from pathlib import Path

MB = 1024 * 1024


def cgroup(folder: Path, anon_mb: int, kills: int = 0) -> Path:
    folder.mkdir(exist_ok=True)
    (folder / "memory.max").write_text(f"{2200 * MB}\n", encoding="utf-8")
    (folder / "memory.current").write_text(f"{(anon_mb + 50) * MB}\n", encoding="utf-8")
    (folder / "memory.stat").write_text(
        f"anon {anon_mb * MB}\nfile {50 * MB}\n", encoding="utf-8"
    )
    (folder / "memory.events").write_text(
        f"low 0\nhigh 0\nmax 0\noom 0\noom_kill {kills}\n", encoding="utf-8"
    )
    return folder


def step(folder: Path, code: str) -> subprocess.CompletedProcess[str]:
    """`python -m tools.ci_memory --step Tests -- python -c CODE`."""
    return subprocess.run(
        [sys.executable, "-m", "tools.ci_memory", "--step", "Tests (pytest)", "--"]
        + [sys.executable, "-c", code],
        env=dict(os.environ, POLYGLOTIC_CGROUP=str(folder), GITHUB_ACTIONS="true"),
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_a_steps_peak_is_said_against_the_cap(tmp_path: Path) -> None:
    folder = cgroup(tmp_path / "cg", 300)
    grow = (
        "import time, pathlib; time.sleep(0.8);"
        f" pathlib.Path({str(folder / 'memory.stat')!r}).write_text("
        f"'anon {1500 * MB}'); time.sleep(1.2)"
    )
    done = step(folder, grow)
    assert done.returncode == 0
    assert (
        "ci_memory: Tests (pytest): peak 1,500 MB that can't be given back"
        in done.stdout
    )
    assert "of the container's cap 2,200 MB, 700 MB to spare" in done.stdout
    assert "::error" not in done.stdout


def test_a_step_killed_for_memory_is_named_with_what_it_reached(tmp_path: Path) -> None:
    """polyglotic-hq 350: a kill (exit 137) says which step, and that it
    needed more than the cap - the evidence for setting the cap."""
    folder = cgroup(tmp_path / "cg", 2100)
    killed = (
        "import pathlib, time; time.sleep(0.8);"
        f" pathlib.Path({str(folder / 'memory.events')!r}).write_text('oom_kill 1');"
        " raise SystemExit(137)"
    )
    done = step(folder, killed)
    assert done.returncode == 137
    assert (
        "::error title=Killed for memory::Tests (pytest) was killed for memory"
        " (exit 137): it needed more than the container's cap 2,200 MB; peak seen"
        " 2,100 MB" in done.stdout
    )


def test_where_the_cgroup_cant_be_read_the_step_runs_unmeasured(tmp_path: Path) -> None:
    done = step(tmp_path / "none", "raise SystemExit(3)")
    assert done.returncode == 3
    assert (
        "ci_memory: Tests (pytest): no cgroup memory here - not measured" in done.stdout
    )
