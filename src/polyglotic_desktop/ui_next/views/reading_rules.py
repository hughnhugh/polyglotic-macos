"""585's reading constraints for a complete candidate layer. No files or windows."""

from collections.abc import Mapping
from itertools import pairwise
from math import ceil
from typing import cast

from polyglotic_desktop.core.listening.preset_reading import (
    OFFERED,
    PRESETS,
    VIDEO_FADE,
    choice_value,
)
from polyglotic_desktop.core.listening.timing import default_caption_mode
from polyglotic_desktop.core.shared.tunables import Tunable, Value, tunable
from polyglotic_desktop.ui_next.views import cards, dwell
from polyglotic_desktop.ui_next.views.card_window_defaults import CARD_READ_SEC

LAG = tunable(
    "dwell.reference_lag",
    2.2,
    "seconds",
    (0, 10),
    source="585 Video median translation lag",
)
NEED = tunable(
    "dwell.reference_need",
    1.8,
    "seconds",
    (0.1, 10),
    source="585 Video translation reading need",
)
INTERVAL = tunable(
    "dwell.reference_interval",
    3.1,
    "seconds",
    (0.1, 15),
    source="585 Video interval between cards",
)
HOLD_LIMITS = (
    (dwell.HOLD_VIDEO_SEC, 2),
    (dwell.HOLD_CONVERSATION, 1),
    (dwell.HOLD_EVERYDAY, 4),
    (dwell.HOLD_LEARNING, 8),
)  # constant: 585 rule 5 budgets in seconds


def reading_rule(
    values: Mapping[str, Value], updates: Mapping[str, Value]
) -> str | None:
    def get[T: Value](item: Tunable[T]) -> T:
        return cast(T, values[item.name])

    if get(dwell.READ_LEAST_SEC) > get(dwell.READ_MOST_SEC):
        return "R1: dwell.read_least must not exceed dwell.read_most"
    # All four reading paces have strictly positive ranges.
    scales, ink = get(cards.DEPTH_SCALES), get(cards.DEPTH_INK)
    required = 1 + ceil((get(LAG) + get(NEED)) / get(INTERVAL))
    if len(scales) < required:
        return f"R2: Video needs at least {required} readable cards for a translation"
    if len(ink) != len(scales) or any(
        steps[0] != 1 or any(back >= front for front, back in pairwise(steps))
        for steps in (scales, ink)
    ):
        return "R3: depth scales and ink need matching, descending steps from full size and ink"
    if get(VIDEO_FADE) < get(dwell.AFTER_LAST_WORD_SEC) + get(dwell.READ_LEAST_SEC):
        return "R4: Video fades before after_last_word plus read_least"
    for hold, budget in HOLD_LIMITS:
        if get(hold) > budget:
            return f"R5: {hold.name} exceeds its {budget} second hold budget"
    if get(CARD_READ_SEC) < get(dwell.READ_LEAST_SEC):
        return "R6: caption_window.card_read must cover dwell.read_least"
    everyday_mode, everyday_path = PRESETS["everyday"]
    for preset, (mode, path) in PRESETS.items():
        timing = get(mode)
        display = get(path)
        if timing == "inherit":
            timing = get(everyday_mode)
        if timing == "inherit":
            timing = str(
                choice_value("caption_mode_chosen", default_caption_mode().value)
            )
        if display == "inherit":
            display = get(everyday_path)
        if timing not in OFFERED[preset] or (
            display == "acquisition" and preset == "video"
        ):
            return f"R7: {preset} does not offer {timing} with {display} display"
    if get(dwell.TRANSLATION_AWAITED_SEC) < get(LAG):
        return "R8: dwell.translation_awaited must cover dwell.reference_lag"
    return None
