"""The new interface wired by `main` (decisions 0031 and 0032; polyglotic-hq
projects 112 and 132): the caption windows and the main window (`Hub`) in
step with the app's commands, state, tray and settings. Made-up apps and
captions only, offscreen."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built, FakeAppList, MemorySettingsStore, RecordingTray
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.captions import (
    Language,
)
from polyglotic_desktop.core.listening.sources import MIC, WHOLE_SYSTEM, SourceId
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.main import (
    Hub,
    Panels,
    QtListener,
    adding_app,
    caption_look,
    captioned_apps,
    captured,
    languages_settings,
    listening_settings,
    look_settings,
    picker_of,
    renaming,
    second_languages_changes,
    session_languages,
    stop_captioning,
    wire_caption_windows,
)
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import STORED_KEY, CaptionLook
from polyglotic_desktop.ui_next.views.home import AppStatus
from polyglotic_desktop.ui_next.views.placement import Rect

APP_1, APP_2 = SourceId("app-1"), SourceId("app-2")
EN, ZH, JA = Language("en"), Language("zh"), Language("ja")


def ids(name: str) -> SourceId:
    return SourceId(
        f"app-{['Chat App', 'Video Player', 'Web Browser', 'Game'].index(name) + 1}"
    )


def test_each_windows_language_is_its_sources_own() -> None:
    value = AppSettings(targets=("en",))
    chosen = listening_settings(value, {APP_1: (ZH,), APP_2: (), MIC: (ZH,)})
    assert chosen.targets == (ZH,)  # all of the windows' languages together
    assert chosen.targets_of(APP_1) == (ZH,)
    assert chosen.targets_of(APP_2) == ()  # Original only: not translated


def test_every_window_original_only_keeps_todays_targets_for_an_older_server() -> None:
    chosen = listening_settings(AppSettings(targets=("ja",)), {APP_1: ()})
    assert chosen.targets == (JA,) and chosen.targets_of(APP_1) == ()


def test_each_windows_spoken_language_is_its_sources_own() -> None:
    """The session's is the one every window names - what a server from
    before 2026-11-09 hears every source as - or Detect when they differ
    (263)."""
    value = AppSettings(spoken_language="en")
    agreed = listening_settings(value, {APP_1: (EN,)}, {APP_1: ZH, MIC: ZH})
    assert agreed.spoken_language == ZH and agreed.spoken_language_of(APP_1) == ZH
    differ = listening_settings(value, {APP_1: (EN,)}, {APP_1: ZH, APP_2: None})
    assert differ.spoken_language is None  # Detect
    assert differ.spoken_language_of(APP_1) == ZH
    assert listening_settings(value).spoken_language == EN  # no windows: today's


def test_a_windows_second_language_is_kept_by_language() -> None:
    """Kept by language; English, every language's but English's own
    by default, isn't kept as a choice, and none is (polyglotic-hq 555)."""
    value = AppSettings(second_languages={"fr": "zh"})
    assert second_languages_changes(value, {"en": "zh"}) == {
        "second_languages": {"fr": "zh", "en": "zh"},
        "no_second_language": (),
    }
    for none in ("", "fr"):
        assert second_languages_changes(value, {"fr": none}) == {
            "second_languages": {},
            "no_second_language": ("fr",),
        }
    assert second_languages_changes(value, {"fr": "en"}) == {
        "second_languages": {},
        "no_second_language": (),
    }
    assert second_languages_changes(AppSettings(), {"en": ""}) == {
        "second_languages": {},
        "no_second_language": (),
    }


def test_without_the_switch_the_settings_are_todays() -> None:
    chosen = listening_settings(
        AppSettings(targets=("en", "zh"), dictation=False, type_theirs=False)
    )
    assert chosen.targets == (EN, ZH) and dict(chosen.source_targets) == {}


def test_a_window_for_each_of_the_first_three_apps_picked() -> None:
    apps = ("Chat App", "Video Player", "Web Browser", "Game")
    value = AppSettings(whole_system=False, apps=apps)
    assert [key for key, _ in captioned_apps(value, True, ids)] == list(apps[:3])
    assert captured(value).apps == apps[:3]  # a 4th isn't captured either
    assert captioned_apps(AppSettings(whole_system=False), True, ids) == []
    whole = captioned_apps(AppSettings(whole_system=True), True, ids)
    assert whole == [("system", WHOLE_SYSTEM)]
    windows_10 = captioned_apps(value, False, ids)  # no per-app capture
    assert windows_10 == [("system", WHOLE_SYSTEM)]


def test_a_windows_close_unticks_its_app() -> None:
    value = AppSettings(whole_system=False, apps=("Chat App", "Game"))
    assert stop_captioning(value, "Game") == {"apps": ("Chat App",)}
    assert stop_captioning(value, "system") == {"whole_system": False, "apps": ()}


def test_the_windows_look_is_todays_captions_settings() -> None:
    look = caption_look(
        AppSettings(opacity=0.5, fade_after=None, caption_mode_chosen="steady")
    )
    assert (look.opacity, look.fade_after, look.preview) == (0.5, None, True)


@pytest.fixture
def switched(qapp: QApplication) -> Iterator[tuple[DesktopApp, CaptionWindows]]:
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    sent: list[bool] = []
    wire_caption_windows(windows, desktop, lambda: sent.append(True))
    windows.set_captioned([("Web Browser", APP_1)])
    yield desktop, windows
    windows.close()
    desktop.close()


def test_captions_reach_the_window(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = switched
    desktop.feed.apply(finished_updates(1, source=APP_1)[0])
    assert len(windows.windows["Web Browser"].view.lines) == 1


def test_a_window_takes_its_apps_name_once_its_source_is_found(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    """At every start the caption windows open before capture finds the
    apps: a window called its app by its file name ("vlc.exe" - its strip,
    its title, "Stop captioning vlc.exe") while Home said "VLC", until a
    setting changed (polyglotic-hq 141)."""
    desktop, windows = switched
    window = windows.windows["Web Browser"]
    assert window.label.name == "Web Browser"  # the key, before the source is known
    desktop.set_app_sources({APP_1: ("Web Browser", "Browser")})
    assert window.label.name == window.tag.label.name == "Browser"
    assert window.windowTitle() == "Browser captions"
    assert window.controls["stop"].text() == "Stop captioning Browser"


def test_a_windows_lines_already_in_its_language_are_saved_for_every_window(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = switched
    window = windows.windows["Web Browser"]
    window.set_second("zh")
    assert desktop.settings.value.preset_second_languages == {"en": "zh"}
    assert desktop.settings.value.second_language_of("en") == "zh"
    windows.set_second_languages({EN: ZH})  # as `follow_settings` hands it back
    window.set_second("")
    assert desktop.settings.value.preset_second_languages == {"en": ""}
    assert desktop.settings.value.second_language_of("en") is None


def test_a_listening_sessions_server_says_whether_windows_spoken_languages_count(
    switched: tuple[DesktopApp, CaptionWindows], qapp: QApplication
) -> None:
    from polyglotic_desktop.connection.session import SessionState, Status

    desktop, windows = switched
    listener = QtListener(desktop, None)
    listener.spoken_per_source.connect(windows.set_spoken_per_source)
    listener.status_changed(Status(SessionState.WAITING))  # no `welcome`: unsaid
    qapp.processEvents()
    assert windows.spoken_per_source is None
    listener.status_changed(Status(SessionState.LISTENING, source_fields=()))
    qapp.processEvents()
    assert windows.spoken_per_source is False  # a server from before 2026-11-09
    fields = ("targets", "spoken_language")
    listener.status_changed(Status(SessionState.LISTENING, source_fields=fields))
    qapp.processEvents()
    assert windows.spoken_per_source is True


def test_homes_spoken_language_is_every_windows(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    """Settings > Captions > Speech's Spoken language sets each window's own
    (263)."""
    desktop, windows = switched
    panels = Panels(desktop.settings, windows)
    panels.languages.set_spoken("yue")
    assert windows.spoken_languages() == {APP_1: Language("yue")}
    assert desktop.settings.value.spoken_language == "yue"
    windows.windows["Web Browser"].set_spoken_language("en")
    panels.languages.set_hints("Caleb")  # another row: the windows kept
    assert windows.spoken_languages() == {APP_1: EN}


def test_my_speech_in_a_window_is_todays_caption_my_own_speech(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = switched
    window = windows.windows["Web Browser"]
    window.set_show_mic(True)
    assert desktop.caption_mic.isChecked() and desktop.settings.value.caption_mic
    desktop.caption_mic.setChecked(False)  # the tray: off everywhere
    assert not window.choices.show_mic and not desktop.settings.value.caption_mic


def test_the_windows_buttons_use_the_apps_commands(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = switched
    window = windows.windows["Web Browser"]
    window.timing_wanted.emit(CaptionMode.INSTANT.value)
    assert desktop.settings.value.caption_mode is CaptionMode.INSTANT
    desktop.pause.setChecked(True)
    window._tick()
    assert window.notice.text() == "Paused"
    window.buttons["lock"].click()  # (it then says how to unlock, for a moment)
    assert desktop.lock_windows.isChecked() and window.locked
    window.buttons["stop"].click()
    assert desktop.settings.value.apps == ()


def test_the_sessions_state_shows_on_the_windows_notice_line(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = switched
    desktop.set_connection(ConnectionState.WAITING, 5.0)
    window = windows.windows["Web Browser"]
    window._tick()
    assert window.notice.text().startswith("Reconnecting - trying again in")
    desktop.set_connection(ConnectionState.SERVER_BUSY, 24.0)  # 203's item 4
    window._tick()
    assert window.notice.text() == "Polyglotic is busy — try again in a few minutes"


def test_todays_settings_keep_the_windows_own_setting(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    """Both save into one file: today's settings keep the key the windows
    saved after today's were read."""
    desktop, windows = switched
    windows.windows["Web Browser"].set_language("ja")
    windows.save_now()
    desktop.settings.update(opacity=0.4)
    store = desktop.settings._store
    assert isinstance(store, MemorySettingsStore)
    assert STORED_KEY in store.values and store.values["opacity"] == 0.4


def settings_from(changes: dict[str, object]) -> AppSettings:
    return replace(AppSettings(), **changes)  # type: ignore[arg-type]


def test_the_panels_values_are_todays_settings() -> None:
    value = AppSettings(
        learning="zh",
        spoken_language="yue",
        second_languages={"en": "zh"},
        spelling_hints=("Caleb",),
        caption_mode_chosen="live",
        opacity=0.4,
        caption_font="Arial",
        word_links="hover",
    )
    languages = session_languages(value, ["en", "ja"])
    assert languages.in_use == ("en", "ja") and languages.live_updates
    assert settings_from(languages_settings(value, languages)) == AppSettings(
        spoken_language="yue",
        second_languages={"en": "zh"},
        spelling_hints=("Caleb",),
    )
    look = caption_look(value)
    back = settings_from(look_settings(look))
    assert caption_look(replace(back, caption_mode_chosen="live")) == look
    assert (back.opacity, back.caption_font, back.word_links) == (0.4, "Arial", "hover")


def test_a_panel_change_is_saved_and_the_windows_follow(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = switched
    panels = Panels(desktop.settings, windows)
    window = windows.windows["Web Browser"]
    windows.set_look(caption_look(desktop.settings.value))
    desktop.settings.changed.connect(
        lambda: windows.set_look(caption_look(desktop.settings.value))
    )
    panels.look.set_opacity(0.3)
    assert window.look.opacity == 0.3  # shown at once; saved once it settles (273)
    assert panels.look_waiting and desktop.settings.value.opacity != 0.3
    panels.save_look()
    assert desktop.settings.value.opacity == 0.3 and window.look.opacity == 0.3
    panels.timing.set_mode(CaptionMode.CALM)
    assert desktop.settings.value.caption_mode is CaptionMode.CALM
    panels.timing.set_max_wait(2.5)  # the longest wait for text (277)
    assert desktop.settings.value.max_wait_for_text == 2.5
    desktop.settings.update(max_wait_for_text=5.0)
    assert panels.timing.value.max_wait == 5.0
    panels.languages.set_spoken("zh")
    assert desktop.settings.value.spoken_language == "zh"
    assert panels.languages.value.in_use == ("en",)  # the window's language
    window.set_language("ja")
    assert panels.languages.value.in_use == ("ja",)
    desktop.settings.update(opacity=0.9)  # elsewhere: the panels show it
    assert panels.look.value.opacity == 0.9


def test_the_looks_reset_leaves_the_windows_where_they_are(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    """248's section 2.2: Settings' reset is the look's only - the
    windows' places are Home's "Reset positions" (261; the Look window's
    reset had put them back too)."""
    desktop, windows = switched
    panels = Panels(desktop.settings, windows)
    window = windows.windows["Web Browser"]
    window.set_text_size(1.5)
    window.move(window.x() + 200, window.y())
    placed = window.choices.geometry, window.choices.preset
    desktop.settings.update(opacity=0.4)
    panels.look.reset()
    assert panels.look.value.opacity == CaptionLook().opacity
    assert window.choices.text_size == 1.5
    assert (window.choices.geometry, window.choices.preset) == placed


def test_all_caption_settings_opens_the_main_window_on_settings_look(
    qapp: QApplication,
) -> None:
    """A caption window's "All caption settings..." (248's F11; 261): the
    main window in front, on Settings, its Look section showing - the
    first of the caption windows' (304)."""
    built = Built()
    hub = built.hub
    hub.window.go_to("words")
    hub.settings.show_section("app")
    built.windows.all_settings_wanted.emit()
    assert hub.window.isVisible() and hub.window.current == "settings"
    assert hub.settings.sections.value() == "look"
    assert hub.settings.section["look"].isVisible()
    built.close()


def test_the_trays_more_languages_opens_settings_on_dictation(
    qapp: QApplication,
) -> None:
    """The tray's "More languages…" for dictation (283): the main window in
    front, on Settings > Dictation, where its language is (304)."""
    built = Built()
    hub = built.hub
    hub.window.go_to("words")
    hub.open_dictation_settings()
    assert hub.window.isVisible() and hub.window.current == "settings"
    assert hub.settings.sections.value() == "dictation"
    assert hub.settings.dictation_language.isVisible()
    built.close()


def test_the_pickers_rows_are_the_settings_and_the_windows(
    switched: tuple[DesktopApp, CaptionWindows],
) -> None:
    desktop, windows = switched
    windows.windows["Web Browser"].set_show_mic(True)
    found = FakeAppList().playing_apps()
    value = replace(desktop.settings.value, source_names={"Web Browser": "Docs"})
    picker = picker_of(value, found, True, windows, hidden=True)
    (row,) = picker.captioned
    assert (row.key, row.label, row.status) == (
        "Web Browser",
        "Docs",
        AppStatus.PLAYING,
    )
    assert row.show_mic and row.translate_into == "en" and picker.hidden
    assert [a.name for a in picker.available] == ["Video Player"]
    assert picker.you is not None and (picker.you.key, picker.you.label) == (
        "mic",
        "You",
    )
    whole = picker_of(AppSettings(whole_system=True), found, True, windows, False)
    assert [r.status for r in whole.captioned] == [AppStatus.EVERYTHING]


def test_adding_a_fourth_app_isnt_asked_for() -> None:
    three = AppSettings(whole_system=False, apps=("a", "b", "c"))
    assert adding_app(three, "d") is None and adding_app(three, "a") is None
    changes = adding_app(AppSettings(whole_system=False, apps=("a",)), "b")
    assert changes is not None
    assert changes["apps"] == ("a", "b") and changes["whole_system"] is False
    assert "b" in changes["source_colors"]  # type: ignore[operator]
    assert renaming(AppSettings(), "a", " Chat ", "App") == {
        "source_names": {"a": "Chat"}
    }
    named = AppSettings(source_names={"a": "Chat"})
    assert renaming(named, "a", "App", "App") == {"source_names": {}}


@pytest.fixture
def hub(
    switched: tuple[DesktopApp, CaptionWindows],
) -> Iterator[tuple[DesktopApp, CaptionWindows, Hub]]:
    desktop, windows = switched
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    yield desktop, windows, built
    built.window.keep_in_tray = False
    built.window.close()


def test_the_main_window_comes_when_the_tray_asks(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, _, built = hub
    pages = built.window.pages
    assert {"home", "account", "settings", "help"} <= set(pages)
    assert built.window.nav_buttons["help"].objectName() == "FootButton"
    built.window.go_to("account")
    desktop.show_window()  # the tray: something is chosen, so the page stays
    assert built.window.isVisible() and built.window.current == "account"
    built.window.hide()
    desktop.window_wanted.emit(False)  # on whatever page it shows
    assert built.window.isVisible() and built.window.current == "account"


def test_closing_the_main_window_hides_it_and_the_tray_says_so_once(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, _, built = hub
    desktop.tray = tray = RecordingTray()
    built.window.keep_in_tray = True  # as `main` sets it where there's a tray
    built.window.show()
    built.window.close()
    assert not built.window.isVisible()  # hidden: the app runs on
    assert len(tray.messages) == 1 and tray.messages[0][1].endswith("Quit from there.")
    built.window.show()
    built.window.close()  # the second time: nothing more
    assert len(tray.messages) == 1


def test_the_tray_says_the_state_home_shows(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, _, built = hub
    desktop.set_connection(ConnectionState.LISTENING)
    assert desktop.state_title == "Listening"
    desktop.pause.setChecked(True)
    assert desktop.state_title == built.home.state.title_label.text() == "Paused"
    desktop.pause.setChecked(False)


def test_home_follows_the_session_and_the_picker_acts(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    desktop.set_connection(ConnectionState.LISTENING)
    assert built.home.state.title_label.text() == "Listening"
    assert "captions in English" in built.home.state.detail.text()
    desktop.set_minutes(12, 48)
    assert built.home.state.minutes.text() == "Minutes this month: 12 of 60"
    desktop.show_notice("server_restarting")
    assert built.home.state.notice.text().startswith("The server is restarting")
    built.picker.set_translate_into("Web Browser", "ja")
    assert windows.windows["Web Browser"].choices.translate_into == "ja"
    built.picker.add("Video Player")
    assert desktop.settings.value.apps == ("Web Browser", "Video Player")
    built.picker.remove("Web Browser")
    assert desktop.settings.value.apps == ("Video Player",)


def test_the_first_run_ends_on_home_picking_what_to_caption(
    qapp: QApplication,
) -> None:
    """DECISIONS.md #25 and 109's section 7: with nothing chosen - a
    learner who stopped everything; a new one captions everything the PC
    plays since 484 - the main window opens on Home with the picker - "Pick
    what to caption", nothing captured or shown until an app is ticked."""
    store = MemorySettingsStore({"targets": ["en"], "whole_system": False})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    try:
        built.window.go_to("words" if "words" in built.window.pages else "account")
        desktop.show_window()
        assert built.window.current == "home"
        assert built.home.state.title_label.text() == "Pick what to caption"
        assert not built.home.picker_card.nothing.isHidden()
        assert windows.windows == {} and not desktop.settings.value.source_chosen
    finally:
        built.window.keep_in_tray = False
        built.window.close()
        windows.close()
        desktop.close()


def test_signed_out_home_offers_sign_in_and_the_windows_go(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    asked: list[bool] = []
    built.account.sign_in.triggered.connect(lambda: asked.append(True))
    desktop.set_connection(ConnectionState.SIGN_IN_NEEDED)
    state = built.home.state
    assert state.title_label.text() == "Not signed in"
    assert state.detail.text() == "sign in with your email to listen"
    state.sign_in.click()
    assert asked == [True]
    window = windows.windows["Web Browser"]
    window._tick()
    assert window.notice.text() == "Not signed in - sign in on Home"
    windows._going.timeout.emit()  # after saying so, the windows go
    assert not window.isVisible()
    built.picker.add("Video Player")  # the picker stays usable (settings: local)
    assert desktop.settings.value.apps == ("Web Browser", "Video Player")
    assert not any(w.isVisible() for w in windows.windows.values())
    desktop.set_connection(ConnectionState.CONNECTING)  # signed in again
    assert all(w.isVisible() for w in windows.windows.values())
    assert state.sign_in.isHidden() and not state.pause.isHidden()


def test_paused_home_the_windows_and_the_tray(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    desktop.pause.setChecked(True)
    assert built.home.state.title_label.text() == "Paused"
    assert built.home.state.pause.text() == "Resume"
    window = windows.windows["Web Browser"]
    window._tick()
    assert window.notice.text() == "Paused" and window.alpha == 1.0
    assert desktop.tray_state.value == "paused"


def test_free_minutes_used_on_home_and_every_window(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    desktop.set_minutes(20, 0)
    window = windows.windows["Web Browser"]
    window._tick()
    words = "Today's free minutes are used - more at midnight"
    assert window.notice.text() == words == built.home.state.notice.text()
    desktop.set_minutes(0, 20)  # more again
    window._tick()
    assert not window.notice.isVisible() and built.home.state.notice.isHidden()


def test_captions_failing_on_the_server_on_home_and_every_window(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """The speech model stopped mid-session: every finished caption failed
    (`processing_failed`) while Home said Listening and the windows stayed
    blank (polyglotic-hq 145). Two in a row are said; a caption ends it."""
    desktop, windows, built = hub
    desktop.set_connection(ConnectionState.LISTENING)
    window = windows.windows["Web Browser"]
    desktop.caption_failed()  # one could be a one-off
    window._tick()
    assert not window.notice.isVisible() and built.home.state.notice.isHidden()
    desktop.caption_failed()
    window._tick()
    words = "Captions failing on the server - still trying"
    assert window.notice.text() == words == built.home.state.notice.text()
    assert not built.home.state.notice.isHidden()
    desktop.feed.apply(finished_updates(1)[0])  # the model is back
    window._tick()
    assert not window.notice.isVisible() and built.home.state.notice.isHidden()
    desktop.caption_failed()
    desktop.caption_failed()
    desktop.set_connection(ConnectionState.WAITING, 5)  # the state says it
    window._tick()
    assert window.notice.text().startswith("Reconnecting")
    assert built.home.state.notice.isHidden()


def test_an_unstable_connection_on_home_and_every_window_until_it_holds(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """polyglotic-hq 165: a connection that keeps dropping is said once it
    has dropped twice, and comes off by itself once it has held."""
    desktop, windows, built = hub
    window = windows.windows["Web Browser"]

    def drop_and_come_back() -> None:
        desktop.set_connection(ConnectionState.LISTENING)
        desktop.set_connection(ConnectionState.WAITING, 2)
        desktop.set_connection(ConnectionState.CONNECTING)
        desktop.set_connection(ConnectionState.LISTENING)

    drop_and_come_back()  # one is a blip
    window._tick()
    assert not window.notice.isVisible() and built.home.state.notice.isHidden()
    drop_and_come_back()
    window._tick()
    words = "Connection unstable - captions may come late"
    assert window.notice.text() == words == built.home.state.notice.text()
    assert not built.home.state.notice.isHidden()
    assert desktop._held.isActive()  # it comes off by itself
    desktop._drops._drops = [t - 600 for t in desktop._drops._drops]  # held since
    desktop._held_again()
    window._tick()
    assert not window.notice.isVisible() and built.home.state.notice.isHidden()


def test_a_stalled_connection_is_said_while_it_lasts(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """polyglotic-hq 165: a 30-second outage never closed the connection -
    "Listening" the whole time, captions 10-24 s late. A stall is said at
    once, and comes off when answers flow (or the session's state says more)."""
    desktop, windows, built = hub
    window = windows.windows["Web Browser"]
    desktop.set_connection(ConnectionState.LISTENING)
    desktop.connection_stalled(True)
    window._tick()
    words = "Connection unstable - captions may come late"
    assert window.notice.text() == words == built.home.state.notice.text()
    desktop.connection_stalled(False)
    window._tick()
    assert not window.notice.isVisible() and built.home.state.notice.isHidden()
    desktop.connection_stalled(True)
    desktop.set_connection(ConnectionState.WAITING, 5)  # it dropped after all
    window._tick()
    assert window.notice.text().startswith("Reconnecting")
    desktop.set_connection(ConnectionState.STOPPED)
    assert built.home.state.notice.isHidden()


def test_stopping_takes_the_unstable_notice_off(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, _windows, built = hub
    for _ in range(2):
        desktop.set_connection(ConnectionState.LISTENING)
        desktop.set_connection(ConnectionState.WAITING, 2)
    desktop.set_connection(ConnectionState.LISTENING)
    assert not built.home.state.notice.isHidden()
    desktop.set_connection(ConnectionState.STOPPED)
    assert built.home.state.notice.isHidden()
    assert not desktop._held.isActive()


def test_a_busy_time_on_home_and_the_windows_with_live_updates(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    desktop.settings.update(caption_mode_chosen=CaptionMode.WHOLE.value)
    built.set_busy(True)  # Steady: nothing slowed that the learner sees
    assert built.home.state.notice.isHidden()
    built.set_busy(False)
    desktop.settings.update(caption_mode_chosen=CaptionMode.INSTANT.value)
    windows.set_timing(CaptionMode.INSTANT)  # as main's follow_settings does
    built.set_busy(True)
    windows.set_busy(True)
    words = "Busy time - live updates slowed; captions continue"
    assert built.home.state.notice.text() == words
    assert windows.windows["Web Browser"].notice.text() == words


def test_the_servers_pace_hint_is_a_busy_time_when_it_begins_or_ends(
    qapp: QApplication,
) -> None:
    desktop = DesktopApp(MemorySettingsStore({}), None, FakeAppList())
    listener = QtListener(desktop, None)
    said: list[bool] = []
    listener.busy_changed.connect(said.append)
    for pace in (None, 1.5, 3.0, None):  # on the session's thread, then queued
        listener.pace_changed(pace)
        qapp.processEvents()
    assert said == [True, False]
    desktop.close()


def test_no_app_wide_stylesheet(qapp: QApplication) -> None:
    before = qapp.styleSheet()
    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    assert qapp.styleSheet() == before
    desktop.settings.update(window_theme="light")
    assert qapp.styleSheet() == before
    desktop.settings.update(window_theme="dark")
    desktop.close()


def test_homes_join_button_joins_and_separates(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    _, windows, built = hub
    join = built.home.join
    assert not join.isEnabled()  # one window
    windows.set_captioned([("Web Browser", APP_1), ("Video Player", APP_2)])
    built.follow()  # a second window joins the first (554)
    assert windows.joined_window is not None
    assert join.isEnabled() and join.text() == "Separate windows"
    join.click()
    assert windows.joined_window is None and join.text() == "Join windows"
    join.click()
    assert windows.joined_window is not None and join.text() == "Separate windows"
