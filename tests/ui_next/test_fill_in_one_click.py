"""Filled lines in one click on the caption window (polyglotic-hq 372; the
user, 2026-11-15, DECISIONS #175: "upgrade it as a one click setting
(probably line by line caption width, new layout, captions run on) from
caption window"): New layout, Line by line and Captions run on together,
and off again back to what was there - one state with the Lab's rows,
every window's."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_caption_window import MIC, Store, areas, window_of
from tests.ui_next.test_joined_window import THREE

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.glyphs import Glyph
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill, Join
from polyglotic_desktop.ui_next.views.panels import LookView

MADE: list[QWidget] = []
FILLED = CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True)


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each window deleted when its test ends (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def test_filled_is_the_three_together() -> None:
    assert FILLED.filled
    assert not CaptionLab().filled
    assert not replace(FILLED, run_on=False).filled
    assert not replace(FILLED, flow=False).filled
    assert not replace(FILLED, fill=Fill.STACKED).filled


def test_on_turns_the_three_on_and_nothing_else() -> None:
    lab = CaptionLab(join=Join.SPACE, aligned=True, older=0.6, fill=Fill.STACKED)
    on = lab.with_filled(True)
    assert on == replace(lab, flow=True, fill=Fill.PAIRED, run_on=True)
    assert on.filled


def test_off_puts_back_what_was_there() -> None:
    before = CaptionLab(fill=Fill.STACKED, join=Join.SPACE)
    on = before.with_filled(True)
    # a choice made in between (here: the join) is kept
    changed = replace(on, join=Join.LINE_ENDS)
    assert changed.with_filled(False, before) == replace(before, join=Join.LINE_ENDS)
    # New layout's Line by line without run-on stays that
    paired = CaptionLab(flow=True, fill=Fill.PAIRED)
    assert paired.with_filled(True).with_filled(False, paired) == paired


def test_off_with_nothing_known_is_the_apps_own() -> None:
    """Turned on in the Lab, or before a restart: off is the layout without
    the Lab - clause rows, today's layout, no run-on."""
    assert replace(FILLED, older=0.6).with_filled(False) == CaptionLab(older=0.6)
    # a "before" that was itself filled says nothing
    assert FILLED.with_filled(False, FILLED) == CaptionLab()


def test_the_look_remembers_and_forgets() -> None:
    before = CaptionLab(fill=Fill.STACKED)
    view = LookView(CaptionLook(lab=before))
    view.set_filled(True)
    assert view.value.lab == before.with_filled(True)
    view.set_filled(True)  # already on: nothing more
    assert view.value.lab.filled
    view.set_filled(False)
    assert view.value.lab == before
    assert view.unfilled is None
    # turned on in the Lab: the button's off is the app's own
    view.set_lab(FILLED)
    view.set_filled(False)
    assert view.value.lab == CaptionLab()


def test_the_button_shows_and_asks(qapp: QApplication) -> None:
    window = window_of(qapp)
    MADE.append(window)
    button = window.buttons["fill"]
    assert window.glyphs["fill"] is Glyph.FILL
    assert not window.controls["fill"].icon().isNull()
    said = QAccessible.queryAccessibleInterface(button)
    assert said.text(QAccessible.Text.Name) == "Fill the width"
    assert "every window" in button.toolTip()
    assert not button.isChecked()
    asked: list[bool] = []
    window.fill_wanted.connect(asked.append)
    button.click()
    assert asked == [True]
    # the Lab's three set elsewhere: the button says so
    window.set_look(replace(window.look, lab=FILLED))
    assert button.isChecked()
    window.set_look(replace(window.look, lab=replace(FILLED, run_on=False)))
    assert not button.isChecked()


def test_every_window_and_the_lab_agree(qapp: QApplication) -> None:
    """One state: a window's button, every other window's and the Lab's
    rows show the same values whichever one changes them."""
    windows = CaptionWindows(Store({"targets": ["en"]}), MIC, areas)
    windows.set_labels(
        {source: SourceLabel(name, "#4dd0e1") for name, source in THREE}, "You"
    )
    look = LookView(CaptionLook(), on_change=windows.set_look)
    windows.fill_wanted.connect(look.set_filled)
    panel = LabPanel(look)
    MADE.append(panel)
    look.subscribe(panel.refresh)
    windows.set_captioned(THREE[:2])
    first, second = windows.windows.values()
    try:
        first.buttons["fill"].click()
        assert look.value.lab == FILLED
        assert first.buttons["fill"].isChecked() and second.buttons["fill"].isChecked()
        panel.refresh()
        assert panel.flow.switch.isChecked() and panel.run_on.switch.isChecked()
        assert panel.fill.value() is Fill.PAIRED
        # the Lab's row turns run-on off: the buttons are off
        panel.run_on.switch.click()
        assert not look.value.lab.filled
        assert not first.buttons["fill"].isChecked()
        assert not second.buttons["fill"].isChecked()
        # on again from the other window, then off: back to that
        kept = look.value.lab
        second.buttons["fill"].click()
        assert look.value.lab.filled
        second.buttons["fill"].click()
        assert look.value.lab == kept
    finally:
        windows.close()
