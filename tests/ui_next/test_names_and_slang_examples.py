"""Names and slang shows examples a learner understands at a glance - slang,
memes, names the speech model mishears, in English and Chinese - and takes
Chinese separators (the user's rehearsal feedback F13, polyglotic-hq 249,
2026-11-08: "use proper examples that the user will understand from the
examples, niche slang that's pop culture or homophones")."""

from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next.controls import Row
from polyglotic_desktop.ui_next.panels import LanguagesPanel
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    SessionLanguages,
    hints_from,
)


def test_the_examples_are_slang_memes_and_names(qapp: QApplication) -> None:
    panel = LanguagesPanel(LanguagesView(SessionLanguages()))
    shown = panel.hints.placeholderText()
    for example in ("rizz", "yyds", "鸡你太美", "原神"):
        assert example in shown
    assert "Caleb" not in shown and "HSK" not in shown
    said = panel.hints.toolTip()
    for example in ("no cap", "永远的神", "streamer"):
        assert example in said
    (row,) = [r for r in panel.findChildren(Row) if r.control is panel.hints]
    assert "the server doesn't keep them" in row.detail.text()  # still said


def test_chinese_commas_and_list_marks_separate_them_too() -> None:
    assert hints_from("yyds，绝绝子、鸡你太美, rizz") == (
        "yyds",
        "绝绝子",
        "鸡你太美",
        "rizz",
    )
    assert hints_from("原神；Valorant;  ") == ("原神", "Valorant")
