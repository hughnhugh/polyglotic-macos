"""Named spans: how long the interface spent on what, by name.

    with spans.span("caption_window.paint"):
        ...

Off by default, when a span costs one check (about 0.1 microseconds);
the UI lab and the budget runs turn recording on (`record_spans`), and
`TIMINGS` keeps each span's durations in memory until written as JSON
(`Timings.write`) - for a lab run, not for normal use, where nothing
would read them.

**Names only, never content:** a name is a constant from the code -
lower-case letters, digits, `_` and `.` (`caption_window.paint`), checked
the first time it's seen - so caption text or words can't become one.
"""

import json
import re
import statistics
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any

NAME = re.compile(r"[a-z][a-z0-9_.]{0,63}")
"""What a span's name may be: a constant, never text from a caption."""


def checked_name(name: str) -> str:
    """`name`, if it's a span name; ValueError if it isn't."""
    if not NAME.fullmatch(name):
        raise ValueError("a span name is lower-case letters, digits, _ and .")
    return name


class Timings:
    """Durations by span name, in milliseconds, kept in memory."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self.clock = clock
        self._samples: dict[str, list[float]] = {}

    def record(self, name: str, ms: float) -> None:
        samples = self._samples.get(name)
        if samples is None:
            samples = self._samples[checked_name(name)] = []
        samples.append(ms)

    def samples(self, name: str) -> list[float]:
        return list(self._samples.get(name, ()))

    def clear(self) -> None:
        self._samples.clear()

    def summary(self) -> dict[str, dict[str, float]]:
        """Per span: how many, the median, the 90th percentile and the most."""
        return {
            name: summarised(samples) for name, samples in sorted(self._samples.items())
        }

    def write(self, path: Path, **extra: Any) -> None:
        """The summary as JSON, with `extra` fields (names and numbers only)."""
        path.write_text(
            json.dumps({**extra, "spans": self.summary()}, indent=1), encoding="utf-8"
        )


def summarised(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "median_ms": round(statistics.median(ordered), 3),
        "p90_ms": round(ordered[int(0.9 * (len(ordered) - 1))], 3),
        "max_ms": round(ordered[-1], 3),
    }


TIMINGS = Timings()
"""Where spans are recorded while recording is on."""

_recording = False
_OFF = nullcontext()


def record_spans(on: bool) -> None:
    """Turns recording on (the lab, a budget run) or off (normal use)."""
    global _recording
    _recording = on


def recording() -> bool:
    return _recording


def span(name: str) -> "nullcontext[None] | _Span":
    """Times the block as `name` while recording; does nothing otherwise."""
    if not _recording:
        return _OFF
    return _Span(name)


class _Span:
    __slots__ = ("name", "start")

    def __init__(self, name: str) -> None:
        self.name = name
        self.start = 0.0

    def __enter__(self) -> None:
        self.start = TIMINGS.clock()

    def __exit__(self, *exc: object) -> None:
        TIMINGS.record(self.name, (TIMINGS.clock() - self.start) * 1000)


@contextmanager
def recorded() -> Iterator[Timings]:
    """Recording on for the block, into a cleared `TIMINGS` (tests, the lab)."""
    was = _recording
    TIMINGS.clear()
    record_spans(True)
    try:
        yield TIMINGS
    finally:
        record_spans(was)
