"""The start's parts beside main's last record, so a start that grew says
which part grew (polyglotic-hq 314).

The timed start (`tools/learner_start.py`) reports where its time went, by
part (`perf.start_parts`). CI's start test
(`tests/ui/test_start_with_a_big_learner.py`) prints the parts of its
starts, and:

- **on a push to main,** keeps them in a file on the PC the runners share
  (`RECORD_FOLDER`, beside CI's lock) - main's last record;
- **on a pull request,** prints each part beside main's, and marks the ones
  that grew.

**Grew, at this load:** the PC the runners share is rarely as busy twice,
and a busier PC slows every part. So main's parts are first scaled by how
the whole start compares (this start's total over main's), and a part grew
if it is `GREW_MS` or more over its scaled share - 15 ms added to one part
shows as about 14 over; a start 30 % slower all round shows nothing.

Recorded, not gated: the budget is the gate (`perf.budgets`). The record is
this PC's alone - never sent anywhere - and holds part names and
milliseconds, nothing else. Anything that goes wrong reading or writing it
is left alone: the test's result never depends on it.

**Two starts are recorded,** each beside its own record of main's
(polyglotic-hq 322): the gate's, `OFFSCREEN`, and the one a learner sees,
`REAL_WINDOWS` (`tests/ui/test_start_with_real_windows.py`) - with real
windows on a private desktop, its parts followed by `AFTER_PAINT`, the time
from the paint to the first moment a click is answered. Main's runs of that
one are also kept, a row each (`history`), so that whether it holds steady
enough to gate can be read off the PC (decision 0111).
"""

from __future__ import annotations

import dataclasses
import json
import os
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path

RECORD_FOLDER = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "polyglotic-ci"
"""On the PC, where both runners' accounts can make files and read each
other's (as CI's lock file: `tools/ci_lock.py`). POLYGLOTIC_START_RECORD
names another folder (the tests')."""

GREW_MS = 8.0
"""A part this much over main's, at this load, is marked: under it the
medians of five starts differ by themselves."""

OFFSCREEN = "parts"
"""The gate's start: offscreen, to the first paint."""
REAL_WINDOWS = "real-windows"
"""The start a learner sees: real windows, to the first answered click."""

AFTER_PAINT = "after_paint"
"""The part after the last: from the first paint to the event loop's first
turn, when a click is answered (`TimedStart.answers_ms`)."""

HISTORY_ROWS = 200
"""Main's runs kept in a start's history: the oldest go."""


@dataclasses.dataclass(frozen=True)
class Record:
    """Main's start, as last recorded on this PC."""

    commit: str
    window_ms: float
    parts: Mapping[str, float]


def typical(starts: Sequence[Mapping[str, float]]) -> dict[str, float]:
    """Each part's median over `starts`, in the order the parts came."""
    names = list(dict.fromkeys(name for start in starts for name in start))
    return {
        name: statistics.median(start.get(name, 0.0) for start in starts)
        for name in names
    }


def grew(
    now: Mapping[str, float], before: Mapping[str, float], by_ms: float = GREW_MS
) -> dict[str, float]:
    """The parts of `now` that grew against `before`, with by how many
    milliseconds at this load (see the module's words). A part `before`
    doesn't have grew by all of it."""
    whole, was = sum(now.values()), sum(before.values())
    scale = whole / was if was > 0 else 1.0
    over = {name: ms - before.get(name, 0.0) * scale for name, ms in now.items()}
    return {name: by for name, by in over.items() if by >= by_ms}


def with_after(
    parts: Mapping[str, float], answers_ms: float | None
) -> dict[str, float]:
    """A start's parts followed by `AFTER_PAINT`, where it went on that far."""
    if answers_ms is None:
        return dict(parts)
    return {**parts, AFTER_PAINT: answers_ms}


def table(
    now: Mapping[str, float], record: Record | None, what: str = "the start's parts"
) -> str:
    """The parts as lines to print: each beside main's, the grown ones
    marked; with no record, the parts alone. `what`: which start's."""
    whole = sum(now.values())
    if record is None:
        lines = [f"{what} ({whole:.0f} ms in all; no record of main's):"]
        lines += [f"  {name:28s}{ms:6.0f} ms" for name, ms in now.items()]
        return "\n".join(lines)
    heading = (
        f"{what} ({whole:.0f} ms in all) beside main's at"
        f" {record.commit[:8]} ({sum(record.parts.values()):.0f} ms):"
    )
    lines = [heading]
    grown = grew(now, record.parts)
    for name, ms in now.items():
        was = record.parts.get(name)
        beside = "new" if was is None else f"main {was:.0f}"
        mark = f"  GREW by {grown[name]:.0f} ms at this load" if name in grown else ""
        lines.append(f"  {name:28s}{ms:6.0f} ms  ({beside}){mark}")
    gone = [name for name in record.parts if name not in now]
    if gone:
        lines.append("  no longer a part: " + ", ".join(gone))
    return "\n".join(lines)


def _folder() -> Path:
    return Path(os.environ.get("POLYGLOTIC_START_RECORD") or RECORD_FOLDER)


def on_main(env: Mapping[str, str] = os.environ) -> bool:
    """Whether this is CI's run of a push to main: the one that records."""
    return (
        env.get("GITHUB_EVENT_NAME") == "push"
        and env.get("GITHUB_REF") == "refs/heads/main"
    )


def _account() -> str:
    return "".join(c for c in os.environ.get("USERNAME", "") if c.isalnum()) or "ci"


def save(
    parts: Mapping[str, float], window_ms: float, commit: str, kind: str = OFFSCREEN
) -> bool:
    """Keeps main's record of the `kind` of start: a file of this account's
    own, since each runner's account can read the other's files there but
    not write them. False, and nothing more, if it can't be written."""
    try:
        folder = _folder()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"start-{kind}-main-{_account()}.json").write_text(
            json.dumps(
                {
                    "commit": commit,
                    "window_ms": round(window_ms, 1),
                    "parts": {part: round(ms, 1) for part, ms in parts.items()},
                },
                indent=1,
            ),
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def keep_in_history(row: Mapping[str, object], kind: str) -> bool:
    """Adds one of main's runs of the `kind` of start to this account's
    history of it: `row` as a line, the last `HISTORY_ROWS` kept. False, and
    nothing more, if it can't be written."""
    try:
        folder = _folder()
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / f"start-{kind}-history-{_account()}.jsonl"
        lines = file.read_text(encoding="utf-8").splitlines() if file.exists() else []
        lines.append(json.dumps(dict(row)))
        file.write_text("\n".join(lines[-HISTORY_ROWS:]) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError):
        return False
    return True


def history(kind: str) -> list[dict[str, object]]:
    """Main's runs of the `kind` of start kept on this PC, every account's,
    oldest first by when each says it was taken (`at`); none if there are
    none or they can't be read."""
    rows: list[dict[str, object]] = []
    try:
        for file in _folder().glob(f"start-{kind}-history-*.jsonl"):
            for line in file.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    except (OSError, ValueError):
        return []
    return sorted(rows, key=lambda row: str(row.get("at", "")))


def load(kind: str = OFFSCREEN) -> Record | None:
    """Main's last record of the `kind` of start on this PC - the newest of
    the accounts' files - or None: none yet, or it can't be read."""
    try:
        files = sorted(
            _folder().glob(f"start-{kind}-main-*.json"),
            key=lambda file: file.stat().st_mtime,
        )
        if not files:
            return None
        found = json.loads(files[-1].read_text(encoding="utf-8"))
        return Record(
            str(found["commit"]),
            float(found["window_ms"]),
            {str(part): float(ms) for part, ms in found["parts"].items()},
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
