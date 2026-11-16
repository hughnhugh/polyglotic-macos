"""A Linux CI step's memory, against its runner container's cap
(polyglotic-hq 344, 350).

    python -m tools.ci_memory --step "Tests (pytest)" -- COMMAND...

The Linux runners are containers on the user's PC, each capped since
2026-11-15 (the desktop's 2,200 MB, with no swap): the Docker VM ran out of
memory at 09:20 that day, with a site job running Chromium and a desktop job
beside the live models (350). A step that needs more than its container's
cap is killed by the kernel (exit 137). This says which step and how much
it reached, so a cap is set from evidence, not raised blindly.

While the command runs, the container's own cgroup (`/sys/fs/cgroup`, the
container's root under cgroup v2) is read every `EVERY` seconds:
`memory.stat`'s `anon` - memory that can't be given back, what a kill is
about - and `memory.current`, which adds the page cache the kernel gives
back under pressure. Afterwards one line gives both peaks, the cap, and how
far under it the step stayed; and if the kernel killed anything in the
container for memory meanwhile (`memory.events`' `oom_kill` went up, or
the command ended 137), an error line names the step: it needed more than
the cap. The whole container is read - the runner's own processes too, a
few hundred MB - and a spike shorter than `EVERY` can be missed.

Where the cgroup can't be read (Windows, another runner), the command runs
and the line says so. The command's own exit code is returned.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

EVERY = 0.5
"""Seconds between readings."""

MB = 1024 * 1024


def cgroup() -> Path:
    return Path(os.environ.get("POLYGLOTIC_CGROUP") or "/sys/fs/cgroup")


def _read(name: str) -> str | None:
    try:
        return (cgroup() / name).read_text(encoding="utf-8")
    except OSError:
        return None


def _field(text: str | None, key: str) -> int | None:
    """`key`'s number in a `memory.stat` or `memory.events` file."""
    for line in (text or "").splitlines():
        name, _, value = line.partition(" ")
        if name == key and value.strip().isdigit():
            return int(value)
    return None


def anon() -> int | None:
    return _field(_read("memory.stat"), "anon")


def current() -> int | None:
    text = _read("memory.current")
    return int(text) if text and text.strip().isdigit() else None


def cap() -> int | None:
    """The container's memory cap in bytes; None if it has none or can't
    be read."""
    text = _read("memory.max")
    return int(text) if text and text.strip().isdigit() else None


def oom_kills() -> int | None:
    return _field(_read("memory.events"), "oom_kill")


def _mb(n: int | None) -> str:
    return "?" if n is None else f"{n / MB:,.0f} MB"


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    split = argv.index("--") if "--" in argv else len(argv)
    own, command = argv[:split], argv[split + 1 :]
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").split("\n\n")[0],
        usage="python -m tools.ci_memory --step NAME -- COMMAND...",
    )
    parser.add_argument("--step", required=True, help="the step's name, for the lines")
    args = parser.parse_args(own)
    if not command:
        parser.error("no command to run (after --)")
    kills_before = oom_kills()
    if anon() is None or current() is None:
        print(
            f"ci_memory: {args.step}: no cgroup memory here - not measured", flush=True
        )
        return subprocess.run(command, check=False).returncode
    peak_anon, peak_all = anon() or 0, current() or 0
    running = subprocess.Popen(command)
    while running.poll() is None:
        peak_anon = max(peak_anon, anon() or 0)
        peak_all = max(peak_all, current() or 0)
        time.sleep(EVERY)
    code = running.returncode
    limit, kills_after = cap(), oom_kills()
    killed = code in (137, -9) or (
        kills_before is not None
        and kills_after is not None
        and kills_after > kills_before
    )
    room = "" if limit is None else f", {_mb(limit - peak_anon)} to spare"
    print(
        f"ci_memory: {args.step}: peak {_mb(peak_anon)} that can't be given back"
        f" ({_mb(peak_all)} with the page cache) of the container's cap"
        f" {_mb(limit) if limit else 'none'}{'' if killed else room}"
        " - the runner's own processes included",
        flush=True,
    )
    if killed:
        line = (
            f"{args.step} was killed for memory (exit {code}): it needed more than"
            f" the container's cap {_mb(limit)}; peak seen {_mb(peak_anon)} that"
            f" can't be given back. Raise the cap from this, or make the step"
            f" smaller (polyglotic-hq 344, scripts/RUNNERS.md)"
        )
        print(f"ci_memory: {line}", flush=True)
        if os.environ.get("GITHUB_ACTIONS"):
            print(f"::error title=Killed for memory::{line}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
