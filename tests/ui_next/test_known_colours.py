"""Learning load's colours as a colour-blind learner sees them
(polyglotic-hq 489): about 8 % of men can't tell red from green, so both
palettes keep their order and stay apart in the Machado, Oliveira and
Fernandes (2009) simulation of deuteranopia and protanopia, and in
greyscale. Distances are `colour_difference` (CIE76 in CIELAB: about 2.3
is just noticeable side by side)."""

from itertools import pairwise

import pytest
from tools.ui_lab.cvd import Sight, seen

from polyglotic_desktop.ui_next.views.known_colours import Palette, known_colour
from polyglotic_desktop.ui_next.views.presets import (
    PRESETS,
    colour_difference,
    luminance,
)

QUARTERS = (0.0, 0.25, 0.5, 0.75, 1.0)
DARK = [p for p in PRESETS if luminance(p.background) < 0.4]
LIGHT = [p for p in PRESETS if luminance(p.background) >= 0.4]


def shades(palette: Palette, panel: str, sight: Sight | None) -> list[str]:
    found = [known_colour(c, palette, panel) for c in QUARTERS]
    return found if sight is None else [seen(c, sight) for c in found]


def test_the_simulation_is_machados() -> None:
    """Spot checks of the matrices: white stays white, and a pure red and
    green - apart for most eyes - come close for a deuteranope."""
    for sight in Sight:
        assert seen("#ffffff", sight) == "#ffffff"
    normal = colour_difference("#e04040", "#40a040")
    deutan = colour_difference(
        seen("#e04040", Sight.DEUTERANOPIA), seen("#40a040", Sight.DEUTERANOPIA)
    )
    assert deutan < normal / 3


@pytest.mark.parametrize("palette", list(Palette))
@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
@pytest.mark.parametrize("sight", list(Sight))
def test_in_greyscale_and_both_simulations_the_order_holds(
    palette: Palette, preset: object, sight: Sight
) -> None:
    """Unknown to known, the lightness runs one way - away from the panel -
    for every sight: the ramp under the hue (`views.known_colours`)."""
    panel = preset.background  # type: ignore[attr-defined]
    light = [luminance(c) for c in shades(palette, panel, sight)]
    if luminance(panel) >= 0.4:
        assert light == sorted(light, reverse=True)
    else:
        assert light == sorted(light)
    assert len(set(light)) == len(light)


@pytest.mark.parametrize("palette", list(Palette))
@pytest.mark.parametrize("preset", DARK, ids=lambda p: p.key)
def test_on_dark_panels_the_ends_and_neighbours_stay_apart(
    palette: Palette, preset: object
) -> None:
    panel = preset.background  # type: ignore[attr-defined]
    for sight in Sight:
        seen_ = shades(palette, panel, sight)
        ends = colour_difference(seen_[0], seen_[-1])
        neighbours = min(colour_difference(a, b) for a, b in pairwise(seen_))
        assert ends >= 20, (sight, ends)
        assert neighbours >= 5, (sight, neighbours)
    # orange to blue is the one for red-green colour blindness: far apart
    if palette is Palette.ORANGE_BLUE:
        for sight in (Sight.DEUTERANOPIA, Sight.PROTANOPIA):
            seen_ = shades(palette, panel, sight)
            assert colour_difference(seen_[0], seen_[-1]) >= 60


@pytest.mark.parametrize("preset", LIGHT, ids=lambda p: p.key)
def test_on_paper_orange_to_blue_is_the_one_that_holds(preset: object) -> None:
    """On Paper's cream the ramp has less room (dark text only): red to
    green keeps its order (above) but a protanope sees its ends close; orange
    to blue stays far apart for both - the reason it's offered."""
    panel = preset.background  # type: ignore[attr-defined]
    for sight in (Sight.DEUTERANOPIA, Sight.PROTANOPIA):
        seen_ = shades(Palette.ORANGE_BLUE, panel, sight)
        assert colour_difference(seen_[0], seen_[-1]) >= 60
    grey = shades(Palette.RED_GREEN, panel, Sight.GREYSCALE)
    assert colour_difference(grey[0], grey[-1]) >= 18
