"""Day 2 (polyglotic-hq 176, from 160's journey): after a good first
session, Home asks once whether to start Polyglotic with Windows - off
unless the learner says yes; the installed app only. The Run key through a
made-up registry: the PC's is never touched."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.main import new_interface
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.views.home import (
    GOOD_FIRST_SESSION,
    offer_start_with_windows,
)

EXE = r"C:\Users\learner\AppData\Local\Polyglotic\current\Polyglotic.exe"


class MadeUpRegistry:
    """The user's Run key, in memory."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.refuse = False

    @contextmanager
    def OpenKey(
        self, key: Any, sub_key: str, reserved: int = 0, access: int = 0
    ) -> Iterator[str]:
        if self.refuse:
            raise PermissionError("refused")
        yield f"{key}\\{sub_key}"

    def QueryValueEx(self, key: Any, name: str) -> tuple[Any, int]:
        if (key, name) not in self.values:
            raise FileNotFoundError(name)
        return self.values[(key, name)], self.REG_SZ

    def SetValueEx(
        self, key: Any, name: str, reserved: int, kind: int, value: str
    ) -> None:
        self.values[(key, name)] = value

    def DeleteValue(self, key: Any, name: str) -> None:
        if (key, name) not in self.values:
            raise FileNotFoundError(name)
        del self.values[(key, name)]


def test_asked_once_after_a_good_session_on_the_installed_app() -> None:
    good = GOOD_FIRST_SESSION
    assert offer_start_with_windows(good, False, False, True)
    assert not offer_start_with_windows(good - 1, False, False, True)  # not yet
    assert not offer_start_with_windows(good, True, False, True)  # asked before
    assert not offer_start_with_windows(good, False, True, True)  # already on
    assert not offer_start_with_windows(good, False, False, False)  # from source


@pytest.mark.windows_only  # Windows' Run key: its module imports winreg (0038)
def test_the_run_key_starts_the_app_in_the_tray() -> None:
    from polyglotic_desktop.platform.windows.startup import (
        RUN_KEY,
        VALUE,
        RunAtSignIn,
        command_for,
    )

    registry = MadeUpRegistry()
    startup = RunAtSignIn(EXE, registry)
    assert not startup.enabled()  # off by default
    startup.set_enabled(True)
    key = f"HKCU\\{RUN_KEY}"
    assert registry.values == {(key, VALUE): f'"{EXE}" --in-tray'}
    assert startup.enabled()
    assert not RunAtSignIn(r"C:\elsewhere\Polyglotic.exe", registry).enabled()
    startup.set_enabled(False)
    assert registry.values == {} and not startup.enabled()
    startup.set_enabled(False)  # not there: nothing to do
    registry.refuse = True
    startup.set_enabled(True)  # Windows refused: quietly not on
    assert not startup.enabled()
    assert command_for(EXE).startswith('"') and command_for(EXE).endswith("--in-tray")


class MadeUpStartup:
    def __init__(self) -> None:
        self.on = False

    def enabled(self) -> bool:
        return self.on

    def set_enabled(self, on: bool) -> None:
        self.on = on


def test_home_asks_once_after_a_good_session_and_yes_turns_it_on(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({"apps": ["Web Browser"]})
    desktop = DesktopApp(store, None, FakeAppList())
    built = new_interface(desktop, store, None, per_app=True)
    hub, startup = built.hub, MadeUpStartup()
    hub.startup = startup
    for _ in range(GOOD_FIRST_SESSION - 1):
        desktop.feed.captioned.emit("app-1")
    assert not hasattr(hub.home, "startup_card")  # not yet
    desktop.feed.captioned.emit("app-1")
    card = hub.home.startup_card
    assert not card.isHidden()
    assert desktop.settings.value.start_with_windows_asked  # asked: once ever
    for _ in range(GOOD_FIRST_SESSION):
        desktop.feed.captioned.emit("app-1")
    assert hub.home.startup_card is card  # not asked again
    button = card.findChild(QPushButton, "home.startup.yes")
    assert button is not None
    button.click()
    assert startup.on and card.isHidden()
    built.close()
    desktop.close()


def test_not_now_leaves_it_off_and_from_source_it_isnt_asked(
    qapp: QApplication,
) -> None:
    store = MemorySettingsStore({"apps": ["Web Browser"]})
    desktop = DesktopApp(store, None, FakeAppList())
    built = new_interface(desktop, store, None, per_app=True)
    for _ in range(GOOD_FIRST_SESSION):
        desktop.feed.captioned.emit("app-1")
    assert not hasattr(built.hub.home, "startup_card")  # from source: never
    startup = MadeUpStartup()
    built.hub.startup = startup
    desktop.feed.captioned.emit("app-1")
    button = built.hub.home.startup_card.findChild(QPushButton, "home.startup.no")
    assert button is not None
    button.click()
    assert not startup.on
    built.close()
    desktop.close()
