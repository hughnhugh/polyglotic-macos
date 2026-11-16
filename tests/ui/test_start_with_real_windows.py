"""The start a learner sees, recorded: `main()` from source with real
windows on a private desktop, a learner of 30,000 words met on the real
CC-CEDICT, from `main()`'s call to the main window's first paint and on to
the first moment a click is answered (`tools/learner_start.py`,
polyglotic-hq 322, decision 0111).

The start gate beside it (`test_start_with_a_big_learner.py`) is offscreen,
and offscreen skips most of what this start is: Windows' fonts read (about
0.3 s), the first native window (about 0.1 s). With real windows the start
was 0.74-0.91 s at every release from 2026-11-08 on, against 0.29-0.37 s
offscreen, and nothing measured it.

**Recorded, not gated** - until it has held steady on main (decision 0111
says how that's judged): this test fails only if the start never reaches
its window. It prints each part beside main's last record on this PC
(`tools/start_record.py`), the grown ones marked, then main's last runs; on
a push to main it keeps the record and a row of history. A pull request
that grows a part says so and why.

Nothing reaches a screen: a desktop made with `CreateDesktop` is never
shown (`docs/real-windows.md`). On CI's runners - services, in session 0 -
the windows are made and painted but Windows never shows them; the fonts
and the native windows cost the same. The start is signed out, so nothing
is captured; its server is an address nothing answers at.

It needs the real CC-CEDICT (POLYGLOTIC_REAL_DICTIONARIES), as the gate
does; without it, it's skipped."""

import os
import statistics
import time
from pathlib import Path

import pytest
from tests.budget_judge import NOTES
from tests.ui.test_start_with_a_big_learner import REAL_DICTIONARIES, STARTS, WORDS
from tools.learner_start import made_up_learner, returning_learner, timed_start

from tools import busy_pc, start_record

LAST_RUNS = 20
"""Main's last runs printed beside this one: enough to see whether the
start holds steady (decision 0111)."""


def _numbers(rows: list[dict[str, object]], key: str) -> list[float]:
    return [float(v) for row in rows if isinstance(v := row.get(key), int | float)]


def history_line(rows: list[dict[str, object]]) -> str:
    """Main's last `LAST_RUNS` runs in a line: the window's and the whole
    start's median and range, and how many were on a calm PC."""
    last = rows[-LAST_RUNS:]
    windows = _numbers(last, "window_ms")
    wholes = _numbers(last, "answered_ms")
    if not windows:
        return "main's runs with real windows: none kept on this PC yet"
    calm = sum(
        1
        for busy in _numbers(last, "busy")
        if not busy_pc.saturated(busy, busy_pc.CALM)
    )
    said = (
        f"main's last {len(windows)} runs with real windows: window"
        f" {statistics.median(windows):.0f} ms"
        f" ({min(windows):.0f}-{max(windows):.0f})"
    )
    if wholes:
        said += (
            f", answering by {statistics.median(wholes):.0f} ms"
            f" ({min(wholes):.0f}-{max(wholes):.0f})"
        )
    return f"{said}; {calm} of them on a calm PC"


@pytest.mark.windows_only  # the app's own OS adapters, and Windows' desktops
def test_the_start_with_real_windows_is_recorded(tmp_path: Path) -> None:
    folder = os.environ.get(REAL_DICTIONARIES)
    if not folder:
        pytest.skip(f"the real CC-CEDICT isn't built here ({REAL_DICTIONARIES})")
    dictionaries = Path(folder)
    learning = tmp_path / "learning.sqlite"
    made_up_learner(dictionaries / "cedict.sqlite", WORDS, learning)

    calm = busy_pc.wait_for_calm()
    starts = [
        timed_start(
            returning_learner(tmp_path / f"start-{i}", learning),
            dictionaries,
            real_windows=True,
        )
        for i in range(1, STARTS + 1)
    ]

    window = statistics.median(start.window_ms for start in starts)
    answers = [start.answers_ms for start in starts if start.answers_ms is not None]
    read = [start.busy for start in starts if start.busy is not None]
    busy = statistics.median(read) if read else None
    parts = start_record.typical(
        [start_record.with_after(start.parts, start.answers_ms) for start in starts]
    )
    said = (
        f"with real windows: window {window:.0f} ms ("
        + ", ".join(f"{start.window_ms:.0f}" for start in starts)
        + ")"
    )
    if answers:
        said += f", answering {statistics.median(answers):.0f} ms after"
    said += f"; before it {busy_pc.describe(calm)}"
    if busy is not None:
        said += f"; during it the rest of the PC {busy:.0%} busy"
    print(said)
    NOTES.append(said)
    NOTES.append(
        start_record.table(
            parts,
            start_record.load(start_record.REAL_WINDOWS),
            "the start with real windows, to the first answered click",
        )
    )
    NOTES.append(history_line(start_record.history(start_record.REAL_WINDOWS)))
    if start_record.on_main():
        commit = os.environ.get("GITHUB_SHA", "")
        start_record.save(parts, window, commit, start_record.REAL_WINDOWS)
        start_record.keep_in_history(
            {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "commit": commit[:8],
                "window_ms": round(window, 1),
                "answered_ms": round(sum(parts.values()), 1) if answers else None,
                "busy": busy,
            },
            start_record.REAL_WINDOWS,
        )

    # recorded, not gated: only that every start reached its window, and
    # went on to answer
    assert all(start.window_ms > 0 for start in starts)
    assert len(answers) == len(starts), "a start painted but never answered"
