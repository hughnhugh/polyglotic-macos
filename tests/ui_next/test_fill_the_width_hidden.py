"""Fill the width is hidden behind its flag, off (polyglotic-hq 555; the
user, 2026-11-20: "Fill the width settings (from navbar / lab) don't work
well at all in these versions. Probably remove this from the app"): the
caption window's button and the Lab's rows that pour captions aren't
shown, and a learner who had it on is back on a clause a row - with
Arrows again. The code stays until the Smooth mode fills lines itself
(polyglotic-hq 552); the tests of the pour turn the flag on.

The files in `tests/ui/settings_files/` are what 0.1.9 and
0.1.10-preview.1 saved (polyglotic-hq project 555's
`work/make_settings_files.py`): one learner with filled lines on from a
window's button, one with the Lab's Translation below."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.releases import flags
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_window import caption_style
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill, Join
from polyglotic_desktop.ui_next.views.panels import LookView

FILES = Path(__file__).parent.parent / "ui" / "settings_files"
VERSIONS = ("0.1.9", "0.1.10-preview.1")
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each window and panel deleted when its test ends (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def saved_by(version: str, learner: str) -> dict[str, object]:
    files = json.loads((FILES / f"{version}.json").read_text(encoding="utf-8"))
    return dict(files[learner])


def test_its_flag_is_off() -> None:
    assert not flags.on(flags.FILL_THE_WIDTH)
    assert flags.FILL_THE_WIDTH in flags.DECLARED


@pytest.mark.parametrize("version", VERSIONS)
def test_filled_lines_on_before_are_a_clause_a_row_with_arrows(version: str) -> None:
    """Filled lines, from a window's button: New layout, Line by line and
    Captions run on - all three back off, as the button turns them off."""
    stored = saved_by(version, "ja_chinese")
    assert stored["caption_lab"] == {"fill": "paired", "flow": True, "run_on": True}
    look = caption_look(AppSettings.from_stored(stored))
    assert look.lab == CaptionLab()
    assert look.word_links is WordLinks.ARROWS
    assert caption_style(look).arrows  # none while captions filled the width
    assert look_settings(look)["caption_lab"] == {}  # saved so at the next change


@pytest.mark.parametrize("version", VERSIONS)
def test_translation_below_before_is_a_clause_a_row(version: str) -> None:
    stored = saved_by(version, "en_chinese")
    assert stored["caption_lab"] == {"fill": "stacked"}
    assert caption_look(AppSettings.from_stored(stored)).lab.fill is Fill.CLAUSES


def test_the_rest_of_the_lab_is_kept() -> None:
    stored = {"fill": "paired", "join": "space", "aligned": True, "flow": True}
    lab = CaptionLab.from_stored({**stored, "run_on": True, "older": 0.6})
    # parts lined up keep New layout, which they need
    assert lab == CaptionLab(flow=True, aligned=True, older=0.6)
    assert lab.fill is Fill.CLAUSES and lab.join is Join.ELLIPSIS


def test_its_button_and_lab_rows_are_not_shown(qapp: QApplication) -> None:
    window = window_of(qapp, 0)
    MADE.append(window)
    # the strip has no Fill the width (its toggles went to the presets'
    # dropdown and Settings: polyglotic-hq 556), and the dropdown hasn't it
    assert "fill" not in window.buttons
    panel = LabPanel(LookView(CaptionLook()))
    MADE.append(panel)
    assert panel.fill_row.isHidden() and panel.join_row.isHidden()
    assert panel.run_on.isHidden()
    assert not panel.flow.isHidden() and not panel.aligned.isHidden()


def test_with_its_flag_on_the_pour_is_there(qapp: QApplication) -> None:
    flags.set_value(flags.FILL_THE_WIDTH, True)
    try:
        lab = CaptionLab.from_stored({"fill": "paired", "flow": True, "run_on": True})
        assert lab.filled
        panel = LabPanel(LookView(CaptionLook()))
        MADE.append(panel)
        assert not panel.fill_row.isHidden() and not panel.join_row.isHidden()
        assert not panel.run_on.isHidden()
    finally:
        flags.set_value(flags.FILL_THE_WIDTH, None)
