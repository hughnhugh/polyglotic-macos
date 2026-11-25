"""One app in its own window, plus everything else the PC plays
(polyglotic-hq DECISIONS.md #59, project 139): the setting and its rule
(one app only), the caption windows, Home's switch and rows, the labels,
Help's check, the transcript, the joined window and Show my speech, and
what the usage statistics are told. Made-up apps; the capture is a fake
(`test_main_wiring` has the sources; Windows' own behaviour was checked on
the user's PC by project 139, without keeping any audio)."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.sources import (
    EVERYTHING_ELSE,
    MIC,
    Capture,
    CaptureMode,
    SourceId,
)
from polyglotic_desktop.main import (
    adding_app,
    captioned_apps,
    chosen_capture,
    everything_else_change,
    follow_settings,
    follow_transcripts,
    picker_of,
    stop_captioning,
    wire_caption_windows,
    wire_transcripts,
)
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui.theme import SOURCE_COLORS
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.home import PickerCard
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.home import (
    AppRow,
    AppStatus,
    Picker,
    PickerView,
)
from polyglotic_desktop.ui_next.views.placement import Rect

KEY = "everything_else"
APP = "Web Browser"
APP_1 = SourceId("app-1")
ONE_AND_ELSE = AppSettings(whole_system=False, apps=(APP,), everything_else=True)


def ids(name: str) -> SourceId:
    return SourceId(f"app-{[APP, 'Video Player', 'Chat App'].index(name) + 1}")


# -- the setting and its rule ------------------------------------------------------


def test_everything_else_is_captioned_beside_one_app_only() -> None:
    """Windows leaves only one app out of a capture: with 0, 2 or 3 apps,
    or everything the PC plays, it doesn't apply (even if it was kept on)."""
    assert ONE_AND_ELSE.captions_everything_else
    assert not AppSettings(whole_system=False, apps=(APP,)).captions_everything_else
    for apps in ((), (APP, "Video Player"), (APP, "Video Player", "Chat App")):
        assert not replace(ONE_AND_ELSE, apps=apps).captions_everything_else
    assert not replace(ONE_AND_ELSE, whole_system=True).captions_everything_else


def test_the_setting_is_saved_and_read_back() -> None:
    stored = ONE_AND_ELSE.to_stored()
    assert stored["everything_else"] is True
    assert AppSettings.from_stored(stored).captions_everything_else
    odd = AppSettings.from_stored({"apps": [APP], "everything_else": "yes"})
    assert odd.everything_else is False  # not valid: its default


def test_it_has_a_colour_of_its_own() -> None:
    colours = ONE_AND_ELSE.source_colors_for()
    assert len({colours["mic"], colours[APP], colours[KEY]}) == 3
    assert colours[KEY] in SOURCE_COLORS


def test_a_window_for_the_app_then_one_for_everything_else() -> None:
    assert captioned_apps(ONE_AND_ELSE, True, ids) == [
        (APP, APP_1),
        (KEY, EVERYTHING_ELSE),
    ]
    two = replace(ONE_AND_ELSE, apps=(APP, "Video Player"))
    assert [k for k, _ in captioned_apps(two, True, ids)] == [APP, "Video Player"]
    windows_10 = captioned_apps(ONE_AND_ELSE, False, ids)  # unchanged there
    assert [k for k, _ in windows_10] == ["system"]


def test_turning_it_on_needs_one_app_and_fixes_its_colour() -> None:
    changes = everything_else_change(AppSettings(whole_system=False, apps=(APP,)), True)
    assert changes is not None and changes["everything_else"] is True
    colours = changes["source_colors"]
    assert isinstance(colours, dict) and KEY in colours
    assert everything_else_change(AppSettings(), True) is None
    assert (
        everything_else_change(
            AppSettings(whole_system=False, apps=(APP, "Chat App")), True
        )
        is None
    )
    assert (
        everything_else_change(replace(ONE_AND_ELSE, whole_system=True), True) is None
    )
    assert everything_else_change(ONE_AND_ELSE, False) == {"everything_else": False}


def test_stopping_it_or_its_app() -> None:
    """Its window's close (or Home's x) turns it off; its app's stops both -
    it can't stay on with no app (or come back with another)."""
    assert stop_captioning(ONE_AND_ELSE, KEY) == {"everything_else": False}
    assert stop_captioning(ONE_AND_ELSE, APP) == {"apps": (), "everything_else": False}
    everything = replace(ONE_AND_ELSE, whole_system=True)
    assert stop_captioning(everything, "system") == {
        "whole_system": False,
        "apps": (),
        "everything_else": False,
    }


def test_no_app_is_added_beside_it() -> None:
    """The limit, shown before it's hit (109's principle 8): while it's on,
    Home's + isn't asked for; and adding an app where it was kept on but
    didn't apply turns it off, so it can't come back with two apps."""
    assert adding_app(ONE_AND_ELSE, "Video Player") is None
    kept = replace(ONE_AND_ELSE, whole_system=True)
    changes = adding_app(kept, "Video Player")
    assert changes is not None and changes["everything_else"] is False


def test_the_usage_statistics_name_the_mode() -> None:
    assert chosen_capture(ONE_AND_ELSE) == Capture(
        CaptureMode.APPS_PLUS_REST, 1, my_speech=False
    )
    assert (
        chosen_capture(AppSettings(whole_system=False, apps=(APP,))).mode
        is CaptureMode.APPS
    )


# -- Home --------------------------------------------------------------------------


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def __getattr__(self, name: str) -> object:
        return lambda *args: self.calls.append((name, args))


def row(key: str, status: AppStatus = AppStatus.PLAYING) -> AppRow:
    return AppRow(key, key, "#ff6e9c", status)


ELSE_ROW = AppRow(KEY, "Everything else", "#6ee7a8", AppStatus.EVERYTHING_ELSE)


def test_the_switch_is_on_with_one_app_only() -> None:
    commands = Commands()
    two = PickerView(Picker(captioned=(row(APP), row("Chat App"))), commands)  # type: ignore[arg-type]
    two.set_everything_else(True)
    assert commands.calls == []  # not with two apps
    one = PickerView(Picker(captioned=(row(APP),)), commands)  # type: ignore[arg-type]
    assert one.value.everything_else_allowed and not one.value.full
    one.set_everything_else(True)
    assert commands.calls == [("set_everything_else", (True,))]
    on = Picker(captioned=(row(APP), ELSE_ROW), everything_else=True)
    assert on.apps == (row(APP),) and on.full  # no app added beside it
    PickerView(on, commands).add("Chat App")  # type: ignore[arg-type]
    assert ("add", ("Chat App",)) not in commands.calls


def test_the_pickers_rows_have_everything_else_after_its_app(
    qapp: QApplication,
) -> None:
    windows = CaptionWindows(None, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    found = FakeAppList().playing_apps()
    picker = picker_of(ONE_AND_ELSE, found, True, windows, False)
    assert [(r.key, r.label, r.status) for r in picker.captioned] == [
        (APP, APP, AppStatus.PLAYING),
        (KEY, "Everything else", AppStatus.EVERYTHING_ELSE),
    ]
    assert picker.everything_else and picker.full
    windows_10 = picker_of(ONE_AND_ELSE, found, False, windows, False)
    assert not windows_10.everything_else
    assert [r.status for r in windows_10.captioned] == [AppStatus.EVERYTHING]
    windows.close()


@pytest.fixture
def card(qapp: QApplication) -> Iterator[tuple[PickerCard, PickerView, Commands]]:
    commands = Commands()
    view = PickerView(Picker(captioned=(row(APP),)), commands)  # type: ignore[arg-type]
    built = PickerCard(view, SOURCE_COLORS)
    yield built, view, commands
    built.deleteLater()


def test_homes_switch_says_why_it_is_off(
    card: tuple[PickerCard, PickerView, Commands],
) -> None:
    built, view, commands = card
    switch = built.everything_else
    assert not switch.isHidden() and switch.switch.isEnabled()
    assert switch.detail.text() == pc_or_mac(
        "Everything the PC plays except Web Browser, in a window of its own",
        "Everything the Mac plays except Web Browser, in a window of its own",
    )
    switch.switch.click()
    assert commands.calls[-1] == ("set_everything_else", (True,))
    view.follow(Picker(captioned=(row(APP), row("Chat App"))))
    assert not switch.switch.isEnabled() and not switch.switch.isChecked()
    assert switch.detail.text().startswith("With one app only")
    view.follow(Picker())
    assert switch.isHidden()  # no app yet: nothing to be beside
    view.follow(
        Picker(captioned=(row("system", AppStatus.EVERYTHING),), whole_system=True)
    )
    assert switch.isHidden()  # everything the PC plays: nothing else
    view.follow(Picker(captioned=(row("system", AppStatus.EVERYTHING),), per_app=False))
    assert switch.isHidden()  # Windows 10: as before


def test_homes_switch_on_shows_its_row_and_the_limit(
    card: tuple[PickerCard, PickerView, Commands],
) -> None:
    built, view, _ = card
    view.follow(Picker(captioned=(row(APP), ELSE_ROW), everything_else=True))
    assert built.everything_else.switch.isChecked()
    assert list(built.rows) == [APP, KEY]
    assert built.rows[KEY].status.text() == pc_or_mac(
        "everything else the PC plays", "everything else the Mac plays"
    )
    assert not built.rows[KEY].stop.isHidden()  # x turns it off
    assert built.count.text() == "1 app + everything else"
    assert not built.full.isHidden()
    assert built.full.text().startswith("One app plus everything else")


# -- the caption windows, labels, transcript, joined window, my speech ----------------


class FakeSources:
    per_app = True
    sample_shown = False

    def app_id(self, name: str) -> SourceId:
        return APP_1

    def shown(self) -> dict[SourceId, tuple[str, str]]:
        return {APP_1: (APP, APP)}


@pytest.fixture
def switched(
    qapp: QApplication,
) -> Iterator[tuple[DesktopApp, CaptionWindows, Transcripts]]:
    store = MemorySettingsStore(
        {"apps": [APP], "everything_else": True, "targets": ["en"]}
    )
    desktop = DesktopApp(store, None, FakeAppList())
    areas = [Rect(0, 0, 1920, 1040)]
    windows = CaptionWindows(store, MIC, lambda: areas)
    transcripts = Transcripts(windows, store, areas=lambda: areas)
    wire_caption_windows(windows, desktop, lambda: None)
    wire_transcripts(transcripts, desktop)
    follow_settings(windows, desktop, FakeSources())  # type: ignore[arg-type]
    yield desktop, windows, transcripts
    transcripts.close()
    windows.close()
    desktop.close()


def test_its_window_label_and_colour(
    switched: tuple[DesktopApp, CaptionWindows, Transcripts],
) -> None:
    desktop, windows, _ = switched
    assert list(windows.windows) == [APP, KEY]
    window = windows.windows[KEY]
    assert window.source == EVERYTHING_ELSE
    labels = desktop.source_labels()
    assert labels[EVERYTHING_ELSE].name == "Everything else"
    assert labels[EVERYTHING_ELSE].color != labels[APP_1].color
    window.buttons["stop"].click()  # its window's close turns it off
    assert desktop.settings.value.apps == (APP,)
    assert not desktop.settings.value.everything_else


def test_its_transcript_joined_window_and_my_speech(
    switched: tuple[DesktopApp, CaptionWindows, Transcripts],
) -> None:
    desktop, windows, transcripts = switched
    for update in finished_updates(2, source=EVERYTHING_ELSE):
        desktop.feed.apply(update)
    assert len(transcripts.transcripts[KEY].lines) == 2
    assert [a.text() for a in transcripts.menu.actions()] == [APP, "Everything else"]
    windows.set_show_mic(KEY, True)
    assert desktop.caption_mic.isChecked()
    assert MIC in windows.targets()  # the mic's lines go to its window too
    windows.join()
    assert windows.joined_window is not None


def test_helps_check_looks_at_it(
    switched: tuple[DesktopApp, CaptionWindows, Transcripts],
) -> None:
    desktop, _, _ = switched
    desktop.set_app_sources({APP_1: (APP, APP)})
    ticked = desktop.caption_facts().ticked
    assert [(t.id, t.name, t.kind) for t in ticked] == [
        (APP_1, APP, "app"),
        (EVERYTHING_ELSE, "Everything else", "system"),
    ]


def test_every_place_captions_are_kept_settles_after_the_time_chosen(
    switched: tuple[DesktopApp, CaptionWindows, Transcripts],
) -> None:
    """polyglotic-hq 309: how long shown text may still change is one
    setting - each caption window, each transcript and the app's own feed
    follow it (decision 0088: each keeps a caption history)."""
    desktop, windows, transcripts = switched
    assert {w.view.settle_after for w in windows.windows.values()} == {1.0}
    desktop.settings.update(text_settles_after=2.0)
    follow_settings(windows, desktop, FakeSources())  # type: ignore[arg-type]
    follow_transcripts(transcripts)
    assert {w.view.settle_after for w in windows.windows.values()} == {2.0}
    assert {t.settle_after for t in transcripts.transcripts.values()} == {2.0}
    assert transcripts.transcripts and desktop.feed.history.settle_after == 2.0
