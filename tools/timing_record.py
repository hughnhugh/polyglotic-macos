"""Main's last timings on this PC, so a pull request's budget failure says
whether the change made the action slower (polyglotic-hq 344, decision
0136).

The UI lab's gated actions are held to their budgets (`perf.budgets`) on
the PC the runners share. An action whose typical time on main has crept
up to its budget goes over on some runs and not others, whatever the pull
request changed: the theme change was 29 ms on main on 2026-11-07 and 76 ms
on 2026-11-14, against 100 ms, and failed pull requests 5 times in a day
that hadn't touched it, each a re-run of the UI lab. So:

- **on a push to main,** the lab keeps every gated action's median and
  longest run here, a file per kind of run (`kind`) - main's last record;
- **on a pull request,** an action over its budget that is not `SLOWER`
  than main's record - neither its median nor its longest run - is "over
  its budget as main is": named, on the run's page and as a warning, and
  not failed. Slower than that, or with no record to compare, it fails as
  before. Main's own runs are always held to the budget alone, so main
  going over is seen there, every time.

The record is this PC's alone - never sent anywhere - and holds state and
action names and milliseconds, nothing else. Anything that goes wrong
reading or writing it is left alone: without a record the gate is the
budget, as it was.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from tools import start_record

SLOWER = 1.5
"""How much slower than main's record an action over its budget may be
before the change is taken for the cause. Main's own runs of one action
differ by up to a third in a day (the theme change: 49-65 ms on
2026-11-10/11), a busy PC's more; a change that makes an action twice as
slow is over this in every try (decision 0136)."""


@dataclasses.dataclass(frozen=True)
class Timing:
    """An action's median and longest run, in milliseconds."""

    median_ms: float
    longest_ms: float

    def slower_than(self, main: Timing) -> bool:
        """Slower than `main` by more than `SLOWER`, at its median or its
        longest run."""
        return (
            self.median_ms > main.median_ms * SLOWER
            or self.longest_ms > main.longest_ms * SLOWER
        )

    def scaled(self, by: float) -> Timing:
        """This timing on a PC `by` times as slow: main's record at a pull
        request's load, `by` being the reference step's time now over its
        time in main's run (`tools.ui_lab.reference`, decision 0169)."""
        return Timing(self.median_ms * by, self.longest_ms * by)


@dataclasses.dataclass(frozen=True)
class Record:
    """Main's timings for one kind of run, and the commit they're of."""

    commit: str
    timings: dict[str, Timing]


def kind(text_size: int, app_text_size: str, language: str) -> str:
    """A kind of lab run: its text sizes and language (CI runs five)."""
    return f"lab-{text_size}-{app_text_size}-{language}"


OFF_WINDOWS = Path.home() / ".polyglotic-ci"
"""The record off Windows: CI's Linux runner's home, in its container,
which lasts from job to job as its registration does - the job's checkout
is cleaned for each one (polyglotic-hq 563)."""


def _folder(system: str = sys.platform) -> Path:
    named = os.environ.get("POLYGLOTIC_TIMING_RECORD")
    if named:
        return Path(named)
    return start_record.RECORD_FOLDER if system == "win32" else OFF_WINDOWS


def _account() -> str:
    return "".join(c for c in os.environ.get("USERNAME", "") if c.isalnum()) or "ci"


def save(of: str, timings: Mapping[str, Timing], commit: str) -> bool:
    """Keeps main's record of the `of` kind of run: a file of this
    account's own, since each runner's account can read the other's files
    there but not write them. False, and nothing more, if it can't be."""
    try:
        folder = _folder()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"timings-{of}-main-{_account()}.json").write_text(
            json.dumps(
                {
                    "commit": commit,
                    "timings": {
                        name: [round(t.median_ms, 2), round(t.longest_ms, 2)]
                        for name, t in timings.items()
                    },
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def load(of: str) -> Record | None:
    """Main's last record of the `of` kind of run on this PC - the newest
    of the accounts' files - or None: none yet, or it can't be read."""
    try:
        files = sorted(
            _folder().glob(f"timings-{of}-main-*.json"),
            key=lambda file: file.stat().st_mtime,
        )
        if not files:
            return None
        found = json.loads(files[-1].read_text(encoding="utf-8"))
        return Record(
            str(found["commit"]),
            {
                str(name): Timing(float(median), float(longest))
                for name, (median, longest) in found["timings"].items()
            },
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
