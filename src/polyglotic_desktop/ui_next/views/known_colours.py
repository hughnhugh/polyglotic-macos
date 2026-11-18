"""Learning load's colours: every word of a caption, and every square of
the map, in a colour by how well the learner knows it (polyglotic-hq 489,
decision 0226; `core.learning.known_chance`). Plain Python, no Qt.

- **Two palettes** (`Palette`): red to green, the user's ("every word has
  a colour ... red (or completely unknown) ... green (mastered word)"),
  and orange to blue for a learner who can't tell red from green - about
  8 % of men (deuteranopia and protanopia). Unknown is the warm end of
  each.
- **A lightness ramp under the hue**, so neither rests on hue alone: on a
  dark panel the less a word is known the darker it is (but readable),
  the better known the lighter, nearest the row's own white; on a light
  panel (Paper's cream) the other way round. Seen in greyscale, or by a
  colour-blind learner, a caption reads from faint (unknown) to full
  (known), and the colours stay in order and apart
  (`tests/ui_next/test_known_colours.py` checks it with the Machado,
  Oliveira and Fernandes 2009 simulation of both).
- **Readable**: each colour at least `AA_TEXT` (4.5:1) against its panel,
  as the load's stages were (`readable_on`); the vibrance slider (481)
  makes them more or less vivid, lightness kept. The contrast slider
  moves the rows' own ink, not these: like saved words' colours, they
  stay at 4.5:1 whatever it says.
- **Steps**: a chance is drawn at the nearest of `STEPS` + 1 colours -
  close enough to look continuous, few enough to keep a format each.
"""

import math
from functools import lru_cache

from polyglotic_desktop.ui_next.views.lab import Palette
from polyglotic_desktop.ui_next.views.presets import AA_TEXT, luminance, readable_on
from polyglotic_desktop.ui_next.views.tone import _in_gamut, vibrant

STEPS = 20
"""A chance is drawn at the nearest twentieth."""

LIGHT_PANEL = 0.4
"""A panel at least this light (`luminance`) takes the light ramp - as the
load's stages did (`caption_marks.LIGHT_PANEL`)."""

_Hue = tuple[float, float]  # OKLCH: chroma, hue (degrees)

HUES: dict[Palette, tuple[_Hue, _Hue, _Hue]] = {
    Palette.RED_GREEN: ((0.20, 28.0), (0.16, 75.0), (0.18, 148.0)),
    Palette.ORANGE_BLUE: ((0.16, 50.0), (0.03, 90.0), (0.13, 245.0)),
}
"""Each palette's chroma and hue at chance 0, 0.5 and 1; between them a
straight line in OKLab's (a, b)."""

LIGHTNESS = {
    (Palette.RED_GREEN, False): (57.0, 89.0),
    (Palette.ORANGE_BLUE, False): (57.0, 82.0),
    (Palette.RED_GREEN, True): (45.0, 25.0),
    (Palette.ORANGE_BLUE, True): (45.0, 25.0),
}
"""The ramp's lightness (CIELAB's L*, which greyscale shows) from chance 0
to 1, on a dark panel and on a light one: the unknown end readable on
every preset's panel (4.5:1 - Quiet's #1b1f26 needs L* 56, Paper's cream
47), the known end nearest the row's own ink - blue a little darker than
green, or it is too pale to read as blue beside white."""


def step(chance: float) -> int:
    """The step (0 - `STEPS`) a chance is drawn at."""
    return min(STEPS, max(0, round(chance * STEPS)))


def known_colour(chance: float, palette: Palette, panel: str, vibrance: int = 0) -> str:
    """The colour ("#rrggbb") of a word known at `chance`, on `panel`, with
    the vibrance slider at `vibrance`."""
    return _at(step(chance), palette, panel.lower(), vibrance)


@lru_cache(maxsize=512)
def _at(at: int, palette: Palette, panel: str, vibrance: int) -> str:
    light = luminance(panel) >= LIGHT_PANEL
    low, mid, high = HUES[palette]
    share = at / STEPS
    if share <= 0.5:
        x, y, t = low, mid, share / 0.5
    else:
        x, y, t = mid, high, (share - 0.5) / 0.5
    (ax, bx), (ay, by) = _ab(x), _ab(y)
    a, b = ax + (ay - ax) * t, bx + (by - bx) * t
    first, last = LIGHTNESS[palette, light]
    colour = _with_lightness(a, b, first + (last - first) * share)
    return readable_on(vibrant(colour, vibrance), panel, AA_TEXT)


def _ab(hue: _Hue) -> tuple[float, float]:
    chroma, degrees = hue
    return chroma * math.cos(math.radians(degrees)), chroma * math.sin(
        math.radians(degrees)
    )


def _with_lightness(a: float, b: float, target: float) -> str:
    """The colour of OKLab hue (a, b), inside sRGB, whose CIELAB L* is
    `target`: its OKLab lightness found by halving."""
    low, high = 0.0, 1.0
    found = "#000000"
    for _ in range(24):
        mid = (low + high) / 2
        found = _in_gamut(mid, a, b, 1.0)
        if _l_star(found) < target:
            low = mid
        else:
            high = mid
    return found


def _l_star(colour: str) -> float:
    y = luminance(colour)
    return 116 * y ** (1 / 3) - 16 if y > 0.008856 else 903.3 * y
