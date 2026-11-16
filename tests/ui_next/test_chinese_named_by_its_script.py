"""Chinese named by the script it's shown in (polyglotic-hq 433, from 432):
with "Show Mandarin in: Traditional", Mandarin's lines arrive converted, so a
transcript's Save and Copy name them "Chinese (Traditional)", and a picker
that means the language says "Chinese", not "Chinese (Simplified)"."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next.languages import (
    language_name,
    learned_name,
    show_mandarin_in_traditional,
    shown_name,
)


@pytest.fixture
def traditional() -> Iterator[None]:
    show_mandarin_in_traditional(True)
    try:
        yield
    finally:
        show_mandarin_in_traditional(False)


def test_a_picker_names_the_language(qapp: QApplication) -> None:
    assert language_name("zh") == "Chinese" == learned_name("zh")
    assert language_name("zh-hant") == "Chinese (Traditional)"  # its own target
    assert language_name("fr") == "French"


def test_lines_are_simplified_unless_shown_in_traditional(qapp: QApplication) -> None:
    assert shown_name("zh") == "Chinese (Simplified)"
    assert shown_name("zh-hant") == "Chinese (Traditional)"
    assert shown_name("en") == "English"


def test_lines_shown_in_traditional_say_so(
    qapp: QApplication, traditional: None
) -> None:
    assert shown_name("zh") == "Chinese (Traditional)"
    assert shown_name("zh-hant") == "Chinese (Traditional)"
    assert shown_name("ja") == "Japanese"  # only Mandarin's lines change
    assert language_name("zh") == "Chinese"  # a picker still names the language
