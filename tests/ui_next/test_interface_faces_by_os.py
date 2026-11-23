"""An interface in Japanese, Korean, Thai or Hindi draws its own script in
its own faces on every OS, not only Windows (polyglotic-hq 571): on Linux a
Japanese interface's kanji were in the Chinese face its list named next,
Noto Sans CJK SC - China's shapes for Japan's characters."""

import sys

import pytest

from polyglotic_desktop.ui_next import style


def test_a_japanese_interface_names_linuxs_japanese_face_before_the_chinese() -> None:
    assert style.script_faces("ja", "linux") == [
        "Yu Gothic UI",
        "Meiryo UI",
        "Noto Sans CJK JP",
        "Source Han Sans",
    ]


def test_each_script_interface_names_linuxs_own_faces() -> None:
    assert "Noto Sans CJK KR" in style.script_faces("ko", "linux")
    assert "Noto Sans Thai" in style.script_faces("th", "linux")
    assert "Noto Sans Devanagari" in style.script_faces("hi", "linux")
    assert "Hiragino Sans" in style.script_faces("ja", "darwin")


def test_windows_faces_are_as_they_were() -> None:
    assert style.script_faces("ja", "win32") == ["Yu Gothic UI", "Meiryo UI"]
    assert style.script_faces("hi", "win32") == ["Nirmala UI"]
    assert style.script_faces("en", "linux") == []
    assert style.script_faces("zh_CN", "linux") == []


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux's own lists")
def test_on_linux_the_japanese_face_comes_before_the_chinese_one() -> None:
    families = style._ui_families(traditional=False, language="ja")
    assert families.index("Noto Sans CJK JP") < families.index("Noto Sans CJK SC")
    # its Latin letters in Linux's Latin face, as Windows' are in Segoe UI
    assert families.index("Noto Sans") < families.index("Noto Sans CJK JP")
    assert "noto sans cjk jp" in style.CHINESE_FACES  # cleared as Chinese ones are
