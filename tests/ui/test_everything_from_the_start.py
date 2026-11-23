"""A new learner's first launch captions everything the PC plays
(polyglotic-hq 484, decision 0225; the user, 2026-11-18: "Make the first
time launch easier, everything the PC plays should be [the default]"). It
follows the default until changed; whoever chose before keeps their choice;
its window is the learner's first, set up with the mic on; it says what it
takes in, and one click on Home captions one app instead."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.core.listening.sources import (
    WHOLE_SYSTEM,
    CaptureMode,
    SourceId,
)
from polyglotic_desktop.main import (
    Hub,
    Panels,
    adding_app,
    captioned_apps,
    captioning,
    chosen_capture,
    picker_of,
    wire_caption_windows,
)
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.recorded_captions import MIC
from polyglotic_desktop.ui.settings import FOLLOW_DEFAULT, AppSettings, Settings
from polyglotic_desktop.ui_next.caption_window import whose_captions
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.views.migration import SYSTEM, stored_windows
from polyglotic_desktop.ui_next.views.placement import Rect

EVERYTHING = pc_or_mac("Everything the PC plays", "Everything the Mac plays")


def ids(name: str) -> SourceId:
    return SourceId(f"app-{name}")


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


# -- the setting ----------------------------------------------------------------------


def test_a_new_learner_captions_everything_the_pc_plays() -> None:
    new = AppSettings.from_stored({})
    assert new.whole_system and new.source_chosen and captioning(new)
    assert "whole_system" in FOLLOW_DEFAULT
    assert captioned_apps(new, True, ids) == [("system", WHOLE_SYSTEM)]
    assert chosen_capture(new).mode is CaptureMode.WHOLE_SYSTEM


def test_a_learner_from_before_keeps_their_choice() -> None:
    """0.1.7 saved every key: nothing chosen stays nothing, apps stay apps."""
    nothing = AppSettings.from_stored({"whole_system": False, "apps": []})
    assert not nothing.whole_system and not nothing.source_chosen
    apps = AppSettings.from_stored({"whole_system": False, "apps": ["Chat"]})
    assert not apps.whole_system and apps.apps == ("Chat",)


def test_untouched_it_follows_the_default() -> None:
    """A record begun (0.1.8) that never changed it: today's default."""
    begun = AppSettings.from_stored({"whole_system": False, "changed": ["opacity"]})
    assert begun.whole_system


def test_apps_picked_under_the_old_default_stay_the_apps() -> None:
    """A record begun under 478's default (off): picking an app moved
    `apps` but not `whole_system`. Those apps were the choice."""
    picked = AppSettings.from_stored(
        {"whole_system": False, "apps": ["Chat"], "changed": ["apps", "source_colors"]}
    )
    assert not picked.whole_system
    assert captioned_apps(picked, True, ids) == [("Chat", ids("Chat"))]


def test_picking_an_app_is_a_choice_kept_at_the_next_start() -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    changes = adding_app(settings.value, "Chat")
    assert changes is not None
    settings.update(**changes)
    assert "whole_system" in settings.value.changed
    again = AppSettings.from_stored(store.values)
    assert not again.whole_system and again.apps == ("Chat",)


def test_one_click_captions_one_app_instead() -> None:
    """From everything the PC plays: that app alone - not the apps picked
    before everything was chosen (not shown), nor everything else beside it."""
    value = AppSettings(apps=("Old",), everything_else=True)
    assert value.whole_system
    changes = adding_app(value, "Chat")
    assert changes is not None
    assert changes["apps"] == ("Chat",) and changes["whole_system"] is False
    assert changes["everything_else"] is False


# -- its window is the learner's first --------------------------------------------------


def test_a_new_learners_saved_file_has_no_window_from_before() -> None:
    """Saved before any window opened (a choice in the first run), the
    file holds everything the PC plays as the default: not a window of the
    old interface's, so the set-up isn't skipped."""
    saved = Settings(MemorySettingsStore({}))
    saved.update(targets=("zh",))
    stored = stored_windows(saved.value.to_stored())
    assert stored.by_key == {} and not stored.set_up and stored.first_window
    # 0.1.7's, chosen: its window from before, as it was
    before = stored_windows({"whole_system": True, "targets": ["en"]})
    assert list(before.by_key) == [SYSTEM] and before.set_up


def test_the_first_window_is_everything_set_up_with_my_speech(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({})
    desktop = DesktopApp(store, None, FakeAppList())
    desktop.settings.update(targets=("zh",))  # saved before any window
    windows = CaptionWindows(store, MIC, areas, offer_set_up=True)
    try:
        windows.set_captioned(captioned_apps(desktop.settings.value, True, ids))
        (window,) = windows.windows.values()
        assert window.key == "system" and window.choices.show_mic
        assert window.set_up is not None  # it sets itself up
    finally:
        windows.close()
        desktop.close()


# -- it says what it is -----------------------------------------------------------------


def test_its_label_and_empty_window_say_everything(qapp: QApplication) -> None:
    desktop = DesktopApp(MemorySettingsStore({}), None, FakeAppList())
    try:
        assert desktop.source_labels()[WHOLE_SYSTEM].name == EVERYTHING
    finally:
        desktop.close()
    assert whose_captions(WHOLE_SYSTEM, EVERYTHING) == pc_or_mac(
        "Anything the PC plays is captioned here",
        "Anything the Mac plays is captioned here",
    )
    assert whose_captions(ids("Chat"), "Chat") == "Chat's captions appear here"


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    made = CaptionWindows(None, MIC, areas)
    yield made
    made.close()


def test_homes_rows_name_it_and_any_app_can_be_captioned_instead(
    windows: CaptionWindows,
) -> None:
    found = FakeAppList().playing_apps()
    value = AppSettings(apps=(found[0].name,))  # picked before everything
    picker = picker_of(value, found, True, windows, False)
    (row,) = picker.captioned
    assert row.key == "system" and row.label == EVERYTHING
    assert found[0].name in [a.name for a in picker.available]
    assert not picker.full


def test_one_app_instead_takes_everythings_window(qapp: QApplication) -> None:
    """Home's one click: the app is captioned in the window everything was
    in - its place, its language and my speech, as the set-up left them."""
    store = MemorySettingsStore({})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, areas, offer_set_up=True)
    wire_caption_windows(windows, desktop, lambda: None)
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    try:
        follow = lambda: windows.set_captioned(  # `main`'s, in short
            captioned_apps(desktop.settings.value, True, ids)
        )
        desktop.settings.changed.connect(follow)
        follow()
        everything = windows.windows["system"]
        everything.set_language("ja")
        assert everything.choices.show_mic  # the first window's
        built.add("Web Browser")
        assert list(windows.windows) == ["Web Browser"]
        app = windows.windows["Web Browser"].choices
        assert app.show_mic and app.translate_into == "ja"
        assert desktop.settings.value.apps == ("Web Browser",)
    finally:
        built.window.keep_in_tray = False
        built.window.close()
        windows.close()
        desktop.close()


def test_start_and_stop_on_home_follow_the_real_capture_choice(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({"whole_system": False})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, areas)
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    try:
        card = built.home.picker_card
        assert built.home.state.pause.isHidden()
        desktop.pause.setChecked(True)
        desktop.set_connection(ConnectionState.LISTENING)
        assert not built.home.state.pause.isHidden()
        assert card.start.accessibleName() == pc_or_mac(
            "Caption everything the PC plays", "Caption everything the Mac plays"
        )
        card.start.click()
        assert not desktop.pause.isChecked()
        assert not built.home.state.pause.isHidden()
        assert desktop.settings.value.whole_system and card.start.isHidden()
        card.rows["system"].stop.click()
        assert not desktop.settings.value.source_chosen
        assert built.home.state.pause.isHidden()
        built.sample_on = True
        built.follow()
        assert not built.home.state.pause.isHidden()
        built.sample_on = False
        built.follow()
        assert built.home.state.pause.isHidden()
        desktop.apps._take(FakeAppList().playing_apps())  # the next discovery result
        built.follow()
        assert card.start.accessibleName() == "Caption Web Browser"
        QTest.keyClick(card.start, Qt.Key.Key_Space)
        assert desktop.settings.value.apps == ("Web Browser",)
        assert not desktop.settings.value.whole_system
        assert not built.home.state.pause.isHidden()
        assert card.active.accessibleName() == "Captioning Web Browser"
        desktop.caption_failed()
        desktop.caption_failed()
        assert card.active.isHidden()  # Home now reports a captioning failure
    finally:
        windows.close()
        built.close()
        desktop.close()
