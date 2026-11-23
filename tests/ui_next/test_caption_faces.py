"""Captions in a face chosen for their language (polyglotic-hq 479, 482;
decision 0223): the faces the app carries, which language takes which,
Thai and Arabic named rather than left to Qt's fallback (Tahoma), Arabic
never slanted and a little larger, readings in a real SemiBold, and a
Chinese row as tall as before."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF, QRawFont
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import CaptionRow, RowKind
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ui_next import caption_faces, fonts, languages, reading_lines
from polyglotic_desktop.ui_next.caption_layout import (
    CaptionLayout,
    CaptionStyle,
    caption_language,
)
from polyglotic_desktop.ui_next.views.captions import Line

ROOT = Path(__file__).resolve().parents[2]


def row(
    text: str, language: str | None, kind: RowKind = RowKind.ORIGINAL
) -> CaptionRow:
    return CaptionRow(text, kind, Language(language) if language else None, 0, True)


# -- which faces, by language (plain Python) ---------------------------------------


def test_each_language_starts_with_its_default_face() -> None:
    first = {
        language: fonts.caption_families(language, system="win32")[0]
        for language in (
            "zh",
            "th",
            "vi",
            "ar",
            "hi",
            "ru",
            "uk",
            "en",
            "es",
            "de",
            None,
        )
    }
    assert first == {
        "zh": "Ma Shan Zheng Captions",
        "th": "Noto Sans Thai Looped",
        "vi": "Be Vietnam Pro",
        "ar": "Noto Naskh Arabic Captions",
        "hi": "Noto Sans Devanagari",
        "ru": "PT Sans",
        "uk": "PT Sans",
        "en": "IBM Plex Sans",
        "es": "IBM Plex Sans",
        "de": "IBM Plex Sans",
        None: "IBM Plex Sans",
    }


def test_thai_and_arabic_name_windows_own_faces_not_qts_fallback() -> None:
    """479: Thai and Arabic captions came out in Tahoma, Qt's fallback,
    because no list named a face for them."""
    assert fonts.caption_families("th", system="win32")[:2] == (
        "Noto Sans Thai Looped",
        "Leelawadee UI",
    )
    assert fonts.caption_families("ar", system="win32")[:2] == (
        "Noto Naskh Arabic Captions",
        "Segoe UI",
    )
    assert "Tahoma" not in fonts.caption_families("th") + fonts.caption_families("ar")


def test_the_downloaded_defaults_come_first_and_windows_own_after() -> None:
    """Traditional Chinese's, Cantonese's, Japanese's and Korean's faces
    are downloaded: until they're here, Qt passes over them to Windows'."""
    assert fonts.caption_families("zh-hant", system="win32")[:4] == (
        "LXGW WenKai TC Captions",
        "Noto Sans TC Captions",
        "Microsoft JhengHei UI",
        "Microsoft JhengHei",
    )
    assert fonts.caption_families("yue", system="win32")[:2] == (
        "Noto Sans HK Captions",
        "Microsoft JhengHei UI",
    )
    assert fonts.caption_families("ja", system="win32")[:2] == (
        "Noto Sans JP Captions",
        "Yu Gothic UI",
    )
    assert fonts.caption_families("ko", system="win32")[:2] == (
        "Pretendard",
        "Malgun Gothic",
    )
    for script in ("zh-hant", "yue", "ja", "ko"):
        assert fonts.FACES[fonts.DEFAULTS[script]].pack, script


def test_every_list_ends_in_the_latin_faces_for_the_letters_in_it() -> None:
    latin = fonts.caption_families("en", system="win32")
    assert latin == ("IBM Plex Sans", "Segoe UI Variable Display", "Segoe UI")
    for language in ("zh", "th", "ar", "hi", "ja", "ko", "ru"):
        families = fonts.caption_families(language, system="win32")
        assert set(latin) <= set(families), language
        assert families.index("IBM Plex Sans") > families.index(families[0]), language
        assert len(set(families)) == len(families), language


def test_the_learners_choice_comes_first() -> None:
    assert fonts.caption_families("zh", "KaiTi", system="win32")[:3] == (
        "KaiTi",
        "Ma Shan Zheng Captions",
        "Noto Sans SC Captions",
    )
    assert fonts.caption_families("en", "IBM Plex Sans", system="win32")[:2] == (
        "IBM Plex Sans",
        "Segoe UI Variable Display",
    )


@pytest.mark.parametrize("system", ["darwin", "linux"])
def test_on_another_os_every_script_has_a_face_of_its_own(system: str) -> None:
    """The Mac check, from the code (no Mac here; 479): each script's list
    holds a face that OS ships, after the default."""
    for script in ("latin", "zh", "zh-hant", "yue", "ja", "ko", "th", "ar", "deva"):
        assert fonts.also(script, system), (system, script)
    assert fonts.caption_families("ko", system="darwin")[:3] == (
        "Pretendard",
        "Malgun Gothic",
        "Apple SD Gothic Neo",
    )
    assert "Thonburi" in fonts.caption_families("th", system="darwin")
    assert "Geeza Pro" in fonts.caption_families("ar", system="darwin")
    assert "Kohinoor Devanagari" in fonts.caption_families("hi", system="darwin")


def test_chinese_is_in_calligraphy_with_its_sans_behind() -> None:
    """532 (the user, preview 1: "make a stand out one the default and
    customisable"): Simplified's default is Ma Shan Zheng, carried by the
    app; Traditional's LXGW WenKai TC - each with the script's sans after
    it, for what the calligraphy hasn't got."""
    assert fonts.caption_families("zh", system="win32")[:3] == (
        "Ma Shan Zheng Captions",
        "Noto Sans SC Captions",
        "Microsoft YaHei UI",
    )
    assert fonts.FACES["Ma Shan Zheng Captions"].kind == fonts.CALLIGRAPHY
    # never slanted (the quiet view's italic, Quick preview's): a brush's
    # strokes bent by a made-up slant read as a mistake, as Arabic's did
    assert fonts.upright("zh", "Ma Shan Zheng Captions")
    assert fonts.FACES["Ma Shan Zheng Captions"].upright  # whatever the script
    # and since 526 no Chinese face is slanted (DECISIONS #230 item 3)
    assert fonts.upright("zh", "Noto Sans SC Captions")
    assert not fonts.FACES["Ma Shan Zheng Captions"].pack  # in the app
    assert fonts.CHOICES["zh"][:2] == (
        "Ma Shan Zheng Captions",
        "Noto Sans SC Captions",
    )
    assert "Polyglotic Kai" in fonts.CHOICES["zh"]
    assert fonts.CHOICES["zh-hant"][0] == "LXGW WenKai TC Captions"
    assert "Noto Sans TC Captions" in fonts.CHOICES["zh-hant"]


def test_readings_skip_a_face_without_tone_marks() -> None:
    """Ma Shan Zheng has no ā or ǒ: a reading in it would be a brush's
    consonants and another face's vowels in one word (532). Nor over the
    other brushed faces (551: Polyglotic Kai's are in Noto Sans SC too)."""
    families = fonts.caption_families("zh", system="win32")
    assert fonts.reading_families(families)[0] == "Noto Sans SC Captions"
    chosen = fonts.caption_families("zh", "Noto Serif SC Captions", system="win32")
    assert fonts.reading_families(chosen)[0] == "Noto Serif SC Captions"
    assert fonts.reading_families(["Some PC Font"]) == ["Some PC Font"]


def test_arabic_is_never_slanted_and_latin_may_be() -> None:
    assert fonts.upright("ar") and fonts.upright("fa", "Tahoma")
    assert not fonts.upright("en") and not fonts.upright(None)


def test_chinese_japanese_and_korean_are_never_slanted() -> None:
    """526 (DECISIONS #230 item 3): the quiet view is italic throughout,
    but a computer's slant of Chinese is harder to read."""
    for language in ("zh", "zh-hant", "yue", "ja", "ko"):
        assert fonts.upright(language)
    assert not fonts.upright("vi") and not fonts.upright("ru")


def test_arabic_and_devanagari_are_drawn_larger_like_chinese() -> None:
    assert fonts.size("ar") == 1.15
    assert fonts.size("hi") == 1.1
    assert fonts.size("zh") == fonts.size("ja") == 1.05
    assert fonts.size("en") == fonts.size("th") == fonts.size(None) == 1.0


# -- the files the app carries -------------------------------------------------------


def test_every_bundled_face_has_its_files_its_licence_and_its_credit() -> None:
    folder = caption_faces.FOLDER
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for face in fonts.BUNDLED:
        for name in face.files:
            assert (folder / name).stat().st_size > 10_000, name
        licence = face.name.replace(" ", "") + "-OFL.txt"
        assert "SIL Open Font License" in (folder / licence).read_text(encoding="utf-8")
        assert face.family in notices, face.family
    assert set(fonts.DEFAULTS.values()) <= set(fonts.FACES)


# -- in Qt -------------------------------------------------------------------------


@pytest.fixture
def faces(qapp: QApplication) -> Iterator[None]:
    caption_faces.load()
    yield
    languages.show_mandarin_in_traditional(False)


@pytest.mark.usefixtures("faces")
def test_the_bundled_faces_are_in_qts_fonts() -> None:
    families = set(caption_faces.load())
    assert {face.family for face in fonts.BUNDLED} <= families
    styles = {
        style: QFontDatabase.weight("Noto Sans SC Captions", style)
        for style in QFontDatabase.styles("Noto Sans SC Captions")
    }
    assert styles == {"Medium": 500, "SemiBold": 600}
    assert QFontDatabase.italic("IBM Plex Sans", "Medium Italic")


@pytest.mark.usefixtures("faces")
def test_ma_shan_zheng_holds_every_hsk_character_and_no_tone_marks() -> None:
    """532's measure: GB2312's characters - all HSK 1-9's and FLEURS
    Mandarin's - and none of pinyin's tone-marked vowels."""
    raw = QRawFont(str(caption_faces.FOLDER / "MaShanZheng-Regular.ttf"), 20)
    for text in ("我需要讲中文，他会。", "边角被绿。", "iPhone 12"):
        assert all(raw.supportsCharacter(ord(c)) for c in text), text
    assert not raw.supportsCharacter(ord("ǒ"))
    assert QFontDatabase.weight("Ma Shan Zheng Captions", "Regular") == 400


@pytest.mark.usefixtures("faces")
def test_simplified_chinese_holds_the_characters_and_readings_its_cut_keeps() -> None:
    medium = QRawFont(str(caption_faces.FOLDER / "NotoSansSC-Medium.ttf"), 20)
    semibold = QRawFont(str(caption_faces.FOLDER / "NotoSansSC-SemiBold.ttf"), 20)
    for text in ("我们明天见啰", "iPhone，。、“”", "ㄨㄛˇ"):
        assert all(medium.supportsCharacter(ord(c)) for c in text), text
    for text in ("wǒmen míngtiān jiàn lǜ", "ㄨㄛˇ ㄇㄣˊ", "ngo5 dei6"):
        assert all(semibold.supportsCharacter(ord(c)) for c in text), text
    assert not semibold.supportsCharacter(ord("我"))  # only what readings draw


@pytest.mark.usefixtures("faces")
def test_a_rows_font_is_its_languages_faces() -> None:
    engine = CaptionLayout()
    thai = engine._font(row("สวัสดีครับ", "th"), 1.0, False)
    assert thai.families()[:2] == ["Noto Sans Thai Looped", "Leelawadee UI"]
    english = engine._font(row("See you", "en", RowKind.TRANSLATION), 1.0, False)
    assert english.families()[0] == "IBM Plex Sans"
    assert english.weight() == QFont.Weight.Medium


@pytest.mark.usefixtures("faces")
def test_arabic_stays_upright_when_text_still_being_spoken_is_italic() -> None:
    """479: Quick preview's provisional lines, and the quiet view, slanted
    Arabic - a slant Arabic doesn't have."""
    engine = CaptionLayout()
    arabic = engine._font(row("مرحبا بالعالم", "ar"), 1.0, True)
    unknown = engine._font(row("مرحبا بالعالم", None), 1.0, True)
    english = engine._font(row("Hello", "en"), 1.0, True)
    assert not arabic.italic() and not unknown.italic()
    assert english.italic()
    assert arabic.pixelSize() == round(engine.style.text_px * 1.15)
    assert unknown.families()[0] == "Noto Naskh Arabic Captions"


@pytest.mark.usefixtures("faces")
def test_mandarin_shown_in_traditional_takes_traditionals_faces() -> None:
    """Noto Sans SC holds Simplified's characters: Traditional ones in it
    would come from another face, character by character."""
    mandarin = row("我們明天見", "zh")
    assert caption_language(mandarin) == "zh"
    languages.show_mandarin_in_traditional(True)
    assert caption_language(mandarin) == "zh-hant"
    font = CaptionLayout()._font(mandarin, 1.0, False)
    assert font.families()[:3] == [
        "LXGW WenKai TC Captions",
        "Noto Sans TC Captions",
        "Microsoft JhengHei UI",
    ]


@pytest.mark.usefixtures("faces")
def test_a_reading_is_in_a_real_semibold_or_its_texts_weight() -> None:
    """479: with Medium alone, a reading asked for at DemiBold got a bold
    Qt made up, some letters lighter than others."""
    engine = CaptionLayout()
    chinese = engine._font(row("我们", "zh"), 1.0, False)
    reading = reading_lines.reading_font(chinese)
    assert reading.weight() == QFont.Weight.DemiBold
    # over Ma Shan Zheng, in Noto Sans SC's real SemiBold (532)
    assert reading.families()[0] == "Noto Sans SC Captions"
    thai = engine._font(row("สวัสดี", "th"), 1.0, False)
    assert reading_lines.reading_font(thai).weight() == QFont.Weight.Medium


@pytest.mark.usefixtures("faces")
def test_a_chinese_row_is_as_tall_as_in_yahei_ui() -> None:
    """479: Noto CJK's own line box is 1.45 times its size, YaHei UI's
    1.27 - every Chinese row would have grown. The cut has YaHei UI's."""
    names = (
        "NotoSansSC-Medium.ttf",
        "NotoSansSC-SemiBold.ttf",
        "MaShanZheng-Regular.ttf",
    )
    for name in names:
        raw = QRawFont(str(caption_faces.FOLDER / name), 100)
        assert raw.ascent() == pytest.approx(101.6, abs=0.6), name
        assert raw.descent() == pytest.approx(25.4, abs=0.6), name
    font = CaptionLayout()._font(row("我们", "zh"), 1.0, False)
    assert QFontMetricsF(font).height() / font.pixelSize() < 1.32


# -- in the captions -------------------------------------------------------------


@pytest.mark.usefixtures("faces")
def test_a_face_that_lands_lays_every_caption_out_again(tmp_path: Path) -> None:
    """479: text laid out before a face was added and drawn after came out
    as boxes - so a face landing mid-session clears the laid-out rows."""
    engine = CaptionLayout()
    row = CaptionRow("Hello", RowKind.ORIGINAL, Language("en"), 0, True)
    line = Line(1, SourceId("app"), False, (row,), False, False, datetime(2026, 11, 18))
    engine.laid(line, 400, 1.0)
    engine.laid(line, 400, 1.0)
    first = engine.laid_out
    before = caption_faces.generation
    landed = tmp_path / "notoserifsc-upright-2026.11.18.ttf"
    landed.write_bytes((caption_faces.FOLDER / "BeVietnamPro-Medium.ttf").read_bytes())
    added = caption_faces.add([landed])
    # Windows names the face by its family; Linux's fontconfig by its weight too
    # Windows names the file's family once; Linux's fontconfig may give both
    # names for it (train C's Checks (Linux), 2026-11-18)
    assert added and set(added) <= {"Be Vietnam Pro", "Be Vietnam Pro Medium"}
    assert caption_faces.generation == before + 1
    engine.laid(line, 400, 1.0)
    assert engine.laid_out > first  # laid out again, in the faces as they are
    assert caption_faces.add([landed]) == added  # once only
    assert caption_faces.generation == before + 1


@pytest.mark.usefixtures("faces")
@pytest.mark.parametrize("weight", [QFont.Weight.DemiBold, QFont.Weight.Bold])
def test_semibold_and_bold_chinese_stay_in_their_face_not_the_readings_cut(
    weight: QFont.Weight,
) -> None:
    """532's measure: Noto Sans SC's SemiBold holds only what readings
    draw. Asked for Semibold or Bold by weight, Qt took it, hadn't the
    characters, and drew them in the next face: YaHei UI before 532, Ma
    Shan Zheng after - a brush face in a learner's chosen sans."""
    from PySide6.QtGui import QTextLayout

    style = replace(
        CaptionStyle(), weight=weight, faces=(("zh", "Noto Sans SC Captions"),)
    )
    font = CaptionLayout(style)._font(row("我们去看电影", "zh"), 1.0, False)
    laid = QTextLayout("我们去看电影", font)
    laid.beginLayout()
    line = laid.createLine()
    line.setLineWidth(4000)
    laid.endLayout()
    drawn = {run.rawFont().familyName() for run in line.glyphRuns()}
    assert drawn == {"Noto Sans SC Captions"}
    reading = reading_lines.reading_font(font)
    assert reading.styleName() == "" and reading.weight() == QFont.Weight.DemiBold
