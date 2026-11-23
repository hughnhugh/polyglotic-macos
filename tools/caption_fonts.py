"""How the captions' bundled faces in src/polyglotic_desktop/ui/assets/fonts
were made (polyglotic-hq 479, 482; decision 0223). Not part of the build:
the outputs are committed. Run from the repo, with uv:

    uv run --with fonttools==4.60.1 python -m tools.caption_fonts OUT_DIR
    # the faces downloaded when chosen, for `tools.package.publish_packs --fonts`
    uv run --with fonttools==4.60.1 python -m tools.caption_fonts OUT_DIR --packs

1. each source from a pinned commit (google/fonts, IBM/plex) and the
   8,105-character list, checked against the SHA-256s recorded below;
2. the faces shipped as their makers publish them where a Reserved Font
   Name forbids changing them (PT Sans, IBM Plex Sans) or a static Medium
   exists (Be Vietnam Pro): copied byte for byte;
3. the others, variable fonts, fixed at Medium (500) - the captions' weight
   (`caption_layout.CaptionStyle.weight`);
4. Noto Naskh Arabic's line box fitted to real Arabic (`NASKH_BOX`);
5. Noto Sans SC cut to the 8,105 General Standard characters and GB2312
   (every HSK 1-9 character; 479's sets), with a SemiBold (600) cut of
   what readings draw (pinyin, zhuyin, Jyutping's digits), so a reading is
   never in a made-up bold; both given Microsoft YaHei UI's line box, so a
   Chinese row is as tall as before (479 section 4: Noto's is 14 % taller);
6. Ma Shan Zheng, Simplified Chinese's calligraphy default (polyglotic-hq
   532), static at Regular, cut the same way (it holds GB2312's characters
   and Latin letters, no pinyin tone marks) and given the same line box.

The three whose shape differs from their maker's - cut, or another line
box - are named "... Captions": some Windows 11 PCs have Noto Sans SC of their
own, and Qt took that one's line box for ours under one name (482).

With `--packs`, the faces downloaded when they're chosen (`fonts.PACKED`)
are made the same way into OUT_DIR, each pack's files named
`<pack>-<style>-<version>.<ext>` beside `fonts.json` (each pack's family,
credit and files), which `publish_packs --fonts` publishes: the CJK faces
cut to their language's standard set (Big5, Big5 + HKSCS, JIS levels 1
and 2, all Hangul) with the line box of the Windows face they replace, a
SemiBold of the readings for Chinese faces that go that heavy; the
others fixed at Medium; the faces with a Reserved Font Name copied as
published (Pretendard, Smiley Sans, PT Serif, IBM Plex Sans Thai Looped
and Arabic) - except LXGW WenKai, which is cut and so named
"Polyglotic Kai". Faces published static at Medium are copied too.

The results' SHA-256s are printed, to compare with the committed files.
"""

import argparse
import hashlib
import json
import os
import shutil
import urllib.request
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

GOOGLE_FONTS = "7af0d90b4d532ffa4b041937b560c6df4e7b1e95"  # google/fonts, 2026-11-18
PLEX = "1da12f02587b630c07e92692d21492d722f53614"  # IBM/plex, @ibm/plex-sans@1.1.0
TGSCC = "d9b599a9c9cc0dd2d58cad829e285bc780cd4451"
"""shengdoushi/common-standard-chinese-characters-table: the Table of
General Standard Chinese Characters (2013), its three levels."""
SOURCE_DATE_EPOCH = (
    "1795392000"  # 2026-11-18: the faces' own date, so the output repeats
)


def _gf(folder: str, file: str) -> str:
    quoted = file.replace("[", "%5B").replace("]", "%5D").replace(",", "%2C")
    return f"https://raw.githubusercontent.com/google/fonts/{GOOGLE_FONTS}/ofl/{folder}/{quoted}"


_PLEX = f"https://raw.githubusercontent.com/IBM/plex/{PLEX}/packages/plex-sans"
_TABLE = f"https://raw.githubusercontent.com/shengdoushi/common-standard-chinese-characters-table/{TGSCC}"

SOURCES: dict[str, tuple[str, str]] = {
    "NotoSansSC[wght].ttf": (
        _gf("notosanssc", "NotoSansSC[wght].ttf"),
        "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da",
    ),
    "NotoSansThaiLooped[wdth,wght].ttf": (
        _gf("notosansthailooped", "NotoSansThaiLooped[wdth,wght].ttf"),
        "a6d220ea215bc2c4bfcd5c5efc4103e20302443f87f6dca7a9ce733a11f2cfbd",
    ),
    "NotoNaskhArabic[wght].ttf": (
        _gf("notonaskharabic", "NotoNaskhArabic[wght].ttf"),
        "67b5a525a661b607971fbd3f96a81b89d3a768e74534fca84f18ac97e6fab72f",
    ),
    "NotoSansDevanagari[wdth,wght].ttf": (
        _gf("notosansdevanagari", "NotoSansDevanagari[wdth,wght].ttf"),
        "14ec4af41f27482216d1c2229f417ff9b1425e1babb014e57d1d40d03229853e",
    ),
    "BeVietnamPro-Medium.ttf": (
        _gf("bevietnampro", "BeVietnamPro-Medium.ttf"),
        "b60832bfa0fcd015158112c64d7e3fdad3b0c6287d1823f85a3103636e845268",
    ),
    "BeVietnamPro-MediumItalic.ttf": (
        _gf("bevietnampro", "BeVietnamPro-MediumItalic.ttf"),
        "b7d43a5f943048f7d4e49a080052acce1902f1eab07f4160299d84abab8119fa",
    ),
    "PT_Sans-Web-Regular.ttf": (
        _gf("ptsans", "PT_Sans-Web-Regular.ttf"),
        "9cc831490532009bae2b3ce0d39c62adfc889060beb421593bfd9d2396d0f10a",
    ),
    "PT_Sans-Web-Italic.ttf": (
        _gf("ptsans", "PT_Sans-Web-Italic.ttf"),
        "5a90fe2d0cd798700935240580bdcc12c0ffc9102c0c7163b3418e13bc21debd",
    ),
    "IBMPlexSans-Medium.ttf": (
        f"{_PLEX}/fonts/complete/ttf/IBMPlexSans-Medium.ttf",
        "331c8639d7598b2cde62a911a71db195e30cb655cd6bdf2e324a7e984955f907",
    ),
    "IBMPlexSans-MediumItalic.ttf": (
        f"{_PLEX}/fonts/complete/ttf/IBMPlexSans-MediumItalic.ttf",
        "9928852bf60d82fdbbfe30eac86bcecd611e4188f0fa4d98938560659fa99c64",
    ),
    "MaShanZheng-Regular.ttf": (
        _gf("mashanzheng", "MaShanZheng-Regular.ttf"),
        "6d2546bb189c732a8ca29af9e22457b152387d158aa459e4ac2ce1e51788b7fb",
    ),
    "tgscc-level-1.txt": (
        f"{_TABLE}/level-1.txt",
        "79a6c710013cc86617d5db65871f59b2d67dee72415d380a2cc7145a51450fe4",
    ),
    "tgscc-level-2.txt": (
        f"{_TABLE}/level-2.txt",
        "d597a6e99ea7b8c41215081f824c6e8587bf1c9a3f45fb13086a826306789785",
    ),
    "tgscc-level-3.txt": (
        f"{_TABLE}/level-3.txt",
        "c9fbc83a9f8cd860306b218bf16c6a4cc56d7c4a22a686d403b176a0dbec7931",
    ),
    "NotoSansSC-OFL.txt": (
        _gf("notosanssc", "OFL.txt"),
        "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    ),
    "MaShanZheng-OFL.txt": (
        _gf("mashanzheng", "OFL.txt"),
        "d7bdb1cee215b689e23c2f95672a6084c790542170648267a55114103d756a08",
    ),
    "NotoSansThaiLooped-OFL.txt": (
        _gf("notosansthailooped", "OFL.txt"),
        "dad6e6abc2bf3fc37cc698af7607c3f4d4235039695713b222e5a034fb5b9b1c",
    ),
    "NotoNaskhArabic-OFL.txt": (
        _gf("notonaskharabic", "OFL.txt"),
        "a7a5a25eb188bf1cd96982030d53e23c33485c69b1044a562254226857ee13af",
    ),
    "NotoSansDevanagari-OFL.txt": (
        _gf("notosansdevanagari", "OFL.txt"),
        "a216f6f8d85c7228093e0ee5e258d9d377e6671f68acb4db1930b29583d0f331",
    ),
    "BeVietnamPro-OFL.txt": (
        _gf("bevietnampro", "OFL.txt"),
        "6b7f8f73609a25ea78c891e34cf37b06f8a676b7ea986e941e43b009110f2a85",
    ),
    "PTSans-OFL.txt": (
        _gf("ptsans", "OFL.txt"),
        "2758cf7a872827f39661cf8cc24188113c030447aefb5ca7145993650076ca8c",
    ),
    "IBMPlexSans-OFL.txt": (
        f"{_PLEX}/LICENSE.txt",
        "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
    ),
}
"""Each source: where it comes from, and its SHA-256."""

COPIED = {
    "BeVietnamPro-Medium.ttf": "BeVietnamPro-Medium.ttf",
    "BeVietnamPro-MediumItalic.ttf": "BeVietnamPro-MediumItalic.ttf",
    "PTSans-Regular.ttf": "PT_Sans-Web-Regular.ttf",
    "PTSans-Italic.ttf": "PT_Sans-Web-Italic.ttf",
    "IBMPlexSans-Medium.ttf": "IBMPlexSans-Medium.ttf",
    "IBMPlexSans-MediumItalic.ttf": "IBMPlexSans-MediumItalic.ttf",
}
"""Faces shipped as published: output name -> source."""

LICENCES = (
    "NotoSansSC-OFL.txt",
    "MaShanZheng-OFL.txt",
    "NotoSansThaiLooped-OFL.txt",
    "NotoNaskhArabic-OFL.txt",
    "NotoSansDevanagari-OFL.txt",
    "BeVietnamPro-OFL.txt",
    "PTSans-OFL.txt",
    "IBMPlexSans-OFL.txt",
)

YAHEI_UI_BOX = (1016, 254)
"""Microsoft YaHei UI's line box (usWinAscent 2080, usWinDescent 521 of
2048 units) at 1,000 units: what a Chinese caption row's height has been."""

NASKH_BOX = (950, 450)
"""Noto Naskh Arabic's line box made to fit real text: its own (1,069 above,
634 below) is 1.7 times its size, a row 40 % taller than Tahoma's; the ink
of 300 FLEURS Arabic sentences reaches 0.93 above and 0.43 below at the
95th percentile (482's measure), so a rare mark below may reach into the
room above the next row's letters, never into them."""

READING_CHARS = (
    {chr(c) for c in range(0x20, 0x7F)}
    | set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüĀÁǍÀĒÉĚÈĪÍǏÌŌÓǑÒŪÚǓÙǕǗǙǛÜńňǹḿ")
    | {chr(c) for c in range(0x3100, 0x3130)}
    | {chr(c) for c in range(0x31A0, 0x31C0)}
    | set("ˉˊˇˋ˙·")
)
"""What a reading line draws: pinyin with its tone marks, zhuyin and its
tone marks, Jyutping's letters and digits."""


@dataclass(frozen=True)
class Instance:
    """A variable font fixed at `weight` - or a static one, at its own -
    named `family` `style`, maybe cut to `chars` and given `box` (ascent,
    descent at 1,000 units)."""

    out: str
    source: str
    family: str
    weight: int
    chars: str | None = None
    box: tuple[int, int] | None = None


INSTANCES = (
    Instance(
        "NotoSansSC-Medium.ttf",
        "NotoSansSC[wght].ttf",
        "Noto Sans SC Captions",
        500,
        "sc",
        YAHEI_UI_BOX,
    ),
    Instance(
        "NotoSansSC-SemiBold.ttf",
        "NotoSansSC[wght].ttf",
        "Noto Sans SC Captions",
        600,
        "readings",
        YAHEI_UI_BOX,
    ),
    Instance(
        "MaShanZheng-Regular.ttf",
        "MaShanZheng-Regular.ttf",
        "Ma Shan Zheng Captions",
        400,
        "sc",
        YAHEI_UI_BOX,
    ),
    Instance(
        "NotoSansThaiLooped-Medium.ttf",
        "NotoSansThaiLooped[wdth,wght].ttf",
        "Noto Sans Thai Looped",
        500,
    ),
    Instance(
        "NotoNaskhArabic-Medium.ttf",
        "NotoNaskhArabic[wght].ttf",
        "Noto Naskh Arabic Captions",
        500,
        box=NASKH_BOX,
    ),
    Instance(
        "NotoSansDevanagari-Medium.ttf",
        "NotoSansDevanagari[wdth,wght].ttf",
        "Noto Sans Devanagari",
        500,
    ),
)
STYLE = {400: "Regular", 500: "Medium", 600: "SemiBold"}


def fetch(sources: Path) -> None:
    """Each source into `sources`, unless it's there; every one checked."""
    sources.mkdir(parents=True, exist_ok=True)
    for name, (url, sha256) in SOURCES.items():
        path = sources / name
        if not path.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                path.write_bytes(response.read())
        found = hashlib.sha256(path.read_bytes()).hexdigest()
        if found != sha256:
            raise SystemExit(f"{name}: SHA-256 {found}, expected {sha256}")


def _gb2312() -> set[str]:
    found = set()
    for lead in range(0xB0, 0xF8):
        for trail in range(0xA1, 0xFF):
            try:
                text = bytes((lead, trail)).decode("gb2312")
            except UnicodeDecodeError:
                continue
            found.add(text)
    return found


def _extras() -> set[str]:
    """Beside a cut's characters: Latin and its pinyin letters, punctuation,
    CJK punctuation, zhuyin, full- and half-width forms."""
    found: set[str] = set()
    for low, high in (
        (0x20, 0x7E),
        (0xA0, 0xFF),
        (0x100, 0x17F),
        (0x1CD, 0x1DC),
        (0x2C7, 0x2D9),
        (0x300, 0x36F),
        (0x2000, 0x206F),
        (0x20AC, 0x20AC),
        (0x2190, 0x2193),
        (0x3000, 0x303F),
        (0x3100, 0x312F),
        (0x31A0, 0x31BF),
        (0xFE30, 0xFE4F),
        (0xFF00, 0xFFEF),
    ):
        found |= {chr(c) for c in range(low, high + 1)}
    return found


def simplified(sources: Path) -> set[str]:
    """The 8,105 General Standard characters, GB2312's and the extras."""
    table = set()
    for level in (1, 2, 3):
        text = (sources / f"tgscc-level-{level}.txt").read_text(encoding="utf-8")
        table |= {line.strip() for line in text.splitlines() if line.strip()}
    return table | _gb2312() | _extras()


def build(sources: Path, out: Path) -> None:
    from fontTools import subset  # type: ignore[import-not-found]
    from fontTools.ttLib import TTFont  # type: ignore[import-not-found]
    from fontTools.varLib import instancer  # type: ignore[import-not-found]

    os.environ["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    out.mkdir(parents=True, exist_ok=True)
    sets = {"sc": simplified(sources), "readings": READING_CHARS}
    for target, source in COPIED.items():
        shutil.copyfile(sources / source, out / target)
    for licence in LICENCES:
        text = (sources / licence).read_bytes().replace(b"\r\n", b"\n")
        (out / licence).write_bytes(text)
    for face in INSTANCES:
        font = TTFont(sources / face.source)
        if face.chars is not None:
            options = subset.Options()
            options.layout_features = ["*"]
            options.name_IDs = ["*"]
            options.name_languages = ["*"]
            options.notdef_outline = True
            subsetter = subset.Subsetter(options)
            subsetter.populate(unicodes=sorted(ord(c) for c in sets[face.chars]))
            subsetter.subset(font)
        if "fvar" in font:  # a static face (Ma Shan Zheng) is at its own weight
            axes = {axis.axisTag: axis for axis in font["fvar"].axes}
            location = {tag: axis.defaultValue for tag, axis in axes.items()}
            location["wght"] = face.weight
            font = instancer.instantiateVariableFont(font, location)
        _name(font, face.family, STYLE[face.weight], face.weight)
        if face.box is not None:
            _box(font, *face.box)
        font.save(out / face.out)
    for path in sorted(out.glob("*.ttf")):
        print(hashlib.sha256(path.read_bytes()).hexdigest(), path.name)


def _name(
    font: object, family: str, style: str, weight: int, italic: bool = False
) -> None:
    """One face of `family` named as Google Fonts' static ones are: Qt
    groups the faces by the typographic names (16, 17)."""
    upright = style
    if italic:
        style = "Italic" if style == "Regular" else f"{style} Italic"
    name = font["name"]  # type: ignore[index]
    for record in list(name.names):
        if record.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
            name.removeNames(nameID=record.nameID)
    version = name.getDebugName(5) or ""
    postscript = f"{family}-{style}".replace(" ", "")
    for name_id, text in (
        (1, f"{family} {upright}"),
        (2, "Italic" if italic else "Regular"),
        (3, f"{version};Polyglotic;{postscript}"),
        (4, f"{family} {style}"),
        (6, postscript),
        (16, family),
        (17, style),
    ):
        name.setName(text, name_id, 3, 1, 0x409)
    os2 = font["OS/2"]  # type: ignore[index]
    os2.usWeightClass = weight
    os2.fsSelection = (os2.fsSelection & ~(1 | 32 | 64)) | (1 if italic else 64)
    head = font["head"]  # type: ignore[index]
    head.macStyle = (head.macStyle & ~3) | (2 if italic else 0)
    if "STAT" in font:  # type: ignore[operator]
        del font["STAT"]  # type: ignore[attr-defined]


def _box(font: object, ascent: int, descent: int) -> None:
    """The face's line box: `ascent` above the baseline, `descent` below,
    at 1,000 units - for Windows (usWin), macOS (hhea) and the typo
    metrics alike, so every OS lays a row out as tall."""
    scale = font["head"].unitsPerEm / 1000  # type: ignore[index]
    up, down = round(ascent * scale), round(descent * scale)
    os2, hhea = font["OS/2"], font["hhea"]  # type: ignore[index]
    os2.usWinAscent, os2.usWinDescent = up, down
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = up, -down, 0
    os2.fsSelection |= 128  # USE_TYPO_METRICS: the same box from either
    hhea.ascent, hhea.descent, hhea.lineGap = up, -down, 0


_GF_PACK_SOURCES = (
    (
        "notosanstc",
        "NotoSansTC[wght].ttf",
        "864727d210d54f2537bbe23b3a839436c3992af72de9322af5270897246bd44f",
    ),
    (
        "notosanshk",
        "NotoSansHK[wght].ttf",
        "76098ee78ec234cd4f8c950742b3f766fea2f8b43d5180d901048f4fc86c6849",
    ),
    (
        "notosansjp",
        "NotoSansJP[wght].ttf",
        "c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f",
    ),
    (
        "notoserifsc",
        "NotoSerifSC[wght].ttf",
        "050080d9255a86808f2945bffac582b31ef32bc36411ce29563b4961670c66f9",
    ),
    (
        "huninn",
        "Huninn-Regular.ttf",
        "1bd770a5ffc0c06723b567686f8b5db5abf9ab54227f3bbc4e6fd648f4698805",
    ),
    (
        "notoseriftc",
        "NotoSerifTC[wght].ttf",
        "0077e18f57c6908f4a000969880940bdb0dad057c0e8d98b49dc364c3d1b09c6",
    ),
    (
        "lxgwwenkaitc",
        "LXGWWenKaiTC-Regular.ttf",
        "4fcc5aec11cbbf737b0cfab7b63796f7f280087a7a656b2f13342cd5e5318d95",
    ),
    (
        "chironheihk",
        "ChironHeiHK[wght].ttf",
        "0d788ded72dc88f478818182179af4c7cd143df0bf86557d29729ab132333930",
    ),
    (
        "chironheihk",
        "ChironHeiHK-Italic[wght].ttf",
        "e9e78771ef2cedf21cc01cf3f547036f55e5b183190473cb6f3804f49507707b",
    ),
    (
        "notoserifhk",
        "NotoSerifHK[wght].ttf",
        "66108860e321aa413e7cb346448b4a418b779d94ae392accb32d163c024ae661",
    ),
    (
        "chironsunghk",
        "ChironSungHK[wght].ttf",
        "c88d5db947f4aad3399105d2c1c808a64580ab65e8cb26e58bb81cd96843d130",
    ),
    (
        "bizudpgothic",
        "BIZUDPGothic-Regular.ttf",
        "258d7156c165f2ff774b6efee637c22c3b950de0d8a10e501137061bc8085d01",
    ),
    (
        "zenmarugothic",
        "ZenMaruGothic-Medium.ttf",
        "3cfdb98a13571ede17fcc769f5093a97c38b80a7b9b2ab754a26b4d822092b3b",
    ),
    (
        "notoserifjp",
        "NotoSerifJP[wght].ttf",
        "2fd527ba12b6a44ec30d796d633360da0aeba6c5d4af1304ce12bb4dc15a7dfc",
    ),
    (
        "zenoldmincho",
        "ZenOldMincho-Medium.ttf",
        "e60c7961e5110d0f08f902de43fe60865f1538845ff2092c779837257efac3bf",
    ),
    (
        "kleeone",
        "KleeOne-SemiBold.ttf",
        "b031ec426c23ca1143ef1f7d58bee7a79efe119ed654152f121c922202b303fd",
    ),
    (
        "notosanskr",
        "NotoSansKR[wght].ttf",
        "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252",
    ),
    (
        "gowundodum",
        "GowunDodum-Regular.ttf",
        "a6e457933227483a11758fd0947bc74422a106d46f0bf057fdaa5af94a30067d",
    ),
    (
        "notoserifkr",
        "NotoSerifKR[wght].ttf",
        "11f8d5de6f1b79195efba3828aaa2ec95c1178f5ae976fb23c8d53250a9938f3",
    ),
    (
        "gowunbatang",
        "GowunBatang-Regular.ttf",
        "466c593e7147412e748af4856d5ad14709b5a860bdf62b9c2546f2c5874e9849",
    ),
    (
        "sarabun",
        "Sarabun-Medium.ttf",
        "cc7c3016daab3321674fdf6e2ef59850dc0c07503de1cbdb8b90fe8080ada2b4",
    ),
    (
        "sarabun",
        "Sarabun-MediumItalic.ttf",
        "263e6bb51d80c228c201a0770e6100181115119fdca7968445d44d2fb94ab009",
    ),
    (
        "ibmplexsansthailooped",
        "IBMPlexSansThaiLooped-Medium.ttf",
        "0219cd6e21c9bb226378fa60ebd73e2550b1adb245fec821c817e2b1efcb1f04",
    ),
    (
        "notoserifthai",
        "NotoSerifThai[wdth,wght].ttf",
        "34a7ad11647c845303aabdde639059806c56b84719e5d2ceb28eb038711bdf53",
    ),
    (
        "ibmplexsansarabic",
        "IBMPlexSansArabic-Medium.ttf",
        "b8363ab9f733dfa4f8e96b8b2102c24b5cf4110fb96d1d3d9a9412f6fb49cf74",
    ),
    (
        "vazirmatn",
        "Vazirmatn[wght].ttf",
        "696249a2c74b39ffdef55de4df2809c5b639d3ff80d618d8160a095d2fd49dca",
    ),
    (
        "amiri",
        "Amiri-Regular.ttf",
        "ab391c4147d054c48976e98322ad0eefe1427aa0e0502a12a4c75d80a70cfcd7",
    ),
    (
        "mukta",
        "Mukta-Medium.ttf",
        "4db18bd8f19582607e8a6af0c4bf158b4b3378b426e42ad39d444d216c70074c",
    ),
    (
        "hind",
        "Hind-Medium.ttf",
        "70f9c1158390d0c93a8bc24b35b4be4b2439653372bbce7381a32c686fb91a98",
    ),
    (
        "notoserifdevanagari",
        "NotoSerifDevanagari[wdth,wght].ttf",
        "1191e07bfeb062d80e252eb85b0eafdfbda1e350707a2a60628668e8f677dbbb",
    ),
    (
        "tirodevanagarihindi",
        "TiroDevanagariHindi-Regular.ttf",
        "d2abcb4d352f0bfab91632df5d9c8173882073c182e662fa731a5a738e6681d7",
    ),
    (
        "tirodevanagarihindi",
        "TiroDevanagariHindi-Italic.ttf",
        "eed07aca7291e34fa2c4f3e48be325b261f60516ecf835610fee30dade0f78ec",
    ),
    (
        "inter",
        "Inter[opsz,wght].ttf",
        "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031",
    ),
    (
        "inter",
        "Inter-Italic[opsz,wght].ttf",
        "acd98e64795781b2058f07b18475e0ecee2a0fe2b42a49e2f9e37d0d6bf66ce6",
    ),
    (
        "atkinsonhyperlegiblenext",
        "AtkinsonHyperlegibleNext[wght].ttf",
        "5a455d1cfa099b601ab70751bb9673e8fe1854dc4500c80e1a220d0d75e31745",
    ),
    (
        "atkinsonhyperlegiblenext",
        "AtkinsonHyperlegibleNext-Italic[wght].ttf",
        "ce9cffed32742ad2d9238c561a93220385e5934cdc02b8eb4097a50efa957dc6",
    ),
    (
        "literata",
        "Literata[opsz,wght].ttf",
        "b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440",
    ),
    (
        "literata",
        "Literata-Italic[opsz,wght].ttf",
        "d483dfaeba9cbf4ce71d32a52ee65df82f7e35b15fff8d1011cdb242d1fcd465",
    ),
    (
        "sourceserif4",
        "SourceSerif4[opsz,wght].ttf",
        "97b2d4da6e3cb494b5a1e66ae176914d852ccabef49e0c02c0df25f3e39aca0b",
    ),
    (
        "sourceserif4",
        "SourceSerif4-Italic[opsz,wght].ttf",
        "15fbc7e4679489a501998c3669272637a6646388ef7e4bd77eebb5bf967a1f42",
    ),
    (
        "notoserif",
        "NotoSerif[wdth,wght].ttf",
        "4d8e6761424656867019081a1a01336f3cb086982682698714054fc33f782713",
    ),
    (
        "notoserif",
        "NotoSerif-Italic[wdth,wght].ttf",
        "e87acbc6c0efd0d9a20d6a8cbbda2b266c14be3a3a6f5af8ec9d7b2460570ad1",
    ),
    (
        "ptserif",
        "PT_Serif-Web-Regular.ttf",
        "a4951fade06ff8f09b7673aa81ffb65a8cd409e24d3289a6dc670bc4dda2557a",
    ),
    (
        "ptserif",
        "PT_Serif-Web-Italic.ttf",
        "f57e95ff9dc85691a3b2e193f2028db36f6663939a46c0fc4f286d618b80b7ce",
    ),
)
_GF_PACK_LICENCES = {
    "notosanstc": "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    "notosanshk": "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    "notosansjp": "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    "notoserifsc": "5e0da210fb04058a8c0087985d2d456b931c2579811a49655721d3cf0c36b6d6",
    "huninn": "d71824aeb09afc4c2cac01acab5c3db79796e927ba37be40d69fb62a412639b6",
    "notoseriftc": "5e0da210fb04058a8c0087985d2d456b931c2579811a49655721d3cf0c36b6d6",
    "lxgwwenkaitc": "4fff27d35db0e22cd81d58da6f20e09f415cf354a3338e3cf1fc0eb9222c7174",
    "chironheihk": "68b9a31cc191bb8f5f428f191209f7d08c6b5b0d4816a293e5bd230724e84f10",
    "notoserifhk": "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    "chironsunghk": "b8aea45c9cb6a682b68e32d2cfa454ce34117770b6bd6a956c1661428918c1f4",
    "bizudpgothic": "e753d7155d53c747d037a445e584c8ecfca6dd79846db610417e282a736b28bc",
    "zenmarugothic": "2a20cf7ce1909d8ee1e949095d340f7d7656705f7c810a2d6faf56800ad0cb3d",
    "notoserifjp": "5e0da210fb04058a8c0087985d2d456b931c2579811a49655721d3cf0c36b6d6",
    "zenoldmincho": "469d214f9842809659c827b7f2adaf40ec0df6efdd5fe18b7127665c32aafaec",
    "kleeone": "e376b0df8e8a2345a9533db6f0a5333a1107975569ad9d1973a7ee557161ca38",
    "notosanskr": "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9",
    "gowundodum": "a7c73f9521cd646bbdfb6684c99a62311bbd7bce11898dc11ef0b3c69eda1aca",
    "notoserifkr": "5e0da210fb04058a8c0087985d2d456b931c2579811a49655721d3cf0c36b6d6",
    "gowunbatang": "49a57cc769fa9affd6eefb9070a61e3d3f6b757c97cafb15848bc6d1c81acc78",
    "sarabun": "b26cae1321380296ba8311b632a397d5eac11b47197f9d0aa0b9310f1531ad60",
    "ibmplexsansthailooped": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
    "notoserifthai": "2e98fd23a52d253db8612cd5942c8f2ff4111b21d2367050fdca91d8ccc374a0",
    "ibmplexsansarabic": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
    "vazirmatn": "17e355067c8284f47743a1ee3b1ef7ff684ff0601eda357f9353b10b3016ab31",
    "amiri": "72de68e5954f4fdd24702292ef5a32f003ca960ec9330dc86e5eefb5dffb9b22",
    "mukta": "2ee5e8e47cd7d08f60bb9555f72b25912c9e81b13f5bc9a0551ddf943da6ca98",
    "hind": "f62ef357d3a1c3d27edd35a6e1ba350e8a8d13499797964eeadefbf0b3b15d1f",
    "notoserifdevanagari": "a216f6f8d85c7228093e0ee5e258d9d377e6671f68acb4db1930b29583d0f331",
    "tirodevanagarihindi": "2ed6051706542c5d6d96480318152b17900bb6d4dbadb11d7d5d6464d8b3e0dd",
    "inter": "5b9321a4298cfeb6b34354164a1c3afc3db114569984c502b9b35d988fd58c57",
    "atkinsonhyperlegiblenext": "aca6a428580965d2297d1b718042dd427c2a9443ece3b0d02d758e161e0c4030",
    "literata": "8742963604cd89dc81437811a850018fc03b2bfad686d7422c8235967c87614e",
    "sourceserif4": "5f94c3fd3a23131a417ab5a0c8452de57e70c3cfb9f604d88241f7065ebf9fd9",
    "notoserif": "cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a",
    "ptserif": "ddf311c28ddf5a5ad9747649837346b67bed9d356789c3072bb27dbce49e514d",
}
_RELEASES = "https://github.com/{}/releases/download/{}/{}"
_RAW = "https://raw.githubusercontent.com/{}/{}/{}"
_PRETENDARD = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/"
_RELEASE_SOURCES: dict[str, tuple[str, str]] = {
    "LXGWWenKai-Medium.ttf": (
        _RELEASES.format("lxgw/LxgwWenKai", "v1.530", "LXGWWenKai-Medium.ttf"),
        "f4b8a34d1f838fe411540cb7c97b1c384ac9738a876c4104500bc42508b2312a",
    ),
    "LXGWWenKai-OFL.txt": (
        _RAW.format("lxgw/LxgwWenKai", "v1.530", "OFL.txt"),
        "1a25e35da1031c6c3436fde545bb9cb5aca954e9873afe510c834b8b79bd21a0",
    ),
    "smiley-sans-v2.0.1.zip": (
        _RELEASES.format(
            "atelier-anchor/smiley-sans", "v2.0.1", "smiley-sans-v2.0.1.zip"
        ),
        "299c0be6c960ae37361762eca76f7d0cd516615435bb96c0d4b98a1e70178a07",
    ),
    "SmileySans-OFL.txt": (
        _RAW.format("atelier-anchor/smiley-sans", "v2.0.1", "LICENSE"),
        "9401f4050f1b66c26b6ccdc8b0e14a3c1cc37aac122eda84386f25854a9bec72",
    ),
    "ZhuqueFangsong-v0.212.zip": (
        _RELEASES.format("TrionesType/zhuque", "v0.212", "ZhuqueFangsong-v0.212.zip"),
        "bb8b661a7643d2296a72d9d10530a00949419c4e527fb61783f73c2ba1a8c062",
    ),
    "ZhuqueFangsong-OFL.txt": (
        _RAW.format("TrionesType/zhuque", "v0.212", "LICENSE.txt"),
        "66cc01ad4df62fca6936431a426104cb32a52ce8da49de9a7d643e02d7659043",
    ),
    "Pretendard-Medium.otf": (
        _PRETENDARD + "dist/public/static/Pretendard-Medium.otf",
        "d39e50e4bb52b4993b6a4eeb821a171254745bd824446af01e1f616b89fface0",
    ),
    "Pretendard-OFL.txt": (
        _PRETENDARD + "LICENSE",
        "d31ddd9f2bed32fd7e302a205cf2380ba0de6529152d239ef99cfb6f261bfc04",
    ),
}
_IN_ZIP = {
    "SmileySans-Oblique.ttf": ("smiley-sans-v2.0.1.zip", "SmileySans-Oblique.ttf"),
    "ZhuqueFangsong-Regular.ttf": (
        "ZhuqueFangsong-v0.212.zip",
        "ZhuqueFangsong-Regular.ttf",
    ),
}
"""Faces inside a release's zip: the zip is what's checked."""

PACK_SOURCES: dict[str, tuple[str, str]] = {
    **{file: (_gf(folder, file), sha) for folder, file, sha in _GF_PACK_SOURCES},
    **{
        f"{folder}-OFL.txt": (_gf(folder, "OFL.txt"), sha)
        for folder, sha in _GF_PACK_LICENCES.items()
    },
    **_RELEASE_SOURCES,
}
PACK_VERSION = "2026.11.18"
"""In each pack file's name: a face published again gets a new one."""
JAPANESE_BOX = (1079, 251)
"""Yu Gothic UI's line box at 1,000 units (2210/514 of 2048)."""
KOREAN_BOX = (1088, 242)
"""Malgun Gothic's (2228/496 of 2048)."""
OPTICAL_SIZE = 20
"""A face with an optical-size axis is fixed at a caption's size."""
STYLES = {400: "Regular", 500: "Medium", 600: "SemiBold"}


@dataclass(frozen=True)
class PackRecipe:
    """How a downloaded face is made: from `upright` (and `italic`), cut
    to `chars` if given, with `box`; `readings`: a SemiBold of what
    readings draw, if the face goes that heavy; `changed=False`: copied as
    published (a Reserved Font Name forbids a change, or it's static at
    Medium already)."""

    pack: str
    licence: str
    upright: str
    italic: str = ""
    chars: str | None = None
    box: tuple[int, int] | None = None
    readings: bool = False
    changed: bool = True


_ZH, _JA, _KO = YAHEI_UI_BOX, JAPANESE_BOX, KOREAN_BOX
PACK_RECIPES = (
    PackRecipe("notosanstc", "notosanstc-OFL.txt", "NotoSansTC[wght].ttf", chars="tc", box=_ZH, readings=True),
    PackRecipe("notosanshk", "notosanshk-OFL.txt", "NotoSansHK[wght].ttf", chars="hk", box=_ZH, readings=True),
    PackRecipe("notosansjp", "notosansjp-OFL.txt", "NotoSansJP[wght].ttf", chars="ja", box=_JA),
    PackRecipe("pretendard", "Pretendard-OFL.txt", "Pretendard-Medium.otf", changed=False),
    PackRecipe("smileysans", "SmileySans-OFL.txt", "SmileySans-Oblique.ttf", changed=False),
    PackRecipe("notoserifsc", "notoserifsc-OFL.txt", "NotoSerifSC[wght].ttf", chars="sc", box=_ZH, readings=True),
    PackRecipe("zhuquefangsong", "ZhuqueFangsong-OFL.txt", "ZhuqueFangsong-Regular.ttf", chars="sc", box=_ZH),
    PackRecipe("polyglotickai", "LXGWWenKai-OFL.txt", "LXGWWenKai-Medium.ttf", chars="sc", box=_ZH),
    PackRecipe("huninn", "huninn-OFL.txt", "Huninn-Regular.ttf", chars="tc", box=_ZH),
    PackRecipe("notoseriftc", "notoseriftc-OFL.txt", "NotoSerifTC[wght].ttf", chars="tc", box=_ZH, readings=True),
    PackRecipe("lxgwwenkaitc", "lxgwwenkaitc-OFL.txt", "LXGWWenKaiTC-Regular.ttf", chars="tc", box=_ZH),
    PackRecipe("chironheihk", "chironheihk-OFL.txt", "ChironHeiHK[wght].ttf", "ChironHeiHK-Italic[wght].ttf", chars="hk", box=_ZH, readings=True),
    PackRecipe("notoserifhk", "notoserifhk-OFL.txt", "NotoSerifHK[wght].ttf", chars="hk", box=_ZH, readings=True),
    PackRecipe("chironsunghk", "chironsunghk-OFL.txt", "ChironSungHK[wght].ttf", chars="hk", box=_ZH, readings=True),
    PackRecipe("bizudpgothic", "bizudpgothic-OFL.txt", "BIZUDPGothic-Regular.ttf", chars="ja", box=_JA),
    PackRecipe("zenmarugothic", "zenmarugothic-OFL.txt", "ZenMaruGothic-Medium.ttf", chars="ja", box=_JA),
    PackRecipe("notoserifjp", "notoserifjp-OFL.txt", "NotoSerifJP[wght].ttf", chars="ja", box=_JA),
    PackRecipe("zenoldmincho", "zenoldmincho-OFL.txt", "ZenOldMincho-Medium.ttf", chars="ja", box=_JA),
    PackRecipe("kleeone", "kleeone-OFL.txt", "KleeOne-SemiBold.ttf", chars="ja", box=_JA),
    PackRecipe("notosanskr", "notosanskr-OFL.txt", "NotoSansKR[wght].ttf", chars="ko", box=_KO),
    PackRecipe("gowundodum", "gowundodum-OFL.txt", "GowunDodum-Regular.ttf", chars="ko", box=_KO),
    PackRecipe("notoserifkr", "notoserifkr-OFL.txt", "NotoSerifKR[wght].ttf", chars="ko", box=_KO),
    PackRecipe("gowunbatang", "gowunbatang-OFL.txt", "GowunBatang-Regular.ttf", chars="ko", box=_KO),
    PackRecipe("sarabun", "sarabun-OFL.txt", "Sarabun-Medium.ttf", "Sarabun-MediumItalic.ttf", changed=False),
    PackRecipe("ibmplexsansthailooped", "ibmplexsansthailooped-OFL.txt", "IBMPlexSansThaiLooped-Medium.ttf", changed=False),
    PackRecipe("notoserifthai", "notoserifthai-OFL.txt", "NotoSerifThai[wdth,wght].ttf"),
    PackRecipe("ibmplexsansarabic", "ibmplexsansarabic-OFL.txt", "IBMPlexSansArabic-Medium.ttf", changed=False),
    PackRecipe("vazirmatn", "vazirmatn-OFL.txt", "Vazirmatn[wght].ttf"),
    PackRecipe("amiri", "amiri-OFL.txt", "Amiri-Regular.ttf", changed=False),
    PackRecipe("mukta", "mukta-OFL.txt", "Mukta-Medium.ttf", changed=False),
    PackRecipe("hind", "hind-OFL.txt", "Hind-Medium.ttf", changed=False),
    PackRecipe("notoserifdevanagari", "notoserifdevanagari-OFL.txt", "NotoSerifDevanagari[wdth,wght].ttf"),
    PackRecipe("tirodevanagarihindi", "tirodevanagarihindi-OFL.txt", "TiroDevanagariHindi-Regular.ttf", "TiroDevanagariHindi-Italic.ttf", changed=False),
    PackRecipe("inter", "inter-OFL.txt", "Inter[opsz,wght].ttf", "Inter-Italic[opsz,wght].ttf"),
    PackRecipe("atkinson", "atkinsonhyperlegiblenext-OFL.txt", "AtkinsonHyperlegibleNext[wght].ttf", "AtkinsonHyperlegibleNext-Italic[wght].ttf"),
    PackRecipe("literata", "literata-OFL.txt", "Literata[opsz,wght].ttf", "Literata-Italic[opsz,wght].ttf"),
    PackRecipe("sourceserif4", "sourceserif4-OFL.txt", "SourceSerif4[opsz,wght].ttf", "SourceSerif4-Italic[opsz,wght].ttf"),
    PackRecipe("notoserif", "notoserif-OFL.txt", "NotoSerif[wdth,wght].ttf", "NotoSerif-Italic[wdth,wght].ttf"),
    PackRecipe("ptserif", "ptserif-OFL.txt", "PT_Serif-Web-Regular.ttf", "PT_Serif-Web-Italic.ttf", changed=False),
)  # fmt: skip
"""Each downloaded face's recipe (`fonts.PACKED`'s faces, by pack)."""


def fetch_packs(sources: Path) -> None:
    """The packs' sources into `sources`, unless they're there; each
    checked; the faces inside a release's zip taken out of it."""
    sources.mkdir(parents=True, exist_ok=True)
    for name, (url, sha256) in PACK_SOURCES.items():
        path = sources / name
        if not path.exists():
            with urllib.request.urlopen(url, timeout=120) as response:
                path.write_bytes(response.read())
        found = hashlib.sha256(path.read_bytes()).hexdigest()
        if found != sha256:
            raise SystemExit(f"{name}: SHA-256 {found}, expected {sha256}")
    for name, (archive, member) in _IN_ZIP.items():
        if not (sources / name).exists():
            with zipfile.ZipFile(sources / archive) as zipped:
                (sources / name).write_bytes(zipped.read(member))


def _decoded(codec: str, leads: Iterable[int], trails: Iterable[int]) -> set[str]:
    """The characters two bytes `lead`, `trail` of `codec` decode to."""
    found = set()
    trail_list = list(trails)
    for lead in leads:
        for trail in trail_list:
            try:
                text = bytes((lead, trail)).decode(codec)
            except UnicodeDecodeError:
                continue
            if len(text) == 1:
                found.add(text)
    return found


_BIG5_TRAILS = [*range(0x40, 0x7F), *range(0xA1, 0xFF)]
_CANTONESE_TEXT = (
    "嘅咗嘢冇啲喺哋佢嚟噉啱嗰乜嘥睇攰餸瞓搵諗噏嚿嘞喎啩咩嘛囉晒冚揸攞撳嘈咁點邊閂揼擰嗱咪噃啫喇"
    "嘑嚡嘆靚嘟嗌嚇冧瀡𨋢𠝹𡃁"
)
CANTONESE = set(_CANTONESE_TEXT)
"""Cantonese's own common characters, some outside Big5 and HKSCS (479)."""
KANA = {chr(c) for c in range(0x3040, 0x3100)} | {chr(c) for c in range(0x31F0, 0x3200)}


def pack_sets(sources: Path) -> dict[str, set[str]]:
    """The character sets a downloaded face is cut to (479's measures)."""
    big5 = _decoded("big5", range(0xA1, 0xFA), _BIG5_TRAILS)
    hkscs = _decoded("big5hkscs", range(0x87, 0xFF), _BIG5_TRAILS)
    jis = _decoded("euc_jp", range(0xA1, 0xF5), range(0xA1, 0xFF))
    hangul = {chr(c) for c in range(0xAC00, 0xD7A4)}
    jamo = {chr(c) for c in range(0x3131, 0x318F)}
    extras = _extras() | READING_CHARS
    return {
        "sc": simplified(sources),
        "tc": big5 | extras,
        "hk": big5 | hkscs | CANTONESE | extras,
        "ja": jis | KANA | extras,
        "ko": hangul | jamo | _extras(),
        "readings": READING_CHARS,
    }


def build_packs(sources: Path, out: Path) -> None:
    """Each `PACK_RECIPES` face into `out`, with `fonts.json`."""
    from fontTools.ttLib import TTFont

    from polyglotic_desktop.ui_next import fonts

    os.environ["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    out.mkdir(parents=True, exist_ok=True)
    sets = pack_sets(sources)
    manifest = []
    for recipe in PACK_RECIPES:
        family = fonts.BY_PACK[recipe.pack].family
        made: list[str] = []

        def named(
            style: str,
            suffix: str = ".ttf",
            pack: str = recipe.pack,
            made: list[str] = made,
        ) -> Path:
            made.append(f"{pack}-{style}-{PACK_VERSION}{suffix}")
            return out / made[-1]

        if not recipe.changed:
            source = sources / recipe.upright
            shutil.copyfile(source, named("upright", source.suffix))
            if recipe.italic:
                shutil.copyfile(sources / recipe.italic, named("italic"))
        else:
            chars = sets[recipe.chars] if recipe.chars else None
            for source_name, italic in ((recipe.upright, False), (recipe.italic, True)):
                if not source_name:
                    continue
                font = _made(TTFont(sources / source_name), chars, 500)
                weight = font["OS/2"].usWeightClass  # type: ignore[index]
                _name(font, family, STYLES.get(weight, "Regular"), weight, italic)
                if recipe.box is not None:
                    _box(font, *recipe.box)
                font.save(named("italic" if italic else "upright"))  # type: ignore[attr-defined]
            whole = TTFont(sources / recipe.upright)
            if recipe.readings and _reaches(whole, 600):
                font = _made(whole, sets["readings"], 600)
                _name(font, family, "SemiBold", 600)
                if recipe.box is not None:
                    _box(font, *recipe.box)
                font.save(named("readings"))  # type: ignore[attr-defined]
        licence = (sources / recipe.licence).read_bytes().replace(b"\r\n", b"\n")
        named("ofl", ".txt").write_bytes(licence)
        credit = licence.decode("utf-8-sig").strip().splitlines()[0].strip()
        manifest.append(
            {"font": recipe.pack, "family": family, "credits": credit, "files": made}
        )
        print(recipe.pack, sum((out / f).stat().st_size for f in made), flush=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
    (out / "fonts.json").write_bytes(text.encode("utf-8"))


def _reaches(font: object, weight: int) -> bool:
    """Whether variable `font`'s weight goes to `weight`."""
    if "fvar" not in font:  # type: ignore[operator]
        return False
    return any(
        axis.axisTag == "wght" and axis.maxValue >= weight
        for axis in font["fvar"].axes  # type: ignore[index]
    )


def _made(font: object, chars: set[str] | None, weight: int) -> object:
    """`font` cut to `chars` (None: whole) and, if variable, fixed at
    `weight` (as near as it goes) and a caption's optical size."""
    from fontTools import subset
    from fontTools.varLib import instancer

    if chars is not None:
        options = subset.Options()
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.name_languages = ["*"]
        options.notdef_outline = True
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=sorted(ord(c) for c in chars))
        subsetter.subset(font)
    if "fvar" in font:  # type: ignore[operator]
        location = {}
        for axis in font["fvar"].axes:  # type: ignore[index]
            value = {"wght": weight, "opsz": OPTICAL_SIZE}.get(
                axis.axisTag, axis.defaultValue
            )
            location[axis.axisTag] = min(max(value, axis.minValue), axis.maxValue)
        font = instancer.instantiateVariableFont(font, location)
        font["OS/2"].usWeightClass = int(location.get("wght", 400))  # type: ignore[index]
    return font


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="where the faces go")
    parser.add_argument(
        "--sources", type=Path, help="the sources (fetched there if missing): OUT/src"
    )
    parser.add_argument(
        "--packs", action="store_true", help="the downloaded faces (fonts.PACKED)"
    )
    args = parser.parse_args(argv)
    sources = args.sources or args.out / "src"
    fetch(sources)
    if args.packs:
        fetch_packs(sources)
        build_packs(sources, args.out)
        return
    build(sources, args.out)


if __name__ == "__main__":
    main()
