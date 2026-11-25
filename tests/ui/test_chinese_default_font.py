"""952: Chinese captions default to each OS's plain CJK UI face while keeping
explicit brush/calligraphy choices from existing saved settings."""

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import CaptionRow, RowKind
from polyglotic_desktop.main import caption_look
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next import caption_faces, fonts, reading_lines
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout
from polyglotic_desktop.ui_next.caption_window import caption_style
from polyglotic_desktop.ui_next.face_rows import FaceBox
from polyglotic_desktop.ui_next.views.caption_window import face_chosen

SETTINGS_FILES = Path(__file__).resolve().parent / "settings_files"


@pytest.mark.parametrize(
    ("system", "simplified", "traditional"),
    [
        ("win32", "Microsoft YaHei UI", "Microsoft JhengHei UI"),
        ("darwin", "PingFang SC", "PingFang TC"),
        ("linux", "Noto Sans CJK SC", "Noto Sans CJK TC"),
    ],
)
def test_fresh_install_chinese_font_is_the_plain_face_per_platform(
    system: str, simplified: str, traditional: str
) -> None:
    fresh = Settings(MemorySettingsStore({})).value
    look = caption_look(fresh)
    assert face_chosen(look, "zh") is None
    assert face_chosen(look, "zh-hant") is None
    assert fonts.caption_families("zh", face_chosen(look, "zh"), system=system)[0] == (
        simplified
    )
    assert (
        fonts.caption_families("zh-hant", face_chosen(look, "zh-hant"), system=system)[
            0
        ]
        == traditional
    )


@pytest.mark.parametrize("filename", ["0.1.9.json", "0.1.10-preview.1.json"])
def test_untouched_existing_profiles_move_to_the_new_plain_default(
    filename: str,
) -> None:
    profiles = json.loads((SETTINGS_FILES / filename).read_text(encoding="utf-8"))
    for name, stored in profiles.items():
        loaded = Settings(MemorySettingsStore(stored)).value
        look = caption_look(loaded)
        assert face_chosen(look, "zh") is None, (filename, name)
        assert face_chosen(look, "zh-hant") is None, (filename, name)
        assert (
            fonts.caption_families("zh", face_chosen(look, "zh"), system="win32")[0]
            == "Microsoft YaHei UI"
        )
        assert (
            fonts.caption_families(
                "zh-hant", face_chosen(look, "zh-hant"), system="win32"
            )[0]
            == "Microsoft JhengHei UI"
        )


def test_empty_default_marker_moves_to_the_new_plain_default() -> None:
    """`caption_faces: {"zh": ""}` encodes 'use this language's default' and
    cannot be distinguished from resetting to default, so it moves to the new
    plain default."""
    stored = {
        "caption_faces": {"zh": "", "zh-hant": "", "en": "PT Sans"},
        "changed": ["caption_faces"],
    }
    loaded = Settings(MemorySettingsStore(stored)).value
    look = caption_look(loaded)
    assert face_chosen(look, "zh") is None
    assert face_chosen(look, "zh-hant") is None
    assert face_chosen(look, "en") == "PT Sans"
    assert (
        fonts.caption_families("zh", face_chosen(look, "zh"), system="win32")[0]
        == "Microsoft YaHei UI"
    )


@pytest.mark.parametrize(
    ("saved_faces", "language", "expected"),
    [
        # Quiet recommended look or explicit Ma Shan Zheng choice
        (
            {"zh": "Ma Shan Zheng Captions", "zh-hant": "LXGW WenKai TC Captions"},
            "zh",
            "Ma Shan Zheng Captions",
        ),
        (
            {"zh": "Ma Shan Zheng Captions", "zh-hant": "LXGW WenKai TC Captions"},
            "zh-hant",
            "LXGW WenKai TC Captions",
        ),
        # Paper recommended look or explicit Polyglotic Kai choice
        ({"zh": "Polyglotic Kai"}, "zh", "Polyglotic Kai"),
    ],
)
def test_existing_user_who_picked_brush_face_keeps_it(
    saved_faces: dict[str, str], language: str, expected: str
) -> None:
    stored = {"caption_faces": saved_faces, "changed": ["caption_faces"]}
    loaded = Settings(MemorySettingsStore(stored)).value
    look = caption_look(loaded)
    assert face_chosen(look, language) == expected
    assert (
        fonts.caption_families(language, face_chosen(look, language), system="win32")[0]
        == expected
    )


def test_legacy_global_brush_font_choice_is_preserved() -> None:
    stored = {"caption_font": "Ma Shan Zheng Captions", "changed": ["caption_font"]}
    loaded = AppSettings.from_stored(stored)
    look = caption_look(loaded)
    assert face_chosen(look, "zh") == "Ma Shan Zheng Captions"
    assert (
        fonts.caption_families("zh", face_chosen(look, "zh"), system="win32")[0]
        == "Ma Shan Zheng Captions"
    )


def test_plain_default_readings_and_latin_follow_plain_face_metrics(
    qapp: QApplication,
) -> None:
    caption_faces.load()
    engine = CaptionLayout(caption_style(caption_look(AppSettings())))
    zh_row = CaptionRow(
        "我们比较focus在找工作", RowKind.ORIGINAL, Language("zh"), 0, True
    )
    font = engine._font(zh_row, 1.0, False)
    expected_px = round(engine.style.text_px * fonts.size("zh"))
    assert font.families()[0] == fonts.default_family("zh")
    assert (
        font.pixelSize() == expected_px
    )  # plain CJK scale (1.05), not calligraphy (1.13)
    assert engine._latin(zh_row, font) is None
    reading = reading_lines.reading_font(font)
    assert reading.families()[0] == fonts.default_family("zh")


def test_face_box_still_offers_brush_and_selects_explicitly(
    qapp: QApplication,
) -> None:
    box = FaceBox("zh")
    picked: list[object] = []
    box.chosen.connect(picked.append)
    try:
        assert box.currentData() == ""
        assert box.currentText() == f"{fonts.default_family('zh')} (Default)"
        brush_index = box.findData("Ma Shan Zheng Captions")
        assert brush_index >= 0
        box.setCurrentIndex(brush_index)
        assert picked == ["Ma Shan Zheng Captions"]
        # Showing a previously explicit platform face matches the default entry cleanly
        box.show_family(fonts.default_family("zh"))
        assert box.currentData() == ""
    finally:
        box.deleteLater()
