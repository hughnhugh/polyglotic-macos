"""Whether the PC is saturated right now, for judging timings fairly
(decision 0040).

The budget tests and the UI lab time interface actions in wall time, on a
PC that the CI runners and every agent's test runs share. An action over
its budget is the code or the PC. When every core is busy, the interface
thread waits its turn and a 2 ms action can take 60; on a PC that is
merely busy (the user's, 2026-11-08: 53-100 % of its 16 threads, median
71 %, while they played a game), nothing went over. So only a saturated
PC earns an action over budget more tries: no budget changes, and a calm
or busy PC gets the one retry it always had.
"""

import ctypes
import os
import sys
import time
from pathlib import Path

SATURATED = 0.5
"""The share of the PC's CPU time in use, over `SAMPLE_SECONDS`, from which
the PC counts as saturated. Half, not 0.9 (2026-11-11): with half the
logical cores busy the physical cores are all taken, and the start-time
check (400 ms; 385-425 ms on a quiet main) failed at 49-56 % busy five
times in one evening on changes that added nothing at start."""

SAMPLE_SECONDS = 0.2
"""Long enough for Windows' CPU counters, which move in 15.6 ms ticks."""

MOST_TRIES = 4
"""Tries for an action over budget: the retry every action gets, then up
to two more while the PC measures saturated."""

CALM = 0.3
"""The share of the PC's CPU time in use below which the PC counts as calm
for the start (decision 0103). The start spreads over seven threads, about
1.3 cores at once, so on this 8-core, 16-thread PC it slows from well below
`SATURATED`: 45 ms more for each 10 % of the PC in use, over its 400 ms
budget from about 44 % busy, and 353 ms at 26 % (polyglotic-hq 312,
2026-11-14). From this share its tries count as taken on a busy PC."""

CALM_WAIT_SECONDS = 60.0
"""How long a try of the start waits for the PC to calm before it's taken
anyway: a busy spell of other agents' tests lasts minutes, so a retry
taken at once lands in the same spell."""


def _cpu_times() -> tuple[float, float] | None:
    """(idle, total) CPU time since start, in any unit; None where the
    platform's counters aren't read."""
    if sys.platform == "win32":
        idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
        if not ctypes.WinDLL("kernel32").GetSystemTimes(
            ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
        ):
            return None
        return float(idle.value), float(kernel.value + user.value)  # kernel has idle
    stat = Path("/proc/stat")
    if stat.is_file():
        fields = [float(n) for n in stat.read_text().split("\n", 1)[0].split()[1:]]
        return fields[3] + fields[4], sum(fields)  # idle and iowait; all
    return None


def busy_share(seconds: float = SAMPLE_SECONDS) -> float | None:
    """The share of the PC's CPU time in use over the next `seconds`, from
    0 to 1; None where it can't be read."""
    before = _cpu_times()
    time.sleep(seconds)
    after = _cpu_times()
    if before is None or after is None or after[1] <= before[1]:
        return None
    return 1 - (after[0] - before[0]) / (after[1] - before[1])


def saturated(share: float | None, level: float = SATURATED) -> bool:
    """Whether `share` counts as busy enough for more tries: `level` and up."""
    return share is not None and share >= level


def wait_for_calm(
    level: float = CALM, most_seconds: float = CALM_WAIT_SECONDS, sample: float = 1.0
) -> float | None:
    """The PC's load over `sample` seconds, read again until it's under
    `level` or `most_seconds` have passed: the last reading. None (and no
    waiting) where the counters can't be read."""
    give_up = time.monotonic() + most_seconds
    while True:
        share = busy_share(sample)
        if share is None or share < level or time.monotonic() >= give_up:
            return share


def _seconds_per_unit() -> float:
    """What one unit of `_cpu_times` is, in seconds."""
    if sys.platform == "win32":
        return 1e-7  # GetSystemTimes: 100 ns
    return 1 / os.sysconf("SC_CLK_TCK")  # /proc/stat: clock ticks


class OthersMeanwhile:
    """The share of the PC's CPU time that everything but this process
    used from now until `share()`: how busy the rest of the PC was while
    this process did the timed work (its own CPU time, every thread's, left
    out)."""

    def __init__(self) -> None:
        self._from = _cpu_times()
        self._own = time.process_time()

    def share(self) -> float | None:
        now, own = _cpu_times(), time.process_time() - self._own
        if self._from is None or now is None or now[1] <= self._from[1]:
            return None
        total = now[1] - self._from[1]
        busy = total - (now[0] - self._from[0]) - own / _seconds_per_unit()
        return min(1.0, max(0.0, busy / total))


def describe(share: float | None) -> str:
    return "the PC's load unknown" if share is None else f"the PC {share:.0%} busy"
