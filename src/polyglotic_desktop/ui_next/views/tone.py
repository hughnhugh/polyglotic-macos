"""Contrast and vibrance: how strongly captions stand out from their panel,
and how vivid their colours are (polyglotic-hq 481; the user, 2026-11-18:
"Make a contrast vibrance settings"). Two sliders beside the colour
presets, one setting for every caption window and transcript, each 0 at
today's look. Plain Python, no Qt.

- **Contrast** (`CONTRAST_RANGE`): soft to crisp. Every line's ink
  (`strength`) - what was said, the translation, the label, readings,
  word links' lines and words in their link's colour, Quick preview's and
  live lines, the quiet view's grey and gold, older captions stepped back.
  Soft takes them all towards Quick preview's faintness: the newest
  caption to `SOFTEST` of its ink, and what's fainter today fainter
  again by as much. Crisp takes them all towards full ink: at its end
  nothing is faint, as with Windows' high contrast (`views.arrivals`). The
  ratios a colour is moved to reach to be readable - a word in its link's
  colour, the quiet view's grey and gold - come down with it (`ratio`).
  Never under `FLOOR` (`floor_alpha`), unless today's look already is.
- **Vibrance** (`VIBRANCE_RANGE`): muted to vivid, as a photo editor's
  (`vibrant`): a colour's chroma in OKLCH scaled - the dull colours
  boosted more than the already vivid, greys left grey, hue and lightness
  kept (a little lightness given where sRGB holds no more chroma at its
  own: `SHIFT`). The look's two text colours (the quiet view's gold), the
  quiet view's blue, saved words' categories' colours, the learning
  load's stages, new-word dots and deck dashes, a reading's picked
  colour, your own speech's colour. Not the panel: the text is what
  changes. Not word links' colours: muted or made vivid, two pairs fell
  under the 13 apart (CIEDE2000) that keeps them told apart (446), so they
  keep theirs.
- **Thickness** (`THICKNESSES`): the captions' font weight, as a number
  the faces honour as far as they hold it (Qt draws the nearest weight a
  face really has: never a made-up bold where a real one exists).
  Medium (500) is today's; readings one step above the text
  (`reading_weight`), as today's 600 over 500.
- **Visibility** (`TextEdge`): what's drawn around the letters to keep them
  readable over a busy video - nothing (today's), a soft shadow, or an
  outline, in black around light text and white around dark
  (`edge_colour`). How solid the panel is stays Look's own slider.

There's no Brightness: on a panel, text's brightness is its distance from
the panel - dimmer text on a dark panel is softer contrast, and "brighter"
text on a light panel is fainter. It's Contrast.

Holds no caption text.
"""

import math
from functools import lru_cache

from polyglotic_desktop.ui_next.views.caption_window import TextEdge
from polyglotic_desktop.ui_next.views.presets import (
    AA_TEXT,
    LARGE_TEXT,
    VIDEOS,
    _mix,
    contrast,
    readable_on,
)

CONTRAST_RANGE = (-100, 100)
"""Soft to crisp; 0 is today's look."""
VIBRANCE_RANGE = (-100, 100)
"""Muted to vivid; 0 is today's look."""

SOFTEST = 0.6
"""At the softest contrast the newest caption is drawn this much of its
ink: Quick preview's dim line (`caption_layout.Ink.provisional_alpha`),
the quiet look the user likes (polyglotic-hq 477)."""

FLOOR = 3.7
"""No text drawn fainter than this against its panel drawn solid by the
contrast slider - 481's recommendation: the faintest Quick preview line
the user has seen and liked (477 measured 3.7:1 to 4.5:1), and over
WCAG 2.2's 3:1 for large text with room for what drawing costs (italic's
thin strokes, anti-aliasing: 4.5 measured 4.3 in the UI lab, 477). Seen
through a panel that isn't solid, over a light or a black video, large
text's 3:1 (`LARGE_TEXT`), as word links' colours are (431)."""


def strength(alpha: float, contrast_: int) -> float:
    """The ink an `alpha` of today's look is drawn at with the contrast
    slider at `contrast_` (`CONTRAST_RANGE`): itself at 0; towards full
    (1.0) up to crisp; towards `SOFTEST` of itself down to soft."""
    share = _share(contrast_)
    if share >= 0:
        return alpha + (1.0 - alpha) * share
    return alpha * (1.0 + share * (1.0 - SOFTEST))


def ratio(target: float, contrast_: int) -> float:
    """What a colour moved to be readable is moved to reach with the
    slider at `contrast_`: today's `target` from the middle up (at full
    ink it reaches more anyway), down to `FLOOR` at the softest."""
    share = _share(contrast_)
    if share >= 0 or target <= FLOOR:
        return target
    return target + (FLOOR - target) * -share


def floored(
    alpha: float, today: float, colour: str, panel: str, opacity: float
) -> float:
    """`alpha` - the ink the slider asks for - raised as far as `colour`
    needs to reach the floor on `panel` (`floor_alpha`), but never past
    `today`'s: a look already fainter than the floor stays as it was."""
    return max(alpha, min(today, floor_alpha(colour, panel, opacity)))


@lru_cache(maxsize=1024)
def floor_alpha(colour: str, panel: str, opacity: float = 1.0) -> float:
    """The least ink (0-1, in steps of 0.01) at which `colour` drawn over
    `panel` reaches `FLOOR` against it drawn solid - and, below a solid
    panel, 3:1 against it seen at its `opacity` over a light or a black
    video (`VIDEOS`). 1.0 when nothing less does."""
    backdrops = [(panel, FLOOR)]
    if opacity < 1.0:
        backdrops += [(_mix(video, panel, opacity), LARGE_TEXT) for video in VIDEOS]
    for step in range(101):
        alpha = step / 100
        if all(
            contrast(_mix(under, colour, alpha), under) >= needs
            for under, needs in backdrops
        ):
            return alpha
    return 1.0


def _share(value: int) -> float:
    low, high = CONTRAST_RANGE
    return max(low, min(high, value)) / high


# -- vibrance -----------------------------------------------------------------------

BOOST = 1.0
"""At the vivid end a colour with no chroma to speak of gains this much
of its own (doubles), one at `VIVID_CHROMA` or more gains none: the dull
colours boosted most, as a photo editor's vibrance."""
VIVID_CHROMA = 0.25
"""OKLCH chroma this high is vivid already (sRGB's red is 0.26, its
yellow 0.21, Classic's yellow translation 0.13)."""
MUTE = 0.45
"""At the muted end every colour keeps 1 - this of its chroma: muted, not
grey - word links' colours still told apart (`tests/ui_next/
test_tone.py`'s numbers)."""
GREY = 0.002
"""Chroma under this is a grey: left as it is."""


@lru_cache(maxsize=1024)
def vibrant(colour: str, vibrance: int) -> str:
    """`colour` ("#rrggbb") with the vibrance slider at `vibrance`
    (`VIBRANCE_RANGE`): itself at 0. Its chroma scaled in OKLCH, lightness
    and hue kept, brought back inside sRGB by chroma alone where it went
    out; greys stay grey."""
    found = colour.lower()
    if vibrance == 0:
        return found
    lightness, a, b = _oklab(found)
    chroma = math.hypot(a, b)
    if chroma < GREY:
        return found
    share = max(VIBRANCE_RANGE[0], min(VIBRANCE_RANGE[1], vibrance)) / 100
    if share > 0:
        scale = 1.0 + share * BOOST * max(0.0, 1.0 - chroma / VIVID_CHROMA)
    else:
        scale = 1.0 + share * MUTE
    return _in_gamut(lightness, a, b, scale)


def chroma(colour: str) -> float:
    """`colour`'s chroma in OKLCH (0 for a grey; about 0.3 at most in sRGB)."""
    _, a, b = _oklab(colour)
    return math.hypot(a, b)


@lru_cache(maxsize=1024)
def caption_text_colour(colour: str, background: str, vibrance: int) -> str:
    """The row's ink after vibrance, retaining its contrast up to 4.5:1."""
    was = contrast(colour, background)
    return readable_on(vibrant(colour, vibrance), background, min(AA_TEXT, was))


SHIFT = 0.05
"""How far a colour made vivid may move in lightness (OKLab's 0-1) towards
where sRGB holds more of its chroma: Classic's yellow and the quiet view's
blue are as vivid as sRGB allows at their own lightness (one channel at
full), so at it alone vivid would leave them as they are."""


def _in_gamut(lightness: float, a: float, b: float, scale: float) -> str:
    """The colour of hue (a, b) at `scale` of its chroma and `lightness` -
    or, where sRGB doesn't hold that, the most of it sRGB holds within
    `SHIFT` of that lightness, the nearest lightness of those."""
    rgb = _srgb(lightness, a * scale, b * scale)
    if _inside(rgb):
        return _hex(rgb)
    best: tuple[float, float, float] | None = None  # its chroma's share, its shift
    for step in range(11):
        for shift in {SHIFT * step / 10, -SHIFT * step / 10}:
            at = min(1.0, max(0.0, lightness + shift))
            low, high = 0.0, scale
            for _ in range(20):
                mid = (low + high) / 2
                if _inside(_srgb(at, a * mid, b * mid)):
                    low = mid
                else:
                    high = mid
            if best is None or low > best[0] + 0.002:
                best = (low, at, abs(shift))
    assert best is not None
    share, at, _ = best
    return _hex(_srgb(at, a * share, b * share))


def _inside(rgb: tuple[float, float, float]) -> bool:
    return all(-1e-6 <= c <= 1 + 1e-6 for c in rgb)


def _linear(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _encoded(value: float) -> float:
    c = max(0.0, min(1.0, value))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _oklab(colour: str) -> tuple[float, float, float]:
    """`colour` in OKLab (Björn Ottosson's, 2020)."""
    digits = colour.lstrip("#")
    r, g, b = (_linear(int(digits[i : i + 2], 16)) for i in (0, 2, 4))
    lms = (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b,
    )
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in lms)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _srgb(lightness: float, a: float, b: float) -> tuple[float, float, float]:
    """OKLab to linear sRGB (each 0-1 inside the gamut)."""
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l3, m3, s3 = l_**3, m_**3, s_**3
    return (
        4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
        -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
        -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3,
    )


def _hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(_encoded(c) * 255):02x}" for c in rgb)


# -- thickness -----------------------------------------------------------------------

GREY_READING = 0.8
"""Where a grey reading sits between its panel and what was said: this
share of the way to what was said, in lightness (polyglotic-hq 532) -
0.6 until 584: on Everyday's panel over a white scene its pinyin was at
2.9:1; at 0.8, 7.5:1 and still a step under the text's white."""


def reading_grey(panel: str, said: str) -> str:
    """Readings' muted grey (polyglotic-hq 532): a grey with no colour of
    its own, `GREY_READING` of the way in lightness from the panel to what
    was said's colour - light on a dark panel, dark on Paper's cream, so
    the text leads on any. Made readable where it's drawn (the layout's
    `link_ink`)."""
    low, _, _ = _oklab(panel)
    high, _, _ = _oklab(said)
    return _hex(_srgb(low + GREY_READING * (high - low), 0.0, 0.0))


THICKNESSES = (300, 400, 500, 600, 700)
"""Light, Regular, Medium, Semibold, Bold - CSS's and Qt's weights, the
numbers a font a later build ships (polyglotic-hq 479) honours as they
are."""
THICKNESS = 500
"""Medium: what captions have always asked for (`CaptionStyle.weight`).
Windows' faces have no Medium: it draws their Regular (481's table)."""


def offered(lightest: int) -> tuple[int, ...]:
    """The thickness steps Look offers (polyglotic-hq 532): from the
    lightest weight of their own the captions' faces have below the one
    Medium draws (`lightest`; Medium if none has one), up. Every face the
    app carries is cut at Medium (Ma Shan Zheng at Regular, its only
    weight), so Light and Regular drew what Medium draws: the slider moved
    and nothing changed. A PC's own face with a Light brings them back."""
    low = max(w for w in THICKNESSES if w <= max(lightest, THICKNESSES[0]))
    return tuple(w for w in THICKNESSES if w >= min(low, THICKNESS))


def reading_weight(thickness: int) -> int:
    """A reading's weight over text of `thickness`: one step above it (600
    over today's 500), Bold at most - no face the captions use holds a
    heavier one."""
    steps = THICKNESSES
    at = steps.index(thickness) if thickness in steps else steps.index(THICKNESS)
    return steps[min(at + 1, len(steps) - 1)]


# -- visibility --------------------------------------------------------------------


_DIAGONAL = math.sqrt(0.5)
_ROUND = (
    (-1.0, 0.0), (1.0, 0.0), (0.0, -1.0), (0.0, 1.0),
    (-_DIAGONAL, -_DIAGONAL), (_DIAGONAL, -_DIAGONAL),
    (-_DIAGONAL, _DIAGONAL), (_DIAGONAL, _DIAGONAL),
)  # fmt: skip
"""Eight ways out, each as far: an outline's copies."""

EDGE_PASSES: dict[TextEdge, tuple[tuple[float, float, float], ...]] = {
    TextEdge.NONE: (),
    TextEdge.SHADOW: ((1.0, 1.0, 0.55), (2.0, 2.0, 0.3)),
    TextEdge.OUTLINE: (
        (0.0, 0.0, 1.0),  # under the letters themselves: see `OUTLINE_SOLID`
        *((dx, dy, 1.0) for dx, dy in _ROUND),
    ),
}
"""Each edge as the text drawn again under it: x and y in pixels at 21 px
text (grown with the text; each moved by whole pixels of the screen, so
every copy lands on the pixels the text does), and how much of the text's
own ink. The outline is round - its corners as far out as its sides, not
1.4 times as far - and solid: copies at 85 % left a grey fringe wherever
only one reached, and at Video's 63 px text, three pixels out, it read
as a blur (polyglotic-hq 584; the user, 2026-11-21: "Big fonts are
blurry during video mode, especially when greyed")."""

OUTLINE_SOLID = 0.3
"""An outline is drawn at full strength under text this faint or more -
and under the letters themselves - so faint text (the words still to
come, an older caption stepped back, at the softest contrast too) is a
solid grey on solid black: its faintness from its colour, never the
video seen through its letters (584). Fainter than this the text is
fading away, and its outline fades with it."""


def edge_colour(text: str) -> str:
    """The edge around text of colour `text`: black around light text,
    white around dark (Paper's) - whichever stands further from it."""
    if contrast(text, "#000000") >= contrast(text, "#ffffff"):
        return "#000000"
    return "#ffffff"
