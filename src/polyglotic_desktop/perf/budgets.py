"""The interface's budgets: how long an action may keep the interface
thread busy, in milliseconds (polyglotic-hq DECISIONS.md #53, from project
108's audit; agreed by the user 2026-11-06/07; tightened by project 243's
measurement of every operation, 2026-11-08 - PERFORMANCE.md there: the
stricter of what people perceive and about three times the typical time
measured on a loaded PC, so a budget never flakes on a busy runner) - and
how much memory an hour of captions may leave behind (`MEMORY_HOUR`,
polyglotic-hq 239, decision 0049).

One place for the numbers: the budget tests and the UI lab read them from
here. Changing one is the user's call (decision 0031).
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Budget:
    """At most `ms` milliseconds of interface-thread work for `what`."""

    name: str
    ms: float
    what: str


@dataclass(frozen=True, slots=True)
class MemoryBudget:
    """At most `mb` megabytes of the app's private memory gained over `what`."""

    name: str
    mb: float
    what: str


FRAME = Budget(
    "frame", 8.0, "one frame while resizing, moving or scrolling (120 fps-capable)"
)
NEW_CAPTION = Budget("new_caption", 4.0, "a new caption applied and drawn")
NEW_CAPTION_WITH_TRANSCRIPT = Budget(
    "new_caption_with_transcript",
    8.0,
    "a new caption applied and drawn with a transcript showing, at 1,000 lines",
)
CLICK = Budget("click", 30.0, "a click to its visible change")
LOOKUP_HOVER = Budget("lookup_hover", 30.0, "a lookup shown, after the hover delay")
LOOKUP_PINNED = Budget("lookup_pinned", 30.0, "a lookup pinned open by a click")
PAGE_SWITCH_COLD = Budget("page_switch_cold", 50.0, "a page shown for the first time")
PAGE_SWITCH_WARM = Budget("page_switch_warm", 8.0, "a page shown again")
DISPLAY_CHANGE = Budget(
    "display_change", 16.0, "a text size, language or display change"
)
THEME = Budget("theme", 100.0, "a theme or light / dark change")
START_FROM_SOURCE = Budget(
    "start_from_source", 400.0, "start to the window shown, from source"
)
START_PACKED = Budget(
    "start_packed",
    1000.0,
    "process launch to the window shown, packed (Python's start and the imports included)",
)
SLOT = Budget("slot", 50.0, "any one slot or event on the interface thread, ever")
IDLE_TIMER = Budget(
    "idle_timer",
    250.0,
    "the shortest periodic timer while nothing moves (a floor, not a ceiling)",
)

ALL = (
    FRAME,
    NEW_CAPTION,
    NEW_CAPTION_WITH_TRANSCRIPT,
    CLICK,
    LOOKUP_HOVER,
    LOOKUP_PINNED,
    PAGE_SWITCH_COLD,
    PAGE_SWITCH_WARM,
    DISPLAY_CHANGE,
    THEME,
    START_FROM_SOURCE,
    START_PACKED,
    SLOT,
    IDLE_TIMER,
)
BY_NAME = {budget.name: budget for budget in ALL}

MEMORY_HOUR = MemoryBudget(
    "memory_hour",
    3.0,
    "an hour of captions (two apps, both transcripts open, a lookup a minute)"
    " once the windows and transcripts are full",
)
"""Held by `tests/ui/test_memory_over_an_evening.py`, a synthetic evening
offscreen in about 9 seconds (decision 0049): measured 1.0 MB with the
layouts bounded, 33 MB when each surface kept 2,500 lines laid out."""
