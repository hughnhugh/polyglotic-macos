"""The tray on Linux, and a desktop with none (polyglotic-hq 571).

- On Linux the desktop's tray shows the tray's menu itself - KDE's and
  GNOME's AppIndicator from what Qt hands them over D-Bus, an X11 tray at
  the click - so the menu is the tray's (`setContextMenu`), and the app
  never opens a second one of its own.
- Where the desktop has no tray (GNOME without its extension), closing the
  main window doesn't leave the app running unseen and unsaid: the first
  time a box says it runs on and offers Quit; after that it just hides,
  and comes back from the launcher.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QWidget
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.main import Hub, Panels, wire_caption_windows
from polyglotic_desktop.ui import app as app_module
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.main_window import MainWindow
from polyglotic_desktop.ui_next.no_tray import keep_running, still_running_box
from polyglotic_desktop.ui_next.views.placement import Rect


@pytest.fixture
def store() -> MemorySettingsStore:
    return MemorySettingsStore({"apps": ["Web Browser"]})


@pytest.fixture
def desktop(qapp: QApplication, store: MemorySettingsStore) -> Iterator[DesktopApp]:
    made = DesktopApp(store, None, FakeAppList())
    yield made
    made.close()
    if made.tray is not None:
        made.tray.deleteLater()


def a_tray_here(monkeypatch: pytest.MonkeyPatch, linux: bool) -> None:
    """A tray on this desktop (offscreen has none), on Linux or not."""
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: True)
    monkeypatch.setattr(app_module, "DESKTOP_SHOWS_TRAY_MENU", linux)


def test_on_linux_the_tray_has_the_menu_and_shows_it_itself(
    desktop: DesktopApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before 571 the menu was never the tray's: KDE's tray then asked the
    app to open one at a point XWayland may not know, and GNOME's
    AppIndicator had none to show."""
    a_tray_here(monkeypatch, linux=True)
    opened: list[bool] = []
    monkeypatch.setattr(desktop, "show_tray_menu", lambda: opened.append(True))
    desktop.show_tray()
    assert desktop.tray is not None
    assert desktop.tray.contextMenu() is desktop.tray_menu
    desktop._tray_activated(QSystemTrayIcon.ActivationReason.Context)
    assert opened == []  # the tray has it open already: not a second one


def test_elsewhere_the_app_opens_the_menu_itself_above_the_taskbar(
    desktop: DesktopApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_tray_here(monkeypatch, linux=False)
    opened: list[bool] = []
    monkeypatch.setattr(desktop, "show_tray_menu", lambda: opened.append(True))
    desktop.show_tray()
    assert desktop.tray is not None
    assert desktop.tray.contextMenu() is None
    desktop._tray_activated(QSystemTrayIcon.ActivationReason.Context)
    assert opened == [True]


def test_every_item_of_the_menu_is_an_action_a_desktop_can_draw(
    desktop: DesktopApp,
) -> None:
    """A desktop's tray draws the menu from its actions (D-Bus's menu has no
    widgets): every item is a plain action, a separator or a submenu."""
    for action in desktop.tray_menu.actions():
        assert type(action) is QAction, action.text()
        shown = action.isVisible()  # Restart to install: hidden until one's ready
        assert not shown or action.isSeparator() or action.text() or action.menu()


def test_where_the_os_has_no_dictation_the_tray_offers_none(
    desktop: DesktopApp,
) -> None:
    """571 found Linux's tray offering "Dictation (preview)", whose key the
    app would then say another program has: until 546's slice 8 neither it
    nor its languages show there (574); everything else does."""
    shown = lambda: [
        a.text().split("	")[0]
        for a in desktop.tray_menu.actions()
        if a.isVisible() and not a.isSeparator()
    ]
    before = shown()
    assert any(t.startswith("Dictation") for t in before)
    desktop.offer_dictation(False)
    after = shown()
    assert not any(t.startswith("Dictation") for t in after)
    assert set(after) == {t for t in before if not t.startswith("Dictation")}
    assert "Pause captions" in after and "Quit" in after


def test_the_box_keeps_running_by_default_and_offers_quit(qapp: QApplication) -> None:
    box = still_running_box(None)
    try:
        roles = {box.buttonRole(b): b.text() for b in box.buttons()}
        assert roles == {
            QMessageBox.ButtonRole.AcceptRole: "Keep running",
            QMessageBox.ButtonRole.DestructiveRole: "Quit",
        }
        assert box.defaultButton() is box.escapeButton()
        assert box.buttonRole(box.defaultButton()) is QMessageBox.ButtonRole.AcceptRole
        assert "launch Polyglotic again" in box.informativeText()
    finally:
        box.deleteLater()


def test_the_box_answers_quit_only_when_quit_is_clicked(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    def clicking(role: QMessageBox.ButtonRole | None) -> object:
        def exec_(box: QMessageBox) -> int:
            for button in box.buttons():
                if role is not None and box.buttonRole(button) is role:
                    button.click()
            return 0

        return exec_

    monkeypatch.setattr(QMessageBox, "exec", clicking(None))  # closed by the title bar
    assert keep_running(None) is True
    monkeypatch.setattr(
        QMessageBox, "exec", clicking(QMessageBox.ButtonRole.DestructiveRole)
    )
    assert keep_running(None) is False
    monkeypatch.setattr(
        QMessageBox, "exec", clicking(QMessageBox.ButtonRole.AcceptRole)
    )
    assert keep_running(None) is True


@pytest.fixture
def hub(desktop: DesktopApp, store: MemorySettingsStore) -> Iterator[Hub]:
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    yield built
    built.close()
    windows.close()


def test_without_a_tray_closing_asks_once_then_just_hides(hub: Hub) -> None:
    asked: list[QWidget] = []

    def keep(parent: QWidget) -> bool:
        asked.append(parent)
        return True

    hub.keep_running = keep
    hub.window.no_tray = True  # as `main` sets it where there's no tray
    hub.window.show()
    hub.window.close()
    assert asked == [hub.window]  # over the window, while it still shows
    assert not hub.window.isVisible()  # hidden: the app runs on
    assert hub.desktop.settings.value.tray_note_shown is True
    hub.window.show()  # back from the launcher (a second start)
    hub.window.close()
    assert asked == [hub.window]  # not again
    assert not hub.window.isVisible()


def test_without_a_tray_quit_in_the_box_quits(
    hub: Hub, monkeypatch: pytest.MonkeyPatch
) -> None:
    quits: list[bool] = []

    def may_quit() -> bool:  # asked: so Quit was chosen (and the test runs on)
        quits.append(True)
        return False

    monkeypatch.setattr(hub.desktop, "may_quit", may_quit)
    hub.keep_running = lambda _parent: False
    hub.window.no_tray = True
    hub.window.show()
    hub.window.close()
    QCoreApplication.processEvents()  # Quit runs once the close is done
    assert quits == [True]


def test_with_a_tray_or_quitting_nothing_is_asked(hub: Hub) -> None:
    asked: list[QWidget] = []

    def keep(parent: QWidget) -> bool:
        asked.append(parent)
        return True

    hub.keep_running = keep
    hub.window.no_tray = True
    hub.window.show()
    hub.close()  # Quit: the window closes for good
    assert not hub.window.isVisible() and asked == []


def test_a_window_closes_as_before_unless_main_says_there_is_no_tray(
    qapp: QApplication,
) -> None:
    window = MainWindow(QAction("Quit"))
    seen: list[bool] = []
    window.closed_without_tray.connect(lambda: seen.append(True))
    window.show()
    assert window.close() is True and seen == []
    window.no_tray = True
    window.show()
    assert window.close() is False and seen == [True]  # `main`'s to answer
    window.no_tray = False
    window.close()
    window.deleteLater()
