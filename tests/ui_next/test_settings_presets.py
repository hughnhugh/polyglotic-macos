"""Settings > Presets (polyglotic-hq 556, decision 0264): the presets, each
to use; New preset; the preset in use to rename, reset or delete; and the
line in every caption section saying which preset is in use (587)."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QPushButton

from polyglotic_desktop.ui_next.settings_page import SECTIONS, SettingsPage
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.preset_menu import (
    PresetItem,
    PresetMenu,
    PresetsView,
)

MENU = PresetMenu(
    (
        PresetItem("everyday", "Everyday"),
        PresetItem("conversation", "Conversation"),
        PresetItem("video", "Video, film & TV"),
        PresetItem("learning", "Learning"),
        PresetItem("own1", "Anime nights", own=True),
    ),
    "video",
    changes=(("Word links", "Off"), ("Subtitles along the bottom", "On")),
)


@pytest.fixture
def page(qapp: QApplication) -> Iterator[tuple[SettingsPage, PresetsView]]:
    view = PresetsView(MENU)
    made = SettingsPage(
        [("margin", "Margin")],
        QAction("Tell us"),
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
        presets=view,
    )
    yield made, view
    if shiboken6.isValid(made):
        made.close()
        shiboken6.delete(made)


def test_presets_are_the_first_section(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    assert SECTIONS[0] == "presets"


def test_each_preset_to_use_and_the_one_in_use_said(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, view = page
    settings.show_section("presets")
    used: list[str] = []
    view.chose = used.append
    rows = settings.presets
    assert rows.findChild(QPushButton, "presets.use.video") is None  # in use
    use = rows.findChild(QPushButton, "presets.use.conversation")
    assert use is not None
    use.click()
    assert used == ["conversation"]


def test_the_preset_in_use_renamed_reset_and_what_it_changes(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, view = page
    settings.show_section("presets")
    steps: list[object] = []
    view.rename = lambda key, name: steps.append(("rename", key, name))
    view.reset = lambda key: steps.append(("reset", key))
    card = settings.preset
    assert card.name.text() == "Video, film & TV"
    assert "Word links: Off" in card.changes.text()
    assert card.delete.isHidden()  # a built-in one stays
    card.name.setText("Films")
    card.name.editingFinished.emit()
    assert not card.reset.isEnabled()  # nothing saved in it to restore (587)
    view.follow(replace(MENU, restorable=True))
    assert card.reset.text() == "Restore Video, film && TV's defaults"
    assert card.reset.shortcut().isEmpty()
    card.reset.click()
    assert steps == [("rename", "video", "Films"), ("reset", "video")]


def test_ones_own_can_be_deleted_and_a_sixth_not_made(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, view = page
    settings.show_section("presets")
    view.follow(PresetMenu(MENU.items, "own1", can_add=False))
    assert not settings.preset.delete.isHidden()
    assert not settings.presets.new.isEnabled()


def test_the_presets_section_says_which_preset_is_in_use(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, _view = page
    settings.show_section("presets")
    assert not settings.preset_line.isHidden()
    assert "Video, film & TV" in settings.preset_line.words.text()
    settings.show_section("app")  # no preset holds the app's own settings
    assert settings.preset_line.isHidden()
