"""Older captions dim step by step, in the Lab (polyglotic-hq 305; the
user, 2026-11-13: "Lab option for gradual text colour change"): each
caption back from the newest a step dimmer, reaching Older captions' ink a
few captions back - by place, not time, so nothing is drawn more while
nothing arrives. Off (all at once, today's) by default. Offscreen,
made-up captions."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import finished_updates
from tests.ui_next.test_caption_window import window_of
from tests.ui_next.test_newest_line_brighter import _inks

from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.views.arrivals import OLDER_ALPHA, Arrival
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.lab import (
    OLDER_STEPS_RANGE,
    CaptionLab,
    by_place,
    ink_between,
)
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.presets import contrast_alpha


def test_five_steps_is_the_default() -> None:
    lab = CaptionLab()
    assert lab.older_steps == 5 and lab.to_stored() == {}
    assert [by_place(n, lab) for n in range(6)] == pytest.approx(
        [1.0, 0.8, 0.6, 0.4, 0.2, 0.0]
    )


def test_step_by_step_reaches_the_older_ink_that_many_captions_back() -> None:
    lab = CaptionLab(older_steps=3)
    steps = [by_place(n, lab) for n in range(5)]
    assert steps == pytest.approx([1.0, 2 / 3, 1 / 3, 0.0, 0.0])
    inks = [ink_between(OLDER_ALPHA, new) for new in steps]
    assert inks == sorted(inks, reverse=True) and inks[3] == OLDER_ALPHA


def test_it_is_kept_and_read_back_leniently() -> None:
    lab = CaptionLab(older_steps=4)
    assert CaptionLab.from_stored(lab.to_stored()) == lab
    for wrong in (0, OLDER_STEPS_RANGE[1] + 1, True, "3", 2.5):
        assert CaptionLab.from_stored({"older_steps": wrong}) == CaptionLab()


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    look = CaptionLook(lab=CaptionLab(older_steps=3), arrival=Arrival.STEP)
    shown = window_of(qapp, captions=8, look=look)
    shown.resize(960, 800)  # room for four captions or more
    qapp.processEvents()
    yield shown
    shown.close()
    shown.deleteLater()


def test_the_window_draws_each_caption_back_a_step_dimmer(
    window: CaptionWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawn = _inks(window, monkeypatch)
    keys = [line.key for line in window.view.lines if line.key in drawn]
    assert len(keys) >= 4
    alphas = [drawn[k].alpha for k in reversed(keys)]  # the newest first
    lab = window.look.lab
    ink = window._ink()
    assert ink.panel is not None
    floor = contrast_alpha(ink.original.name(), ink.panel, lab.older)
    wanted = [ink_between(floor, by_place(n, lab)) for n in range(len(keys))]
    assert alphas == pytest.approx(wanted)
    assert alphas[0] == 1.0 and alphas[3:] == [floor] * (len(alphas) - 3)
    # a new caption: each moves a place back, a step dimmer
    (new,) = finished_updates(1, start=50)
    window.view.apply(new)
    window.apply_changed(new_caption=True)
    after = _inks(window, monkeypatch)
    assert after[keys[-1]].alpha == pytest.approx(wanted[1])
    window.set_look(
        replace(window.look, lab=CaptionLab(new_for=0.0, older_steps=1))
    )  # all at once again
    today = _inks(window, monkeypatch)
    assert {today[k].alpha for k in today if k != window.view.lines[-1].key} == {
        contrast_alpha(
            today[next(iter(today))].original.name(), ink.panel, CaptionLab().older
        )
    }


class Paints(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() is QEvent.Type.Paint:
            self.count += 1
        return False


def test_nothing_is_drawn_while_nothing_arrives(
    window: CaptionWindow, qapp: QApplication
) -> None:
    """By place, not time: once a caption is in, the window sleeps - no
    timer, no paint - however long nothing comes (the interface thread's
    cost while nothing changes: none)."""
    import time

    window.canvas.repaint()
    paints = Paints()
    window.canvas.installEventFilter(paints)
    end = time.monotonic() + 1.0
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.02)
    window.canvas.removeEventFilter(paints)
    assert paints.count == 0
    assert not window.arriving


@pytest.fixture
def panel(qapp: QApplication) -> Iterator[LabPanel]:
    shown = LabPanel(LookView(CaptionLook()))
    yield shown
    shown.close()
    shiboken6.delete(shown)


def test_the_lab_card_moves_it_and_says_it(panel: LabPanel) -> None:
    assert panel.older_steps.shown.text() == "Over 5 captions"
    panel.older_steps.slider.setValue(2)  # 1, 2, 3: over 3 captions
    assert panel.view.value.lab.older_steps == 3
    assert panel.older_steps.shown.text() == "Over 3 captions"
    panel.reset.click()
    assert panel.view.value.lab.older_steps == 5
    assert panel.older_steps.shown.text() == "Over 5 captions"


def test_a_new_caption_step_by_step_within_its_budget(qapp: QApplication) -> None:
    """The places are worked out at each paint: a new caption among 150
    still within NEW_CAPTION, timed as the other budget tests are."""
    from tests.budget_judge import sampled, within

    from polyglotic_desktop.perf import budgets

    look = CaptionLook(lab=CaptionLab(older_steps=6), arrival=Arrival.STEP)
    window = window_of(qapp, captions=150, look=look)
    window.canvas.repaint()
    arriving = iter(finished_updates(40, start=150))

    def arrive() -> None:
        window.view.apply(next(arriving))
        window.apply_changed(new_caption=True)
        window.canvas.repaint()

    try:
        within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 10))
    finally:
        window.close()
        window.deleteLater()
