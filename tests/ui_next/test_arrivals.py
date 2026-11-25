"""The one spring used by caption and card arrivals."""

from collections.abc import Iterator
from dataclasses import replace
from itertools import pairwise

import pytest
from PySide6.QtWidgets import QApplication
from tests.budget_judge import sampled, within
from tests.ui_next.line_replay import FIXTURES, load, measure
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
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import ARRIVALS, AppSettings
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_surface import PAD
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.arrivals import ENTRY_GAP_PX, Arrival, effective
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.cards import GLIDE_FASTEST, Glide

FRAME = 1 / 60
GLIDE_SETTLE_SEC = 5.0


def test_step_and_slide_is_the_default_and_step_is_reduced_motion() -> None:
    assert CaptionLook().arrival is Arrival.STEP_AND_SLIDE
    assert effective(Arrival.STEP_AND_SLIDE, reduced_motion=False).slides
    assert effective(Arrival.STEP_AND_SLIDE, reduced_motion=True) is Arrival.STEP


def positions(glide: Glide, seconds: float = 2.0) -> list[float]:
    return [glide.to(frame * FRAME) for frame in range(round(seconds / FRAME) + 1)]


def test_every_growth_is_one_gentle_glide_with_a_300_px_per_second_cap() -> None:
    glide = Glide()
    glide.push(0.0, 180.0)
    samples = positions(glide)
    speeds = [abs(a - b) / FRAME for a, b in pairwise(samples)]
    assert samples[0] == 180.0 and samples[-1] == 0.0
    assert speeds[0] < max(speeds) / 3
    assert max(speeds) <= GLIDE_FASTEST.value + 0.01


def test_a_growth_mid_glide_pushes_remaining_distance_without_a_step() -> None:
    glide = Glide()
    glide.push(0.0, 82.0)
    before = glide.to(0.2)
    speed = glide.speed
    glide.push(0.2, 44.0)
    assert glide.px == pytest.approx(before + 44.0)
    assert glide.speed == pytest.approx(speed)
    pushed = glide.px
    assert glide.to(0.2 + FRAME) < pushed


def test_a_negative_rest_height_change_glides_without_a_step() -> None:
    glide = Glide()
    glide.push(0.0, -60.0)
    samples = positions(glide)
    assert samples[0] == -60.0
    assert all(a <= b <= 0.0 for a, b in pairwise(samples))
    assert samples[-1] == 0.0


def test_a_burst_of_captions_too_much_to_follow_is_at_rest_at_once(
    qapp: QApplication,
) -> None:
    settled = []

    def observe(window: CaptionWindow, now: float) -> None:
        if window.bursts:
            settled.append(not window.arriving)

    result = measure(load(FIXTURES / "m.json"), qapp, observe=observe)
    assert result.bursts == 1 and settled and all(settled)


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
        window.glide.push(clock.now, offset, most=window.height())
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
    clock.now += GLIDE_SETTLE_SEC
    rest = tops(window)
    risen = {round(before[k] - rest[k], 3) for k in kept & rest.keys()}
    assert len(risen) == 1 and risen.pop() > 0  # all by the same, to rest
    assert rest[key] - rest[newest] == pytest.approx(gap - ENTRY_GAP_PX.value, abs=0.01)


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
        clock.now += GLIDE_SETTLE_SEC
        tops(window)
        window.canvas.scroll_by(1000)
        held = window.view.scroll.anchor
        assert held is not None and held.key == window.view.lines[0].key
        before = tops(window)
        before_keys = [line.key for line, _, _ in window.canvas.placed]
        before_rect = next(
            rect for line, _, rect in window.canvas.placed if line.key == held.key
        )
        assert window.receive(second)
        after = tops(window)
        after_keys = [line.key for line, _, _ in window.canvas.placed]
        after_rect = next(
            rect for line, _, rect in window.canvas.placed if line.key == held.key
        )
        assert window.view.scroll.anchor == held
        assert before_keys == after_keys == [held.key, window.view.lines[1].key]
        assert after[held.key] == pytest.approx(before[held.key])
        assert after_rect.top() == pytest.approx(before_rect.top())
        assert after_rect.top() >= window.pace.geometry().bottom()
        window.canvas.scroll_by(-1000)
        assert window.view.scroll.following
    finally:
        window.close()


def test_the_frame_timer_runs_while_it_slides_and_stops_at_rest(
    window: CaptionWindow, clock: Clock
) -> None:
    arrive(window)
    assert window.arriving and window._tick_timer.isActive()
    clock.now += GLIDE_SETTLE_SEC
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
    clock.now += GLIDE_SETTLE_SEC  # the next tick comes late: the slide is over
    window._tick()
    qapp.processEvents()
    assert canvas.placed[-1][2].bottom() <= clip + 0.5  # the last row whole


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
        clock.now += GLIDE_SETTLE_SEC
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
        clock.now += GLIDE_SETTLE_SEC
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
        clock.now += GLIDE_SETTLE_SEC  # what came before is at rest
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
    first = tops(window)
    assert window.arriving
    clock.now += GLIDE_SETTLE_SEC
    rest = tops(window)
    for old in first.keys() & rest.keys() - {key}:
        assert first[old] == pytest.approx(rest[old])
    assert first[key] - rest[key] == pytest.approx(
        ENTRY_GAP_PX.value * window.view.text_size
    )


def test_editing_an_earlier_original_does_not_restart_the_arrival_slide(
    qapp: QApplication,
    clock: Clock,
) -> None:
    window = opened(qapp, clock, captions=0)
    try:
        window.resize(760, 650)
        window.set_language("")
        first, second, third = [
            replace(update, clauses=(Clause("A short caption."),))
            for update in finished_updates(3)
        ]
        for update in (first, second):
            window.receive(update)
            clock.now += GLIDE_SETTLE_SEC
            tops(window)
        window.receive(third)
        clock.now += 0.2
        before = tops(window)
        speed = window.glide.speed
        assert speed < 0
        edited, newest = sorted(before)[-2:]
        revision = replace(second, clauses=(Clause("Some more words. " * 11),))
        window.receive(revision)
        assert window.glide.speed == pytest.approx(speed)
        after = tops(window)
        assert after[edited] == pytest.approx(before[edited])
        assert after[newest] == pytest.approx(before[newest])
        clock.now += GLIDE_SETTLE_SEC
        expanded = tops(window)
        assert expanded[edited] < before[edited]
        window.receive(second)
        assert window.arriving and window.glide.px < 0
        assert tops(window)[edited] == pytest.approx(expanded[edited])
        clock.now += GLIDE_SETTLE_SEC
        rest = tops(window)
        assert rest[edited] > expanded[edited]
        assert rest[newest] == pytest.approx(expanded[newest])
    finally:
        window.close()


def test_the_first_caption_enters_below_the_foot_and_clears_it(
    qapp: QApplication,
) -> None:
    stream = load(FIXTURES / "a.json")
    stream["events"] = stream["events"][:1]
    first_row = []
    foot = 0.0

    def observe(window: CaptionWindow, now: float) -> None:
        nonlocal foot
        _, laid, rect = window.canvas.placed[-1]
        row = laid.rows[0]
        first_row.append(rect.y() + row.top + row.layout.lineAt(0).y())
        foot = PAD + window.canvas._seen_height()

    result = measure(stream, qapp, observe=observe)
    assert first_row[0] == pytest.approx(foot + ENTRY_GAP_PX.value)
    assert first_row[-1] < foot and result.peak_speed <= GLIDE_FASTEST.value


def test_new_clause_rows_close_the_entry_gap(qapp: QApplication) -> None:
    gaps = []

    def observe(window: CaptionWindow, now: float) -> None:
        if now >= 0.5:
            _, laid, _ = window.canvas.placed[-1]
            original = [
                row.top for row in laid.rows if row.row.kind is RowKind.ORIGINAL
            ]
            gaps.append(original[1] - original[0])

    measure(load(FIXTURES / "b.json"), qapp, observe=observe)
    assert gaps[0] - gaps[-1] == pytest.approx(ENTRY_GAP_PX.value, abs=0.1)
    assert gaps[0] > gaps[len(gaps) // 2] > gaps[-1]


def test_a_new_wrap_closes_the_same_entry_gap(qapp: QApplication) -> None:
    gaps = []

    def observe(window: CaptionWindow, now: float) -> None:
        if now >= 0.5:
            _, laid, _ = window.canvas.placed[-1]
            first, second, *_ = (r for r in laid.rows if r.row.kind is RowKind.ORIGINAL)
            assert first.layout.lineCount() == second.layout.lineCount() == 1
            gaps.append(
                second.top
                + second.layout.lineAt(0).y()
                - first.top
                - first.layout.lineAt(0).y()
            )

    measure(load(FIXTURES / "e.json"), qapp, observe=observe)
    assert gaps[0] - gaps[-1] == pytest.approx(ENTRY_GAP_PX.value, abs=0.1)
    assert gaps[0] > gaps[len(gaps) // 2] > gaps[-1]


def test_a_gliding_caption_frame_fits_its_budget(
    qapp: QApplication, clock: Clock
) -> None:
    window = opened(qapp, clock)

    def samples():
        clock.now += GLIDE_SETTLE_SEC
        tops(window)
        arrive(window, len(window.view.lines))
        tops(window)

        def frame() -> None:
            clock.now += FRAME
            assert window.arriving
            window._tick()

        return sampled(qapp, [frame] * 24, warm=False)

    try:
        within(budgets.FRAME, samples)
    finally:
        window.close()


def test_a_leaving_pair_fades_by_its_visible_share(
    qapp: QApplication, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = opened(qapp, clock)
    fractions = []
    paint = window.canvas.engine.paint

    def record(painter, line, laid, at, ink, marks, **kwargs):
        for clause, alpha in (kwargs.get("pair_opacity") or {}).items():
            rows = [r for r in laid.rows if r.row.clause == clause]
            top = at.y() + min(r.top for r in rows)
            bottom = at.y() + max(
                r.top + r.layout.boundingRect().height() for r in rows
            )
            if top < PAD < bottom:
                fractions.append((alpha, (bottom - PAD) / (bottom - top)))
        return paint(painter, line, laid, at, ink, marks, **kwargs)

    monkeypatch.setattr(window.canvas.engine, "paint", record)
    try:
        arrive(window)
        for _ in range(90):
            clock.now += FRAME
            window.canvas.repaint()
        assert len(fractions) >= 3
        assert all(actual == pytest.approx(expected) for actual, expected in fractions)
        assert max(a for a, _ in fractions) - min(a for a, _ in fractions) > 0.1
    finally:
        window.close()


def test_the_spring_keeps_its_pace_at_each_speech_cadence(
    qapp: QApplication, clock: Clock
) -> None:
    samples = []
    for interval, speaking in ((0.8, False), (6.0, False), (2.5, True)):
        window = opened(qapp, clock)
        try:
            arrive(window, 0)
            clock.now += GLIDE_SETTLE_SEC
            tops(window)
            clock.now += interval
            window.speaking = speaking
            arrive(window, 1)
            start = window.glide.px
            clock.now += 0.2
            samples.append(start - window.glide.to(clock.now))
        finally:
            window.close()
    assert samples[0] > 0
    assert samples == pytest.approx([samples[0]] * len(samples))
