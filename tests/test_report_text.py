from polyglotic_desktop.core.report_text import clean_report_text, limited_clean_text


def test_report_text_is_nfc_trimmed_and_keeps_newlines_and_tabs() -> None:
    assert clean_report_text("  e\u0301\tthere\n  ") == "é\tthere"


def test_report_text_removes_controls_zero_width_and_bidi_marks() -> None:
    controls = "\x00\x08\x0b\x0c\x0e\x1f\x7f"
    zero_width = "\u200b\u200c\u200d\u2060\ufeff"
    bidi = "".join(
        chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))
    )
    assert clean_report_text(f"a{controls}{zero_width}{bidi}b") == "ab"


def test_report_text_keeps_at_most_two_blank_lines_and_limits_code_points() -> None:
    assert clean_report_text("a\n\n\n\n\n b") == "a\n\n\n b"
    assert limited_clean_text("e\u0301🙂x", 2) == "é🙂"


def test_supplementary_characters_each_count_as_one_code_point() -> None:
    assert limited_clean_text("🙂" * 3, 2) == "🙂🙂"
