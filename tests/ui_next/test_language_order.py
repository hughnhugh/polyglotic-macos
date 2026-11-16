"""The language pickers' order (polyglotic-hq 293, the user: "It makes it
feel like the app is only for chinese / english"): the learner's own
languages first - Windows' display languages that captions are translated
into - then the rest by name. Nothing is pinned on top for everyone."""

import pytest
from PySide6.QtWidgets import QApplication

from polyglotic_desktop.ui_next.languages import language_name, target_languages


def codes(own: list[str] | None) -> list[str]:
    return [str(c) for c in target_languages(own)]


def test_the_learners_own_languages_come_first(qapp: QApplication) -> None:
    assert codes(["ja", "fr"])[:2] == ["ja", "fr"]
    assert codes(["zh-hant"])[0] == "zh-hant"
    assert codes(["sw", "de"])[0] == "de"  # one not offered is left out


def test_then_every_other_by_name_none_pinned(qapp: QApplication) -> None:
    found = codes([])
    names = [language_name(c) for c in found]
    assert names == sorted(names)
    assert found[0] == "ar" and found.index("en") > found.index("zh")  # Arabic first
    with_japanese = codes(["ja"])
    assert sorted(with_japanese) == sorted(found)  # each once, nothing lost


def test_without_a_list_it_reads_windows(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default is Windows' own list (`own_languages`): whatever this PC
    says, every language is there once."""
    monkeypatch.undo()  # this PC's own, not the tests' English one
    found = codes(None)
    assert sorted(found) == sorted(codes([])) and len(set(found)) == len(found)
