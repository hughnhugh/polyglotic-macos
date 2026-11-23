"""How a new caption arrives: step and slide (D), with the step (B) as its
form with no motion - polyglotic-hq DECISIONS.md #104 (the user,
2026-11-09), from 253's prototypes; built in 267.

The rules are plain Python (`views.arrivals`); the window's tests step its
own clock (`CaptionWindow.clock`) and read where its last paint drew each
line (`Canvas.placed`) or photograph it (`grab`), never the screen."""

from collections.abc import Iterator
from dataclasses import replace
from itertools import pairwise

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import finished_updates
from tests.ui_next.test_caption_window import _on_words, areas, window_of

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import ARRIVALS, AppSettings
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.arrivals import (
    ENTRY_GAP_PX,
    SLIDE_MAX_SEC,
    SLIDE_MIN_SEC,
    SLIDE_SEC,
    Arrival,
    Motion,
    effective,
    pace_of,
    slide_seconds,
)
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.cards import GLIDE_FASTEST

# -- the rules ---------------------------------------------------------------------------


def test_step_and_slide_is_the_default_and_the_step_its_form_without_motion() -> None:
    assert CaptionLook().arrival is Arrival.STEP_AND_SLIDE
    assert effective(Arrival.STEP_AND_SLIDE, reduced_motion=False).slides
    assert effective(Arrival.STEP_AND_SLIDE, reduced_motion=True) is Arrival.STEP
    assert not Arrival.STEP.slides


def test_the_pace_comes_from_the_session_not_the_text() -> None:
    """Captions coming quicker slide quicker; speech still under way as one
    lands, quicker again (the next is on its way); the first one at the
    typical pace."""
    assert pace_of(None, speaking=False) == 1.0
    assert pace_of(1.0, speaking=False) > pace_of(2.5, speaking=False) == 1.0
    assert pace_of(5.0, speaking=False) < 1.0
    assert pace_of(2.5, speaking=True) > pace_of(2.5, speaking=False)
    assert 0.5 <= pace_of(0.01, speaking=True) <= 2.5  # within what can be read
    assert 0.5 <= pace_of(600.0, speaking=False) <= 2.5


def test_a_slide_takes_0_22_to_0_9_seconds_by_the_pace() -> None:
    assert slide_seconds(1.0) == SLIDE_SEC
    assert slide_seconds(2.5) == pytest.approx(SLIDE_MIN_SEC) == 0.22
    assert slide_seconds(0.5) == pytest.approx(SLIDE_MAX_SEC) == 0.9
    assert slide_seconds(2.0) < slide_seconds(1.0) < slide_seconds(0.7)


def test_the_stack_eases_to_rest_and_a_new_line_closes_its_gap() -> None:
    motion = Motion()
    motion.start(10.0, risen_px=60.0, new={7}, seconds=0.5, most_px=300.0)
    assert motion.offset(10.0) == 60.0 and motion.entry(7, 10.0) == 1.0
    halfway = motion.offset(10.25)
    assert halfway == pytest.approx(30.0)  # the stack eases into and out of motion
    assert 0.0 < motion.entry(7, 10.25) < 0.5
    assert motion.moving(10.49)
    assert motion.offset(10.5) == 0.0 and motion.entry(7, 10.5) == 0.0
    assert not motion.moving(10.5)
    assert motion.slide is None and not motion.entries


def test_a_tall_instant_arrival_moves_at_a_readable_speed_and_clears_the_foot() -> None:
    # The 643 Everyday film: older text rose 140 px while the incoming
    # translation crossed the foot of the panel, then settled 2 px inside.
    motion = Motion()
    motion.start(0.0, risen_px=140.0, new={5}, seconds=0.9, most_px=420)
    offsets = [
        motion.offset(t / 1000) + ENTRY_GAP_PX * motion.entry(5, t / 1000)
        for t in range(1001)
    ]
    assert max((a - b) * 1000 for a, b in pairwise(offsets)) <= GLIDE_FASTEST.value
    # From first visible ink at the window edge to a fully readable row.
    assert sum(2 < px < 44 for px in offsets) < 300


def test_a_caption_mid_slide_carries_on_from_where_the_text_is() -> None:
    motion = Motion()
    motion.start(0.0, risen_px=60.0, new={1}, seconds=0.5, most_px=300.0)
    left = motion.offset(0.2)
    motion.start(0.2, risen_px=40.0, new={2}, seconds=0.5, most_px=300.0)
    assert motion.offset(0.2) == pytest.approx(40.0 + left)


def test_a_burst_of_captions_too_much_to_follow_is_at_rest_at_once() -> None:
    """Captions arriving faster than they're painted (a burst after a
    stall) mustn't pile up a slide from far below the window."""
    motion = Motion()
    for n in range(20):
        motion.start(0.0, risen_px=60.0, new={n}, seconds=0.5, most_px=300.0)
        assert motion.offset(0.0) <= 300.0
    assert motion.offset(0.0) < 300.0 and len(motion.entries) < 20


# -- in the window -----------------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def opened(
    qapp: QApplication, clock: Clock, captions: int = 8, **kwargs: object
) -> CaptionWindow:
    window = window_of(qapp, captions=captions, **kwargs)  # type: ignore[arg-type]
    window.clock = clock
    window.canvas.repaint()  # what the learner sees: an arrival measures from it
    return window


def arrive(window: CaptionWindow, n: int = 0) -> int:
    """The next finished caption arrives; its key."""
    (update,) = finished_updates(1, start=100 + n)
    window.view.apply(update)
    window.apply_changed(new_caption=True)
    return window.view.lines[-1].key


def tops(window: CaptionWindow) -> dict[int, float]:
    """Each line's top as the window draws it now, on the screen."""
    window.canvas.repaint()
    top = window.canvas.mapToGlobal(window.canvas.rect().topLeft()).y()
    return {line.key: top + rect.top() for line, _, rect in window.canvas.placed}


@pytest.fixture(
    params=[1.0, 0.5, 2.0],
    ids=["translation-100", "translation-50", "translation-200"],
)
def window(
    qapp: QApplication, clock: Clock, request: pytest.FixtureRequest
) -> Iterator[CaptionWindow]:
    """At a translation the size of what was said, at half of it and at
    twice it (polyglotic-hq 305): every slide and step holds at each."""
    shown = opened(qapp, clock, translation_size=request.param)
    if request.param > 1.0:  # taller: still two captions or more in view
        shown.resize(shown.width(), 460)
        qapp.processEvents()
        shown.canvas.repaint()
    yield shown
    shown.close()


def test_list_arrival_keeps_text_still_visible_above_its_resting_page(
    qapp: QApplication, clock: Clock
) -> None:
    window = opened(qapp, clock)
    try:
        window.resize(1000, 420)
        qapp.processEvents()
        window.canvas.repaint()
        canvas = window.canvas
        lines = canvas.lines_in_view()
        at_rest = window.view.scroll.placed(
            lines, canvas._height, canvas._view_height(), canvas._gap()
        )
        first = next(
            i for i, line in enumerate(lines) if line.key == at_rest[0].line.key
        )
        assert first > 0
        previous = lines[first - 1]
        # As in the 116 s recording, a whole earlier caption still fits
        # above the page while the stack is one caption below its destination.
        offset = canvas._height(previous) + canvas._gap() - at_rest[0].top
        window.motion.start(
            clock.now, offset, set(), SLIDE_MAX_SEC, most_px=window.height()
        )
        assert previous.key in tops(window)
    finally:
        window.close()


def test_nothing_jumps_the_text_rises_into_place_and_the_new_caption_follows(
    window: CaptionWindow, clock: Clock
) -> None:
    before = tops(window)
    key = arrive(window)
    first = tops(window)
    kept = before.keys() & first.keys()
    assert len(kept) >= 2
    assert all(first[k] == pytest.approx(before[k]) for k in kept)  # no jump
    newest = max(before)
    gap = first[key] - first[newest]
    clock.now += 0.15
    moving = tops(window)
    visible = kept & moving.keys()
    assert visible and all(moving[k] < first[k] for k in visible)
    # A line still visible at the start may now have left through the top.
    assert all(k < min(visible) for k in kept - visible)
    assert moving[key] - moving[newest] < gap  # closing on the line above
    clock.now += SLIDE_MAX_SEC
    rest = tops(window)
    risen = {round(before[k] - rest[k], 3) for k in kept & rest.keys()}
    assert len(risen) == 1 and risen.pop() > 0  # all by the same, to rest
    assert rest[key] - rest[newest] == pytest.approx(gap - ENTRY_GAP_PX, abs=0.01)


def test_editing_an_earlier_original_does_not_restart_the_arrival_slide(
    qapp: QApplication, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: False)
    window = opened(qapp, clock, captions=0)
    try:
        window.resize(760, 420)
        window.set_language("")
        first, second, third = [
            replace(update, clauses=(Clause("A short caption."),))
            for update in finished_updates(3)
        ]
        assert window.receive(first)
        assert window.receive(second)
        clock.now += SLIDE_MAX_SEC
        tops(window)
        edited = window.view.lines[-1].key
        assert window.receive(third)
        slide = window.motion.slide
        assert slide is not None
        clock.now += slide.seconds / 2
        before = tops(window)
        newest = window.view.lines[-1].key
        revision = replace(second, clauses=(Clause("Some more words. " * 11),))
        assert window.receive(revision)
        after = tops(window)
        assert after[edited] < before[edited]
        assert after[newest] == pytest.approx(before[newest])
        assert window.motion.slide is slide
        clock.now += SLIDE_MAX_SEC
        assert not window.arriving
        before = tops(window)
        assert window.receive(second)  # the original shrinks in place again
        after = tops(window)
        assert after[edited] > before[edited]
        assert after[newest] == pytest.approx(before[newest])
        assert not window.arriving

        foot = window.canvas.placed[-1][2].bottom()
        assert window.receive(replace(revision, caption_id=third.caption_id))
        expanded = tops(window)
        assert expanded[newest] < after[newest]
        assert window.canvas.placed[-1][2].bottom() == pytest.approx(foot)
        assert not window.arriving
    finally:
        window.close()


def test_scrolled_back_caption_window_stays_held_when_an_original_shrinks(
    qapp: QApplication, clock: Clock
) -> None:
    window = opened(qapp, clock, captions=0)
    try:
        window.resize(760, 300)
        window.set_language("")
        first, second = [
            replace(update, clauses=(Clause("A short caption."),))
            for update in finished_updates(2)
        ]
        long_second = replace(second, clauses=(Clause("Some more words. " * 80),))
        assert window.receive(first)
        assert window.receive(long_second)
        clock.now += SLIDE_MAX_SEC
        tops(window)
        window.canvas.scroll_by(1000)
        held = window.view.scroll.anchor
        assert held is not None and held.key == window.view.lines[0].key
        before = tops(window)
        assert window.receive(second)
        after = tops(window)
        assert window.view.scroll.anchor == held
        assert after[held.key] == pytest.approx(before[held.key])
        window.canvas.scroll_by(-1000)
        assert window.view.scroll.following
    finally:
        window.close()


def test_the_frame_timer_runs_while_it_slides_and_stops_at_rest(
    window: CaptionWindow, clock: Clock
) -> None:
    arrive(window)
    assert window.arriving and window._tick_timer.isActive()
    clock.now += SLIDE_MAX_SEC
    window._tick()
    assert not window.arriving and not window._tick_timer.isActive()


def test_a_slide_ends_painted_at_rest_however_late_its_last_frame(
    qapp: QApplication, window: CaptionWindow, clock: Clock
) -> None:
    """The user's "translation often gets cut off at the bottom" (polyglotic-hq
    272): a slow paint made the frame timer's ticks late, the last frame
    painted was mid-slide - the newest caption's last rows still below the
    clip - and the tick that found the slide over painted nothing more."""
    arrive(window)
    clock.now += 0.1
    window._tick()
    qapp.processEvents()  # a frame mid-slide
    canvas = window.canvas
    clip = canvas.height() - PAD
    assert canvas.placed[-1][2].bottom() > clip + 1  # still rising into view
    clock.now += SLIDE_MAX_SEC  # the next tick comes late: the slide is over
    window._tick()
    qapp.processEvents()
    assert canvas.placed[-1][2].bottom() <= clip + 0.5  # the last row whole


def test_captions_coming_faster_slide_faster(
    window: CaptionWindow, clock: Clock
) -> None:
    arrive(window, 0)  # the first since it opened: the typical pace
    assert window.motion.slide is not None
    assert window.motion.slide.seconds == SLIDE_SEC
    clock.now += 0.8
    arrive(window, 1)
    assert window.motion.slide.seconds == pytest.approx(SLIDE_MIN_SEC)
    clock.now += 6.0
    arrive(window, 2)
    assert window.motion.slide.seconds == pytest.approx(SLIDE_MAX_SEC)
    window.speaking = True  # the next one already being said
    clock.now += 2.5
    arrive(window, 3)
    assert window.motion.slide.seconds < SLIDE_SEC


def test_the_session_says_when_speech_is_under_way(qapp: QApplication) -> None:
    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_captioned([("a", APP)])
        shown = windows.windows["a"]
        windows.heard([APP])
        assert shown.speaking
        windows.heard([])
        assert not shown.speaking and shown.listening  # its caption on its way
    finally:
        windows.close()


def test_scrolled_back_nothing_slides(window: CaptionWindow) -> None:
    window.canvas.scroll_by(300)
    before = tops(window)
    arrive(window)
    assert not window.arriving
    assert tops(window) == before


def test_the_lab_s_photographs_are_at_rest(window: CaptionWindow) -> None:
    window.always_shown = True
    arrive(window)
    assert not window.arriving


def test_a_preview_line_fills_its_translation_space_without_another_slide(
    qapp: QApplication, clock: Clock
) -> None:
    """Quick Preview's finished caption fills the slot left by its preview."""
    window = opened(qapp, clock, look=CaptionLook(preview=True))
    try:
        window.resize(1000, 420)
        french = Language("fr")
        finished = CaptionUpdate(
            CaptionId("quick-preview"),
            APP,
            CaptionKind.FINISHED,
            (Clause("Bonjour.", {Language("en"): "Hello."}),),
            french,
            (french,),
        )
        heard = replace(finished, kind=CaptionKind.LIVE, clauses=(Clause("Bonjour."),))
        window.view.apply(heard)
        window.apply_changed(new_caption=True)
        clock.now += SLIDE_MAX_SEC
        before = tops(window)
        key = window.view.lines[-1].key
        assert key in before and len(before) > 1

        window.view.apply(finished)
        window.apply_changed(new_caption=True)
        assert tops(window) == pytest.approx(before)
        assert not window.arriving
        (laid,) = (laid for line, laid, _ in window.canvas.placed if line.key == key)
        assert any(row.row.kind is RowKind.TRANSLATION for row in laid.rows)
    finally:
        window.close()


def test_with_animations_off_it_is_the_step_pixel_for_pixel(
    qapp: QApplication,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows' animation effects off (Qt's motion preference, as 260's
    listening mark reads it): step and slide draws exactly what the step
    does, from the arrival's first frame."""
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: True)
    images = []
    for arrival in (Arrival.STEP_AND_SLIDE, Arrival.STEP):
        shown = opened(qapp, clock, look=CaptionLook(arrival=arrival))
        arrive(shown)
        assert not shown.arriving
        images.append(shown.canvas.grab().toImage())
        shown.close()
    assert images[0] == images[1]


def test_at_rest_it_looks_exactly_like_the_step(
    qapp: QApplication, clock: Clock
) -> None:
    images = []
    for arrival in (Arrival.STEP_AND_SLIDE, Arrival.STEP):
        shown = opened(qapp, clock, look=CaptionLook(arrival=arrival))
        arrive(shown)
        clock.now += SLIDE_MAX_SEC
        images.append(shown.canvas.grab().toImage())
        shown.close()
    assert images[0] == images[1]


def test_a_joined_window_s_columns_slide_too(qapp: QApplication, clock: Clock) -> None:
    windows = CaptionWindows(None, MIC, areas)
    try:
        windows.set_captioned([("a", APP), ("b", MIC)])
        for each in windows.windows.values():
            each.clock = clock  # from the start: a clock swapped mid-slide misleads
        for update in finished_updates(8, APP):
            windows.apply(update)
            qapp.processEvents()  # painted between them, as on a busy PC
            clock.now += 2.0
        windows.join()
        clock.now += SLIDE_MAX_SEC  # what came before is at rest
        column = windows.windows["a"]
        assert column.host is not None and column.sliding
        column.canvas.repaint()
        before = tops(column)
        (update,) = finished_updates(1, APP, start=100)
        windows.apply(update)
        assert column.arriving
        first = tops(column)
        assert all(first[k] == pytest.approx(before[k]) for k in before.keys() & first)
    finally:
        windows.close()


# -- kept with the settings --------------------------------------------------------------


def test_the_choice_is_kept_with_the_settings() -> None:
    assert AppSettings().caption_arrival == "step_and_slide"
    assert set(ARRIVALS) == {arrival.value for arrival in Arrival}
    back = AppSettings.from_stored(AppSettings(caption_arrival="step").to_stored())
    look = caption_look(back)
    assert look.arrival is Arrival.STEP
    assert look_settings(replace(look, arrival=Arrival.STEP_AND_SLIDE))[
        "caption_arrival"
    ] == ("step_and_slide")
    assert AppSettings.from_stored({"caption_arrival": "fade"}).caption_arrival == (
        "step_and_slide"
    )


def test_the_mouse_coming_over_mid_slide_shows_the_newest_caption_whole(
    window: CaptionWindow, clock: Clock
) -> None:
    """The user's "the text will get cut off at the bottom" (polyglotic-hq
    291): the mouse came over the window while a caption slid in, the slide
    stopped where it was - its last rows below the window's edge - and
    stayed so for as long as the mouse moved over it. Now what's in flight
    is at rest at once, and nothing moves under the mouse from there - on
    a caption's words, where it holds them since 554."""
    arrive(window)
    clock.now += 0.1
    canvas = window.canvas
    clip = canvas.height() - PAD
    tops(window)
    assert canvas.placed[-1][2].bottom() > clip + 1  # mid-slide: rising into view
    window.came_over()  # the mouse comes over it, onto a caption's words
    window._hold_on_words(_on_words(window))
    held = tops(window)
    assert canvas.placed[-1][2].bottom() <= clip + 0.5  # the newest whole
    assert not window.arriving
    (later,) = finished_updates(1, start=300)
    window.receive(later)  # in at once (583): the view holds instead
    assert window.view.lines[-1].caption_id == later.caption_id
    clock.now += 1.5
    window._hold_on_words(_on_words(window))  # still moving over them
    assert {k: v for k, v in tops(window).items() if k in held} == held
    window.leaveEvent(None)  # it left: a moment later the view goes live
    window._hold_timer.timeout.emit()
    assert window.view.scroll.following


def test_back_at_the_newest_it_slides_from_what_was_last_seen(
    window: CaptionWindow, clock: Clock
) -> None:
    """Captions that came in while the learner was scrolled back don't
    pile up into the first slide back at the newest: it slides only by
    what changed since the window last showed the newest."""
    window.resize(window.width(), 900)  # room: no slide is too long to follow
    window.canvas.repaint()
    window.canvas.scroll_by(300)
    arrive(window, 0)  # read later
    window.go_live()
    clock.now += 2.0
    key = arrive(window, 1)  # before the window paints again
    assert window.motion.slide is None  # nothing seen to rise from
    assert set(window.motion.entries) == {key}  # it still comes in from below
