"""The reference step: a fixed piece of interface work the lab times just
before each gated state, so a pull request's timings are compared with
main's at like load (polyglotic-hq 381, decision 0169).

The gated actions are timed in wall time on a PC the CI runners and every
agent's runs share. On a busy PC the same code runs slower - Settings'
section switch at 8-10 ms on pull requests against main's calm 5.3 ms
(polyglotic-hq 367), 1.5-1.9x, over decision 0136's `SLOWER` with nothing
changed. The step is the same kind of work as the actions it stands beside -
one of two panels of wrapped labels hidden, the other shown, laid out and
painted, with everything it queues - and its code never changes with a pull
request, so it slows as they do when the PC is busy, its clock lower or its
cores shared, and not when the code under test gets slower.

Main keeps each gated state's step beside its timings; a pull request's
state is compared with main's scaled by its step now over main's then
(`timing_record.Timing.scaled`).
"""

import gc
import statistics
import time

from PySide6.QtCore import QEvent, QEventLoop
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

NAME = "reference_step"
"""The step's name in main's record, beside each state's actions."""

RUNS = 12
"""Switches timed; their median is the step's time (a switch is 1.5-2.5 ms
on a calm PC, 2026-11-16)."""

LABELS = 24
"""Labels in each panel: a warm Settings section switch's kind of work."""

TEXT = (
    "这个游戏的画面很漂亮。 This game looks beautiful, 頑張って。"
    " A caption wraps onto a second line at this width."
)


def _pump(app: QApplication) -> None:
    """As `Lab.pump`: everything queued on the interface thread."""
    for _ in range(2):
        app.sendPostedEvents()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def time_step(app: QApplication) -> float:
    """The step's time now, in milliseconds: the median of `RUNS` switches
    between two panels of `LABELS` wrapped labels, each shown once first."""
    window = QWidget()
    layout = QVBoxLayout(window)
    panels = []
    for _ in range(2):
        panel = QWidget(window)
        column = QVBoxLayout(panel)
        for n in range(LABELS):
            label = QLabel(f"{n} {TEXT}", panel)
            label.setWordWrap(True)
            column.addWidget(label)
        layout.addWidget(panel)
        panels.append(panel)
    window.resize(420, 900)
    window.show()
    samples = []
    collecting = gc.isenabled()
    gc.disable()  # as `Lab.time`: a collection is the process's
    try:
        for n in range(2 + RUNS):  # both panels shown once: not timed
            start = time.perf_counter()
            panels[n % 2].setVisible(True)
            panels[1 - n % 2].setVisible(False)
            _pump(app)
            if n >= 2:
                samples.append((time.perf_counter() - start) * 1000)
    finally:
        if collecting:
            gc.enable()
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return statistics.median(samples)
