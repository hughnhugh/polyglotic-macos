"""The fonts each OS has for the interface, after Windows' in every font
list (polyglotic-hq 179) - and the faces captions are drawn in, by
language (polyglotic-hq 479, 482; decision 0223).

The interface's lists name Windows' fonts first - Segoe UI, Microsoft
YaHei and JhengHei, Yu Gothic - as the app always has. On macOS and Linux
none of those exist, and Qt fell back to whatever it found (DejaVu, in
171's Linux probe), so each list ends with that OS's own (`also`). On
Windows `also` adds nothing: the lists, and so the interface, are as they
were.

A caption's language picks its face (`caption_families`): the learner's
choice for it, else its default (`DEFAULTS`, 479's picks; Simplified and
Traditional Chinese default to this OS's plain CJK UI face, with the
calligraphy and kai faces kept as choices and the script's sans behind
them, `BEHIND`) - carried by the app where it's small (`BUNDLED`, in
ui/assets/fonts) - then the OS's
own faces for its script, named, so Thai and Arabic are never left to
Qt's fallback (Tahoma, 479), then the Latin ones for the Latin letters a
caption holds. A face the app doesn't have yet is passed over by Qt, so
the OS's own draws until it comes. Plain Python: the faces are added to
Qt's fonts by `caption_faces`.
"""

import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from polyglotic_desktop.core.shared.tunables import Applies, tunable

WEIGHT_FACES: dict[int, tuple[str, ...]] = {
    300: ("Segoe UI Variable Display Light",),
    600: ("Segoe UI Variable Display Semibold",),
}
"""Faces holding one weight of a family the captions use (polyglotic-hq
481): Windows lists Segoe UI Variable Display's Light and Semibold as
families of their own, so asked of "Segoe UI Variable Display" a Light
drew Regular and a Semibold Bold. Named before it at that weight only;
where they aren't (Windows 10, a Mac) the next family serves."""

OTHER_OS: dict[str, dict[str, tuple[str, ...]]] = {
    "darwin": {
        "latin": ("Helvetica Neue",),
        "zh": ("PingFang SC",),
        "zh-hant": ("PingFang TC",),
        "yue": ("PingFang HK",),
        "ja": ("Hiragino Sans",),
        "ko": ("Apple SD Gothic Neo",),
        "th": ("Thonburi",),
        "ar": ("Geeza Pro",),
        "deva": ("Kohinoor Devanagari",),
    },
    "linux": {
        "latin": ("Noto Sans", "Cantarell", "DejaVu Sans"),
        "zh": ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei"),
        "zh-hant": ("Noto Sans CJK TC", "Source Han Sans TC"),
        "yue": ("Noto Sans CJK HK", "Source Han Sans HC"),
        "ja": ("Noto Sans CJK JP", "Source Han Sans"),
        "ko": ("Noto Sans CJK KR", "Source Han Sans K"),
        "th": ("Noto Sans Thai", "Noto Sans Thai Looped"),
        "ar": ("Noto Naskh Arabic", "Noto Sans Arabic"),
        "deva": ("Noto Sans Devanagari",),
    },
}
"""Each OS's families by script: Latin text, Simplified Chinese ("zh"),
Traditional ("zh-hant"), Hong Kong's ("yue"), Japanese ("ja"), Korean,
Thai, Arabic and Devanagari ("deva"). macOS's Korean, Thai, Arabic and
Devanagari faces are the ones it ships (479: not yet seen on a Mac)."""


CJK_SCRIPTS = ("zh", "zh-hant", "yue", "ja", "ko")
"""Scripts whose system CJK font families Linux desktops supply (polyglotic-hq
647): checked once so minimal installs without `fonts-noto-cjk` log why glyphs
may show as boxes."""


def also(script: str, system: str = sys.platform) -> tuple[str, ...]:
    """This OS's fonts for `script`, to follow Windows' in a font list -
    none on Windows."""
    return OTHER_OS.get(system, {}).get(script, ())


def missing_cjk_families(
    installed: Collection[str], system: str = sys.platform
) -> dict[str, tuple[str, ...]]:
    """CJK scripts for `system` that have none of their OS font families in
    `installed` (case-insensitive): `{script: expected_families}`."""
    have = {family.casefold() for family in installed}
    missing: dict[str, tuple[str, ...]] = {}
    for code in CJK_SCRIPTS:
        families = also(code, system)
        if families and not any(family.casefold() in have for family in families):
            missing[code] = families
    return missing


# -- Captions -------------------------------------------------------------

SANS, SERIF, HANDWRITTEN, CALLIGRAPHY = "sans", "serif", "handwritten", "calligraphy"
"""What kind of face: how a language's list groups them (Look) -
calligraphy, a brush's (532), apart from handwriting, a pen's."""


@dataclass(frozen=True)
class Face:
    """A caption face: its family as Qt names it, its kind, its files in
    ui/assets/fonts if the app carries it, whether it's never slanted -
    drawn upright by design, or slanted by design (its own italic) - and
    its name as the learner sees it, if not its family's."""

    family: str
    kind: str = SANS
    files: tuple[str, ...] = ()
    upright: bool = False
    shown: str = ""
    pack: str = ""
    """Its name in the signed pack list, for a face downloaded when it's
    chosen (482's font packs): its files come as riders (`FontOffer`)."""
    scripts: tuple[str, ...] = ()
    """The scripts Look offers it for (a downloaded face's, and a bundled
    one that isn't its script's default)."""
    text_style: str = ""
    """The style its text is in, for a family that also holds a SemiBold
    cut of what readings draw and nothing else (Noto Sans SC's, and the
    downloaded serifs' and Chiron's): asked for a heavier weight, its text
    stays in this style, made bold by Qt. Asked by weight alone, Qt took
    the readings' cut, hadn't the characters, and drew them in the next
    face - Semibold and Bold Chinese came out in YaHei, or Ma Shan Zheng
    (polyglotic-hq 532's measure)."""
    brushed: bool = False
    """A brush's or a hand's Chinese face (Ma Shan Zheng; LXGW WenKai TC,
    Polyglotic Kai): only its Han characters are drawn in it (551, the
    user's preview 1: "focus" came out in Ma Shan Zheng's own cursive
    letters). The Latin letters, digits and Latin punctuation in a line of
    it are in the Latin captions' face (`latin_runs`), and readings over
    it - pinyin, zhuyin - in the face after it: Ma Shan Zheng has no tone
    marks (532), and a brush's letters read as handwriting, not text."""

    @property
    def name(self) -> str:
        return self.shown or self.family


BUNDLED = (
    Face(
        "Ma Shan Zheng Captions",
        CALLIGRAPHY,
        ("MaShanZheng-Regular.ttf",),
        upright=True,  # a brush's own slant: a made-up one bends its strokes
        shown="Ma Shan Zheng",
        scripts=("zh",),
        brushed=True,
    ),
    Face(
        "Noto Sans SC Captions",
        files=("NotoSansSC-Medium.ttf", "NotoSansSC-SemiBold.ttf"),
        shown="Noto Sans SC",
        scripts=("zh",),
        text_style="Medium",
    ),
    Face("Noto Sans Thai Looped", files=("NotoSansThaiLooped-Medium.ttf",)),
    Face(
        "Be Vietnam Pro",
        files=("BeVietnamPro-Medium.ttf", "BeVietnamPro-MediumItalic.ttf"),
    ),
    Face(
        "Noto Naskh Arabic Captions",
        SERIF,
        ("NotoNaskhArabic-Medium.ttf",),
        upright=True,
        shown="Noto Naskh Arabic",
    ),
    Face("Noto Sans Devanagari", files=("NotoSansDevanagari-Medium.ttf",)),
    Face("PT Sans", files=("PTSans-Regular.ttf", "PTSans-Italic.ttf")),
    Face(
        "IBM Plex Sans",
        files=("IBMPlexSans-Medium.ttf", "IBMPlexSans-MediumItalic.ttf"),
    ),
)
"""The faces the app carries (482, built by `tools.caption_fonts`): the
small scripts' defaults and Simplified Chinese's two - Ma Shan Zheng, a
brush's regular script (kaishu), its default since 532: GB2312's 6,763
characters, every one HSK 1-9 and FLEURS' Mandarin use; and Noto Sans SC,
behind it (`BEHIND`) for the rarer ones and readings, cut to the 8,105
General Standard characters and GB2312, with a SemiBold of what readings
draw, so pinyin is never in a made-up bold. The three whose shape isn't
their maker's (cut, or another line box) have a family name of their
own: some Windows 11 PCs have a Noto Sans SC, and Qt can take its line
box for ours under one name."""


def _packed(
    pack: str,
    name: str,
    kind: str,
    scripts: tuple[str, ...],
    changed: bool = True,
    upright: bool = False,
    family: str = "",
    readings: bool = False,
    brushed: bool = False,
) -> Face:
    """A downloaded face: `changed` (cut or fixed at a weight by
    `tools.caption_fonts`) has a family of its own, "<name> Captions";
    `readings`, a SemiBold cut of readings beside its Medium text
    (`Face.text_style`); `brushed`, only its Han characters drawn in it."""
    family = family or (f"{name} Captions" if changed else name)
    text_style = "Medium" if readings else ""
    return Face(family, kind, (), upright, name, pack, scripts, text_style, brushed)


PACKED = (
    # the defaults of the languages whose faces are big (479: delivery C)
    _packed("notosanstc", "Noto Sans TC", SANS, ("zh-hant",)),
    _packed("notosanshk", "Noto Sans HK", SANS, ("yue",)),
    _packed("notosansjp", "Noto Sans JP", SANS, ("ja",)),
    _packed("pretendard", "Pretendard", SANS, ("ko",), changed=False),
    # every other face 479's sheet offers
    _packed("smileysans", "Smiley Sans", SANS, ("zh",), changed=False, upright=True),
    _packed("notoserifsc", "Noto Serif SC", SERIF, ("zh",), readings=True),
    _packed("zhuquefangsong", "Zhuque Fangsong", SERIF, ("zh",)),
    _packed(
        "polyglotickai",
        "Polyglotic Kai",
        HANDWRITTEN,
        ("zh",),
        family="Polyglotic Kai",
        brushed=True,
    ),
    _packed("huninn", "jf open Huninn", SANS, ("zh-hant",)),
    _packed("notoseriftc", "Noto Serif TC", SERIF, ("zh-hant",), readings=True),
    _packed("lxgwwenkaitc", "LXGW WenKai TC", HANDWRITTEN, ("zh-hant",), brushed=True),
    _packed("chironheihk", "Chiron Hei HK", SANS, ("yue",), readings=True),
    _packed("notoserifhk", "Noto Serif HK", SERIF, ("yue",), readings=True),
    _packed("chironsunghk", "Chiron Sung HK", SERIF, ("yue",), readings=True),
    _packed("bizudpgothic", "BIZ UDPGothic", SANS, ("ja",)),
    _packed("zenmarugothic", "Zen Maru Gothic", SANS, ("ja",)),
    _packed("notoserifjp", "Noto Serif JP", SERIF, ("ja",)),
    _packed("zenoldmincho", "Zen Old Mincho", SERIF, ("ja",)),
    _packed("kleeone", "Klee One", HANDWRITTEN, ("ja",)),
    _packed("notosanskr", "Noto Sans KR", SANS, ("ko",)),
    _packed("gowundodum", "Gowun Dodum", SANS, ("ko",)),
    _packed("notoserifkr", "Noto Serif KR", SERIF, ("ko",)),
    _packed("gowunbatang", "Gowun Batang", SERIF, ("ko",)),
    _packed("sarabun", "Sarabun", SANS, ("th",), changed=False),
    _packed("ibmplexsansthailooped", "IBM Plex Sans Thai Looped", SANS, ("th",), False),
    _packed("notoserifthai", "Noto Serif Thai", SERIF, ("th",)),
    _packed("ibmplexsansarabic", "IBM Plex Sans Arabic", SANS, ("ar",), changed=False),
    _packed("vazirmatn", "Vazirmatn", SANS, ("ar",)),
    _packed("amiri", "Amiri", SERIF, ("ar",), changed=False),
    _packed("mukta", "Mukta", SANS, ("deva",), changed=False),
    _packed("hind", "Hind", SANS, ("deva",), changed=False),
    _packed("notoserifdevanagari", "Noto Serif Devanagari", SERIF, ("deva",)),
    _packed("tirodevanagarihindi", "Tiro Devanagari Hindi", SERIF, ("deva",), False),
    _packed("inter", "Inter", SANS, ("latin", "vi", "cyrl")),
    _packed("atkinson", "Atkinson Hyperlegible Next", SANS, ("latin",)),
    _packed("literata", "Literata", SERIF, ("latin", "vi", "cyrl")),
    _packed("sourceserif4", "Source Serif 4", SERIF, ("latin", "vi", "cyrl")),
    _packed("notoserif", "Noto Serif", SERIF, ("vi",)),
    _packed("ptserif", "PT Serif", SERIF, ("cyrl",), changed=False),
)
"""The faces downloaded when they're chosen (polyglotic-hq 479's sheet,
482): Traditional Chinese's, Cantonese's, Japanese's and Korean's defaults
- downloaded when that language is captioned - and every other choice.
Built by `tools.caption_fonts packs`; LXGW WenKai, cut, is "Polyglotic
Kai" (its Reserved Font Name). Until one is here, the OS's own draws."""

FACES = {face.family: face for face in (*BUNDLED, *PACKED)}
BY_PACK = {face.pack: face for face in PACKED}

SCRIPTS = {
    "zh": "zh",
    "zh-hant": "zh-hant",
    "yue": "yue",
    "ja": "ja",
    "ko": "ko",
    "th": "th",
    "vi": "vi",
    "ar": "ar",
    "fa": "ar",
    "ur": "ar",
    "hi": "deva",
    "mr": "deva",
    "ne": "deva",
    "ru": "cyrl",
    "uk": "cyrl",
    "be": "cyrl",
}
"""A caption language's faces go by its script; every language not named
is written in Latin letters (or Greek, which the Latin face has too)."""

DEFAULTS = {
    "yue": "Noto Sans HK Captions",
    "ja": "Noto Sans JP Captions",
    "ko": "Pretendard",
    "th": "Noto Sans Thai Looped",
    "vi": "Be Vietnam Pro",
    "ar": "Noto Naskh Arabic Captions",
    "deva": "Noto Sans Devanagari",
    "cyrl": "PT Sans",
    "latin": "IBM Plex Sans",
}
"""Each script's bundled or downloaded default face (479's picks, DECISIONS
#207). Simplified (`zh`) and Traditional (`zh-hant`) Chinese default to this
OS's plain CJK UI face (`default_family`, polyglotic-hq 952) so captions stay
easy to read and OCR-friendly; calligraphy and kai faces stay choices in
`CHOICES`. Cantonese's, Japanese's and Korean's are downloaded (`PACKED`):
the OS's own draws until they're here."""

BEHIND = {"zh": "Noto Sans SC Captions", "zh-hant": "Noto Sans TC Captions"}
"""The script's sans behind a brushed Chinese face (532): draws the
characters Ma Shan Zheng hasn't (the rarer 1,342 of the 8,105) and the
readings over any brushed face (`Face.brushed`), and serves as a bundled
fallback when a minimal OS lacks system CJK fonts."""

WINDOWS = {
    "latin": ("Segoe UI Variable Display", "Segoe UI"),
    "zh": ("Microsoft YaHei UI", "Microsoft YaHei"),
    "zh-hant": ("Microsoft JhengHei UI", "Microsoft JhengHei"),
    "yue": ("Microsoft JhengHei UI", "Microsoft JhengHei"),
    "ja": ("Yu Gothic UI", "Meiryo UI"),
    "ko": ("Malgun Gothic",),
    "th": ("Leelawadee UI",),
    "ar": ("Segoe UI",),
    "deva": ("Nirmala UI",),
}
"""Windows' own faces for each script, after the default: what the
captions were drawn in before 482 - Thai's and Arabic's now named, as
Windows 11 has them (479: Qt's fallback was Tahoma)."""

ALL_SCRIPTS = tuple(dict.fromkeys((*SCRIPTS.values(), "latin")))
"""Every caption script the app configures faces for."""

CHOICES: dict[str, tuple[str, ...]] = {
    script_: tuple(
        dict.fromkeys(
            [
                *((DEFAULTS[script_],) if script_ in DEFAULTS else ()),
                *(
                    face.family
                    for face in (*BUNDLED, *PACKED)
                    if script_ in face.scripts
                ),
            ]
        )
    )
    for script_ in ALL_SCRIPTS
}
"""The faces Look's row for a script's language offers (482), by family:
its app default first when it has one, then the others the app carries, then
the downloaded ones."""

SCRIPT_SCALE_BOUNDS = (
    0.7,
    1.5,
)  # constant: visual-height matching envelope across scripts
"""Allowed range for per-script optical size matching (`SCRIPT_SCALES`)."""

SCRIPT_SCALES = {
    "latin": tunable(
        "fonts.script_scale.latin",
        1.0,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 reference: IBM Plex Sans Medium (cap 69.8, x 52.0, sentence ink 97.0 at 100 px)",
        applies=Applies.LIVE,
    ),
    "vi": tunable(
        "fonts.script_scale.vi",
        1.0,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 measured: Be Vietnam Pro Medium (x 53.0, cap 74.0 at 100 px; matches Latin x-height within 2 %)",
        applies=Applies.LIVE,
    ),
    "cyrl": tunable(
        "fonts.script_scale.cyrl",
        1.0,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 measured: PT Sans Regular (cap 70.0, x 50.0 at 100 px; matches Latin cap-height within 0.3 %)",
        applies=Applies.LIVE,
    ),
    "zh": tunable(
        "fonts.script_scale.zh",
        1.05,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655/766: Noto Sans SC sentence ink 95 px at 100 px, IBM Plex Sans 97 px",
        applies=Applies.LIVE,
    ),
    "zh-hant": tunable(
        "fonts.script_scale.zh_hant",
        1.05,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 script match: Traditional Chinese matches Simplified Chinese CJK visual scale",
        applies=Applies.LIVE,
    ),
    "yue": tunable(
        "fonts.script_scale.yue",
        1.05,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 script match: Cantonese Han characters match Simplified Chinese CJK visual scale",
        applies=Applies.LIVE,
    ),
    "ja": tunable(
        "fonts.script_scale.ja",
        1.05,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 measured: Yu Gothic UI fallback (sentence ink 87.0 at 100 px; at 1.05 -> 91.4 vs Latin 97.0) and Noto Sans JP CJK em-box",
        applies=Applies.LIVE,
    ),
    "ko": tunable(
        "fonts.script_scale.ko",
        1.05,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 measured: Malgun Gothic fallback (Hangul body 78.0 at 100 px; at 1.05 -> 81.9, matching CJK visual scale)",
        applies=Applies.LIVE,
    ),
    "th": tunable(
        "fonts.script_scale.th",
        1.0,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="655 measured: Noto Sans Thai Looped Medium (cap 71.4, x 53.9, base consonant 58.0 at 100 px; matches Latin within 4 %)",
        applies=Applies.LIVE,
    ),
    "ar": tunable(
        "fonts.script_scale.ar",
        1.15,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="482/655 measured: Noto Naskh Arabic Captions (body 47.0 at 100 px; at 1.15 -> 54.1 vs Latin x-height 52.0, within 4 %)",
        applies=Applies.LIVE,
    ),
    "deva": tunable(
        "fonts.script_scale.deva",
        1.1,
        "scale",
        SCRIPT_SCALE_BOUNDS,
        source="482/655 measured: Noto Sans Devanagari Medium (consonant body 62.2 at 100 px; at 1.10 -> 68.4 vs Latin cap-height 69.8, within 2 %)",
        applies=Applies.LIVE,
    ),
}
"""Each script's visual-height scale relative to Latin (`size`), measured from
the bundled fonts' glyph heights so 100 % reads at the same visual size across
scripts (482, 655)."""

CALLIGRAPHY_SCALE = tunable(
    "fonts.script_scale.chinese_calligraphy",
    1.13,
    "scale",
    SCRIPT_SCALE_BOUNDS,
    source="766 Windows grabs: Ma Shan Zheng median 90.5 px vs Noto Sans SC 97 px at scale 1.05",
    applies=Applies.LIVE,
)

SIZES = {
    script_: item.default
    for script_, item in SCRIPT_SCALES.items()
    if item.default != 1.0
}
"""Default non-1.0 script scales, for callers inspecting the static table."""

UPRIGHT_SCRIPTS = frozenset({"ar", "zh", "zh-hant", "yue", "ja", "ko"})
"""Scripts never slanted: Arabic has no italic, and a slant made up for it
reads as a mistake (479); nor have Chinese, Japanese and Korean - the
computer's slant of them is harder to read, in the quiet view and in a
provisional line alike (polyglotic-hq 526, DECISIONS #230 item 3)."""


def script(language: str | None) -> str:
    """The script a caption language is written in (`SCRIPTS`)."""
    return SCRIPTS.get(language or "", "latin")


def own(script_: str, system: str = sys.platform) -> tuple[str, ...]:
    """The OS's own faces for `script_`: Windows' names, then this OS's."""
    return (*WINDOWS.get(script_, ()), *also(script_, system))


def platform_own(script_: str, system: str = sys.platform) -> tuple[str, ...]:
    """This OS's own faces for `script_`: its own (`also`) on macOS/Linux,
    else Windows' (`WINDOWS`)."""
    return also(script_, system) or WINDOWS.get(script_, ())


def default_family(script_: str, system: str = sys.platform) -> str | None:
    """The default caption face for `script_` on `system`: the app's own
    (`DEFAULTS`), or this OS's primary UI face where the script defaults to
    the platform face (Simplified and Traditional Chinese, polyglotic-hq 952)."""
    if script_ in DEFAULTS:
        return DEFAULTS[script_]
    faces = platform_own(script_, system)
    return faces[0] if faces else None


def listed_own(script_: str, system: str = sys.platform) -> tuple[str, ...]:
    """The OS's own faces Look's row lists for `script_`: its own, or the
    Latin ones for a script Windows draws in them (Vietnamese, Cyrillic)."""
    return own(script_, system) if script_ in WINDOWS else own("latin", system)


def caption_families(
    language: str | None, chosen: str | None = None, system: str = sys.platform
) -> tuple[str, ...]:
    """The families a caption in `language` is drawn in, first to last:
    `chosen` (the learner's face for it), its script's default (or this OS's
    plain UI face for Chinese), the sans behind a brushed face (`BEHIND`),
    the OS's own for its script, then the Latin ones for the Latin letters
    in it."""
    script_ = script(language)
    behind = BEHIND.get(script_)
    if script_ in DEFAULTS:
        found: list[str | None] = [
            chosen,
            DEFAULTS[script_],
            behind,
            *own(script_, system),
        ]
    elif brushed(chosen):
        found = [
            chosen,
            behind,
            *platform_own(script_, system),
            *own(script_, system),
        ]
    else:
        found = [
            chosen,
            *platform_own(script_, system),
            *own(script_, system),
            behind,
        ]
    if script_ != "latin":
        found += [DEFAULTS["latin"], *own("latin", system)]
    return tuple(dict.fromkeys(family for family in found if family))


def reading_families(families: Sequence[str]) -> list[str]:
    """`families` (a caption's) without the faces that don't draw readings
    (`Face.brushed`): a reading over Ma Shan Zheng is in Noto Sans SC, over
    LXGW WenKai TC in Noto Sans TC."""
    kept = [f for f in families if not brushed(f)]
    return kept or list(families)


def brushed(family: str | None) -> bool:
    """Whether only the Han characters of a line in `family` are drawn in
    it (`Face.brushed`)."""
    face = FACES.get(family or "")
    return face is not None and face.brushed


def _latin(char: str) -> bool:
    """A Latin letter (with any accent, Vietnamese's too), a digit, or
    ASCII's punctuation and symbols - not full-width forms, nor the
    punctuation Chinese shares (“”, ·, —, …), which its faces draw."""
    point = ord(char)
    return (
        0x21 <= point <= 0x7E
        or (0xC0 <= point <= 0x24F and point not in (0xD7, 0xF7))
        or 0x1E00 <= point <= 0x1EFF
    )


_SPACES = frozenset(" \u00a0")
_WITHIN = _SPACES | {"\u2019"}
"""Kept in a Latin run between two of its characters: the space of "machine
learning", and the apostrophe of "don't"."""
_MARKS = range(0x300, 0x370)
"""Combining accents: part of the letter before them."""


def latin_runs(text: str) -> tuple[tuple[int, int], ...]:
    """The Latin runs in a line of Chinese, as `[start, end)` character
    spans: its letters, digits and Latin punctuation - "focus", "2026",
    "3.5%", "Wi-Fi" - with the spaces between them and after them, for the
    Latin captions' face (`Face.brushed`, 551). A space after a word goes
    with it: a word and its space are measured alone (`views.pour`), and
    so are as wide there as in the line."""
    runs: list[tuple[int, int]] = []
    start = end = -1
    for index, char in enumerate(text):
        if _latin(char) or (end == index and ord(char) in _MARKS):
            if start < 0:
                start = index
            end = index + 1  # spaces before it, between two Latin ones, kept
        elif start >= 0 and char not in _WITHIN:
            runs.append((start, _spaced(text, end)))
            start = end = -1
    if start >= 0:
        runs.append((start, _spaced(text, end)))
    return tuple(runs)


def _spaced(text: str, end: int) -> int:
    """Where a run ending at `end` ends with the spaces after it."""
    while end < len(text) and text[end] in _SPACES:
        end += 1
    return end


def size(language: str | None, family: str | None = None) -> float:
    """Optical scale for the script, with a separate default for brush faces."""
    if brushed(family):
        return CALLIGRAPHY_SCALE.value
    item = SCRIPT_SCALES.get(script(language))
    return item.value if item is not None else 1.0


def upright(language: str | None, family: str | None = None) -> bool:
    """Whether a caption in `language`, in `family`, is never slanted:
    Arabic's, and a face drawn slanted already (its own italic)."""
    face = FACES.get(family or "")
    return script(language) in UPRIGHT_SCRIPTS or (face is not None and face.upright)
