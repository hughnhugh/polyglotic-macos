"""Start at sign-in in Settings > App (polyglotic-hq 571): shown only where
the OS can start this copy (the installed app: `main` hands the Hub its
`StartWithWindows`), as it is now; the switch turns it on or off there,
and Home then needn't ask."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.main import Hub, Panels, wire_caption_windows
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect


class Kept:
    """`StartWithWindows` in memory; `refuse`: the OS won't."""

    def __init__(self, on: bool = False) -> None:
        self.on = on
        self.refuse = False
        self.asked: list[bool] = []

    def enabled(self) -> bool:
        return self.on

    def set_enabled(self, on: bool) -> None:
        self.asked.append(on)
        if not self.refuse:
            self.on = on


@pytest.fixture
def hub(qapp: QApplication) -> Iterator[Hub]:
    store = MemorySettingsStore({"apps": ["Web Browser"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    yield built
    built.close()
    windows.close()
    desktop.close()


def test_hidden_where_the_os_can_t_start_this_copy(hub: Hub) -> None:
    """From source, the Store's copy, and Linux before 571: no switch."""
    assert hub.settings.start_card.isHidden()


def test_shown_as_it_is_and_off_by_default(hub: Hub) -> None:
    chosen: list[bool] = []
    hub.settings.start_at_sign_in_chosen.connect(chosen.append)
    hub.use_startup(Kept())
    assert not hub.settings.start_card.isHidden()
    assert not hub.settings.start_at_sign_in.switch.isChecked()
    hub.use_startup(Kept(on=True))  # turned on before, here or by Home
    assert hub.settings.start_at_sign_in.switch.isChecked()
    assert chosen == []  # shown as it is, not chosen


def test_the_switch_turns_it_on_and_off(hub: Hub) -> None:
    kept = Kept()
    hub.use_startup(kept)
    switch = hub.settings.start_at_sign_in.switch
    switch.setChecked(True)
    assert kept.asked == [True] and kept.on
    assert hub.desktop.settings.value.start_with_windows_asked  # Home needn't ask
    switch.setChecked(False)
    assert kept.asked == [True, False] and not kept.on


def test_the_switch_shows_what_the_os_did(hub: Hub) -> None:
    kept = Kept()
    kept.refuse = True  # a folder that can't be written: quietly not on
    hub.use_startup(kept)
    hub.settings.start_at_sign_in.switch.setChecked(True)
    assert kept.asked == [True]
    assert not hub.settings.start_at_sign_in.switch.isChecked()


def test_yes_on_home_shows_in_settings(hub: Hub) -> None:
    kept = Kept()
    hub.use_startup(kept)
    hub.home.start_with_windows_answered.emit(True)
    assert kept.on and hub.settings.start_at_sign_in.switch.isChecked()
