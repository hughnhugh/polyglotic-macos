"""Explicit Settings saves and bar autosave (decisions 0283 and 0290)."""

import time
from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.main import Panels, follow_presets
from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.preset_menu import (
    PresetItem,
    PresetMenu,
    PresetsView,
    Undo,
)

ITEMS = (
    PresetItem("everyday", "Everyday"),
    PresetItem("conversation", "Conversation"),
    PresetItem("video", "Video, film & TV"),
    PresetItem("learning", "Learning"),
    PresetItem("own1", "Learning 2", own=True),
)
EDITED = PresetMenu(ITEMS, "learning", edited=3)


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, areas)
    found.set_captioned([("Discord.exe", APP)])
    yield found
    found.close()


def _window(windows: CaptionWindows, qapp: QApplication) -> CaptionWindow:
    window = windows.windows["Discord.exe"]
    window.show()
    qapp.processEvents()
    return window


def test_the_chip_keeps_its_name_while_settings_has_a_draft(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = _window(windows, qapp)
    windows.set_presets(PresetMenu(ITEMS, "learning"))
    assert window.preset_chip.text() == "Learning ▾"
    windows.set_presets(EDITED)
    assert window.preset_chip.text() == "Learning ▾"
    assert window.preset_chip.accessibleName() == "Preset: Learning"


def test_the_dropdown_leaves_save_save_as_and_discard_to_settings(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = _window(windows, qapp)
    windows.set_presets(EDITED)
    window.toggle_presets()
    dropdown = window.presets
    assert dropdown is not None
    names = [b.objectName() for b in dropdown.findChildren(QPushButton)]
    assert not {
        "presets.step.save",
        "presets.step.save_as",
        "presets.step.discard",
    }.intersection(names)
    assert "presets.customise" in names


def test_a_built_in_restores_its_defaults_and_ones_own_renames_and_deletes(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = _window(windows, qapp)
    windows.set_presets(PresetMenu(ITEMS, "everyday", restorable=True))
    window.toggle_presets()
    dropdown = window.presets
    assert dropdown is not None

    def names() -> set[str]:
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        return {b.objectName() for b in dropdown.findChildren(QPushButton)}

    assert "presets.step.restore" in names()
    assert "presets.step.delete" not in names()
    windows.set_presets(PresetMenu(ITEMS, "own1"))
    qapp.processEvents()
    assert {"presets.step.rename", "presets.step.delete"} <= names()
    assert "presets.step.restore" not in names()


def test_undo_on_the_notice_line_is_a_click(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    window = _window(windows, qapp)
    steps: list[str] = []
    windows.preset_step.connect(steps.append)
    windows.offer_undo("Changes to <Learning> weren't saved.", 8.0)
    notice = window.findChild(QLabel, "caption_window.notice")
    assert notice is not None and notice.isVisible()
    assert "&lt;Learning&gt;" in notice.text()  # a learner's name, never markup
    assert not notice.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    notice.linkActivated.emit("undo")
    assert steps == ["undo"]
    window.show_notice("Copied the newest caption")  # a notice without a step
    assert notice.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


@pytest.fixture
def page(qapp: QApplication) -> Iterator[tuple[SettingsPage, PresetsView]]:
    view = PresetsView(PresetMenu(ITEMS, "learning"))
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


def test_the_settings_line_says_what_isnt_saved_with_its_steps(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, view = page
    settings.show_section("presets")
    line = settings.preset_line
    assert not line.isHidden() and line.words.text() == "Using the preset Learning"
    assert not line.save_as.isHidden() and line.save.isHidden()
    view.follow(EDITED)
    assert line.words.text() == "Preset: Learning · 3 changes not saved"
    assert line.save.text() == "Save to Learning"
    assert not line.save.isHidden() and not line.discard.isHidden()
    saved: list[str] = []
    view.save = lambda: saved.append("save")
    view.discard = lambda: saved.append("discard")
    line.save.click()
    line.discard.click()
    assert saved == ["save", "discard"]
    view.follow(PresetMenu(ITEMS, "conversation", undo=(Undo.SWITCHED, "Learning")))
    assert "Changes to Learning weren't saved" in line.words.text()
    assert not line.undo.isHidden() and line.save.isHidden()


def test_the_line_is_only_where_a_presets_settings_are(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, _view = page
    settings.show_section("presets")
    assert not settings.preset_line.isHidden()
    for section in (
        "look",
        "links",
        "readings",
        "timing",
        "speech",
        "dictation",
        "hotkeys",
        "app",
        "lab",
    ):
        settings.show_section(section)
        assert settings.preset_line.isHidden(), section


def test_save_as_names_the_new_preset_in_the_line(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, view = page
    settings.show_section("presets")
    line = settings.preset_line
    made: list[str] = []
    view.add = made.append
    line.save_as.click()
    assert not line.name.isHidden() and line.name.text() == "Learning 3"  # 2 taken
    line.name.setText("Films with friends")
    line.name.returnPressed.emit()
    assert made == ["Films with friends"] and line.name.isHidden()
    line.save_as.click()
    line.cancel.click()
    assert made == ["Films with friends"] and not line.save_as.isHidden()


def test_a_dropdowns_save_as_opens_the_line_on_presets(
    page: tuple[SettingsPage, PresetsView],
) -> None:
    settings, view = page
    settings.show_section("app")
    view.naming.change(True)  # `main`, for a window's "Save as new preset…"
    assert not settings.preset_line.isHidden()  # on Presets now
    assert not settings.preset_line.name.isHidden()


@pytest.fixture
def wired(qapp: QApplication) -> Iterator[tuple[Settings, CaptionWindows, Panels]]:
    settings = Settings(MemorySettingsStore({}))
    windows = CaptionWindows(None, MIC, areas)
    windows.set_captioned([("Discord.exe", APP)])
    panels = Panels(settings, windows)
    settings.changed.connect(lambda: follow_presets(windows, settings.value))
    windows.preset_step.connect(panels.preset_step)  # as `main` wires them
    yield settings, windows, panels
    windows.close()


def _said(windows: CaptionWindows) -> str:
    return windows.windows["Discord.exe"].notices.showing(time.monotonic())[1] or ""


def test_switching_with_changes_not_saved_offers_undo(
    wired: tuple[Settings, CaptionWindows, Panels],
) -> None:
    settings, windows, panels = wired
    panels.choose_preset("learning")
    settings.update(fade_after=6.0)
    assert windows.preset_menu.edited == 1
    panels.choose_preset("conversation")
    assert settings.value.preset == "conversation"
    assert "learning" not in settings.value.preset_values  # nothing saved
    assert 'href="undo"' in _said(windows)
    assert windows.preset_menu.undo == (Undo.SWITCHED, "Learning")
    windows.preset_step.emit("undo")  # Undo on a window's notice line
    assert settings.value.preset == "learning" and settings.value.fade_after == 6.0
    assert windows.preset_menu.edited == 1 and windows.preset_menu.undo is None


def test_a_switch_with_nothing_lost_offers_nothing_and_the_same_one_is_no_step(
    wired: tuple[Settings, CaptionWindows, Panels],
) -> None:
    settings, windows, panels = wired
    panels.choose_preset("learning")
    assert windows.preset_menu.undo is None and "undo" not in _said(windows)
    settings.update(fade_after=6.0)
    panels.choose_preset("learning")  # picked again: the change stays
    assert settings.value.fade_after == 6.0 and windows.preset_menu.edited == 1


def test_undo_goes_once_anything_changes_after_the_step(
    wired: tuple[Settings, CaptionWindows, Panels],
) -> None:
    settings, windows, panels = wired
    settings.update(opacity=0.5)
    panels.discard_preset()
    assert windows.preset_menu.undo == (Undo.DISCARDED, "Everyday")
    settings.update(opacity=0.7)
    assert windows.preset_menu.undo is None
    panels.undo_preset()  # too late: nothing
    assert settings.value.opacity == 0.7


def test_save_and_save_as_from_the_steps(
    wired: tuple[Settings, CaptionWindows, Panels],
) -> None:
    settings, windows, panels = wired
    panels.choose_preset("learning")
    settings.update(fade_after=6.0)
    panels.presets.save()
    assert settings.value.preset_values["learning"] == {"fade_after": 6.0}
    assert windows.preset_menu.edited == 0
    settings.update(opacity=0.4)
    panels.save_preset_as(panels.presets.value.new_name)
    assert settings.value.preset == "own1"
    assert settings.value.preset_names["own1"] == "Learning 2"
    assert settings.value.preset_parents["own1"] == "learning"
    assert windows.preset_menu.chosen_parent == "learning"
    assert settings.value.preset_values["learning"] == {"fade_after": 6.0}


def test_video_defaults_to_instant(
    wired: tuple[Settings, CaptionWindows, Panels],
) -> None:
    settings, _windows, panels = wired
    panels.choose_preset("video")
    assert settings.value.caption_mode_chosen == "live"
    assert (
        use_presets.base_of(settings.value, "video")[0]["caption_mode_chosen"] == "live"
    )
