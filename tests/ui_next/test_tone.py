"""Contrast and vibrance's arithmetic (`views.tone`; polyglotic-hq 481): the
contrast slider's ink and ratios, the floor, and vibrance's chroma in
OKLCH - 0 today's look on both. Plain Python, no Qt."""

import math

import pytest

from polyglotic_desktop.ui_next.views.presets import (
    LARGE_TEXT,
    PRESETS,
    VIDEOS,
    ColourPreset,
    _mix,
    contrast,
)
from polyglotic_desktop.ui_next.views.tone import (
    FLOOR,
    MUTE,
    SOFTEST,
    THICKNESS,
    THICKNESSES,
    _oklab,
    chroma,
    floor_alpha,
    floored,
    ratio,
    reading_weight,
    strength,
    vibrant,
)

ALPHAS = (1.0, 0.85, 0.82, 0.72, 0.6, 0.36)
"""Today's inks: the newest caption, a live one, an older caption's
translation and what was said, Quick preview's line (and the quiet view's),
the quiet view's older ones."""


# -- contrast --------------------------------------------------------------------


@pytest.mark.parametrize("alpha", ALPHAS)
def test_contrast_0_is_todays_ink(alpha: float) -> None:
    assert strength(alpha, 0) == alpha


@pytest.mark.parametrize("alpha", ALPHAS)
def test_crisp_is_full_ink_and_soft_is_quick_previews_faintness(alpha: float) -> None:
    assert strength(alpha, 100) == 1.0
    assert strength(alpha, -100) == pytest.approx(alpha * SOFTEST)
    inks = [strength(alpha, c) for c in range(-100, 101, 5)]
    assert inks == sorted(inks)  # never back the other way


def test_the_softest_is_quick_previews_line() -> None:
    assert strength(1.0, -100) == pytest.approx(SOFTEST) == pytest.approx(0.6)


def test_a_ratio_comes_down_to_the_floor_on_the_soft_side_only() -> None:
    assert ratio(5.0, 0) == ratio(5.0, 100) == 5.0
    assert ratio(5.0, -100) == pytest.approx(FLOOR)
    assert FLOOR < ratio(5.0, -50) < 5.0
    assert ratio(3.0, -100) == 3.0  # already under the floor: left


def test_the_floor_is_over_wcags_large_text() -> None:
    """481's recommendation: the faintest Quick preview line the user has
    seen and liked (477: 3.7:1), over WCAG 2.2's 3:1 for large text."""
    assert FLOOR == 3.7 > LARGE_TEXT


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_the_floor_ink_reaches_the_floor_on_every_presets_panel(
    preset: ColourPreset,
) -> None:
    """The least ink that reads: the floor on the panel drawn solid, 3:1
    seen through it over a light or a black video - and a step less
    doesn't, on one of them."""
    backs = [(preset.background, FLOOR)]
    if preset.opacity < 1.0:
        backs += [
            (_mix(video, preset.background, preset.opacity), LARGE_TEXT)
            for video in VIDEOS
        ]

    def reads(colour: str, alpha: float) -> bool:
        return all(
            contrast(_mix(under, colour, alpha), under) >= needs
            for under, needs in backs
        )

    for colour in (preset.original, preset.translation):
        alpha = floor_alpha(colour, preset.background, preset.opacity)
        assert 0.0 < alpha < 1.0
        assert reads(colour, alpha) and not reads(colour, alpha - 0.01)


def test_the_floor_never_takes_ink_past_todays() -> None:
    """A look already under the floor (a custom grey on a grey panel) stays
    as it was: the slider never makes it stronger by going soft."""
    assert floor_alpha("#777777", "#666666") == 1.0
    assert floored(0.4, 0.7, "#777777", "#666666", 1.0) == 0.7
    assert floored(0.6, 1.0, "#ffffff", "#0a0c10", 1.0) == 0.6  # reads: left


# -- vibrance --------------------------------------------------------------------

GREYS = ("#ffffff", "#e6e6e6", "#9a9a9a", "#808080", "#1a1a1a", "#000000")
DULL, VIVID = "#acbf60", "#ff5252"
"""Word links' olive, and their red."""


@pytest.mark.parametrize("colour", ("#ffd76e", "#6fc3ff", "#7a3e00", "#acbf60"))
def test_vibrance_0_is_the_colour_itself(colour: str) -> None:
    assert vibrant(colour, 0) == colour
    assert vibrant(colour.upper(), 0) == colour


@pytest.mark.parametrize("grey", GREYS)
@pytest.mark.parametrize("vibrance", (-100, -40, 40, 100))
def test_greys_stay_grey(grey: str, vibrance: int) -> None:
    found = vibrant(grey, vibrance)
    assert chroma(found) < 0.01
    assert abs(_oklab(found)[0] - _oklab(grey)[0]) < 0.01


def test_vivid_boosts_the_dull_colours_more_than_the_vivid_ones() -> None:
    dull = chroma(vibrant(DULL, 100)) / chroma(DULL)
    vivid = chroma(vibrant(VIVID, 100)) / chroma(VIVID)
    assert dull > 1.3 and vivid < 1.2 and dull > vivid + 0.2


@pytest.mark.parametrize("colour", ("#ffd76e", "#6fc3ff", "#7a3e00", "#acbf60"))
def test_muted_keeps_the_rest_of_the_chroma_lightness_and_hue(colour: str) -> None:
    muted = vibrant(colour, -100)
    assert chroma(muted) == pytest.approx(chroma(colour) * (1 - MUTE), abs=0.004)
    (l1, a1, b1), (l2, a2, b2) = _oklab(colour), _oklab(muted)
    assert l2 == pytest.approx(l1, abs=0.005)
    hue = math.degrees(math.atan2(b2, a2) - math.atan2(b1, a1))
    assert abs((hue + 180) % 360 - 180) < 2


@pytest.mark.parametrize("vibrance", range(-100, 101, 25))
@pytest.mark.parametrize("colour", ("#ffd76e", "#6fc3ff", "#ff9f43", "#ffe600"))
def test_every_colour_it_gives_is_a_colour(colour: str, vibrance: int) -> None:
    found = vibrant(colour, vibrance)
    assert len(found) == 7 and found.startswith("#")
    int(found[1:], 16)  # hex digits
    if vibrance >= 0:  # never less vivid going vivid, nor more going muted
        assert chroma(found) >= chroma(colour) - 0.003
    else:
        assert chroma(found) <= chroma(colour) + 0.003


# -- thickness -------------------------------------------------------------------


def test_thickness_is_a_weight_medium_today_and_readings_a_step_above() -> None:
    assert THICKNESSES == (300, 400, 500, 600, 700) and THICKNESS == 500
    assert [reading_weight(w) for w in THICKNESSES] == [400, 500, 600, 700, 700]
    assert reading_weight(THICKNESS) == 600  # today's DemiBold pinyin
    assert reading_weight(450) == 600  # not a step: as today's
