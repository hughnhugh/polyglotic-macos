"""Parts lined up in every way of filling, and in one click on the caption
window (polyglotic-hq 372; the user, 2026-11-15, DECISIONS #175: "the
parts lined up feature should be an independent one click setting which
applies to every mode"). The fixed-pitch fonts of `test_flow`."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.test_caption_window import MIC as WINDOW_MIC
from tests.ui_next.test_caption_window import Store, areas, window_of
from tests.ui_next.test_flow import (
    ALL,
    CROSSED,
    MEANT,
    SAID,
    Pitch,
    models,
    one,
)
from tests.ui_next.test_joined_window import THREE

from polyglotic_desktop.core.listening.caption_model import CaptionModel
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.ui.recorded_captions import (
    COMPUTER,
    CONTROLS,
    GAME,
    RESTART,
    clause,
    finished,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.glyphs import Glyph
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.flow import (
    Cut,
    Flow,
    Flowed,
    FlowOptions,
    flow_options,
)
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill
from polyglotic_desktop.ui_next.views.panels import LookView

ROWS_LINED = FlowOptions(aligned=True)
BELOW_LINED = FlowOptions(Cut.CAPTION, aligned=True)
PAIRED_LINED = FlowOptions(share=True, split=True, aligned=True)
EVERY_WAY = (ROWS_LINED, BELOW_LINED, PAIRED_LINED)
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each window deleted when its test ends (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


def drawn_at(
    captions: list[CaptionModel], flowed: Flowed, caption: int, side: RowKind
) -> dict[tuple[int, int], tuple[int, float]]:
    """Each character of `side` in `caption`, by (clause, character): the
    line it is on - counted among that side's lines in its pair, so the
    k-th line of what was said faces the k-th of its translation - and the
    x it is drawn at."""
    found: dict[tuple[int, int], tuple[int, float]] = {}
    count: dict[tuple[int, RowKind], int] = {}
    pitch = Pitch()
    for line in flowed.lines:
        n = count.get((line.pair, line.side), 0)
        count[(line.pair, line.side)] = n + 1
        for run in line.runs:
            if run.caption != caption or run.words.side is not side:
                continue
            text = captions[caption].clauses[run.words.clause].text(side)
            for char in range(run.words.start, run.words.end):
                x = run.x + pitch.width(text[run.words.start : char])
                found[(run.words.clause, char)] = (line.pair * 100 + n, x)
    return found


def first_drawn(text: str, start: int, end: int) -> int | None:
    """The first character of `text[start:end]` that isn't a space."""
    return next((n for n in range(start, end) if not text[n].isspace()), None)


def lined_parts(captions: list[CaptionModel], flowed: Flowed) -> tuple[int, int]:
    """How many parts start at their counterpart's place on the facing
    line, and how many parts there are that could."""
    lined = total = 0
    for n, caption in enumerate(captions):
        said = drawn_at(captions, flowed, n, SAID)
        meant = drawn_at(captions, flowed, n, MEANT)
        for c, part in enumerate(caption.clauses):
            for (a, b), (p, q) in part.parts:
                start_said = first_drawn(part.original, a, b)
                start_meant = first_drawn(part.translation or "", p, q)
                if start_said is None or start_meant is None:
                    continue
                total += 1
                line_a, x_a = said[(c, start_said)]
                line_b, x_b = meant[(c, start_meant)]
                if line_a == line_b and abs(x_a - x_b) < 0.5:
                    lined += 1
    return lined, total


@pytest.mark.parametrize("options", EVERY_WAY, ids=["rows", "below", "line by line"])
@pytest.mark.parametrize("width", [600, 900, 1400])
def test_each_part_starts_where_its_counterpart_does(
    options: FlowOptions, width: int
) -> None:
    captions = models(finished("a", GAME, CONTROLS), finished("b", CROSSED, COMPUTER))
    lined, total = lined_parts(
        captions, Flow(Pitch()).compose(captions, width, options)
    )
    assert total >= 8 and lined == total


@pytest.mark.parametrize("fill", list(Fill))
def test_without_lined_up_parts_are_not_lined_up(fill: Fill) -> None:
    """What the option changes: the same captions, laid out without it,
    have parts away from their counterparts."""
    captions = models(finished("a", GAME, CONTROLS), finished("b", CROSSED, COMPUTER))
    plain = Flow(Pitch()).compose(captions, 900, flow_options(fill))
    lined, total = lined_parts(captions, plain)
    assert lined < total


def test_a_clause_a_row_keeps_each_clause_on_pairs_of_its_own() -> None:
    captions = one(GAME, CONTROLS, COMPUTER, RESTART)
    flowed = Flow(Pitch()).compose(captions, 900, ROWS_LINED)
    clauses_in: dict[int, set[int]] = {}
    for line in flowed.lines:
        for run in line.runs:
            clauses_in.setdefault(line.pair, set()).add(run.words.clause)
    assert all(len(found) == 1 for found in clauses_in.values())
    assert all(not line.joins for line in flowed.lines)  # no joins in rows


def test_a_long_clause_a_row_goes_on_at_its_parts_not_side_by_side() -> None:
    """Without lining up, a clause wider than the window wraps what was
    said over lines, then its translation; lined up, each pair holds
    parts and their counterparts."""
    captions = one(CROSSED)
    flowed = Flow(Pitch()).compose(captions, 300, ROWS_LINED)
    sides = [line.side for line in flowed.lines]
    assert sides[:4] == [SAID, MEANT, SAID, MEANT]
    lined, total = lined_parts(captions, flowed)
    assert lined == total


def test_translation_below_keeps_what_was_said_above_its_translation() -> None:
    captions = models(finished("a", *ALL[:4]), finished("b", CROSSED))
    flowed = Flow(Pitch()).compose(captions, 500, BELOW_LINED)
    for caption in range(len(captions)):
        sides = [
            line.side
            for line in flowed.lines
            if any(run.caption == caption for run in line.runs)
        ]
        assert sides == sorted(sides, key=lambda side: side is not SAID)
        assert sides.count(SAID) == sides.count(MEANT) >= 2
    # one block a caption: the gap between captions is the pair gap
    assert len({line.pair for line in flowed.lines}) == len(captions)


def test_a_part_wider_than_the_line_is_cut_on_both_sides_in_step() -> None:
    """Where a mode can't line up honestly: a stretch with no place both
    sides can be cut, wider than the window. It is cut as Line by line cuts
    a clause, both sides, so the lines stay in step - a line of what was
    said, the line of its translation - and each piece starts lined up."""
    unlinked = clause(
        "这是一个很长很长的没有任何词语对应的句子，",
        "this is a very long sentence with no word links at all in it,",
    )
    captions = one(unlinked)
    rows = Flow(Pitch()).compose(captions, 200, ROWS_LINED)
    sides = [line.side for line in rows.lines]
    assert len(sides) >= 4 and sides == [SAID, MEANT] * (len(sides) // 2)
    below = Flow(Pitch()).compose(captions, 200, BELOW_LINED)
    sides = [line.side for line in below.lines]
    assert sides == sorted(sides, key=lambda side: side is not SAID)
    assert sides.count(SAID) == sides.count(MEANT) >= 2


def test_the_lab_lines_parts_up_in_every_way() -> None:
    for fill in Fill:
        assert flow_options(fill, aligned=True).aligned
        assert not flow_options(fill).aligned


# -- the choice: the Lab's value, and one click on the window ------------------------


def test_lined_up_needs_new_layout_alone() -> None:
    for fill in Fill:
        lab = CaptionLab(fill=fill)
        on = lab.with_lined_up(True)
        assert on == replace(lab, flow=True, aligned=True) and on.lined_up
        assert lab.choose(aligned=True) == on  # the Lab's row: the same
        assert on.with_lined_up(False, lab) == lab  # off: back to what was there


def test_lined_up_off_keeps_what_the_other_click_needs() -> None:
    lined = CaptionLab().with_lined_up(True)
    filled = lined.with_filled(True)
    # fill off: New layout stays, parts are still lined up
    assert filled.with_filled(False, lined) == lined
    # lined up off while filled: New layout stays for the filled lines
    assert filled.with_lined_up(False, CaptionLab()) == replace(filled, aligned=False)
    # not known (turned on in the Lab, or a restart): New layout as it is
    assert lined.with_lined_up(False) == CaptionLab(flow=True)


def test_the_look_remembers_what_lined_up_turned_on() -> None:
    view = LookView(CaptionLook(lab=CaptionLab(fill=Fill.STACKED)))
    view.set_lined_up(True)
    assert view.value.lab == CaptionLab(fill=Fill.STACKED, flow=True, aligned=True)
    view.set_lined_up(False)
    assert view.value.lab == CaptionLab(fill=Fill.STACKED)
    assert view.unlined is None


def test_the_button_shows_and_asks(qapp: QApplication) -> None:
    window = window_of(qapp)
    MADE.append(window)
    button = window.buttons["aligned"]
    assert window.glyphs["aligned"] is Glyph.ALIGNED
    assert not window.controls["aligned"].icon().isNull()
    said = QAccessible.queryAccessibleInterface(button)
    assert said.text(QAccessible.Text.Name) == "Line up the parts"
    assert "every window" in button.toolTip()
    assert not button.isChecked()
    asked: list[bool] = []
    window.aligned_wanted.connect(asked.append)
    button.click()
    assert asked == [True]
    window.set_look(replace(window.look, lab=CaptionLab(flow=True, aligned=True)))
    assert button.isChecked()
    window.set_look(replace(window.look, lab=CaptionLab(aligned=True)))
    assert not button.isChecked()  # without New layout it does nothing


def test_every_window_and_the_lab_agree(qapp: QApplication) -> None:
    windows = CaptionWindows(Store({"targets": ["en"]}), WINDOW_MIC, areas)
    windows.set_labels(
        {source: SourceLabel(name, "#4dd0e1") for name, source in THREE}, "You"
    )
    look = LookView(CaptionLook(), on_change=windows.set_look)
    windows.aligned_wanted.connect(look.set_lined_up)
    panel = LabPanel(look)
    MADE.append(panel)
    windows.set_captioned(THREE[:2])
    first, second = windows.windows.values()
    try:
        first.buttons["aligned"].click()
        assert look.value.lab == CaptionLab(flow=True, aligned=True)
        assert second.buttons["aligned"].isChecked()
        panel.refresh()
        assert panel.aligned.switch.isChecked() and panel.flow.switch.isChecked()
        assert panel.fill.value() is Fill.CLAUSES  # however captions fill
        panel.aligned.switch.click()
        assert not first.buttons["aligned"].isChecked()
    finally:
        windows.close()
