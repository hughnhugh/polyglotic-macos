"""A downloaded update offered where the learner looks (polyglotic-hq 299),
offscreen: "Version X is ready. Restart to install it." with what's new in
two lines, Restart now and Later on Home; the tray's line; what Settings
says each look found. Later asks again only at the next start; nothing
restarts the app but the learner's Restart now."""

import sys
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QPushButton
from tests.releases.test_updates import FakeUpdater
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui.test_main_updates import settle, wait_for
from tests.ui_next.test_account_settings_help import (  # noqa: F401 - its fixture
    settings_deleted,
    settings_page,
)
from tests.ui_next.test_home import home

from polyglotic_desktop.core.releases.updates import Found, UpdateCheck, Updates
from polyglotic_desktop.main import BackgroundUpdates, UpdateShown
from polyglotic_desktop.ports.updates import Update
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.views.home import Picker

ALPHA = "win-x64-alpha"
NOTES = (
    "### New\n\n"
    "- Hear a word: the speaker on a word's card says it aloud. More slowly\n"
    "  on the next click.\n"
    "- Text size: Settings > App > Text size.\n"
    "- A third line, not shown.\n"
)
READY = Update("0.2.0", notes=NOTES)
LINUX = sys.platform.startswith("linux")


def ready_line(version: str) -> str:
    """Home's and Settings > Updates' update-ready line on this OS (640)."""
    if LINUX:
        return (
            f"Version {version} is ready. Quit and start Polyglotic again to "
            "finish updating."
        )
    return f"Version {version} is ready. Restart to install it."


def tray_ready_line(version: str) -> str:
    """The tray's update-ready line on this OS (640)."""
    if LINUX:
        return f"Quit to finish updating to {version}"
    return f"Restart to install version {version}"


def button(rig: "Rig", name: str) -> QPushButton:
    found = rig.home.findChild(QPushButton, name)
    assert found is not None, name
    return found


class Rig:
    def __init__(self) -> None:
        self.home, _ = home(Picker())
        self.desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
        self.settings = settings_page()
        self.restarts = 0
        self.anyway = 0
        self.shown = UpdateShown(
            self.home, self.desktop, self.settings, self._restart, self._anyway
        )

    def _restart(self) -> None:
        self.restarts += 1

    def _anyway(self) -> None:
        self.anyway += 1

    def found(
        self, found: Found, downloaded: Update | None, held: Update | None = None
    ) -> None:
        self.shown.found(found, downloaded, held)  # as from the updates' thread
        QApplication.processEvents()

    def close(self) -> None:
        self.desktop.close()
        self.home.close()
        shiboken6.delete(self.home)
        shiboken6.delete(self.desktop)  # the offer with it; Settings: its fixture


def test_a_downloaded_update_is_offered_on_home_in_the_tray_and_in_settings(
    qapp: QApplication,
) -> None:
    rig = Rig()
    try:
        rig.found(Found.UP_TO_DATE, None)
        assert rig.home.update_card.isHidden()
        assert not rig.desktop.install_update.isVisible()
        assert rig.settings.update_found.text() == "Polyglotic is up to date."
        assert rig.settings.restart_now.isHidden()

        rig.found(Found.READY, READY)
        assert not rig.home.update_card.isHidden()
        assert rig.home.update_title.text() == ready_line("0.2.0")
        assert [line.text() for line in rig.home.whats_new] == [
            "• Hear a word: the speaker on a word's card says it aloud.",
            "• Text size: Settings > App > Text size.",
        ]
        assert rig.desktop.install_update.isVisible()
        assert rig.desktop.install_update.text() == tray_ready_line("0.2.0")
        assert rig.settings.update_found.text() == ready_line("0.2.0")
        assert not rig.settings.restart_now.isHidden()
    finally:
        rig.close()


def test_restart_now_from_home_the_tray_or_settings_restarts(
    qapp: QApplication,
) -> None:
    rig = Rig()
    try:
        rig.found(Found.READY, READY)
        button(rig, "home.update.restart").click()
        rig.desktop.install_update.trigger()
        rig.settings.restart_now.click()
        assert rig.restarts == 3
    finally:
        rig.close()


def test_later_asks_again_only_at_the_next_start(qapp: QApplication) -> None:
    """Later hides Home's card for this run: the next looks - every few
    hours - find it, or a newer one, and Home doesn't ask again. The tray's
    line stays, quietly, for whoever wants it now."""
    rig = Rig()
    try:
        rig.found(Found.READY, READY)
        button(rig, "home.update.later").click()
        assert rig.home.update_card.isHidden()
        rig.found(Found.READY, READY)  # the next look
        rig.found(Found.READY, Update("0.3.0"))  # and a newer one
        assert rig.home.update_card.isHidden()
        assert rig.desktop.install_update.text() == tray_ready_line("0.3.0")
        assert rig.restarts == 0  # nothing restarts by itself
    finally:
        rig.close()


def test_settings_say_why_there_is_nothing_to_install(qapp: QApplication) -> None:
    """A feed out of reach and a failed download: said in Settings, and
    nothing offered on Home - the next look tries again."""
    rig = Rig()
    try:
        rig.settings.update_now.click()
        assert rig.settings.update_found.text() == "Checking for updates…"
        rig.found(Found.NO_FEED, None)
        assert rig.settings.update_found.text().startswith(
            "Couldn't reach the update server."
        )
        rig.found(Found.NOT_DOWNLOADED, None)
        assert rig.settings.update_found.text().startswith(
            "The update couldn't be downloaded."
        )
        assert rig.home.update_card.isHidden()
        assert not rig.desktop.install_update.isVisible()
        # one downloaded earlier stays ready, whatever a later look found
        rig.found(Found.NO_FEED, READY)
        assert rig.settings.update_found.text().startswith("Version 0.2.0 is ready")
    finally:
        rig.close()


def test_the_first_look_reaches_the_interface_built_after_it(
    qapp: QApplication,
) -> None:
    """The first look runs before the interface exists: its outcome is
    told to the listener as soon as there is one."""
    updater = FakeUpdater({UpdateCheck(): READY})
    updates = BackgroundUpdates(Updates(updater, ALPHA))
    updates.check()
    settle(updates)
    told: list[tuple[Found, Update | None, Update | None]] = []
    updates.tell(lambda found, update, held: told.append((found, update, held)))
    assert told == [(Found.READY, READY, None)]
    updates.check()
    settle(updates)
    assert told[-1] == (Found.READY, READY, None) and len(told) == 2


def test_restart_now_applies_it_as_the_app_quits(qapp: QApplication) -> None:
    """main's Restart now: what's downloaded applies once the app has quit,
    and the new version starts - before the usual at-exit step."""
    updater = FakeUpdater({UpdateCheck(): READY})
    updates = BackgroundUpdates(Updates(updater, ALPHA))
    updates.check()
    updates.restart_when_quitting()
    updates.at_exit()
    wait_for(lambda: updater.calls[-1].startswith("apply"))
    assert updater.calls == [
        "find None False",
        "download 0.2.0",
        "apply at exit 0.2.0 and start",
    ]


HELD = Update("0.2.0", notes=NOTES, size=91_960_000)


def test_on_a_metered_connection_home_offers_download_anyway_with_its_size(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 345: found, not downloaded - Home says how big it is
    and offers Download anyway; once it's downloaded, Restart now."""
    rig = Rig()
    try:
        rig.found(Found.METERED, None, HELD)
        assert not rig.home.update_card.isHidden()
        assert rig.home.update_title.text() == (
            "Version 0.2.0 is available: 92.0 MB to download."
        )
        assert rig.home.update_then.text().startswith("Your connection is metered")
        anyway = button(rig, "home.update.download_anyway")
        assert not anyway.isHidden() and anyway.isEnabled()
        assert button(rig, "home.update.restart").isHidden()
        assert rig.home.whats_new[0].text().startswith("• Hear a word")
        assert not rig.desktop.install_update.isVisible()  # nothing to install yet
        assert rig.settings.update_found.text().startswith(
            "Version 0.2.0 is available. Your connection is metered"
        )

        anyway.click()
        assert rig.anyway == 1
        assert not anyway.isEnabled()
        assert rig.home.update_then.text().startswith("Downloading.")

        rig.found(Found.NOT_DOWNLOADED, None, HELD)  # it failed: again
        assert anyway.isEnabled() and not anyway.isHidden()

        rig.found(Found.READY, HELD)  # downloaded: Restart now (Quit now on Linux)
        assert rig.home.update_title.text() == ready_line("0.2.0")
        assert anyway.isHidden()
        assert not button(rig, "home.update.restart").isHidden()
        assert rig.desktop.install_update.isVisible()
    finally:
        rig.close()


def test_a_size_not_known_isnt_said(qapp: QApplication) -> None:
    rig = Rig()
    try:
        rig.found(Found.METERED, None, Update("0.2.0"))
        assert rig.home.update_title.text() == "Version 0.2.0 is available."
    finally:
        rig.close()


def test_later_stops_the_metered_offer_until_the_next_start(
    qapp: QApplication,
) -> None:
    rig = Rig()
    try:
        rig.found(Found.METERED, None, HELD)
        button(rig, "home.update.later").click()
        rig.found(Found.METERED, None, HELD)
        assert rig.home.update_card.isHidden()
    finally:
        rig.close()


def test_download_anyway_runs_on_the_updates_thread_and_tells(
    qapp: QApplication,
) -> None:
    updater = FakeUpdater({UpdateCheck(): HELD})
    updates = BackgroundUpdates(Updates(updater, ALPHA, lambda: True))
    told: list[tuple[Found, Update | None, Update | None]] = []
    updates.tell(lambda found, update, held: told.append((found, update, held)))
    updates.check()
    settle(updates)
    assert told[-1] == (Found.METERED, None, HELD)
    updates.download_anyway()
    settle(updates)
    assert told[-1] == (Found.READY, HELD, None)
    assert updater.calls == ["find None False", "download 0.2.0"]


def test_the_update_card_is_framed_as_a_card_like_whats_new_beside_it(
    qapp: QApplication,
) -> None:
    """The stylesheet draws a card's frame by its object name, `Card`: the
    update card had another name, so on Home it was drawn bare beside
    What's new's framed card (345's pictures, 361's rehearsal)."""
    rig = Rig()
    try:
        rig.found(Found.READY, READY)
        rig.home.show_whats_new("0.2.0", ("A line",))
        assert rig.home.update_card.objectName() == "Card"
        assert rig.home.update_card.objectName() == rig.home.whats_new_card.objectName()
    finally:
        rig.close()


# -- Linux: not writable and quit-to-apply wording (polyglotic-hq 640) -----------------


NOT_WRITABLE_TEXT = (
    "Polyglotic can't update itself in this folder. Move it to your "
    "Applications folder (~/Applications) and start it from there."
)


def test_not_writable_is_shown_on_home_and_in_settings_with_open_folder(
    qapp: QApplication,
) -> None:
    """640: an AppImage in a folder the learner can't change shows the notice
    on Home and in Settings > Updates, each with a button that opens the folder."""
    opened = 0

    def open_folder() -> None:
        nonlocal opened
        opened += 1

    rig = Rig()
    rig.shown = UpdateShown(
        rig.home,
        rig.desktop,
        rig.settings,
        rig._restart,
        rig._anyway,
        open_folder,
    )
    try:
        rig.found(Found.NOT_WRITABLE, None)
        assert not rig.home.not_writable_card.isHidden()
        assert rig.home.not_writable_notice.text() == NOT_WRITABLE_TEXT
        assert rig.home.update_card.isHidden()
        assert rig.settings.update_found.text() == NOT_WRITABLE_TEXT
        assert not rig.settings.open_app_folder.isHidden()
        assert rig.settings.restart_now.isHidden()

        button(rig, "home.update.open_folder").click()
        rig.settings.open_app_folder.click()
        assert opened == 2

        rig.found(Found.UP_TO_DATE, None)
        assert rig.home.not_writable_card.isHidden()
        assert rig.settings.open_app_folder.isHidden()
    finally:
        rig.close()


def test_on_linux_update_ready_says_quit_and_start_again(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """640: on Linux, a downloaded update applies when the app quits, so
    Home, Settings and the tray say so instead of Windows' restart wording."""
    monkeypatch.setattr(sys, "platform", "linux")
    rig = Rig()
    try:
        rig.found(Found.READY, READY)
        assert not rig.home.update_card.isHidden()
        assert rig.home.update_title.text() == (
            "Version 0.2.0 is ready. Quit and start Polyglotic again to finish updating."
        )
        assert rig.home.update_then.text() == (
            "Or later: it applies when you quit Polyglotic."
        )
        assert button(rig, "home.update.restart").text() == "Quit now"
        assert rig.settings.update_found.text() == (
            "Version 0.2.0 is ready. Quit and start Polyglotic again to finish updating."
        )
        assert rig.settings.restart_now.text() == "Quit now"
        assert rig.desktop.install_update.isVisible()
        assert rig.desktop.install_update.text() == "Quit to finish updating to 0.2.0"
        assert "Restart" not in rig.home.update_title.text()
        assert "Restart" not in rig.settings.update_found.text()
        assert "Restart" not in rig.desktop.install_update.text()
    finally:
        rig.close()


def test_open_update_folder_opens_the_appimages_folder(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """640: Open folder opens the folder holding the running AppImage."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    from polyglotic_desktop.adapters.velopack_updates import AppImage
    from polyglotic_desktop.main import open_update_folder

    opened: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", opened.append)
    folder = tmp_path / "opt-polyglotic"
    folder.mkdir()
    here = AppImage(folder / "Polyglotic.AppImage", tmp_path / "m", tmp_path / "pk")
    open_update_folder(here)
    assert opened == [QUrl.fromLocalFile(str(folder))]


def test_on_linux_trays_quit_applies_the_downloaded_update(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """640: clicking Quit in the tray runs at_exit, which applies a
    downloaded update on Linux (restart=False)."""
    updater = FakeUpdater({UpdateCheck(): READY})
    updates = BackgroundUpdates(Updates(updater, "linux-x64-alpha", apply_on_quit=True))
    updates.check()
    settle(updates)

    desktop = DesktopApp(MemorySettingsStore(), None, FakeAppList())
    applied: list[bool] = []

    def _exit(_code: int = 0) -> None:
        updates.at_exit()
        applied.append(True)

    monkeypatch.setattr(qapp, "exit", _exit)
    try:
        desktop.quit.trigger()
        assert applied == [True]
        assert updater.calls == [
            "find None False",
            "download 0.2.0",
            "apply at exit 0.2.0",
        ]
    finally:
        desktop.close()
        shiboken6.delete(desktop)
