"""The interface-thread watchdog: logs any stretch of interface-thread work
over the slot budget (50 ms; DECISIONS.md #53, "nothing on the interface
thread over 50 ms, ever") - by name and duration only.

How it sees: Qt's event dispatcher says when the interface thread wakes
(`awake`) and when it's about to wait again (`aboutToBlock`); the time
between is one stretch of work - the slots and events it handled. A
helper thread, woken by `awake`, looks at the interface thread's Python
stack once the stretch has run half the budget (counted from the
stretch's start), and names where it is: the innermost frame of the app's
own code, as `file.py:function` - never locals, arguments or any text (so
never caption text or words). It looks again every half budget while
the work goes on, and the work is named by the place it saw most often:
a look that lands as the work ends, before the thread gets back to
answering, sees the code it went back to, and must not rename it
(polyglotic-hq 344). When the stretch ends the warning is logged, e.g.

    interface thread busy 312 ms in overlay.py:_render (from app.py:_retheme)

**A loop that isn't Qt's** (polyglotic-hq 302): Windows' own Save dialog,
a window being moved or resized, a menu of Windows' own - each runs its
own message loop on the interface thread, which still runs Qt's timers
and posted events, so the app goes on answering; but Qt's dispatcher says
nothing until it ends, so it looked like one long stretch ("busy 10530
ms in words_page.py:_export_deck" in a tester's log was, most likely, the
Save dialog open while they chose where to save: the export itself runs
on a thread of its own).
So once a stretch passes half the budget, the helper asks the interface
thread to answer (a queued call) every `ASK_EVERY` seconds, one question
at a time. Work is what keeps it from answering: the longest time between
answers (or from the stretch's start, or to its end) is the time
reported. A stretch spent answering is logged at INFO, so a report still
says a dialog was open or a window was moved:

    interface thread answered in a loop outside Qt's for 10530 ms in
    words_page.py:_export_deck (a dialog, a menu or a window being moved)

and one with work in it says both - Windows' Save dialog kept the thread
from answering for 424-488 ms of its own work, open 3 or 8 s (302,
measured on a private desktop, 2026-11-13):

    interface thread busy 448 ms in words_page.py:_export_deck, of 3051 ms
    in a loop outside Qt's (a dialog, a menu or a window being moved)

Cheap enough to stay on in normal use: two Python calls per pass of the
event loop on the interface thread (a few microseconds), and a helper
thread that sleeps while the interface is idle and through any stretch
under half the budget, and asks only during a longer one.
`main` starts it.
"""

import contextlib
import logging
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from types import FrameType

from PySide6.QtCore import (
    QAbstractEventDispatcher,
    QObject,
    Qt,
    QThread,
    Signal,
    Slot,
)

from polyglotic_desktop.perf import budgets

log = logging.getLogger(__name__)

PACKAGE = "polyglotic_desktop"
"""The app's own code: frames from its files are named; others are skipped."""

ASK_EVERY = 0.01
"""Seconds between the helper's questions while a long stretch answers
them: the error in a measured stretch of work, at most."""

DIDNT_CATCH = "a stretch the watchdog didn't catch"
"""Where, for work the helper never looked at while it ran."""


class Watchdog(QObject):
    """Watches the thread it's made on - the interface thread."""

    _ask = Signal(int)
    """From the helper: answer, if you can, for this stretch."""

    def __init__(
        self,
        threshold_ms: float = budgets.SLOT.ms,
        report: Callable[[float, str], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """`report(ms, where)` is called for each slow stretch (after the
        warning is logged)."""
        super().__init__(parent)
        self.threshold_ms = threshold_ms
        self.report = report
        self.slow = 0  # stretches over the threshold so far
        self.answering = 0  # stretches spent answering, in a loop outside Qt's
        self._thread_id = threading.get_ident()
        self._busy_since: float | None = None
        self._stretch = 0  # counts stretches, so the helper knows which it saw
        self._caught: tuple[int, float, str] = (0, 0.0, "")
        """A stretch, the spell of work in it the helper looked at (the
        spell's start: `_answered_at` then), and where it was seen most often
        in that spell (`_watch`)."""
        self._answered_at = 0.0  # this stretch's start, then its last answer
        self._answers = 0  # in this stretch
        self._worst: tuple[float, str] = (0.0, "")  # its longest work, and where
        self._asked = False  # a question is waiting for its answer
        self._woken = threading.Event()
        self._stopped = False
        self._helper: threading.Thread | None = None
        self._dispatcher: QAbstractEventDispatcher | None = None
        self._ask.connect(self._answer, Qt.ConnectionType.QueuedConnection)

    def start(self) -> None:
        dispatcher = QAbstractEventDispatcher.instance(QThread.currentThread())
        if dispatcher is None or self._helper is not None:
            return
        self._dispatcher = dispatcher
        dispatcher.awake.connect(self._awake)
        dispatcher.aboutToBlock.connect(self._about_to_block)
        self._helper = threading.Thread(
            target=self._watch, name="interface-watchdog", daemon=True
        )
        self._helper.start()

    def stop(self) -> None:
        self._stopped = True
        self._woken.set()
        if self._dispatcher is not None:
            self._dispatcher.awake.disconnect(self._awake)
            self._dispatcher.aboutToBlock.disconnect(self._about_to_block)
            self._dispatcher = None
        if self._helper is not None:
            self._helper.join(timeout=1)
            self._helper = None

    # -- on the interface thread --------------------------------------------------------

    @Slot()
    def _awake(self) -> None:
        if self._busy_since is None:
            self._stretch += 1
            now = time.perf_counter()
            self._busy_since = self._answered_at = now
            self._answers = 0
            self._worst = (0.0, "")
            self._woken.set()

    @Slot(int)
    def _answer(self, stretch: int) -> None:
        """The helper's question, answered: the thread got to it. In a loop
        outside Qt's this comes while the stretch goes on; the work since
        the last answer is measured."""
        self._asked = False
        if self._busy_since is None or stretch != self._stretch:
            return  # asked during a stretch that has ended
        now = time.perf_counter()
        self._worked(now)
        self._answered_at = now
        self._answers += 1

    @Slot()
    def _about_to_block(self) -> None:
        since = self._busy_since
        if since is None:
            return
        self._busy_since = None
        now = time.perf_counter()
        total_ms = (now - since) * 1000
        if total_ms <= self.threshold_ms:
            return
        self._worked(now)
        ms, where = self._worst
        if ms <= self.threshold_ms:
            self.answering += 1
            log.info(
                "interface thread answered in a loop outside Qt's for %d ms in %s"
                " (a dialog, a menu or a window being moved)",
                round(total_ms),
                self._where(),
            )
            return
        self.slow += 1
        if self._answers and total_ms - ms > self.threshold_ms:
            log.warning(
                "interface thread busy %d ms in %s, of %d ms in a loop outside"
                " Qt's (a dialog, a menu or a window being moved)",
                round(ms),
                where,
                round(total_ms),
            )
        else:
            log.warning("interface thread busy %d ms in %s", round(ms), where)
        if self.report is not None:
            self.report(ms, where)

    def _worked(self, now: float) -> None:
        """The work since the stretch began or last answered ends at `now`:
        kept if it's the stretch's longest so far, named by where the helper
        saw it during this spell - never by a look in another spell."""
        ms = (now - self._answered_at) * 1000
        if ms > self._worst[0]:
            stretch, spell, where = self._caught
            if stretch != self._stretch or spell != self._answered_at:
                where = DIDNT_CATCH
            self._worst = (ms, where)

    def _where(self) -> str:
        """Where the helper last saw this stretch, in any spell of it."""
        stretch, _, where = self._caught
        if stretch != self._stretch:
            return DIDNT_CATCH
        return where

    # -- on the helper thread -----------------------------------------------------------

    def _watch(self) -> None:
        half = self.threshold_ms / 2000  # seconds
        while not self._stopped:
            self._woken.wait()
            self._woken.clear()
            if self._stopped:
                return
            stretch, since = self._stretch, self._busy_since
            if since is None:
                continue
            # half the budget counted from the stretch's start - not from
            # when this thread got round to it, which may be well after (a
            # short stretch just before left it behind: "a stretch the
            # watchdog didn't catch"); asking only from then, a thread that
            # answers at once never shows a spell of work over the budget
            time.sleep(max(0.0, since + half - time.perf_counter()))
            looked = since
            seen: dict[str, int] = {}  # this spell's looks, by where
            seen_in = since  # the spell they're of: its start
            while self._still(stretch):
                now = time.perf_counter()
                spell = self._answered_at
                if now - max(spell, looked) >= half:
                    looked = now  # unanswered this long: where is it?
                    if spell != seen_in:
                        seen, seen_in = {}, spell
                    place = where_in(self._thread_id)
                    seen[place] = seen.get(place, 0) + 1
                    # the place seen most often, the first on a tie: a look
                    # that lands as the work ends, before the thread answers,
                    # sees the code it went back to (polyglotic-hq 344:
                    # "run_loop", "loop_outside_qt" named for the work)
                    most = max(seen, key=seen.__getitem__)
                    self._caught = (stretch, spell, most)
                if not self._asked:
                    self._asked = True
                    with contextlib.suppress(RuntimeError):  # deleted, quitting
                        self._ask.emit(stretch)
                time.sleep(ASK_EVERY)

    def _still(self, stretch: int) -> bool:
        return (
            not self._stopped
            and self._busy_since is not None
            and self._stretch == stretch
        )


def where_in(thread_id: int) -> str:
    """Where `thread_id` is in the app's own code: the innermost frame, and
    the outermost if it's another (leaving out `main`, which runs the event
    loop) - `file.py:function` only."""
    frame: FrameType | None = sys._current_frames().get(thread_id)
    ours: list[str] = []
    while frame is not None:
        path = Path(frame.f_code.co_filename)
        if PACKAGE in path.parts:
            ours.append(f"{path.name}:{frame.f_code.co_name}")
        frame = frame.f_back
    if ours and ours[-1] == "main.py:main":
        ours.pop()
    if not ours:
        return "Qt or a library, outside the app's code"
    if len(ours) == 1 or ours[0] == ours[-1]:
        return ours[0]
    return f"{ours[0]} (from {ours[-1]})"
