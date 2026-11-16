"""The apps with sound, found off the interface thread: the app picker's
poll and main's look for a chosen app never list them there."""

import threading

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.main import Hub, Panels
from polyglotic_desktop.ports.capture import PlayingApp, SourceCategory
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.apps_with_sound import AppsWithSound
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect

PLAYER = PlayingApp(10, "Video Player", True, SourceCategory.VIDEO)
BROWSER = PlayingApp(20, "Web Browser", True, SourceCategory.BROWSER)


class CountingAppList:
    """Answers with `apps`, noting the thread each time it's asked."""

    def __init__(self, *apps: PlayingApp) -> None:
        self.apps = list(apps)
        self.threads: list[str] = []
        self.ran_on: list[threading.Thread] = []
        self.fail = False

    def playing_apps(self) -> list[PlayingApp]:
        self.threads.append(threading.current_thread().name)
        self.ran_on.append(threading.current_thread())
        if self.fail:
            raise OSError("COM said no")
        return list(self.apps)


def until_found(apps: AppsWithSound) -> None:
    loop = QEventLoop()
    apps.found.connect(loop.quit)
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    apps.found.disconnect(loop.quit)


def test_even_the_first_answer_is_found_off_the_interface_thread(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 291: on a tester's Windows 10 PC with four output
    devices, the first list - asked there and then on the interface thread,
    while Home opened - held it 1.2s (Windows' audio devices, the first time
    they're asked). Now the first ask starts a look on its thread and
    answers none until it's found (`found`: the hub and the sources follow
    it again). The first look waits for the start - `main` asks for it
    after the window's first paint - so it doesn't slow the start."""
    listed = CountingAppList(PLAYER)
    apps = AppsWithSound(listed)
    assert apps.playing_apps() == []  # nothing yet
    assert listed.threads == []  # nor looking yet: not while the app starts
    until_found(apps)  # FIRST_LOOK_MS later (main asks sooner: `look`)
    assert apps.playing_apps() == [PLAYER]
    here = threading.current_thread().name
    assert here not in listed.threads
    listed.apps.append(BROWSER)
    assert apps.playing_apps() == [PLAYER]  # what was found last
    apps.look()
    until_found(apps)
    assert apps.playing_apps() == [PLAYER, BROWSER]
    assert listed.threads == ["apps-with-sound_0"] * 2
    apps.stop()


def test_a_failed_look_keeps_the_last_list(qapp: QApplication) -> None:
    listed = CountingAppList(PLAYER)
    apps = AppsWithSound(listed)
    apps.look()
    until_found(apps)
    listed.fail = True
    apps.look()
    until_found(apps)
    assert apps.playing_apps() == [PLAYER]
    apps.stop()


def test_every_look_runs_on_one_thread_kept_between_looks(qapp: QApplication) -> None:
    """117 Low 12: not a new thread (and a new join to COM) every few seconds."""
    listed = CountingAppList(PLAYER)
    apps = AppsWithSound(listed)
    for _ in range(3):
        apps.look()
        until_found(apps)
    assert len(listed.ran_on) == 3
    thread = listed.ran_on[0]
    assert thread is not threading.current_thread()
    assert all(t is thread for t in listed.ran_on)
    assert thread.is_alive()  # kept between looks
    apps.stop()
    assert not thread.is_alive()


def test_after_stop_no_look_starts(qapp: QApplication) -> None:
    listed = CountingAppList(PLAYER)
    apps = AppsWithSound(listed)
    apps.stop()
    found: list[bool] = []
    apps.found.connect(lambda: found.append(True))
    apps.look()
    QApplication.processEvents()
    assert listed.ran_on == [] and found == []


def test_the_app_pickers_poll_lists_nothing_on_the_interface_thread(
    qapp: QApplication,
) -> None:
    listed = CountingAppList(PLAYER)
    store = MemorySettingsStore()
    desktop = DesktopApp(store, None, listed)
    assert desktop.apps is not None
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    hub = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    hub.window.show()  # offscreen; Home's picker looks once
    hub.picker.refresh()
    until_found(desktop.apps)
    here = threading.current_thread().name
    listed.apps.append(BROWSER)
    hub.home._looking.timeout.emit()  # Home's poll
    until_found(desktop.apps)
    assert here not in listed.threads  # not even the first time (291)
    assert len(hub.picker.value.available) == 2  # filled when found
    thread = listed.ran_on[-1]
    hub.close()
    windows.close()
    desktop.close()
    assert not thread.is_alive()  # the look's thread ends with the app
