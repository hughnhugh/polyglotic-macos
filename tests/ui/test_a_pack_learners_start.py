"""A pack learner's start doesn't freeze (polyglotic-hq 436): Chinese learned
with Spanish beside it (a pack language, decision 0175), the app from source
in a process of its own, offscreen, on to a moment after Spanish's learning
data has opened (`tools/learner_start.py`). The app's own watchdog logs no
stretch of interface-thread work over `PACK_LEARNER_BUDGET_MS` from the
packs' opening to then, in a typical start (the median of `STARTS`).

What it guards: a pack's word split reads its data on a thread of its own
as the pack opens - simplemma's Spanish, about 0.4 s of Python. Spanish's
learning data, Words section and Learning card opened on the interface
thread at the same moment, and the two took turns at the interpreter:
every call from Qt into the app's code waited its turn, and the interface
froze 0.44-0.72 s on real windows (426). Here, before the fix: 122-331 ms
in each of 5 starts; after it, 55-80 ms (436, 2026-11-17). The learning
data now opens once the split has read (`PackDelivery.ready`) and is shown
in the event loop's next turn, and the read runs in short turns at the
interpreter, one pack at a time (`perf.turns`; decision 0207)."""

import statistics
from pathlib import Path

import pytest
from tests.packs_storage import tiny_pack
from tests.ui.test_check_install import sample_dictionaries
from tools.learner_start import made_up_learner, returning_learner, timed_start

PACK_LEARNER_BUDGET_MS = 100.0
"""The longest stretch allowed (436's brief): twice the slot budget
(`perf.budgets.SLOT`, 50 ms), which opening a language's learning data is
near by itself - its file in one turn, its Words section, Learning's card
and the windows' marks in the next."""

STARTS = 3
"""Starts judged, each a process of its own: their median, so one start
slowed by the rest of the PC doesn't fail it, and a freeze in every start
does."""


@pytest.mark.windows_only  # the app's own OS adapters
def test_a_pack_learners_start_doesnt_freeze_the_interface(tmp_path: Path) -> None:
    dictionaries = sample_dictionaries(tmp_path / "dictionaries")
    tiny_pack(dictionaries / "packs", language="es", dictionary="wiktes")
    learning = tmp_path / "learning.sqlite"
    made_up_learner(dictionaries / "cedict.sqlite", 5, learning)

    starts = [
        timed_start(
            returning_learner(tmp_path / f"data-{n}", learning, pack_language="es"),
            dictionaries,
            until_pack="es",
        )
        for n in range(STARTS)
    ]

    said = "; ".join(f"{s.pack_busy_ms} ms in {s.pack_busy_in or '-'}" for s in starts)
    longest = [s.pack_busy_ms for s in starts if s.pack_busy_ms is not None]
    assert len(longest) == STARTS, f"Spanish's learning data never opened: {said}"
    assert statistics.median(longest) <= PACK_LEARNER_BUDGET_MS, (
        f"the interface thread froze at a pack learner's start: {said}"
    )
