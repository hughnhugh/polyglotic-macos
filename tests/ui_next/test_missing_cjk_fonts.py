"""Missing system CJK font family logging (polyglotic-hq 647; 644 bug 5).

Minimal Linux installs (or WSL) without `fonts-noto-cjk` show boxes for
Japanese and Traditional Chinese glyphs. Ubuntu and Fedora desktops already
ship CJK fonts, so the app doesn't bundle them - it logs the missing CJK font
families once instead.
"""

import logging

import pytest

from polyglotic_desktop.ui_next import caption_faces, fonts


def test_missing_cjk_families_reports_only_absent_scripts_on_linux() -> None:
    assert set(fonts.missing_cjk_families([], system="linux")) == {
        "zh",
        "zh-hant",
        "yue",
        "ja",
        "ko",
    }
    # Full desktop (Ubuntu / Fedora with Noto Sans CJK installed)
    full = [
        "Noto Sans",
        "Noto Sans CJK SC",
        "Noto Sans CJK TC",
        "Noto Sans CJK HK",
        "Noto Sans CJK JP",
        "Noto Sans CJK KR",
    ]
    assert fonts.missing_cjk_families(full, system="linux") == {}
    # Only Simplified installed -> Traditional, Cantonese, Japanese, Korean missing
    partial = ["Noto Sans CJK SC"]
    assert set(fonts.missing_cjk_families(partial, system="linux")) == {
        "zh-hant",
        "yue",
        "ja",
        "ko",
    }
    # Windows has no OTHER_OS list
    assert fonts.missing_cjk_families([], system="win32") == {}


def test_log_missing_cjk_fonts_logs_once_when_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(caption_faces, "_cjk_checked", False)
    with caplog.at_level(logging.WARNING, logger=caption_faces.__name__):
        first = caption_faces.log_missing_cjk_fonts(
            installed=["DejaVu Sans"], system="linux"
        )
        second = caption_faces.log_missing_cjk_fonts(
            installed=["DejaVu Sans"], system="linux"
        )
    assert "ja" in first and "zh-hant" in first
    assert second == {}
    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Noto Sans CJK JP" in warnings[0]
    assert "Noto Sans CJK TC" in warnings[0]
    assert "fonts-noto-cjk" in warnings[0]


def test_log_missing_cjk_fonts_stays_quiet_when_cjk_fonts_exist(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(caption_faces, "_cjk_checked", False)
    installed = [
        "Noto Sans CJK SC",
        "Noto Sans CJK TC",
        "Noto Sans CJK HK",
        "Noto Sans CJK JP",
        "Noto Sans CJK KR",
    ]
    with caplog.at_level(logging.WARNING, logger=caption_faces.__name__):
        missing = caption_faces.log_missing_cjk_fonts(
            installed=installed, system="linux"
        )
    assert missing == {}
    assert caplog.records == []
