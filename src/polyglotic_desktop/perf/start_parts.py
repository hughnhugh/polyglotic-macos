"""The start's parts: where the time from `main()` to the window's first
paint goes, by name (polyglotic-hq 314).

    start_parts.begin()          # main() has begun
    ...
    start_parts.done("learner")  # this part ends here; the next begins

Each `done` records the time since the mark before it, so the parts add up
to the whole start with nothing left between them. `main` and the parts it
builds (`new_interface`, `Hub`) mark as they go; the timed start
(`tools/learner_start.py`) reads `parts()` at the first paint, and CI's
start test prints them beside main's last record (`tools/start_record.py`),
so a start that grew says which part grew.

Always on: a mark is one clock read, about a dozen in a start. Before
`begin` - a `Hub` built by a test or the UI lab - a mark does nothing.

**Names only, never content:** a part's name is a constant from the code,
checked like a span's (`spans.checked_name`).
"""

import time

from polyglotic_desktop.perf.spans import checked_name

_last: float | None = None
_parts: dict[str, float] = {}


def begin() -> None:
    """The start begins now: every part recorded before is forgotten."""
    global _last
    _parts.clear()
    _last = time.perf_counter()


def done(part: str) -> None:
    """`part` ends now and the next begins. A name marked twice adds up."""
    global _last
    if _last is None:
        return
    now = time.perf_counter()
    _parts[checked_name(part)] = _parts.get(part, 0.0) + (now - _last) * 1000
    _last = now


def end() -> None:
    """The window has painted: marks do nothing from here on."""
    global _last
    _last = None


def parts() -> dict[str, float]:
    """Each part's milliseconds so far, in the order they were first marked."""
    return dict(_parts)
