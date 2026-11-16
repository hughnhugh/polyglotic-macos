"""A new caption's lines arrive one at a time, in the Lab (polyglotic-hq
309; the user, 2026-11-14: a finished caption's rows "land together" -
"shown one after another a short moment apart ... never all together, and
never falling behind speech by more than the longest wait for text"):
poured lines and clause rows alike. Off by default: all together, as it
was. Offscreen, made-up captions, a made-up clock."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui_next.made_up import EN, finished_updates, live_update
from tests.ui_next.test_caption_window import window_of

import polyglotic_desktop.ui_next.caption_window as caption_window_module
from polyglotic_desktop.core.listening.captions import CaptionUpdate, Clause
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.ui.recorded_captions import APP
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout, CaptionStyle
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.captions import CaptionLines
from polyglotic_desktop.ui_next.views.lab import LINE_GAP_RANGE, CaptionLab, Fill
from polyglotic_desktop.ui_next.views.panels import LookView

MADE: list[QWidget] = []
GAP = 0.25


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


class Clock:
    def __init__(self) -> None:
        self.now = 50.0

    def __call__(self) -> float:
        return self.now


def paced(
    qapp: QApplication,
    gap: float = GAP,
    arrival: Arrival = Arrival.STEP,
    **lab: object,
) -> tuple[CaptionWindow, Clock]:
    look = CaptionLook(arrival=arrival, lab=CaptionLab(line_gap=gap, **lab))  # type: ignore[arg-type]
    window = window_of(qapp, captions=2, look=look)
    MADE.append(window)
    clock = Clock()
    window.clock = clock
    window.canvas.repaint()
    return window, clock


def three_clauses(caption_id: str = "long") -> CaptionUpdate:
    """A finished caption of three translated clauses: six rows."""
    clauses = (
        Clause("我的电脑又卡了，", {EN: "My computer froze again,"}),
        Clause("我得重新启动，", {EN: "I have to restart it,"}),
        Clause("等我一下。", {EN: "wait for me."}),
    )
    return replace(
        finished_updates(1, start=9)[0],
        caption_id=CaptionId(caption_id),
        clauses=clauses,
    )


def shown_of(window: CaptionWindow, caption_id: str) -> tuple[float, float] | None:
    """(the height of caption `caption_id` drawn now, its whole height) -
    None if none of it is drawn."""
    window.canvas.repaint()
    for line, laid, rect in window.canvas.placed:
        if str(line.caption_id) == caption_id:
            return rect.height(), laid.height
    return None


def breaks_of(window: CaptionWindow, caption_id: str) -> tuple[float, ...]:
    line = next(ln for ln in window.view.lines if str(ln.caption_id) == caption_id)
    return window.canvas._laid(line).breaks


# -- where a caption's lines end ----------------------------------------------------


@pytest.mark.parametrize("fill", list(Fill))
@pytest.mark.parametrize("width", [180, 420, 900])
def test_a_laid_caption_says_where_each_of_its_lines_ends(
    qapp: QApplication, fill: Fill, width: int
) -> None:
    view = CaptionLines((APP,), EN, keep=10)
    view.apply(three_clauses())
    laid = CaptionLayout(CaptionStyle(fill=fill)).laid(view.lines[0], width, 1.0)
    tops = set()
    for row in laid.rows:
        for n in range(row.layout.lineCount()):
            text_line = row.layout.lineAt(n)  # by its baseline: pieces of two
            # rows on a poured line share it, whatever their fonts' ascents
            tops.add(round(row.top + text_line.y() + text_line.ascent()))
    assert len(laid.breaks) == len(tops)  # one for each line of text across it
    assert list(laid.breaks) == sorted(set(laid.breaks))
    assert laid.breaks[-1] == laid.height
    for top, end in zip(sorted(tops), laid.breaks, strict=True):
        assert top < end


# -- off by default -----------------------------------------------------------------


def test_without_a_gap_a_captions_lines_come_together(qapp: QApplication) -> None:
    """Today's: fails if lines were held back at 0."""
    assert CaptionLab().line_gap == 0.0
    window, _ = paced(qapp, 0.0)
    assert window.receive(three_clauses())
    drawn = shown_of(window, "long")
    assert drawn is not None and drawn[0] == drawn[1]
    assert not window.reveal.pending and not window._reveal_timer.isActive()


def test_the_gap_is_saved_and_read_back_within_its_range() -> None:
    assert CaptionLab(line_gap=0.3).to_stored() == {"line_gap": 0.3}
    assert CaptionLab.from_stored({"line_gap": 0.3}).line_gap == 0.3
    assert CaptionLab.from_stored({"line_gap": 9}).line_gap == 0.0  # out of range
    assert CaptionLab.from_stored({"line_gap": "soon"}).line_gap == 0.0


# -- one at a time ------------------------------------------------------------------


@pytest.mark.parametrize("fill", list(Fill))
def test_a_new_captions_lines_come_one_at_a_time_the_gap_apart(
    qapp: QApplication, fill: Fill
) -> None:
    """Its first line at once - no later than today - then one each gap,
    in clause rows and poured alike; nothing of a line still to come is
    drawn, and nothing is below the window's bottom edge."""
    window, clock = paced(qapp, fill=fill)
    window.resize(300, window.height())
    qapp.processEvents()
    assert window.receive(three_clauses())
    breaks = breaks_of(window, "long")
    assert len(breaks) >= 4
    bottom = window.canvas.height() - caption_window_module.PAD
    for n, end in enumerate(breaks):
        drawn = shown_of(window, "long")
        assert drawn is not None
        assert abs(drawn[0] - end) < 0.01, n  # its first n + 1 lines, no more
        _, _, rect = window.canvas.placed[-1]
        assert rect.bottom() <= bottom + 0.5  # the newest line at the bottom edge
        if n + 1 < len(breaks):
            assert window._reveal_timer.isActive()
            clock.now += GAP / 2
            window._show_next_line()
            again = shown_of(window, "long")
            assert again is not None and abs(again[0] - end) < 0.01  # not yet
            clock.now += GAP / 2
            window._show_next_line()
    assert not window.reveal.pending and not window._reveal_timer.isActive()


def test_a_word_on_a_line_still_to_come_is_not_under_the_mouse(
    qapp: QApplication,
) -> None:
    window, _ = paced(qapp)
    window.receive(three_clauses())
    window.canvas.repaint()
    _, laid, rect = window.canvas.placed[-1]
    assert len(laid.rows) == 6 and rect.height() < laid.height
    first = window.canvas.hit(QPointF(rect.x() + 8, rect.y() + laid.rows[0].top + 6))
    assert first is not None and first[1].index == 0
    for y in range(int(rect.bottom()) + 1, window.canvas.height()):
        assert window.canvas.hit(QPointF(rect.x() + 8, float(y))) is None


def test_captions_arriving_together_show_oldest_first(qapp: QApplication) -> None:
    window, clock = paced(qapp)
    window.receive(three_clauses("one"))
    window.receive(three_clauses("two"))
    assert shown_of(window, "one") is not None
    assert shown_of(window, "two") is None  # none of its lines yet: not there
    for _ in range(len(breaks_of(window, "one")) - 1):
        assert shown_of(window, "two") is None
        clock.now += GAP
        window._show_next_line()
    one = shown_of(window, "one")
    assert one is not None and one[0] == one[1]
    clock.now += GAP
    window._show_next_line()
    two = shown_of(window, "two")
    assert two is not None and abs(two[0] - breaks_of(window, "two")[0]) < 0.01


def test_no_line_waits_longer_than_the_longest_wait_for_text(
    qapp: QApplication,
) -> None:
    """Decision 0068's bound wins over the gap."""
    window, clock = paced(qapp, 0.5)
    window.longest_wait = 0.6
    window.receive(three_clauses("one"))
    window.receive(three_clauses("two"))
    clock.now += 0.6
    window._show_next_line()
    for name in ("one", "two"):
        drawn = shown_of(window, name)
        assert drawn is not None and drawn[0] == drawn[1]
    assert not window.reveal.pending and not window._reveal_timer.isActive()


def test_a_caption_already_there_shows_what_it_gains_at_once(
    qapp: QApplication,
) -> None:
    """Live text wrapping onto its next line, a translation arriving
    under its clause: as today - holding back its last line would take
    away text that was there."""
    window, clock = paced(qapp)
    live = live_update("growing")
    window.receive(live)
    while window.reveal.pending:
        clock.now += GAP
        window._show_next_line()
    clock.now += 0.01  # within the gap of the last line shown
    window.receive(replace(three_clauses("growing"), kind=live.kind))
    drawn = shown_of(window, "growing")
    assert drawn is not None and drawn[0] == drawn[1]
    assert len(breaks_of(window, "growing")) == 6 and not window.reveal.pending


# -- everything at once -------------------------------------------------------------


def test_the_mouse_over_the_window_shows_every_line_and_none_comes_under_it(
    qapp: QApplication,
) -> None:
    window, clock = paced(qapp)
    window.receive(three_clauses())
    window._hold()
    drawn = shown_of(window, "long")
    assert drawn is not None and drawn[0] == drawn[1]
    assert not window._reveal_timer.isActive()
    before = [rect.top() for _, _, rect in window.canvas.placed]
    clock.now += 5.0
    window._show_next_line()
    window.canvas.repaint()
    assert [rect.top() for _, _, rect in window.canvas.placed] == before


def test_a_resize_and_scrolling_back_show_every_line(qapp: QApplication) -> None:
    window, _ = paced(qapp)
    window.receive(three_clauses())
    window.resize(window.width() - 60, window.height())
    qapp.processEvents()
    drawn = shown_of(window, "long")
    assert drawn is not None and drawn[0] == drawn[1]
    window.receive(three_clauses("next"))
    assert window.reveal.pending
    window.canvas.scroll_by(40.0)
    assert not window.view.scroll.following
    drawn = shown_of(window, "next")
    assert drawn is None or drawn[0] == drawn[1]  # whole, if in view at all
    window._show_next_line()
    assert not window.reveal.pending


def test_the_labs_gap_reaches_running_windows(qapp: QApplication) -> None:
    window, _ = paced(qapp, 0.0)
    panel = LabPanel(LookView(window.look, window.set_look))
    MADE.append(panel)
    panel.line_gap.slider.setValue(panel.line_gap.slider.maximum())
    assert window.look.lab.line_gap == LINE_GAP_RANGE[1]
    window.receive(three_clauses())
    assert window.reveal.pending
    panel.line_gap.slider.setValue(0)  # off again: what waited is there
    drawn = shown_of(window, "long")
    assert drawn is not None and drawn[0] == drawn[1] and not window.reveal.pending


# -- the slide ----------------------------------------------------------------------


def test_each_line_that_comes_slides_the_text_above_up(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step and slide: a line coming in is an arrival like a caption's -
    the text above keeps its place for the first frame and rises."""
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: False)
    window, clock = paced(qapp, arrival=Arrival.STEP_AND_SLIDE)
    if not window.sliding:
        pytest.skip("the lab's photographs: nothing slides")
    window.receive(three_clauses())
    window.canvas.repaint()
    clock.now += 2.0  # the first line's slide at rest
    window.canvas.repaint()
    assert not window.arriving
    key = window.canvas.placed[-2][0].key  # the caption before the new one

    def top() -> float:
        window.canvas.repaint()
        return next(r.top() for ln, _, r in window.canvas.placed if ln.key == key)

    older = top()
    window._show_next_line()
    assert window.arriving and window.motion.offset(clock.now) > 1.0
    assert abs(top() - older) < 1.0  # where it was, for the first frame
    clock.now += 2.0
    assert top() < older - 1.0  # risen by the line that came
