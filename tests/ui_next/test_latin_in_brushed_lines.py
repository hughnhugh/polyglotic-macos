"""Only a line of Chinese's Han characters take the brush (polyglotic-hq 551:
preview 0.1.10-preview.1 drew "focus" in "比较focus在找工作" in Ma Shan
Zheng's own cursive letters). Its Latin letters, digits and Latin
punctuation are in the Latin captions' face; pinyin and zhuyin over it in
the plain face behind it."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime

import pytest
from PySide6.QtGui import QFontMetricsF, QTextLayout
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import CaptionRow, RowKind
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ui_next import caption_faces, fonts, languages
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    _FlowFont,
)
from polyglotic_desktop.ui_next.views.captions import Line
from polyglotic_desktop.ui_next.views.lab import Fill

MIXED = "嗯，所以你现在还是比较focus在找工作这件事。"
FOCUS = (MIXED.index("focus"), MIXED.index("focus") + len("focus"))


def runs(text: str) -> list[str]:
    return [text[a:b] for a, b in fonts.latin_runs(text)]


# -- which characters (plain Python) ------------------------------------------


def test_a_latin_word_in_a_line_of_chinese_is_a_run() -> None:
    assert fonts.latin_runs(MIXED) == (FOCUS,)


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("我有2026年的iPhone 15 Pro吗？", ["2026", "iPhone 15 Pro"]),
        ("用Wi-Fi，3.5%的人", ["Wi-Fi", "3.5%"]),
        ("你好,世界!", [",", "!"]),
        ("machine learning 很难", ["machine learning "]),  # with its space after
        ("说 don’t 就好", ["don’t "]),  # the space before stays the line's
        ("café很好", ["café"]),
        ("nǐ hǎo，Việt Nam", ["nǐ hǎo", "Việt Nam"]),
        ("“你好”·——……", []),  # Chinese's own punctuation, its faces draw
        ("ＡＢＣ１２３", []),  # full-width forms are Chinese text's
        ("我们去看电影", []),
    ],
)
def test_letters_digits_and_latin_punctuation_are_runs(
    text: str, found: list[str]
) -> None:
    assert runs(text) == found


def test_the_brush_and_hand_faces_are_brushed_and_the_plain_ones_not() -> None:
    for family in (
        "Ma Shan Zheng Captions",
        "Polyglotic Kai",
        "LXGW WenKai TC Captions",
    ):
        assert fonts.brushed(family), family
    plain: tuple[str | None, ...] = (
        "Noto Sans SC Captions",
        "Noto Sans TC Captions",
        "Noto Serif SC Captions",
        "Smiley Sans",
        "Klee One Captions",
        "IBM Plex Sans",
        "Some PC Font",
        None,
    )
    for other in plain:
        assert not fonts.brushed(other), other


def test_readings_over_a_brushed_face_are_in_the_plain_face_behind_it() -> None:
    """Pinyin and zhuyin "stay in a plain face, easy to read" (the release
    notes) - over Paper's Polyglotic Kai and Traditional's LXGW WenKai TC
    too, not only Ma Shan Zheng (532)."""
    for chosen, sans in (
        (None, "Noto Sans SC Captions"),
        ("Polyglotic Kai", "Noto Sans SC Captions"),
    ):
        families = fonts.caption_families("zh", chosen, system="win32")
        assert fonts.reading_families(families)[0] == sans
    families = fonts.caption_families("zh-hant", system="win32")
    assert fonts.reading_families(families)[0] == "Noto Sans TC Captions"


# -- drawn (Qt) ------------------------------------------------------------------


@pytest.fixture
def faces(qapp: QApplication) -> Iterator[None]:
    caption_faces.load()
    yield
    languages.show_mandarin_in_traditional(False)


def _line(text: str, language: str = "zh") -> Line:
    row = CaptionRow(text, RowKind.ORIGINAL, Language(language), 0, True)
    return Line(1, SourceId("app"), False, (row,), False, False, datetime(2026, 11, 20))


def _drawn(layout: QTextLayout, start: int, end: int) -> set[str]:
    """The families the characters `[start, end)` of `layout` are drawn in
    - by family, not weight: Linux's fontconfig may name IBM Plex Sans'
    Medium file "IBM Plex Sans Medium" (as test_caption_faces says)."""
    found = set()
    for n in range(layout.lineCount()):
        line = layout.lineAt(n)
        a = max(start, line.textStart())
        b = min(end, line.textStart() + line.textLength())
        if a < b:
            found |= {r.rawFont().familyName() for r in line.glyphRuns(a, b - a)}
    return {name.removesuffix(" Medium").removesuffix(" Regular") for name in found}


@pytest.mark.usefixtures("faces")
@pytest.mark.parametrize("fill", [Fill.CLAUSES, Fill.STACKED])
def test_focus_in_a_ma_shan_zheng_line_is_in_the_latin_captions_face(
    fill: Fill,
) -> None:
    engine = CaptionLayout(replace(CaptionStyle(), fill=fill))
    laid = engine.laid(_line(MIXED), 2000, 1.0)
    layout = laid.rows[0].layout
    assert _drawn(layout, *FOCUS) == {"IBM Plex Sans"}
    assert _drawn(layout, 0, FOCUS[0]) == {"Ma Shan Zheng Captions"}
    assert _drawn(layout, FOCUS[1], len(MIXED)) == {"Ma Shan Zheng Captions"}


@pytest.mark.usefixtures("faces")
def test_the_latin_run_is_the_size_latin_text_is_drawn_beside_it() -> None:
    engine = CaptionLayout()
    chinese = engine._font(_line(MIXED).rows[0], 1.0, False)
    english = engine._font(
        CaptionRow("focus", RowKind.TRANSLATION, Language("en"), 0, True), 1.0, False
    )
    latin = engine._latin(_line(MIXED).rows[0], chinese)
    assert latin is not None
    assert latin.families() == english.families()
    assert latin.pixelSize() == english.pixelSize() < chinese.pixelSize()
    assert latin.weight() == chinese.weight() and not latin.italic()


@pytest.mark.usefixtures("faces")
def test_the_learners_english_face_is_the_latin_runs_face() -> None:
    style = replace(CaptionStyle(), faces=(("en", "PT Sans"),))
    engine = CaptionLayout(style)
    row = _line(MIXED).rows[0]
    latin = engine._latin(row, engine._font(row, 1.0, False))
    assert latin is not None and latin.families()[0] == "PT Sans"


@pytest.mark.usefixtures("faces")
@pytest.mark.parametrize(
    ("language", "chosen"),
    [("zh", "Polyglotic Kai"), ("zh-hant", None), ("zh", "Ma Shan Zheng Captions")],
)
def test_every_brushed_face_gives_its_latin_to_the_latin_face(
    language: str, chosen: str | None
) -> None:
    """Paper's Polyglotic Kai and Traditional's LXGW WenKai TC are
    downloaded: their lines' Latin runs are asked of the Latin face
    whether they're here or not."""
    faces_ = ((language, chosen),) if chosen else ()
    engine = CaptionLayout(replace(CaptionStyle(), faces=faces_))
    row = _line(MIXED, language).rows[0]
    latin = engine._latin(row, engine._font(row, 1.0, False))
    assert latin is not None and latin.families()[0] == "IBM Plex Sans"


@pytest.mark.usefixtures("faces")
@pytest.mark.parametrize(
    ("language", "chosen"),
    [("zh", "Noto Sans SC Captions"), ("zh", "Noto Serif SC Captions"), ("en", None)],
)
def test_a_plain_face_keeps_its_own_latin_letters(
    language: str, chosen: str | None
) -> None:
    """Broadcast's Noto Sans SC draws "focus" in its own sans, as before."""
    faces_ = ((language, chosen),) if chosen else ()
    engine = CaptionLayout(replace(CaptionStyle(), faces=faces_))
    row = _line(MIXED, language).rows[0]
    assert engine._latin(row, engine._font(row, 1.0, False)) is None


@pytest.mark.usefixtures("faces")
def test_the_pour_and_the_composer_measure_the_line_as_it_is_drawn() -> None:
    """A row is poured by its measured width: measured in Ma Shan Zheng's
    narrow cursive, "focus" would overrun its line."""
    engine = CaptionLayout(replace(CaptionStyle(), fill=Fill.STACKED))
    row = _line(MIXED).rows[0]
    font = engine._font(row, 1.0, False)
    latin = engine._latin(row, font)
    laid = engine.laid(_line(MIXED), 4000, 1.0).rows[0].layout
    drawn = laid.lineAt(0).naturalTextWidth()
    flow = _FlowFont(font, 0.0, latin)
    assert flow.width(MIXED) == pytest.approx(drawn, abs=1.0)
    assert QFontMetricsF(font).horizontalAdvance(MIXED) < drawn - 5  # the old measure
