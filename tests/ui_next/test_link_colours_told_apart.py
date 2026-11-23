"""Every pair of word links' colours told apart (polyglotic-hq 446; the
user, 2026-11-17: "orange colour linkage is not that distinguishable from
the brown one especially the word colouring"): at least TOLD_APART in
CIEDE2000 on every colour preset's panel - drawn solid, and seen through
at its opacity over a light video and a black one - as a link's line
(its colour at 90 %) and as a word in its link's colour (`link_ink`,
moved to be readable: 431's rule)."""

from itertools import combinations

import pytest
from PySide6.QtGui import QColor

from polyglotic_desktop.ui_next.caption_layout import Ink, link_ink
from polyglotic_desktop.ui_next.caption_marks import (
    APART_FROM_TEXT,
    LINK_COLORS,
    Panel,
    link_colours,
)
from polyglotic_desktop.ui_next.views.presets import (
    PRESETS,
    VIDEOS,
    ColourPreset,
    _mix,
)
from polyglotic_desktop.ui_next.views.presets import ciede2000 as colours_apart
from polyglotic_desktop.ui_next.views.presets import ciede2000_lab as ciede2000

TOLD_APART = 13.0
"""The least CIEDE2000 between any two link colours as drawn: over the
11.1 of the orange and brown the user couldn't tell apart as words, and
where the closest pair the user hasn't flagged (red and pink) is, 13.1.
With ten colours, readable on every panel and apart from white and the
yellows, 446's search found 14.7 the most for any palette."""

LINE_ALPHA = 0.9
"""A link's curve is drawn at 90 % of its colour (`caption_layout._arrows`)."""


def _lab(colour: str) -> tuple[float, float, float]:
    d = colour.lstrip("#")
    rgb = [int(d[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb)
    xyz = (
        (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047,
        0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
        (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883,
    )
    fx, fy, fz = (
        t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29
        for t in xyz
    )
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


@pytest.mark.parametrize(
    ("lab1", "lab2", "expected"),
    [  # Sharma, Wu and Dalal's (2005) test data, pairs 1, 7, 17 and 25
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ],
)
def test_the_colour_difference_is_ciede2000(
    lab1: tuple[float, float, float], lab2: tuple[float, float, float], expected: float
) -> None:
    assert ciede2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def _backdrops(preset: ColourPreset) -> list[str]:
    """Its panel drawn solid, and at its opacity over each video."""
    found = [preset.background]
    if preset.opacity < 1.0:
        found += [_mix(video, preset.background, preset.opacity) for video in VIDEOS]
    return found


def _drawn(colour: str, preset: ColourPreset, as_word: bool) -> list[str]:
    """What the eye gets on each backdrop: a word in its link's colour, or
    the link's line."""
    if as_word:
        ink = Ink(panel=preset.background, panel_opacity=preset.opacity)
        shade, alpha = link_ink(QColor(colour), ink, QColor("#ffffff")).name(), 1.0
    else:
        shade, alpha = colour, LINE_ALPHA
    return [_mix(under, shade, alpha) for under in _backdrops(preset)]


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
@pytest.mark.parametrize("as_word", [False, True], ids=["line", "word"])
def test_every_two_link_colours_are_told_apart(
    preset: ColourPreset, as_word: bool
) -> None:
    drawn = {c: [_lab(s) for s in _drawn(c, preset, as_word)] for c in LINK_COLORS}
    close = [
        (a, b, round(found, 1))
        for a, b in combinations(LINK_COLORS, 2)
        if (found := min(map(ciede2000, drawn[a], drawn[b]))) < TOLD_APART
    ]
    assert close == []


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_no_link_colour_is_drawn_near_the_text_of_the_rows_it_links(
    preset: ColourPreset,
) -> None:
    """polyglotic-hq 554 (the user, 2026-11-20: "make the font colours
    slightly more dynamic to not take same or similar colours to font
    colour"): on every preset a word in its link's colour, as drawn
    (`link_ink`), is at least APART_FROM_TEXT from both rows' own colours -
    Classic's gold had orange at 18.8 and olive at 18.0, Ember's orange
    its own orange at 1.9 - and enough colours are left for a line's links."""
    panel = Panel(
        preset.background, preset.original, preset.translation, opacity=preset.opacity
    )
    kept = link_colours(panel)
    assert len(kept) >= 7
    ink = Ink(panel=preset.background, panel_opacity=preset.opacity)
    for colour in kept:
        for row in (preset.original, preset.translation):
            word = link_ink(QColor(colour), ink, QColor(row)).name()
            assert colours_apart(word, row) >= APART_FROM_TEXT, (colour, row)
