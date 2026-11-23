"""Like this PC where the OS's light or dark is read by the app, not Qt
(polyglotic-hq 571): on GNOME preferring dark, GitHub's runner showed Qt
saying light, so the window was light. Linux's settings portal is read
instead (`theme.os_mode`, from `OsAdapters.system_mode`), and a change is
followed."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop import main
from polyglotic_desktop.platform.linux import hints
from polyglotic_desktop.ui import theme
from polyglotic_desktop.ui.app import DesktopApp


@pytest.fixture
def portal() -> Iterator[list[str | None]]:
    """What the OS says, as `theme.os_mode` reads it; Qt's again after."""
    says: list[str | None] = ["dark"]
    theme.os_mode = lambda: says[0]
    yield says
    theme.os_mode = None


def test_the_os_s_answer_comes_before_qt_s(portal: list[str | None]) -> None:
    assert theme.system_theme() == "dark"
    portal[0] = "light"
    assert theme.system_theme() == "light"


def test_no_preference_is_qt_s(qapp: QApplication, portal: list[str | None]) -> None:
    theme.os_mode = None
    qt = theme.system_theme()
    portal[0] = None
    theme.os_mode = lambda: portal[0]
    assert theme.system_theme() == qt


def test_like_this_pc_follows_the_portal_and_its_changes(
    qapp: QApplication, portal: list[str | None]
) -> None:
    store = MemorySettingsStore({"window_theme": "system"})
    app = DesktopApp(store, None, FakeAppList())
    themed: list[bool] = []
    app.themed.connect(lambda: themed.append(True))
    try:
        assert theme.current == "dark"
        portal[0] = "light"  # the learner switched the desktop to light
        app._follow_os_mode()  # the 10 s check
        assert theme.current == "light" and themed == [True]
        app._follow_os_mode()  # no change: nothing restyled
        assert themed == [True]
    finally:
        app.close()


def test_a_chosen_mode_stays_whatever_the_portal_says(
    qapp: QApplication, portal: list[str | None]
) -> None:
    app = DesktopApp(MemorySettingsStore({"window_theme": "dark"}), None, FakeAppList())
    try:
        portal[0] = "light"
        app._follow_os_mode()
        assert theme.current == "dark"
    finally:
        app.close()


def test_linux_reads_the_portal_and_the_others_qt() -> None:
    assert main.linux_adapters().system_mode is hints.prefers
    assert main.macos_adapters().system_mode is None
