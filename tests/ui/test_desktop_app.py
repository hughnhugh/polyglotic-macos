"""The app behind its windows (`ui.app.DesktopApp`), offscreen: settings
remembered through the port and read leniently; the tray menu's named
commands and the hotkeys; the session's state kept here, with the
server's minutes and notices announced for Home and the caption windows,
and the tray saying the state Home shows - and, once, that the app is
still running there; the tray asking for the main window. Made-up apps
only."""

import sys
import threading

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from tests.ui.fakes import MemorySettingsStore, RecordingTray, make_app

from polyglotic_desktop.ui import app as ui_app
from polyglotic_desktop.ui.app import (
    DARK_TRAY_MENU,
    ConnectionState,
    DesktopApp,
    tray_menu_place,
)
from polyglotic_desktop.ui.icons import TrayState
from polyglotic_desktop.ui.os_words import pc_mac_or_linux
from polyglotic_desktop.ui.recorded_captions import clause, finished, live
from polyglotic_desktop.ui.settings import AppSettings

# -- settings ------------------------------------------------------------------------------


def test_stored_settings_are_read_leniently() -> None:
    settings = AppSettings.from_stored(
        {
            "targets": ["zh", "en"],
            "text_scale": 9.0,  # out of range
            "word_links": "sparkles",  # not a choice
            "caption_mic": "yes",  # not a bool
            "fade_after": None,
            "overlay_geometry": {"en": [1, 2, 300, 200], "zh": "here"},
            "unknown": 1,
        }
    )
    assert settings.targets == ("zh", "en")
    assert settings.text_scale == 1.0
    assert settings.word_links == AppSettings().word_links  # the default
    assert settings.caption_mic is False and settings.fade_after is None
    assert settings.overlay_geometry == {}  # one bad entry: the default
    assert AppSettings.from_stored(settings.to_stored()) == settings


def test_the_one_app_an_older_version_picked_is_still_picked() -> None:
    settings = AppSettings.from_stored({"app_name": "Video Player"})
    assert settings.apps == ("Video Player",)
    assert "app_name" not in settings.to_stored()
    # saved since: the newer setting wins
    assert AppSettings.from_stored({"app_name": "Video Player", "apps": []}).apps == ()
    assert AppSettings.from_stored({"apps": ["A", 3]}).apps == ()  # not valid


def test_every_change_is_saved_through_the_port(qapp: QApplication) -> None:
    store = MemorySettingsStore({"targets": ["en"], "locked": True})
    app = make_app(store)
    assert app.lock_windows.isChecked()  # every caption window locked, as left
    app.lock_windows.setChecked(False)
    assert store.values["locked"] is False
    app.caption_mic.setChecked(True)
    assert store.values["caption_mic"] is True
    app.settings.update(locked=True)  # changed elsewhere: the command follows
    assert app.lock_windows.isChecked()
    app.close()


# -- the commands --------------------------------------------------------------------------


SCREEN = QRect(0, 0, 2560, 1440)
MENU = QSize(243, 231)  # 141's, on the user's screen


def _on(area: QRect, at: QPoint) -> QRect:
    return QRect(tray_menu_place(at, MENU, area), MENU)


def test_the_tray_menu_opens_above_the_taskbar_wherever_it_is() -> None:
    """141: Qt placed it against the whole screen - (2292, 1209), Quit over
    a 48 px taskbar at the bottom - where a mouse jumping onto Quit missed."""
    bottom = QRect(0, 0, 2560, 1392)
    menu = _on(bottom, QPoint(2292, 1416))
    assert bottom.contains(menu) and menu.bottom() == bottom.bottom()
    assert menu.left() == 2292  # from the mouse, as Windows' own
    assert _on(bottom, QPoint(2540, 1416)).right() == 2559  # kept on the screen
    top = QRect(0, 48, 2560, 1392)
    assert _on(top, QPoint(2292, 24)).top() == 48  # below a taskbar at the top
    left = QRect(48, 0, 2512, 1440)
    assert _on(left, QPoint(24, 1300)).left() == 48
    right = QRect(0, 0, 2512, 1440)
    assert right.contains(_on(right, QPoint(2530, 1300)))
    assert _on(SCREEN, QPoint(1200, 700)) == QRect(1200, 700 - 231, 243, 231)


def test_a_right_click_on_the_tray_icon_opens_the_menu_on_the_work_area(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows' and the Mac's: on Linux the tray shows it itself (571)
    monkeypatch.setattr(ui_app, "DESKTOP_SHOWS_TRAY_MENU", False)
    app = make_app()
    app.tray = QSystemTrayIcon(app)  # offscreen has no tray: as show_tray makes it
    assert app.tray.contextMenu() is None  # Qt's own placement isn't used
    app._tray_activated(QSystemTrayIcon.ActivationReason.Context)
    menu = app.tray_menu
    assert menu.isVisible()
    screen = QApplication.primaryScreen()
    assert screen is not None
    assert screen.availableGeometry().contains(menu.geometry())
    menu.close()
    app.close()


def test_the_tray_menu_is_measured_as_it_will_show(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The taskbar turned dark since the icon last checked (every 10 s):
    the menu is styled for it before it's measured, so its first opening
    is placed by the size it shows at, not the light one's (polyglotic-hq
    146: about 35 x 14 px off)."""
    monkeypatch.setattr(ui_app, "DESKTOP_SHOWS_TRAY_MENU", False)  # not Linux's (571)
    light = [True]
    app = DesktopApp(MemorySettingsStore(), None, None, light_taskbar=lambda: light[0])
    app.tray = QSystemTrayIcon(app)  # offscreen has no tray: as show_tray makes it
    app.set_connection(ConnectionState.NOT_CONNECTED)  # styled for a light taskbar
    light_size = app.tray_menu.sizeHint()
    light[0] = False
    measured: list[QSize] = []
    place = ui_app.tray_menu_place

    def placed(at: QPoint, size: QSize, area: QRect) -> QPoint:
        measured.append(size)
        return place(at, size, area)

    monkeypatch.setattr(ui_app, "tray_menu_place", placed)
    app._tray_activated(QSystemTrayIcon.ActivationReason.Context)
    menu = app.tray_menu
    assert menu.styleSheet() == DARK_TRAY_MENU
    assert menu.sizeHint() != light_size  # the dark menu's size differs
    assert measured == [menu.sizeHint()]
    menu.close()
    app.close()


def test_the_tray_menu_has_the_named_commands(qapp: QApplication) -> None:
    app = make_app()
    menu = [a for a in app.tray_menu.actions() if not a.isSeparator()]
    assert [a.objectName() for a in menu] == [
        "app.open",
        "app.install_update",  # hidden until an update is ready (polyglotic-hq 299)
        "account.usage",  # a capped plan's allowance left (polyglotic-hq 684)
        "app.pause",
        "windows.lock",
        "windows.hide",
        "app.caption_mic",
        "app.dictation",  # dictation on or off (polyglotic-hq 283)
        "app.dictation_language",  # and its language, as modes
        "captions.delay",  # each caption's delay, on request (polyglotic-hq 271)
        "feedback.problem",
        "feedback.suggestion",
        "app.quit",
    ]
    texts = {a.objectName(): a.text() for a in menu}

    assert texts["windows.lock"] == "Lock all caption windows"
    assert texts["windows.hide"] == "Hide all caption windows"
    assert not app.install_update.isVisible()
    assert not app.usage.isVisible()  # nothing to say without a meter
    app.close()


def test_the_tray_turns_dictation_on_and_follows_settings(qapp: QApplication) -> None:
    app = make_app()
    assert app.dictation.isChecked()  # on for a new learner (478; off in 283)
    app.dictation.trigger()
    assert not app.settings.value.dictation
    app.settings.update(dictation=True)  # Settings' switch
    assert app.dictation.isChecked()
    app.close()


def test_the_tray_switches_dictations_language_like_a_mode(qapp: QApplication) -> None:
    """Detect, English, Mandarin, Cantonese - and the one chosen in
    Settings, if it's another - at the tray (polyglotic-hq 283)."""
    app = make_app()
    app.set_dictation_languages(
        [("en", "English"), ("zh", "Mandarin"), ("yue", "Cantonese"), ("ko", "Korean")]
    )

    def shown() -> list[tuple[str, bool]]:
        return [
            (a.text(), a.isChecked())
            for a in app.dictation_language_menu.actions()
            if a.isCheckable()
        ]

    assert shown() == [
        ("Detect automatically", True),
        ("English", False),
        ("Mandarin", False),
        ("Cantonese", False),
    ]
    mandarin = app.dictation_language_menu.actions()[2]
    mandarin.trigger()
    assert app.settings.value.dictation_language == "zh"
    assert [checked for _, checked in shown()] == [False, False, True, False]
    app.settings.update(dictation_language="ko")  # chosen in Settings
    qapp.processEvents()  # listed again once the event loop runs
    assert shown()[-1] == ("Korean", True)
    app.dictation_language_menu.actions()[1].trigger()  # English, from the tray
    qapp.processEvents()
    assert app.settings.value.dictation_language == "en"
    assert [text for text, _ in shown()][-1] == "Cantonese"  # Korean's gone
    asked: list[bool] = []
    app.dictation_settings_wanted.connect(lambda: asked.append(True))
    app.more_dictation_languages.trigger()
    assert asked == [True]
    app.close()


def test_hotkeys_lock_pause_and_hide_from_any_thread(qapp: QApplication) -> None:
    """Ctrl+Alt+L, P and H, as the proof of concept: Windows calls them on
    the hotkeys' own thread; they run on the Qt thread. No Ctrl+Alt+W: it
    checked the newest line ("Looks wrong?"), which went (polyglotic-hq
    339)."""
    app = make_app()
    shown = {k: a.shortcut().toString() for k, a in app.hotkeys.items()}
    keys = "Meta+Ctrl+" if sys.platform == "darwin" else "Ctrl+Alt+"  # ⌃⌘ (428)
    if sys.platform.startswith("linux"):
        keys = "Ctrl+Alt+Shift+"  # Ctrl+Alt+L locks some desktops' screens (570)
    on = {"lock": keys + "L", "pause": keys + "P", "hide": keys + "H", "live": "Space"}
    assert shown == {k: on.get(k, "") for k in app.hotkeys}
    for key in ("lock", "pause", "hide"):
        worker = threading.Thread(target=app.hotkey_pressed.emit, args=(key,))
        worker.start()
        worker.join()
    assert not app.pause.isChecked()  # queued: nothing yet
    qapp.processEvents()
    assert app.pause.isChecked() and app.pause.text() == "Resume"
    assert app.lock_windows.isChecked()
    assert app.hide_windows.isChecked()
    assert app.settings.value.locked  # saved, as when clicked
    app.hotkey_pressed.emit("pause")
    qapp.processEvents()
    assert not app.pause.isChecked()
    app.hotkeys_not_working(["hide"])  # another app has Ctrl+Alt+H: not shown
    assert app.hide_windows.shortcut().isEmpty()
    app.close()


def test_tray_displays_registered_shortcuts_when_the_platform_hides_them(
    qapp: QApplication,
) -> None:
    hide = Qt.ApplicationAttribute.AA_DontShowShortcutsInContextMenus
    original = qapp.testAttribute(hide)
    qapp.setAttribute(hide, True)
    try:
        app = make_app()
        for action in (app.pause, app.lock_windows, app.hide_windows):
            assert not action.shortcut().isEmpty()
            assert action.isShortcutVisibleInContextMenu()
        app.hotkeys_not_working(["hide"])
        assert app.hide_windows.shortcut().isEmpty()
    finally:
        qapp.setAttribute(hide, original)
        app.close()


def test_the_tray_asks_for_the_main_window(qapp: QApplication) -> None:
    """The tray's Open Polyglotic asks for it on the picker while nothing is
    chosen (DECISIONS.md #25)."""
    app = make_app()
    asked: list[bool] = []
    app.window_wanted.connect(asked.append)
    app.open_window.trigger()
    assert asked == [True]
    app.close()


def test_nothing_offers_looks_wrong(qapp: QApplication) -> None:
    """ "Looks wrong?" left the interface (polyglotic-hq 339; the user,
    2026-11-15: "get rid of the looks wrong report button"): no comparison
    card, no command to check the newest line, nothing in the tray."""
    app = make_app()
    assert not hasattr(app, "looks_wrong") and not hasattr(app, "check_line")
    texts = [a.text() for a in app.tray_menu.actions()]
    assert not any("best model" in t or "Looks wrong" in t for t in texts)
    app.close()


# -- the session's state -------------------------------------------------------------------


def test_the_sessions_state_is_kept_and_announced(qapp: QApplication) -> None:
    app = make_app()
    seen: list[tuple[object, object]] = []
    app.connection_changed.connect(lambda state, retry: seen.append((state, retry)))
    assert app.connection is ConnectionState.NOT_CONNECTED
    app.set_connection(ConnectionState.WAITING, 4.0)
    assert (app.connection, app.retry_in) == (ConnectionState.WAITING, 4.0)
    assert seen == [(ConnectionState.WAITING, 4.0)]
    assert app.caption_facts().connection == "waiting"  # Help's check reads it
    app.close()


def test_listening_moved_says_so_on_the_caption_windows_once(
    qapp: QApplication,
) -> None:
    app = make_app()
    lines: list[str] = []
    app.caption_notice.connect(lines.append)
    app.set_connection(ConnectionState.LISTENING)
    app.set_connection(ConnectionState.MOVED)
    app.set_connection(ConnectionState.MOVED)  # the same state again: no new line
    assert lines == ["Listening continues on another device"]
    app.close()


def test_the_servers_minutes_and_notices_are_announced(qapp: QApplication) -> None:
    app = make_app()
    minutes: list[tuple[float, object]] = []
    home: list[str] = []
    windows: list[str] = []
    app.minutes_changed.connect(lambda used, left: minutes.append((used, left)))
    app.home_notice.connect(home.append)
    app.caption_notice.connect(windows.append)
    app.set_minutes(10.0, 590.0)
    assert minutes == [(10.0, 590.0)]
    app.show_notice("not_a_known_code")  # a newer server's: not shown
    assert home == [] and windows == []
    app.show_notice("translator_warming_up")
    assert len(home) == 1 and "Translation is starting" in home[0]
    assert windows == home
    app.show_feedback("sent", just_sent=True)  # a report's outcome: Home only
    assert home[-1] == "Thanks - we have your report." and len(windows) == 1
    app.close()


def test_a_warm_up_notice_leaves_home_once_captions_show_it_is_over(
    qapp: QApplication,
) -> None:
    """Home keeps a server notice on its banner for minutes; "The speech
    model is starting" came off the caption windows after a few seconds
    but stayed on Home after captions were back (polyglotic-hq 145)."""
    app = make_app()
    home: list[str] = []
    app.home_notice.connect(home.append)
    app.show_notice("models_warming_up")
    assert "Captioning is starting" in home[-1]
    app.feed.apply(live("c1"))  # no words yet: still starting
    assert home[-1] != ""
    app.feed.apply(live("c1", clause("你好")))  # a caption: the model is up
    assert home[-1] == ""
    app.show_notice("translator_warming_up")
    app.feed.apply(finished("c1", clause("你好")))  # captions, no translation yet
    assert "Translation is starting" in home[-1]
    app.feed.apply(finished("c2", clause("谢谢", "Thanks")))
    assert home[-1] == ""
    app.show_notice("models_warming_up")
    app.show_feedback("sent", just_sent=True)  # Home's banner says this now
    app.feed.apply(finished("c3", clause("再见", "Bye")))
    assert home[-1] == "Thanks - we have your report."  # not taken off
    app.close()


def test_the_servers_restart_notice_leaves_home_once_listening_again(
    qapp: QApplication,
) -> None:
    """ "Polyglotic's server is restarting - captions carry on in a moment" stayed
    on Home's banner for two minutes after the session listened again and
    captions were back - through a later outage too (polyglotic-hq 203)."""
    app = make_app()
    home: list[str] = []
    app.home_notice.connect(home.append)
    app.set_connection(ConnectionState.LISTENING)
    app.show_notice("server_restarting")
    assert home[-1].startswith("Polyglotic's server is restarting")
    app.set_connection(ConnectionState.WAITING, 1.0)  # it's restarting
    app.set_connection(ConnectionState.CONNECTING)
    assert home[-1].startswith("Polyglotic's server is restarting")
    app.set_connection(ConnectionState.LISTENING)  # back
    assert home[-1] == ""
    app.show_notice("translator_warming_up")  # other notices stay a while
    app.set_connection(ConnectionState.WAITING, 1.0)
    app.set_connection(ConnectionState.LISTENING)
    assert "Translation is starting" in home[-1]
    app.close()


def test_the_tray_follows_the_state(qapp: QApplication) -> None:
    app = make_app(MemorySettingsStore({"apps": ["Video Player"]}))
    assert app.tray_state is TrayState.IDLE
    app.set_connection(ConnectionState.LISTENING)
    assert app.tray_state is TrayState.LISTENING
    app.pause.setChecked(True)
    assert app.tray_state is TrayState.PAUSED
    app.close()


STILL_CAPTIONING = (
    "Polyglotic is still captioning",
    pc_mac_or_linux(
        "Use the tray icon to quit.",
        "Use the menu bar icon to quit.",
        "Use the panel icon to quit.",  # 571
    ),
)


def test_closing_the_main_window_the_first_time_the_tray_says_it_still_runs(
    qapp: QApplication,
) -> None:
    """Once per PC: closing the window had hidden it without a word, and
    learners thought they had quit (polyglotic-hq 135, finding 10)."""
    store = MemorySettingsStore({"apps": ["Video Player"]})
    app = make_app(store)
    app.tray = tray = RecordingTray()
    app.set_connection(ConnectionState.LISTENING)
    app.note_in_tray()
    assert tray.messages == [STILL_CAPTIONING]
    app.note_in_tray()  # closed again: nothing more
    assert tray.messages == [STILL_CAPTIONING]
    assert store.load()["tray_note_shown"] is True
    app.close()
    again = make_app(store)  # the next start remembers it
    again.tray = later = RecordingTray()
    again.note_in_tray()
    assert later.messages == []
    again.close()


def test_the_tray_note_says_what_fits_the_state(qapp: QApplication) -> None:
    app = make_app(MemorySettingsStore({"apps": ["Video Player"]}))
    quit_there = pc_mac_or_linux(
        "Use the tray icon to quit.",
        "Use the menu bar icon to quit.",
        "Use the panel icon to quit.",
    )
    # not connected (or nothing picked): nothing is captioned
    assert app.tray_note() == ("Polyglotic is still running", quit_there)
    app.set_connection(ConnectionState.LISTENING)
    assert app.tray_note() == STILL_CAPTIONING
    app.pause.setChecked(True)
    assert app.tray_note() == (
        "Captions are paused",
        pc_mac_or_linux(
            "Use the tray icon to resume or quit.",
            "Use the menu bar icon to resume or quit.",
            "Use the panel icon to resume or quit.",
        ),
    )
    app.close()


def test_without_a_tray_there_is_no_note_and_none_is_remembered(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore()
    app = make_app(store)
    assert app.tray is None  # offscreen: no tray
    app.note_in_tray()
    assert app.settings.value.tray_note_shown is False
    app.close()
