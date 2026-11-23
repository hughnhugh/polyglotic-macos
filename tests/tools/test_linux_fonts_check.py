"""What 571's fonts check counts as found (tools/linux_fonts_check.py) - the
check itself runs on GitHub's Linux runners, in each distribution's fonts."""

from tools import linux_fonts_check


def test_a_languages_findings_name_boxes_and_the_wrong_face() -> None:
    clean = {"language": "ja", "boxes": [], "chinese_in_a_japanese_face": []}
    assert linux_fonts_check.findings(clean) == []
    found = linux_fonts_check.findings(
        {"language": "ja", "boxes": ["⚙ Settings"], "japanese_in_a_chinese_face": ["x"]}
    )
    assert found[0].startswith("boxes: 1") and found[1].startswith("japanese_in")
    assert linux_fonts_check.findings({"error": "no Qt"}) == ["didn't run: no Qt"]


def test_scripts_are_told_apart_by_their_blocks() -> None:
    assert [linux_fonts_check.script_of(c) for c in "日に한ไहЖa1"] == [
        "han",
        "kana",
        "hangul",
        "thai",
        "devanagari",
        "cyrillic",
        "latin",
        "",
    ]
