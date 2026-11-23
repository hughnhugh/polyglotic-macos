"""The learning load's switch and its page lead to each other (polyglotic-hq
342; the user, 2026-11-15: "Learning load setting should link to learning
load in learning tab"): Settings > Lab's switch has "Open it on Learning"
while it's on, which opens Learning at the load's card for the language in
use; and the card says it's turned on in Settings > Lab, a link there.
Offscreen, the sample dictionary."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.panels import LookPanel, TimingPanel


@pytest.fixture
def built(qapp: QApplication) -> Iterator[Built]:
    built = Built(MemorySettingsStore({"learning": "zh"}), tools=True)
    yield built
    built.close()


def test_the_link_is_wired_without_making_lab_at_the_start(built: Built) -> None:
    """Settings' caption sections are made when first shown, not at the
    start (polyglotic-hq 544): the hub wires Lab's link through the page,
    so neither Lab nor any other caption section is made with the window."""
    assert not built.hub.settings.findChildren(LabPanel)
    assert not built.hub.settings.findChildren(LookPanel)
    assert not built.hub.settings.findChildren(TimingPanel)


def test_the_labs_switch_opens_the_load_on_learning(
    qapp: QApplication, built: Built
) -> None:
    hub = built.hub
    lab = hub.settings.lab
    assert lab.to_load.isHidden()  # off: nothing to open
    built.desktop.settings.update(caption_lab={"load": True})
    hub.window.show()
    hub.window.go_to("settings")
    hub.settings.show_section("lab")
    qapp.processEvents()
    assert not lab.to_load.isHidden()
    assert "Open it on Learning" in lab.to_load.text()
    lab.to_load.linkActivated.emit("load")
    qapp.processEvents()
    qapp.processEvents()
    assert hub.window.current == "learning"
    page = hub.learning
    assert not page.load.isHidden()  # filled as the page came into view
    # scrolled so the load's card is at the top of the page
    inner = page.widget()
    assert inner is not None
    top = page.load.mapTo(inner, page.load.rect().topLeft()).y()
    assert page.verticalScrollBar().value() > 0
    assert abs(page.verticalScrollBar().value() - top) <= 40
    built.desktop.settings.update(caption_lab={"load": False})
    qapp.processEvents()
    assert lab.to_load.isHidden()


def test_the_load_says_where_it_is_turned_on_and_leads_there(
    qapp: QApplication, built: Built
) -> None:
    hub = built.hub
    built.desktop.settings.update(caption_lab={"load": True})
    hub.window.show()
    hub.window.go_to("learning")
    qapp.processEvents()
    where = hub.learning.load.where
    assert "Settings > Lab" in where.text() and "turn it off" in where.text()
    where.linkActivated.emit("lab")
    qapp.processEvents()
    assert hub.window.current == "settings"
    assert hub.settings.sections.value() == "lab"
    assert hub.settings.lab.load.isVisible()
