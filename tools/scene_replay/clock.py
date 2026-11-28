"""The patched clock: one made-up time for everything the display reads.

A caption window reads the time in three ways: its own `clock`, the `time`
module (`time.monotonic()` in the tick and the fades) and Qt's timers (the
tick itself, the reading holds, the pacing waits). The replay owns all
three, so a run is the same twice and a second of captions takes as long as
its frames take to work out.

- `Hands.now` is the time. `Hands()` is the window's `clock`.
- `patched()` swaps `QTimer.start`, `stop`, `isActive`, `remainingTime` and
  `singleShot` for ones that keep their appointments here, and gives the
  display's modules a `time` whose clocks read `now`. No real timer runs
  while it is in force.
- `advance(to)` moves the time on and rings every timer that falls due,
  in order, as the event loop would.

Only Python's calls are patched: a timer Qt starts for itself (a tooltip's
delay, a scroll bar's repeat) is not seen. None of those draws a caption.
"""

import importlib
import time as real_time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import shiboken6
from PySide6.QtCore import QObject, QTimer

CLOCKED = (
    "polyglotic_desktop.ui_next.caption_window",
    "polyglotic_desktop.ui_next.caption_windows",
    "polyglotic_desktop.ui_next.joined_window",
    "polyglotic_desktop.ui_next.transcript_window",
    "polyglotic_desktop.ui_next.video",
    "polyglotic_desktop.ui_next.views.captions",
)
"""The display modules that may read the `time` module. One that does not
import it is left alone."""

START = 100.0
"""Where the made-up time starts, in seconds: not zero, so a "never" of 0
in the product is in the past, as it is on a real PC."""

MOST_RINGS = 10_000
"""Timers rung in one `advance` before the replay gives up: a timer that
restarts itself with no delay would otherwise never let the frame end."""


class Hands:
    """The made-up time, and the timers waiting on it."""

    def __init__(self) -> None:
        self.now = START
        self._due: dict[QTimer, float] = {}
        self._once: list[tuple[float, int, QObject | None, Callable[[], Any]]] = []
        self._order = 0
        self.rung = 0

    def __call__(self) -> float:
        return self.now

    # --- what the patched QTimer calls ---

    def start(self, timer: QTimer, *args: Any) -> None:
        if args:
            timer.setInterval(int(args[0]))
        self._due[timer] = self.now + timer.interval() / 1000

    def stop(self, timer: QTimer) -> None:
        self._due.pop(timer, None)

    def active(self, timer: QTimer) -> bool:
        return timer in self._due

    def remaining(self, timer: QTimer) -> int:
        due = self._due.get(timer)
        return -1 if due is None else max(0, round((due - self.now) * 1000))

    def single_shot(self, msec: int, *args: Any) -> None:
        receiver = args[0] if len(args) > 1 and isinstance(args[0], QObject) else None
        self._order += 1
        self._once.append((self.now + msec / 1000, self._order, receiver, args[-1]))

    # --- the replay's side ---

    def advance(self, to: float) -> None:
        """Move the time to `to`, ringing each timer due on the way at its
        own moment."""
        rings = 0
        while True:
            timers = [
                (due, 0, timer)
                for timer, due in self._due.items()
                if due <= to + 1e-9 and shiboken6.isValid(timer)
            ]
            once = [(due, order) for due, order, _, _ in self._once if due <= to + 1e-9]
            if not timers and not once:
                break
            rings += 1
            if rings > MOST_RINGS:
                raise RuntimeError("a timer keeps restarting itself with no delay")
            first_timer = min(timers, key=lambda item: item[0], default=None)
            first_once = min(once, default=None)
            if first_once is not None and (
                first_timer is None or first_once[0] <= first_timer[0]
            ):
                index = next(
                    i for i, item in enumerate(self._once) if item[1] == first_once[1]
                )
                due, _, receiver, call = self._once.pop(index)
                self.now = max(self.now, due)
                if receiver is None or shiboken6.isValid(receiver):
                    call()
            else:
                assert first_timer is not None
                due, _, timer = first_timer
                self.now = max(self.now, due)
                if timer.isSingleShot():
                    del self._due[timer]
                else:
                    self._due[timer] = due + max(timer.interval(), 1) / 1000
                timer.timeout.emit()
            self.rung += 1
        self._due = {t: d for t, d in self._due.items() if shiboken6.isValid(t)}
        self.now = max(self.now, to)

    @contextmanager
    def patched(self) -> Iterator["Hands"]:
        real = {
            name: getattr(QTimer, name)
            for name in ("start", "stop", "isActive", "remainingTime", "singleShot")
        }
        hands = self
        QTimer.start = lambda timer, *a: hands.start(timer, *a)  # type: ignore[method-assign]
        QTimer.stop = lambda timer: hands.stop(timer)  # type: ignore[method-assign]
        QTimer.isActive = lambda timer: hands.active(timer)  # type: ignore[method-assign]
        QTimer.remainingTime = lambda timer: hands.remaining(timer)  # type: ignore[method-assign]
        QTimer.singleShot = staticmethod(  # type: ignore[method-assign]
            lambda msec, *a: hands.single_shot(msec, *a)
        )
        shim = SimpleNamespace(
            **{
                name: getattr(real_time, name)
                for name in dir(real_time)
                if not name.startswith("_")
            }
        )
        shim.monotonic = shim.perf_counter = lambda: hands.now
        swapped: list[tuple[Any, Any]] = []
        for name in CLOCKED:
            try:
                module: Any = importlib.import_module(name)
            except ImportError:  # an older tree without this module
                continue
            if getattr(module, "time", None) is real_time:
                swapped.append((module, module.time))
                module.time = shim
            if getattr(module, "perf_counter", None) is real_time.perf_counter:
                swapped.append((module, None))
                module.perf_counter = shim.perf_counter
        try:
            yield self
        finally:
            for name, method in real.items():
                setattr(QTimer, name, method)
            for module, was in swapped:
                if was is None:
                    module.perf_counter = real_time.perf_counter
                else:
                    module.time = was
            self._due.clear()
            self._once.clear()
