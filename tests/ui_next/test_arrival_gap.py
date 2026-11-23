"""The Lab's gap between new captions (polyglotic-hq 284; the user's live
testing, 270's FEEDBACK.md line 51: "If multiple lines land at the same
time ... Should separate them by 0.5 seconds at least"): captions arriving
together come into a window one at a time, the gap apart, in order,
nothing dropped - and none waits longer than the longest wait for text
(decision 0068)."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import finished_updates, live_update, withdrawn
from tests.ui_next.test_caption_window import window_of

from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.lab import CaptionLab
from polyglotic_desktop.ui_next.views.pacing import Pacing


class Clock:
    def __init__(self) -> None:
        self.now = 50.0

    def __call__(self) -> float:
        return self.now


def paced(qapp: QApplication, gap: float) -> tuple[CaptionWindow, Clock]:
    look = CaptionLook(arrival=Arrival.STEP, lab=CaptionLab(arrival_gap=gap))
    window = window_of(qapp, captions=2, look=look)
    clock = Clock()
    window.clock = clock
    return window, clock


def ids(window: CaptionWindow) -> list[str]:
    return [str(line.caption_id) for line in window.view.lines]


def test_captions_arriving_together_come_in_the_gap_apart_in_order(
    qapp: QApplication,
) -> None:
    window, clock = paced(qapp, 0.5)
    try:
        before = ids(window)
        burst = finished_updates(3, start=2)
        shown = [window.receive(update) for update in burst]
        assert shown == [True, False, False]  # the first at once
        assert ids(window) == [*before, "app-00002"]
        assert window._pace_timer.isActive()  # woken for the next
        clock.now += 0.3
        window._let_paced()
        assert ids(window)[-1] == "app-00002"  # not yet: 0.3 s of 0.5
        clock.now += 0.2
        window._let_paced()
        assert ids(window)[-1] == "app-00003"
        clock.now += 0.5
        window._let_paced()
        assert ids(window) == [*before, "app-00002", "app-00003", "app-00004"]
        assert not window._pace_timer.isActive() and not len(window.pacing)
    finally:
        window.close()


def test_without_a_gap_they_all_come_at_once(qapp: QApplication) -> None:
    """Today's: fails if the gap applied at 0."""
    window, _ = paced(qapp, 0.0)
    try:
        assert [window.receive(u) for u in finished_updates(3, start=2)] == [True] * 3
        assert ids(window)[-3:] == ["app-00002", "app-00003", "app-00004"]
    finally:
        window.close()


def test_a_waiting_captions_own_updates_come_after_it(qapp: QApplication) -> None:
    """A live update, then its finished caption, behind another new caption:
    the live one waits its turn, and the finished one follows it at once
    (it isn't a new caption) - in order, nothing dropped."""
    window, clock = paced(qapp, 1.0)
    try:
        (first,) = finished_updates(1, start=2)
        window.receive(first)
        live = live_update("app-later")
        finished = replace(finished_updates(1, start=3)[0], caption_id=live.caption_id)
        window.receive(live)
        window.receive(finished)
        assert "app-later" not in ids(window) and len(window.pacing) == 2
        clock.now += 1.0
        window._let_paced()
        assert ids(window)[-1] == "app-later"
        assert not window.view.lines[-1].live  # its finished caption came too
        assert not len(window.pacing)
    finally:
        window.close()


def test_updates_to_shown_captions_pass_while_nothing_waits(
    qapp: QApplication,
) -> None:
    window, _ = paced(qapp, 1.0)
    try:
        shown = ids(window)[-1]
        assert window.receive(withdrawn(shown))  # not new: at once
        assert shown not in ids(window)
        assert not len(window.pacing)
    finally:
        window.close()


def test_none_waits_longer_than_the_longest_wait_for_text(
    qapp: QApplication,
) -> None:
    """Decision 0068 wins when the two pull apart: a burst bigger than the
    wait over the gap is let in once each has waited the longest wait."""
    window, clock = paced(qapp, 1.5)
    window.longest_wait = 2.0
    try:
        for update in finished_updates(4, start=2):
            window.receive(update)
        clock.now += 1.5
        window._let_paced()  # the second, the gap after the first
        assert ids(window)[-1] == "app-00003"
        clock.now += 0.5  # 2 s since they came: the rest, closer than the gap
        window._let_paced()
        assert ids(window)[-1] == "app-00005" and not len(window.pacing)
    finally:
        window.close()


def test_the_mouse_still_holds_them_and_they_go_on_paced(
    qapp: QApplication,
) -> None:
    """Nothing moves under the mouse (109's rule): the view holds, and
    what arrives while it's on the words comes in the gap apart all the
    same - the mouse never holds a caption (583)."""
    window, clock = paced(qapp, 0.5)
    try:
        before = ids(window)
        window._hold()
        for update in finished_updates(2, start=2):
            window.receive(update)
        assert ids(window) == [*before, "app-00002"]
        clock.now += 0.5
        window._let_paced()
        assert ids(window)[-1] == "app-00003"
    finally:
        window.close()


def test_turning_the_gap_off_lets_the_waiting_in(qapp: QApplication) -> None:
    window, _ = paced(qapp, 1.0)
    try:
        for update in finished_updates(3, start=2):
            window.receive(update)
        assert len(window.pacing) == 2
        window.set_look(replace(window.look, lab=CaptionLab()))
        assert not len(window.pacing) and ids(window)[-1] == "app-00004"
    finally:
        window.close()


def test_another_sources_updates_never_wait_here(qapp: QApplication) -> None:
    window, _ = paced(qapp, 1.0)
    try:
        (other,) = finished_updates(1, source=MIC, start=9)
        assert window.receive(other) is False  # my speech isn't shown here
        assert not len(window.pacing)
        assert APP in window.view.sources
    finally:
        window.close()


def test_the_pacing_on_its_own() -> None:
    pacing = Pacing()
    first, second = finished_updates(2)
    pacing.add(first, 0.0)
    pacing.add(second, 0.0)

    def is_new(update: object) -> bool:
        return True

    assert pacing.next(0.0, 0.5, 3.0, is_new) is first
    assert pacing.next(0.0, 0.5, 3.0, is_new) is None
    assert pacing.wait_for(0.0, 0.5, 3.0) == pytest.approx(0.5)
    assert pacing.next(0.4999, 0.5, 3.0, is_new) is second  # a timer a hair early
    assert pacing.wait_for(1.0, 0.5, 3.0) is None


def test_the_window_lets_the_next_in_on_its_own_timer(qapp: QApplication) -> None:
    """With real time (no clock stepped): the second of two captions
    arriving together comes in on the window's own timer, the gap later."""
    import time

    look = CaptionLook(arrival=Arrival.STEP, lab=CaptionLab(arrival_gap=0.2))
    window = window_of(qapp, captions=2, look=look)
    try:
        for update in finished_updates(2, start=2):
            window.receive(update)
        assert ids(window)[-1] == "app-00002"
        until = time.monotonic() + 0.6
        while time.monotonic() < until and len(window.pacing):
            qapp.processEvents()
            time.sleep(0.01)
        assert ids(window)[-1] == "app-00003" and not len(window.pacing)
    finally:
        window.close()
