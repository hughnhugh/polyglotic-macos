"""A caption window's settings list the apps it can caption - the ones with
sound, then browsers and the main apps before they play - and picking one
captions it there, in the window's place (the user's rehearsal feedback
F12, polyglotic-hq 249, 2026-11-08: "Allow you to select the app you want
to caption in captioning window. Browsers should be a default app you can
select to caption, it doesn't have to be playing sound first. ... "Don't
see your app here? make sure there is audio playing from it"")."""

from collections.abc import Iterator
from functools import partial

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui.test_main_wiring import FakePipeline
from tests.ui.test_sample import sources_with_sample

from polyglotic_desktop.main import (
    follow_settings,
    new_interface,
    plan_sources,
    switching_app,
)
from polyglotic_desktop.platform.windows.categories import COMMON_APPS, known_name
from polyglotic_desktop.ports.capture import CommonApp
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.settings_popover import COLUMN_ROWS, ROWS
from polyglotic_desktop.ui_next.views.app_choices import (
    AppChoice,
    AppState,
    app_choices,
)

CHROME = CommonApp("chrome.exe", "Google Chrome")


def test_found_apps_first_playing_first_then_common_ones() -> None:
    found = [("vlc.exe", "VLC", False), ("Discord.exe", "Discord", True)]
    common = [("discord.exe", "Discord"), ("chrome.exe", "Google Chrome")]
    assert app_choices(found, common, "vlc.exe", ()) == [
        AppChoice("Discord.exe", "Discord", AppState.PLAYING),
        AppChoice("vlc.exe", "VLC", AppState.QUIET),
        AppChoice("chrome.exe", "Google Chrome", AppState.NOT_PLAYING_YET),
    ]  # Discord once: found beats common, whatever the case


def test_apps_other_windows_caption_aren_t_listed() -> None:
    found = [("zoom.exe", "Zoom", True), ("vlc.exe", "VLC", True)]
    common = [("chrome.exe", "Google Chrome")]
    names = [
        c.name
        for c in app_choices(
            found, common, "vlc.exe", ("vlc.exe", "zoom.exe", "chrome.exe")
        )
    ]
    assert names == ["vlc.exe"]  # this window's own stays


def test_the_browsers_and_main_apps_are_listed_before_they_play() -> None:
    names = [app.name for app in COMMON_APPS]
    for browser in (
        "msedge.exe",
        "chrome.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
    ):
        assert browser in names
    for main in ("discord.exe", "zoom.exe", "ms-teams.exe", "spotify.exe", "vlc.exe"):
        assert main in names
    assert all(name == name.lower() for name in names)
    for common in COMMON_APPS:  # the same public name as the known-apps list's
        assert known_name(common.name) in (None, common.title)


def test_switching_keeps_the_order_and_the_colour() -> None:
    value = AppSettings(
        apps=("Discord.exe", "vlc.exe"),
        source_colors={"Discord.exe": "#4dd0e1", "vlc.exe": "#a5d66f"},
    )
    changes = switching_app(value, "vlc.exe", "chrome.exe")
    assert changes is not None
    assert changes["apps"] == ("Discord.exe", "chrome.exe")
    assert changes["source_colors"]["chrome.exe"] == "#a5d66f"  # type: ignore[index]
    assert switching_app(value, "vlc.exe", "Discord.exe") is None  # captioned
    assert switching_app(value, "zoom.exe", "chrome.exe") is None  # not here


def test_a_common_app_not_playing_yet_is_captioned_once_it_plays() -> None:
    """What per-app capture needs: the app's process, found by its audio
    session - so a browser picked before it plays waits, and joins then."""
    from polyglotic_desktop.ports.capture import PlayingApp, SourceCategory

    value = AppSettings(whole_system=False, apps=("chrome.exe",))
    assert plan_sources(value, [], per_app=True).apps == ()  # nothing to catch yet
    playing = [PlayingApp(4242, "chrome.exe", True, SourceCategory.BROWSER)]
    assert [a[0] for a in plan_sources(value, playing, per_app=True).apps] == [4242]


@pytest.fixture
def built(qapp: QApplication) -> Iterator[tuple[DesktopApp, object]]:
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    interface = new_interface(desktop, store, None, per_app=True, common_apps=(CHROME,))
    sources = sources_with_sample(FakePipeline(), FakeAppList())
    follow = partial(follow_settings, interface.windows, desktop, sources)
    desktop.settings.changed.connect(follow)  # as `main` has it
    follow()
    apps = desktop.apps
    assert apps is not None
    if not apps.playing_apps():  # the first look, on its thread (291)
        loop = QEventLoop()
        apps.found.connect(loop.quit)
        QTimer.singleShot(2000, loop.quit)
        loop.exec()
    yield desktop, interface
    interface.close()
    desktop.close()


def test_the_window_s_settings_list_the_apps_and_say_what_to_do(
    built: tuple[DesktopApp, object], qapp: QApplication
) -> None:
    desktop, interface = built
    assert ROWS[0] == "app" and "app" in COLUMN_ROWS
    windows = interface.windows  # type: ignore[attr-defined]
    window = windows.windows["Web Browser"]
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None and popover.rows["app"].isVisibleTo(popover)
    assert popover.app.text().startswith(window.label.name)
    assert not popover.no_app.isVisibleTo(popover)
    popover.app.click()  # the list opens inside the popover
    listed = [popover.apps.item(i).text() for i in range(popover.apps.count())]
    assert listed == [
        "Web Browser - playing",
        "Video Player",
        "Google Chrome - starts when it plays",
    ]
    assert popover.no_app.isVisibleTo(popover)
    assert popover.no_app.text() == (
        "Don't see your app here? Make sure it's playing audio."
    )
    assert "starts when Google Chrome plays" in popover.apps.item(2).toolTip()
    place = window.geometry()
    popover._app_chosen(popover.apps.item(2))  # Google Chrome
    qapp.processEvents()
    assert desktop.settings.value.apps == ("chrome.exe",)
    assert "Web Browser" not in windows.windows
    chrome = windows.windows["chrome.exe"]
    assert chrome.geometry() == place  # in the window it replaced


def test_a_window_for_everything_the_pc_plays_lists_no_apps(
    built: tuple[DesktopApp, object],
) -> None:
    desktop, interface = built
    windows = interface.windows  # type: ignore[attr-defined]
    assert windows.app_choices("Web Browser")
    desktop.settings.update(whole_system=True)
    assert windows.app_choices("Web Browser") == []


def test_a_click_on_the_strip_s_label_opens_the_apps(
    built: tuple[DesktopApp, object], qapp: QApplication
) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    _, interface = built
    window = interface.windows.windows["Web Browser"]  # type: ignore[attr-defined]
    window.show()
    window.hovered = True
    window._show_band(True)
    qapp.processEvents()
    on_label = QPointF(window.tag.mapTo(window, window.tag.rect().center()))
    for kind, buttons in (
        (QMouseEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
        (QMouseEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
    ):
        event = QMouseEvent(
            kind, on_label, window.mapToGlobal(on_label), Qt.MouseButton.LeftButton,
            buttons, Qt.KeyboardModifier.NoModifier,
        )  # fmt: skip
        if kind is QMouseEvent.Type.MouseButtonPress:
            window.mousePressEvent(event)
        else:
            window.mouseReleaseEvent(event)
    popover = window.popover
    assert popover is not None and popover.isVisible()
    assert popover.apps.isVisibleTo(popover) and popover.apps.count() == 3


def test_settings_reopened_after_the_app_list_has_no_gaps(
    built: tuple[DesktopApp, object], qapp: QApplication
) -> None:
    """A window's settings closed with the app list open, then opened again:
    the list is shut, and the popover is as tall as its rows - not as tall
    as it was with the list open, the extra spread as gaps between every
    row (246's possible bug, seen by 269: 447 px, then 671)."""
    _, interface = built
    window = interface.windows.windows["Web Browser"]  # type: ignore[attr-defined]
    window.show()
    window.toggle_settings()
    qapp.processEvents()
    popover = window.popover
    assert popover is not None and popover.isVisible()
    first = popover.height()
    popover._toggle_apps()  # the apps it can caption, opened
    qapp.processEvents()
    assert popover.apps.isVisible() and popover.height() > first
    window.toggle_settings()  # closed with the list open
    qapp.processEvents()
    window.toggle_settings()
    qapp.processEvents()
    assert popover.isVisible() and popover.apps.isHidden()
    assert popover.height() == first
