"""Chinese never falls back to a Japanese face anywhere in the interface
(polyglotic-hq 215): the interface's Chinese faces behind every font
(`style.use_chinese_behind_every_font`), and Japanese still in its own
Japanese face - by its language, or by its kana when that isn't known."""

import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from tools.ui_lab import lab

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import CaptionRow, RowKind
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout
from polyglotic_desktop.ui_next.fonts import caption_families

YAHEI, JHENGHEI = "Microsoft YaHei UI", "Microsoft JhengHei UI"


def _behind(family: str) -> list[str]:
    """The faces behind `family`, as written (Qt keeps them in lower case)."""
    names = {f.lower(): f for f in (style.SYMBOLS, YAHEI, JHENGHEI, "Windows' own")}
    return [names.get(f, f) for f in QFont.substitutes(family)]


def test_the_interfaces_chinese_is_behind_every_font(qapp: QApplication) -> None:
    """Behind every family Qt has and the interface's own - after the
    symbols' face, before anything else behind it (the lab's stand-in for
    what Windows finds) - in the interface's order: JhengHei first for
    Traditional; and back again, nothing left twice."""
    first = QFontDatabase.families()[0]
    QFont.insertSubstitution(first, "Windows' own")
    try:
        style.use_interface_language("zh_CN")
        assert _behind("Segoe UI")[:3] == [style.SYMBOLS, YAHEI, JHENGHEI]
        assert _behind("Segoe UI Variable Text")[1:3] == [YAHEI, JHENGHEI]
        assert _behind(first)[:2] == [YAHEI, JHENGHEI]
        assert _behind(first)[-1] == "Windows' own"
        style.use_interface_language("zh_TW")
        assert _behind("Segoe UI")[:3] == [style.SYMBOLS, JHENGHEI, YAHEI]
        assert _behind(first)[:2] == [JHENGHEI, YAHEI]
        assert _behind(first).count(YAHEI) == 1
        assert _behind(first)[-1] == "Windows' own"
    finally:
        style.use_interface_language("en")
        QFont.removeSubstitutions(first)
        QFont.insertSubstitutions(
            first, [f for f in QFont.substitutes(first) if f != "windows' own"]
        )
    assert _behind("Segoe UI")[:3] == [style.SYMBOLS, YAHEI, JHENGHEI]


def _row(text: str, language: str | None) -> CaptionRow:
    spoken = None if language is None else Language(language)
    return CaptionRow(text, RowKind.ORIGINAL, spoken, 0, True)


@pytest.mark.parametrize(
    ("text", "language", "drawn_as"),
    [
        ("日本語のテキストです", None, "ja"),  # kana: Japanese
        ("我们这么说汉字", None, "zh"),
        ("日本語", "ja", "ja"),  # its language says so
        ("hello there", None, None),
    ],
)
def test_a_lines_fonts_come_by_its_script_when_its_language_isnt_known(
    qapp: QApplication, text: str, language: str | None, drawn_as: str | None
) -> None:
    """A caption line whose language the server didn't say: Japanese (it
    has kana) in a Japanese face, not the Chinese one every Chinese-looking
    line had (YaHei, China's glyph shapes) - in its language's caption
    faces since 482 (`fonts.caption_families`)."""
    font = CaptionLayout()._font(_row(text, language), 1.0, False)
    assert font.families() == list(caption_families(drawn_as))


_DRAWN = """
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QFont, QTextLayout
from PySide6.QtWidgets import QApplication, QMenu, QToolTip
from tools.ui_lab import lab
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_layout import CJK_FAMILIES, LATIN_FAMILIES

def faces(text, font):
    layout = QTextLayout(text, font)
    layout.beginLayout()
    layout.createLine()
    layout.endLayout()
    return sorted({r.rawFont().familyName() for r in layout.glyphRuns()})

app = lab.application()  # Windows' fonts, and what Windows finds: MS UI Gothic
if sys.argv[1] != "before":
    style.use_interface_language(sys.argv[1])
japanese = QFont()
japanese.setFamilies([*CJK_FAMILIES["ja"], *LATIN_FAMILIES])
print(faces("收藏到", QFont()))  # what names no font: a dialog's
print(faces("收藏到", QApplication.font(QMenu())))  # a menu's
print(faces("收藏到", QToolTip.font()))  # a tooltip's
print(faces("日本語のテキスト", japanese))  # a Japanese line's
"""


@pytest.mark.parametrize(
    ("language", "chinese"),
    [("before", "MS UI Gothic"), ("en", YAHEI), ("zh_CN", YAHEI), ("zh_TW", JHENGHEI)],
)
def test_chinese_is_drawn_in_the_interfaces_face_and_japanese_in_its_own(
    language: str, chinese: str
) -> None:
    """As drawn in Windows' fonts (the lab's): what names no font, a menu
    and a tooltip have their Chinese in the interface's face - before, in
    MS UI Gothic, a Japanese one - and a Japanese line stays in Yu Gothic.
    In a process of its own for each: Qt keeps the fonts behind a family
    as it first found them."""
    if not lab.WINDOWS_FONTS.is_dir():
        pytest.skip("needs Windows' fonts")
    done = subprocess.run(
        [sys.executable, "-c", _DRAWN, language],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        cwd=Path(__file__).parents[2],
    )
    assert done.returncode == 0, done.stderr[-2000:]
    lines = done.stdout.strip().splitlines()
    assert lines == [str([chinese])] * 3 + [str(["Yu Gothic UI"])]
