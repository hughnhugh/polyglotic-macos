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
choice for it, else its default (`DEFAULTS`, 479's picks) - carried by
the app where it's small (`BUNDLED`, in ui/assets/fonts) - then the OS's
own faces for its script, named, so Thai and Arabic are never left to
Qt's fallback (Tahoma, 479), then the Latin ones for the Latin letters a
caption holds. A face the app doesn't have yet is passed over by Qt, so
the OS's own draws until it comes. Plain Python: the faces are added to
Qt's fonts by `caption_faces`.
"""

import sys
from dataclasses import dataclass

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


def also(script: str, system: str = sys.platform) -> tuple[str, ...]:
    """This OS's fonts for `script`, to follow Windows' in a font list -
    none on Windows."""
    return OTHER_OS.get(system, {}).get(script, ())


# -- Captions -------------------------------------------------------------

SANS, SERIF, HANDWRITTEN = "sans", "serif", "handwritten"
"""What kind of face: how a language's list groups them (Look)."""


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
    """The scripts Look offers it for (a downloaded face's)."""

    @property
    def name(self) -> str:
        return self.shown or self.family


BUNDLED = (
    Face(
        "Noto Sans SC Captions",
        files=("NotoSansSC-Medium.ttf", "NotoSansSC-SemiBold.ttf"),
        shown="Noto Sans SC",
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
small scripts' defaults and Simplified Chinese's - Noto Sans SC cut to the
8,105 General Standard characters and GB2312, with a SemiBold of what
readings draw, so pinyin is never in a made-up bold. The two whose shape
isn't their maker's (cut, or another line box) have a family name of their
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
) -> Face:
    """A downloaded face: `changed` (cut or fixed at a weight by
    `tools.caption_fonts`) has a family of its own, "<name> Captions"."""
    family = family or (f"{name} Captions" if changed else name)
    return Face(family, kind, (), upright, name, pack, scripts)


PACKED = (
    # the defaults of the languages whose faces are big (479: delivery C)
    _packed("notosanstc", "Noto Sans TC", SANS, ("zh-hant",)),
    _packed("notosanshk", "Noto Sans HK", SANS, ("yue",)),
    _packed("notosansjp", "Noto Sans JP", SANS, ("ja",)),
    _packed("pretendard", "Pretendard", SANS, ("ko",), changed=False),
    # every other face 479's sheet offers
    _packed("smileysans", "Smiley Sans", SANS, ("zh",), changed=False, upright=True),
    _packed("notoserifsc", "Noto Serif SC", SERIF, ("zh",)),
    _packed("zhuquefangsong", "Zhuque Fangsong", SERIF, ("zh",)),
    _packed(
        "polyglotickai", "Polyglotic Kai", HANDWRITTEN, ("zh",), family="Polyglotic Kai"
    ),
    _packed("huninn", "jf open Huninn", SANS, ("zh-hant",)),
    _packed("notoseriftc", "Noto Serif TC", SERIF, ("zh-hant",)),
    _packed("lxgwwenkaitc", "LXGW WenKai TC", HANDWRITTEN, ("zh-hant",)),
    _packed("chironheihk", "Chiron Hei HK", SANS, ("yue",)),
    _packed("notoserifhk", "Noto Serif HK", SERIF, ("yue",)),
    _packed("chironsunghk", "Chiron Sung HK", SERIF, ("yue",)),
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
    "zh": "Noto Sans SC Captions",
    "zh-hant": "Noto Sans TC Captions",
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
"""Each script's default face (479's picks, DECISIONS #207). Traditional
Chinese's, Cantonese's, Japanese's and Korean's are downloaded (`PACKED`):
the OS's own draws until they're here."""

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

CHOICES: dict[str, tuple[str, ...]] = {
    script: tuple(
        dict.fromkeys(
            [default, *(face.family for face in PACKED if script in face.scripts)]
        )
    )
    for script, default in DEFAULTS.items()
}
"""The faces Look's row for a script's language offers (482), by family:
its default first, then the downloaded ones."""

SIZES = {"zh": 1.05, "zh-hant": 1.05, "yue": 1.05, "ja": 1.05, "ar": 1.15, "deva": 1.1}
"""A script's text drawn a little larger than Latin at the same pixel
size: Chinese and Japanese, whose denser strokes read as easily (today's
overlay's); Arabic and Devanagari, whose letters' bodies are smaller than
Latin's x-height in their faces (482's measure: Noto Naskh Arabic's 0.47
of its size, IBM Plex Sans' x-height 0.53; Noto Sans Devanagari's 0.62
against Nirmala UI's 0.73)."""

UPRIGHT_SCRIPTS = frozenset({"ar"})
"""Scripts never slanted: Arabic has no italic, and a slant made up for it
reads as a mistake (479)."""


def script(language: str | None) -> str:
    """The script a caption language is written in (`SCRIPTS`)."""
    return SCRIPTS.get(language or "", "latin")


def own(script_: str, system: str = sys.platform) -> tuple[str, ...]:
    """The OS's own faces for `script_`: Windows' names, then this OS's."""
    return (*WINDOWS.get(script_, ()), *also(script_, system))


def listed_own(script_: str, system: str = sys.platform) -> tuple[str, ...]:
    """The OS's own faces Look's row lists for `script_`: its own, or the
    Latin ones for a script Windows draws in them (Vietnamese, Cyrillic)."""
    return own(script_, system) if script_ in WINDOWS else own("latin", system)


def caption_families(
    language: str | None, chosen: str | None = None, system: str = sys.platform
) -> tuple[str, ...]:
    """The families a caption in `language` is drawn in, first to last:
    `chosen` (the learner's face for it), its script's default, the OS's
    own for its script, then the Latin ones for the Latin letters in it."""
    script_ = script(language)
    found = [chosen, DEFAULTS.get(script_), *own(script_, system)]
    if script_ != "latin":
        found += [DEFAULTS["latin"], *own("latin", system)]
    return tuple(dict.fromkeys(family for family in found if family))


def size(language: str | None) -> float:
    """How much larger `language`'s text is drawn than Latin (`SIZES`)."""
    return SIZES.get(script(language), 1.0)


def upright(language: str | None, family: str | None = None) -> bool:
    """Whether a caption in `language`, in `family`, is never slanted:
    Arabic's, and a face drawn slanted already (its own italic)."""
    face = FACES.get(family or "")
    return script(language) in UPRIGHT_SCRIPTS or (face is not None and face.upright)
