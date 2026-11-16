"""The caption windows' colour presets, and exact colours - plain Python,
no Qt (polyglotic-hq 248's section 6, the user's F16; Q7 A: all ten,
Classic staying the default; built by 261).

A preset is a matched set: what was said, the translation, the panel and
how solid the panel is. Choosing one sets all four; the slider still
moves after, and a preset is still the one chosen while its three colours
are (`preset_of`) - change any colour and it's "Custom", from the preset
it started from.

Each preset's two text colours clear WCAG 2.2's 4.5:1 against its own
panel drawn solid (`contrast`; a test fails if one is edited below it) -
and against its panel at its own opacity over a light or a dark video,
an older caption's stepped-back ink included (the user's live testing,
polyglotic-hq 270: "not high contrast enough, not visible enough"; 284
raised Ember's, Paper's and Quiet's panels to it). They differ in
brightness or warmth, not only hue, so colour-blind viewers can tell the
rows apart (248's section 6.1). The colours are 248's `contrast.py`'s.

Holds no caption text.
"""

import re
from dataclasses import dataclass

from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

AA_TEXT = 4.5
"""WCAG 2.2's 1.4.3 for normal text: every preset's text at least this
against its panel (caption text is large, whose floor is 3:1)."""


@dataclass(frozen=True)
class ColourPreset:
    """A matched set of colours ("#rrggbb") and the panel's opacity (0-1)."""

    key: str
    original: str
    translation: str
    background: str
    opacity: float


PRESETS: tuple[ColourPreset, ...] = (
    ColourPreset("classic", "#ffffff", "#ffd76e", "#0a0c10", 0.72),
    ColourPreset("broadcast", "#ffffff", "#ffe600", "#000000", 1.0),
    ColourPreset("teletext", "#ffffff", "#5ee3ff", "#000000", 1.0),
    ColourPreset("ember", "#dcecff", "#ffa64d", "#0b1a33", 0.88),
    ColourPreset("violet", "#efe7ff", "#ffd166", "#1b1033", 0.85),
    ColourPreset("forest", "#eefff2", "#9af28a", "#0f1f16", 0.85),
    ColourPreset("paper", "#1a1a1a", "#7a3e00", "#f6f1e6", 0.96),
    ColourPreset("quiet", "#e6e6e6", "#ffb347", "#1b1f26", 0.85),
    ColourPreset("high_contrast", "#ffffff", "#ffff00", "#000000", 1.0),
    ColourPreset("clear", "#ffffff", "#e69f00", "#000000", 1.0),
)
"""248's ten, in its order; Classic - today's look - first, the default.
Ember's panel 85 -> 88 %, Paper's 94 -> 96 % and Quiet's 55 -> 85 % (284):
the least that keeps every caption, older ones included, at 4.5:1 over a
light video (#f3f5f7) and a black one. Quiet stays muted in its colours;
its see-through panel couldn't (a white scene behind 55 % left its
yellow at 2.1:1)."""

BY_KEY = {preset.key: preset for preset in PRESETS}


def preset_of(look: CaptionLook) -> ColourPreset | None:
    """The preset whose three colours `look` has - its opacity is free -
    or None: custom colours."""
    for preset in PRESETS:
        if (preset.original, preset.translation, preset.background) == (
            look.original,
            look.translation,
            look.background,
        ):
            return preset
    return None


_HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")


def hex_colour(text: str) -> str | None:
    """`text` as a colour "#rrggbb" in lower case - "ffd76e", "#FFD76E" and
    "#fd7" all read - or None if it isn't one."""
    found = _HEX.fullmatch(text.strip())
    if found is None:
        return None
    digits = found.group(1).lower()
    if len(digits) == 3:
        digits = "".join(d * 2 for d in digits)
    return f"#{digits}"


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    """WCAG 2.2's relative luminance of "#rrggbb"."""
    digits = colour.lstrip("#")
    r, g, b = (_channel(int(digits[i : i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(text: str, under: str) -> float:
    """WCAG 2.2's contrast ratio of two "#rrggbb" colours (1 to 21)."""
    high, low = sorted((luminance(text), luminance(under)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _lab(colour: str) -> tuple[float, float, float]:
    """`colour` in CIELAB (D65): lightness, then the two colour axes."""
    digits = colour.lstrip("#")
    r, g, b = (_channel(int(digits[i : i + 2], 16)) for i in (0, 2, 4))
    xyz = (
        (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047,
        0.2126 * r + 0.7152 * g + 0.0722 * b,
        (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883,
    )
    x, y, z = (t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in xyz)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def colour_difference(a: str, b: str) -> float:
    """How far apart two "#rrggbb" colours look: CIE76's distance in CIELAB
    (about 2.3 is just noticeable side by side; thin text needs far more)."""
    return float(
        sum((p - q) ** 2 for p, q in zip(_lab(a), _lab(b), strict=True)) ** 0.5
    )


def readable_at(colour: str, under: str, alpha: float, ratio: float = AA_TEXT) -> str:
    """`colour` drawn `alpha` opaque over `under` (a faint reading, an
    older caption's words) reaching `ratio` against it - or the nearest to
    it that does, as `readable_on` moves it (polyglotic-hq 395: words and
    pinyin in their link's colour)."""
    end = (
        "#000000"
        if contrast("#000000", under) > contrast("#ffffff", under)
        else "#ffffff"
    )
    for step in range(21):
        mixed = _mix(colour, end, step / 20)
        if contrast(_mix(under, mixed, alpha), under) >= ratio:
            return mixed
    return end


def _mix(colour: str, towards: str, share: float) -> str:
    a, b = colour.lstrip("#"), towards.lstrip("#")
    mixed = (
        round(int(a[i : i + 2], 16) * (1 - share) + int(b[i : i + 2], 16) * share)
        for i in (0, 2, 4)
    )
    return "#" + "".join(f"{c:02x}" for c in mixed)


def readable_on(colour: str, under: str, ratio: float = AA_TEXT) -> str:
    """`colour` if it reaches `ratio` against `under` - or the nearest to it
    that does, towards black on a light panel or white on a dark one: an
    app's label colour, chosen for dark panels, on Paper's cream."""
    if contrast(colour, under) >= ratio:
        return colour
    end = (
        "#000000"
        if contrast("#000000", under) > contrast("#ffffff", under)
        else "#ffffff"
    )
    for step in range(1, 21):
        mixed = _mix(colour, end, step / 20)
        if contrast(mixed, under) >= ratio:
            return mixed
    return end
