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

Three of them are also recommended looks (`LOOKS`, polyglotic-hq 532:
the user, preview 1, "this theme and settings are nice, this should be a
recommended preset, paper should be another, broadcast another"): a
whole look - colours, caption text, readings and Chinese faces - picked
in one click and changed as freely after.

Holds no caption text.
"""

import math
import re
from dataclasses import dataclass, replace
from functools import lru_cache

from polyglotic_desktop.core.listening.display import ReadingColour, ReadingSize
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, TextEdge

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
    ColourPreset("classic", "#ffffff", "#ffd76e", "#0a0c10", 0.88),
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
yellow at 2.1:1). Classic's 72 -> 88 % (584): the app's default look,
its text and translation at 7:1 over a white scene (`ui.settings.OPACITY`)."""

BY_KEY = {preset.key: preset for preset in PRESETS}


@dataclass(frozen=True)
class RecommendedLook:
    """A whole look (532): a colour preset's colours and panel, the caption
    text (contrast, vibrance, thickness, what's around the letters), the
    readings' size and colour, and Chinese's faces - each language named
    in `faces` set to its family, every other language's left as chosen."""

    key: str
    colours: str
    """Its colour preset's key (`BY_KEY`)."""
    opacity: float
    contrast: int
    vibrance: int
    thickness: int
    edge: TextEdge
    reading_size: ReadingSize
    reading_colour: ReadingColour
    faces: tuple[tuple[str, str], ...]

    @property
    def preset(self) -> ColourPreset:
        return BY_KEY[self.colours]


CHINESE = ("zh", "zh-hant")
"""The languages a look sets the faces of: Mandarin in Simplified and in
Traditional characters (`CaptionLook.faces`' codes)."""

LOOKS: tuple[RecommendedLook, ...] = (
    RecommendedLook(
        "quiet",
        "quiet",
        0.96,
        100,
        100,
        600,
        TextEdge.SHADOW,
        ReadingSize.MEDIUM,
        ReadingColour.GREY,
        (("zh", "Ma Shan Zheng Captions"), ("zh-hant", "LXGW WenKai TC Captions")),
    ),
    RecommendedLook(
        "paper",
        "paper",
        0.96,
        50,
        0,
        500,
        TextEdge.NONE,
        ReadingSize.MEDIUM,
        ReadingColour.GREY,
        (("zh", "Polyglotic Kai"), ("zh-hant", "LXGW WenKai TC Captions")),
    ),
    RecommendedLook(
        "broadcast",
        "broadcast",
        1.0,
        100,
        0,
        700,
        TextEdge.NONE,
        ReadingSize.MEDIUM,
        ReadingColour.GREY,
        (("zh", "Noto Sans SC Captions"), ("zh-hant", "Noto Sans TC Captions")),
    ),
)
"""The three (532), in the user's order:

- **Quiet** - the user's own picture of preview 1 (2026-11-18): soft grey
  and amber, contrast and vibrance at the top, Semibold, a soft shadow,
  grey readings at Medium (its picture's pinyin is that size; Small's
  are 11 px at the captions' first text size), Chinese in calligraphy
  (Ma Shan Zheng; LXGW WenKai TC).
  Its panel 96 % solid, not its colour preset's 85 %: over a busy window
  85 % let a window's edges through at 15 % of their contrast, and they
  read as the captions' own (the user's picture, preview 1); 93 % still
  showed them (532's pictures). A blur behind the panel would keep it
  see-through - Windows can, the app can't draw it itself.
- **Paper** - dark ink on cream, a little crisper, Medium, no edge (a
  shadow on cream reads as a smudge), grey readings at Medium, Chinese
  in a textbook's handwritten kai (Polyglotic Kai, LXGW WenKai TC).
- **Broadcast** - white and yellow on solid black, as on TV: crisp, Bold,
  readings at Medium, Chinese in the plain sans (Noto Sans SC, TC).
"""

LOOKS_BY_KEY = {look.key: look for look in LOOKS}


def with_look(look: CaptionLook, key: str) -> CaptionLook:
    """`look` as the recommended look `key` makes it: what it sets, and
    nothing else changed."""
    chosen = LOOKS_BY_KEY[key]
    preset = chosen.preset
    faces = {**dict(look.faces), **dict(chosen.faces)}
    return replace(
        look,
        original=preset.original,
        translation=preset.translation,
        background=preset.background,
        opacity=chosen.opacity,
        contrast=chosen.contrast,
        vibrance=chosen.vibrance,
        thickness=chosen.thickness,
        edge=chosen.edge,
        reading_size=chosen.reading_size,
        reading_colour=chosen.reading_colour,
        faces=tuple(sorted(faces.items())),
    )


def look_of(look: CaptionLook) -> RecommendedLook | None:
    """The recommended look `look` is, everything it sets as it set it -
    or None: changed since, or never picked."""
    for chosen in LOOKS:
        if with_look(look, chosen.key) == look:
            return chosen
    return None


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


# Pure and called on every repaint with the same few colours (a look drag:
# 9.5 ms a frame against 4.4 before 799 and 805 added link colours and
# contrast shares, polyglotic-hq 821), so their answers are kept.
COLOUR_CACHE = 4096
"""Colour answers kept per function: a few windows' inks, panels and shares."""


@lru_cache(maxsize=COLOUR_CACHE)
def luminance(colour: str) -> float:
    """WCAG 2.2's relative luminance of "#rrggbb"."""
    digits = colour.lstrip("#")
    r, g, b = (_channel(int(digits[i : i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(text: str, under: str) -> float:
    """WCAG 2.2's contrast ratio of two "#rrggbb" colours (1 to 21)."""
    high, low = sorted((luminance(text), luminance(under)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@lru_cache(maxsize=COLOUR_CACHE)
def contrast_alpha(colour: str, panel: str, retained: float) -> float:
    """Paint alpha that retains `retained` of full ink's WCAG contrast.

    `retained` is a 0..1 ratio. Quantising upward to hundredths matches the
    layout's other alpha searches and guarantees that rounding never dips
    below the requested contrast.
    """
    retained = max(0.0, min(1.0, retained))
    full = contrast(colour, panel)
    target = min(full, max(AA_TEXT, full * retained))
    for step in range(101):
        alpha = step / 100
        if contrast(_mix(panel, colour, alpha), panel) >= target:
            return alpha
    return 1.0


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


def ciede2000(a: str, b: str) -> float:
    """How far apart two "#rrggbb" colours look as CIEDE2000 has it (its
    weights all 1): nearer the eye than `colour_difference` across hues -
    the told-apart rule for word links' colours (polyglotic-hq 446, 554)."""
    return ciede2000_lab(_lab(a), _lab(b))


def ciede2000_lab(
    lab1: tuple[float, float, float], lab2: tuple[float, float, float]
) -> float:
    """CIEDE2000 between two CIELAB colours (Sharma, Wu and Dalal, 2005)."""
    (l1, a1, b1), (l2, a2, b2) = lab1, lab2
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    else:
        dhp = h2p - h1p - 360 if h2p > h1p else h2p - h1p + 360
    d_l, d_c = l2 - l1, c2p - c1p
    d_h = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))
    l_bar, c_barp = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar = (h1p + h2p) / 2
    else:
        h_bar = (h1p + h2p + (360 if h1p + h2p < 360 else -360)) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(h_bar - 30))
        + 0.24 * math.cos(math.radians(2 * h_bar))
        + 0.32 * math.cos(math.radians(3 * h_bar + 6))
        - 0.20 * math.cos(math.radians(4 * h_bar - 63))
    )
    theta = 30 * math.exp(-(((h_bar - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(c_barp**7 / (c_barp**7 + 25**7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * c_barp
    s_h = 1 + 0.015 * c_barp * t
    r_t = -math.sin(math.radians(2 * theta)) * r_c
    return math.sqrt(
        (d_l / s_l) ** 2
        + (d_c / s_c) ** 2
        + (d_h / s_h) ** 2
        + r_t * (d_c / s_c) * (d_h / s_h)
    )


@lru_cache(maxsize=COLOUR_CACHE)
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


LARGE_TEXT = 3.0
"""WCAG 2.2's 1.4.3 for large text, which caption text is."""

VIDEOS = ("#f3f5f7", "#000000")
"""A light video and a black one: what a panel that isn't solid is seen
over, at its worst (284)."""


def readable_through(
    colour: str, panel: str, opacity: float, alpha: float, ratio: float
) -> str:
    """`colour` drawn `alpha` opaque, readable as a caption's text is
    (polyglotic-hq 431): `ratio` on `panel` drawn solid (`readable_at`),
    and 3:1 - large text's floor - on it seen at its `opacity` over a
    light or a black video (`VIDEOS`). Moved towards white on a dark
    panel, black on a light one, only as far as it needs. 395 checked the
    solid panel only: on Classic's 72 % over a light video, #e040fb was at
    2.4:1."""
    found = readable_at(colour, panel, alpha, ratio)
    if opacity >= 1.0:
        return found
    for video in VIDEOS:
        found = readable_at(found, _mix(video, panel, opacity), alpha, LARGE_TEXT)
    return found


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
