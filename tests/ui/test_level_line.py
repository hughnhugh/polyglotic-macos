"""Home's line asking for the level (polyglotic-hq 293): the first run
doesn't ask it, so words are estimated at a middle level and Home says,
quietly, "Set your level so we know which words to explain" - until the
learner sets it or says Not now. Offscreen."""

import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.core.shared import Level
from polyglotic_desktop.ui.level_picker import LevelPicker


def line_shown(built: Built) -> bool:
    return not built.hub.home.level_line.isHidden()


def button(built: Built, name: str) -> QPushButton:
    found = built.hub.home.level_line.findChild(QPushButton, name)
    assert found is not None
    return found


def test_shown_until_the_level_is_set(qapp: QApplication) -> None:
    built = Built(MemorySettingsStore(), tools=True)
    tools = built.desktop.tools
    assert tools is not None and tools.vocabulary.line is None
    assert line_shown(built)
    tools.vocabulary.set_level(Level(tools.vocabulary.scheme, 2))
    assert not line_shown(built)
    built.close()


def test_not_now_hides_it_for_good(qapp: QApplication) -> None:
    store = MemorySettingsStore()
    built = Built(store, tools=True)
    button(built, "home.level.not_now").click()
    assert not line_shown(built)
    assert store.values["level_line_dismissed"] is True
    built.close()
    again = Built(store, tools=True)  # the next start
    assert not line_shown(again)
    again.close()


def test_not_for_a_language_with_no_levels(qapp: QApplication) -> None:
    """The level is a full dictionary's: a learner of Spanish alone (a basic
    dictionary) isn't asked, nor one whose chosen language runs only from
    the next start - and adding Spanish hides it at once."""
    built = Built(MemorySettingsStore({"also_learning": ["es"]}), tools=True)
    assert not line_shown(built)
    built.close()
    built = Built(MemorySettingsStore({"learning": "en"}), tools=True)  # zh runs
    assert not line_shown(built)
    built.close()
    built = Built(MemorySettingsStore(), tools=True)
    assert line_shown(built)
    built.desktop.settings.update(also_learning=("es",))
    assert not line_shown(built)
    built.close()


def test_without_a_learners_tools_there_is_no_line(qapp: QApplication) -> None:
    built = Built(MemorySettingsStore(), tools=False)
    assert not line_shown(built)
    built.close()


def test_set_your_level_opens_the_setting(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no language chosen yet, Learning - where one is chosen, and its
    card has Change your level; with the language in use chosen, the level
    picker itself."""
    pickers: list[LevelPicker] = []

    def exec_(dialog: LevelPicker) -> int:
        pickers.append(dialog)
        return 0  # closed

    monkeypatch.setattr(LevelPicker, "exec", exec_)
    built = Built(MemorySettingsStore(), tools=True)
    button(built, "home.level.set").click()
    assert built.hub.window.current == "learning" and pickers == []
    built.close()
    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    button(built, "home.level.set").click()
    assert len(pickers) == 1
    built.close()
