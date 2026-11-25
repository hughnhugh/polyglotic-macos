"""Motion and contrast of the caption list. The card stack's Glide sets its pace."""

from enum import StrEnum

from polyglotic_desktop.core.shared.tunables import tunable

OLDER_ALPHA = 0.85
OLDER_TRANSLATION_ALPHA = 0.85
"""Contrast retained by older captions, as a share of the newest line's
WCAG contrast ratio (0..1). This is deliberately contrast, not paint alpha:
`contrast_alpha` converts it for each look and text colour. The named setting
is a percentage in the Lab, with a supported 50--100 % range and an 85 %
default; original, translation and reading rows therefore keep the same light
fade on light and dark panels."""
GLIDE_SETTLE_SEC = 0.75
"""Seconds allowed for secondary translation gaps to follow the spring."""
ENTRY_GAP_PX = tunable(
    "arrivals.entry_gap_px",
    18.0,
    "px at text size 1.0",
    (0.0, 40.0),
    source="827 new rows close on the pair above",
)
"""How much further below its resting place a new caption starts, at text
size 1.0: the gap it closes as it rises to meet the line above."""
TOP_FADE_PAIRS = tunable(
    "lines.top_fade_pairs",
    1.0,
    "pairs",
    (0.0, 2.0),
    source="827 caption pairs fade as they cross the top edge",
)


def visible_ink(top: float, bottom: float, edge: float) -> float:
    """Opacity of a leaving pair over the configured distance from its foot."""
    band = (bottom - top) * TOP_FADE_PAIRS.value
    if band <= 0:
        return 1.0
    return max(0.0, min(1.0, (bottom - edge) / band))


class Arrival(StrEnum):
    """How a new caption arrives (the look's `arrival`)."""

    STEP = "step"
    STEP_AND_SLIDE = "step_and_slide"

    @property
    def slides(self) -> bool:
        return self is Arrival.STEP_AND_SLIDE


def effective(arrival: Arrival, reduced_motion: bool) -> Arrival:
    """The arrival to draw: with Windows' animation effects off, nothing
    slides - step and slide is the step."""
    return Arrival.STEP if reduced_motion else arrival


def older_alphas(
    high_contrast: bool,
    following: bool,
    older: tuple[float, float] = (OLDER_ALPHA, OLDER_TRANSLATION_ALPHA),
) -> tuple[float, float]:
    """How much of the newest caption's contrast older rows retain:
    B's step, which both arrivals take - `older`
    (the Lab can change it, `views.lab`) - none with Windows' high
    contrast, or while the learner has scrolled back (not `following` the
    newest)."""
    if high_contrast or not following:
        return 1.0, 1.0
    return older


def ease_out(t: float) -> float:
    """Cubic fade curve, clamped to its 0..1 domain."""
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) ** 3
