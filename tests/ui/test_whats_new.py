"""What's new after an update (polyglotic-hq 345), wired by `main`: the
notes the app carries, on Home once per version until Close - the newest
in a few lines, the other versions named - and every version's in Help;
nothing on a fresh install's first run. Made-up notes; offscreen."""

from collections.abc import Iterator
from typing import Any

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from tests.lexicon.sample import chinese_sample
from tests.releases.test_notes import FILE
from tests.ui.fakes import FakeAppList, MemorySettingsStore, tools_for

from polyglotic_desktop import main
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.main import Hub, Panels, show_whats_new
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect

Rig = tuple[DesktopApp, Hub]


@pytest.fixture
def rig(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setattr(main, "release_notes", lambda: FILE)
    made: list[tuple[DesktopApp, Hub, CaptionWindows]] = []

    def make(seen: str | None) -> Rig:
        tools = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
        store = MemorySettingsStore({"apps": ["Web Browser"], "whats_new_seen": seen})
        desktop = DesktopApp(store, tools, FakeAppList())
        windows = CaptionWindows(
            store, MIC, lambda: [Rect(0, 0, 1920, 1040)], learner=tools
        )
        assert desktop.apps is not None
        hub = Hub(
            desktop, windows, Panels(desktop.settings, windows), desktop.apps, True
        )
        made.append((desktop, hub, windows))
        return desktop, hub

    yield make
    for desktop, hub, windows in made:
        hub.window.keep_in_tray = False
        hub.window.close()
        hub.window.deleteLater()
        windows.close()
        desktop.close()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_after_an_update_home_says_whats_new_until_close(rig: Any) -> None:
    desktop, hub = rig("0.1.5")
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    home = hub.home
    assert not home.whats_new_card.isHidden()
    assert home.whats_new_title.text() == "What's new in Polyglotic 0.1.6"
    assert [line.text() for line in home.whats_new_lines if not line.isHidden()] == [
        "• What's new: after an update, Home says what changed.",
        "• A thing fixed.",
    ]
    assert home.whats_new_more.isHidden()  # no other version, notes in English
    # Help keeps every version's, up to this one, the newest open
    assert [t.name for t in hub.help.versions] == [
        "Version 0.1.6",
        "Version 0.1.5",
        "Version 0.1.4",
    ]
    assert hub.help.versions[0].title.isChecked()
    assert not hub.help.versions[1].title.isChecked()
    assert hub.help.versions[0].text.text().startswith("New\n• What's new:")

    button(home, "home.whats_new.close").click()
    assert home.whats_new_card.isHidden()
    assert desktop.settings.value.whats_new_seen == "0.1.6"


def test_closed_it_doesnt_come_back_at_the_next_start(rig: Any) -> None:
    desktop, hub = rig("0.1.6")
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    assert hub.home.whats_new_card.isHidden()
    assert len(hub.help.versions) == 3  # Help still has them


def test_a_fresh_installs_first_run_shows_none(rig: Any) -> None:
    desktop, hub = rig(None)
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=True, english=True)
    assert hub.home.whats_new_card.isHidden()
    assert desktop.settings.value.whats_new_seen == "0.1.6"


def test_from_a_version_that_kept_nothing_this_versions_notes(rig: Any) -> None:
    """0.1.5 and before kept no `whats_new_seen`."""
    desktop, hub = rig(None)
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    assert not hub.home.whats_new_card.isHidden()
    assert hub.home.whats_new_more.isHidden()
    assert desktop.settings.value.whats_new_seen is None  # until Close


def test_several_skipped_the_newest_and_the_others_named(rig: Any) -> None:
    desktop, hub = rig("0.1.4")
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=False)
    assert hub.home.whats_new_title.text() == "What's new in Polyglotic 0.1.6"
    assert hub.home.whats_new_more.text() == (
        "Also new since your last update: 0.1.5. The release notes are in English."
    )
    assert not hub.help.whats_new_language.isHidden()


def test_all_the_changes_opens_helps_whats_new(rig: Any) -> None:
    desktop, hub = rig("0.1.4")
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    hub.help.versions[0].title.setChecked(False)
    button(hub.home, "home.whats_new.all").click()
    assert hub.window.current == "help"
    assert hub.help.versions[0].title.isChecked()
    assert desktop.settings.value.whats_new_seen == "0.1.4"  # not closed yet


def test_no_notes_file_no_card_and_no_help_section(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "release_notes", lambda: "")
    desktop, hub = rig("0.1.5")
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    assert hub.home.whats_new_card.isHidden()
    assert hub.help.whats_new.isHidden()


def button(page: QWidget, name: str) -> QPushButton:
    found = page.findChild(QPushButton, name)
    assert found is not None, name
    return found


def test_all_the_changes_shows_whats_new_from_its_heading(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All the changes lands on What's new's heading and the newest
    version's title, not the middle of the notes (361: with the real notes,
    taller than Help's view, Qt's `ensureWidgetVisible` centred the section
    and the learner landed mid-list in 0.1.6's Better)."""
    from pathlib import Path

    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    real = (Path(main.__file__).parents[2] / "RELEASE-NOTES.md").read_text(
        encoding="utf-8"
    )
    monkeypatch.setattr(main, "release_notes", lambda: real)
    desktop, hub = rig("0.1.5")
    hub.window.resize(1000, 740)
    hub.window.show()
    QApplication.processEvents()
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    QApplication.processEvents()
    button(hub.home, "home.whats_new.all").click()
    QTest.qWait(200)  # the page settles within the 500 ms it's kept at the heading
    page = hub.help
    view = page.viewport()
    assert page.whats_new.height() > view.height()  # the case: taller than the view
    top = page.whats_new.mapTo(view, QPoint(0, 0)).y()
    title = page.versions[0].title
    title_top = title.mapTo(view, QPoint(0, 0)).y()
    assert 0 <= top <= 40, top
    assert title_top >= 0 and title_top + title.height() <= view.height(), title_top


def test_all_the_changes_twice_lets_go_once(rig: Any) -> None:
    """Two clicks on All the changes in quick succession: kept at the
    heading, then let go once - nothing disconnected twice."""
    from PySide6.QtTest import QTest

    from polyglotic_desktop.ui_next import help_page

    desktop, hub = rig("0.1.5")
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    button(hub.home, "home.whats_new.all").click()
    button(hub.home, "home.whats_new.all").click()
    QTest.qWait(help_page.KEEP_WHATS_NEW_MS + 200)
    assert not hub.help._whats_new_kept


def test_helps_notes_are_built_when_help_is_first_shown_not_at_the_start(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every version's notes laid out in Help took about 100 ms of each
    start on the interface thread, right after the first paint, Help unseen
    (361: the packed app's watchdog, every start). They're built when Help
    is first shown - or All the changes, or anything that reads them."""
    from pathlib import Path

    from polyglotic_desktop.ui_next.help_page import Topic

    real = (Path(main.__file__).parents[2] / "RELEASE-NOTES.md").read_text(
        encoding="utf-8"
    )
    monkeypatch.setattr(main, "release_notes", lambda: real)
    desktop, hub = rig("0.1.6")
    hub.window.show()
    QApplication.processEvents()
    show_whats_new(hub, desktop.settings, "0.1.6", fresh=False, english=True)
    QApplication.processEvents()
    built = [
        t for t in hub.help.findChildren(Topic) if t.objectName() == "help.version"
    ]
    assert built == []  # Help not shown yet: nothing laid out
    assert not hub.help.whats_new.isHidden()  # though it has notes to show
    hub.window.go_to("help")
    QApplication.processEvents()
    built = [
        t for t in hub.help.findChildren(Topic) if t.objectName() == "help.version"
    ]
    assert len(built) > 3 and built[0].title.isChecked()
