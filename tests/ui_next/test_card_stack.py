"""Steady's card stack in a caption window (polyglotic-hq 552, decision
0260): the captions dealt onto cards, a translation coming into room
already kept, scrolling back, and the two zones still there with it off."""

from collections.abc import Iterator
from dataclasses import replace
from itertools import pairwise
from math import ceil, hypot

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_lookup_card import AREA
from tools.video_motion.paint_ink import PaintInk

from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.playout import PlayoutRules, ReadingPath
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.ui.captions import CaptionFeed
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout
from polyglotic_desktop.ui_next.caption_window import (
    CARD_READ_SEC,
    CARD_WAIT_SEC,
    COVER_FADE_SEC,
    HOME_CARDS_MOST,
    PAD,
    TRANSLATION_WAIT_SEC,
    VEIL_SEC,
    CaptionWindow,
    band_height,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.arrivals import Arrival
from polyglotic_desktop.ui_next.views.card_window_defaults import (
    TRANSLATION_WIDTH_RATIO,
)
from polyglotic_desktop.ui_next.views.cards import (
    FLAT_ENOUGH,
    GLIDE_FASTEST,
    NEW_CARD_AFTER_SEC,
)
from polyglotic_desktop.ui_next.views.dwell import HOLD_VIDEO_SEC
from polyglotic_desktop.ui_next.views.presets import with_look

EN, FR = Language("en"), Language("fr")
SAID = "the quick brown fox jumps over the lazy dog and runs far away again"
MEANT = "le renard brun et rapide saute par-dessus le chien et court au loin"


def caption(n: int, translated: bool = True, live: bool = False) -> CaptionUpdate:
    said = f"{n} {SAID}."
    return CaptionUpdate(
        CaptionId(f"c{n}"), APP, CaptionKind.LIVE if live else CaptionKind.FINISHED,
        (Clause(said, {FR: f"{n} {MEANT}."} if translated else {}),),
        EN, (EN,), established=len(said) if live else 0,
    )  # fmt: skip


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, lambda: [AREA])
    found.word_clock = Clock()
    found.set_captioned([("app", APP)])
    found.set_playout(PlayoutRules(delay=0.0, hold_back=0))
    found.set_timing(CaptionMode.STEADY)
    found.windows["app"].resize(520, 460)
    found.windows["app"].set_language("fr")
    found.windows["app"].clock = found.word_clock  # its glide, on this clock
    yield found
    found.close()


def rest(windows: CaptionWindows, *, step: float = 2.0) -> CaptionWindow:
    """The stack come to rest, and painted."""
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    window = windows.windows["app"]
    for _ in range(6):  # advance the dwell and return-to-live timers by hand
        clock.now += step
        if window._veil.isActive():
            window._veil.timeout.emit()
        window.check_card_room()
    window.grab()  # painted: what is placed is what is drawn
    return window


def say(
    windows: CaptionWindows, *updates: CaptionUpdate, step: float = 2.0
) -> CaptionWindow:
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    for update in updates:
        clock.now += NEW_CARD_AFTER_SEC.value + 0.5  # after a pause: it starts a card
        windows.apply(update)
        while (due := windows.playout.due()) is not None:
            clock.now = max(clock.now, due)
            windows.release_words()
            windows.windows["app"].check_card_room()
    return rest(windows, step=step)


def said(window: CaptionWindow) -> list[str]:
    return [
        " ".join(row.text for row in line.rows if row.kind is RowKind.ORIGINAL)
        for line in window.view.lines
    ]


def tops(window: CaptionWindow) -> dict[str, float]:
    """Where each card drawn flat has its top."""
    return {line.caption_id: rect.top() for line, _, rect in window.canvas.placed}


def wheel(window: CaptionWindow, notches: int) -> None:
    window.wheelEvent(
        QWheelEvent(
            QPointF(100, 100),
            QPointF(100, 100),
            QPoint(),
            QPoint(0, 120 * notches),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
    )


@pytest.mark.parametrize("mode", [CaptionMode.STEADY, CaptionMode.CALM])
def test_updates_of_a_dealt_caption_skip_the_new_caption_gap(
    windows: CaptionWindows, mode: CaptionMode
) -> None:
    windows.set_timing(mode)
    window = windows.windows["app"]
    window.set_look(replace(window.look, lab=replace(window.look.lab, arrival_gap=1.0)))
    update = caption(1, translated=False, live=True)
    window.receive(update)
    translated = caption(1, translated=True)
    window.receive(translated)
    assert not window.pacing.waits(translated)


def test_a_paced_mode_deals_cards_and_the_others_show_captions(
    windows: CaptionWindows,
) -> None:
    window = say(windows, caption(1))
    assert window.deck is not None
    assert window.zones is None and window.zone.isHidden()
    assert len(window.view.lines) > 1  # the caption is more than one line here
    assert all(line.caption_id.startswith("card:") for line in window.view.lines)
    assert " ".join(said(window)) == f"1 {SAID}."
    windows.set_timing(CaptionMode.WHOLE)
    windows.apply(caption(2))
    rest(windows)
    assert window.deck is None
    assert "c2" in [line.caption_id for line in window.view.lines]


def test_every_card_is_one_line_of_each_side(windows: CaptionWindows) -> None:
    window = say(windows, caption(1), caption(2))
    width = window.canvas._width()
    for line in window.view.lines:
        laid = window.canvas._laid(line)
        for row in laid.rows:
            assert row.layout.lineCount() == 1
            assert row.layout.maximumWidth() <= width + 0.5


def test_a_translation_arriving_moves_no_card(windows: CaptionWindows) -> None:
    window = say(
        windows, caption(1), caption(2, translated=False, live=True), step=0.35
    )
    before, lines = tops(window), said(window)
    assert not any(
        row.kind is RowKind.TRANSLATION for row in window.view.lines[-1].rows
    )
    say(windows, caption(2))  # finished, with its translation
    assert any(row.kind is RowKind.TRANSLATION for row in window.view.lines[-1].rows)
    assert said(window) == lines  # no word changed card
    after = tops(window)
    assert before and {key: after[key] for key in before} == before


@pytest.mark.parametrize("own", [False, True], ids=["app", "own-speech"])
def test_refinished_translation_leaves_no_card_sized_hole_in_a_tall_stack(
    windows: CaptionWindows, own: bool
) -> None:
    windows.set_show_mic("app", own)  # synthetic source ID, no audio device
    window = windows.windows["app"]
    window.resize(750, 1050)
    window.set_look(with_look(window.look, "paper"))
    window.set_language("zh")
    target = Language("zh")

    def update(n: int, translation: str = "") -> CaptionUpdate:
        return CaptionUpdate(
            CaptionId(f"map{n}"), MIC if own else APP, CaptionKind.FINISHED,
            (Clause(f"Map {n}.", {target: translation} if translation else {}),),
            EN, (EN,),
        )  # fmt: skip

    # A delayed translation wraps, then a correction fits on one row.
    # Later cards each need just one row for their own translation.
    for n in range(24):
        say(windows, update(n), update(n, "地圖"))
    canvas = window.canvas
    assert window.view.lines[-1].by_you == own
    assert not own or canvas.engine.style.own_right
    normal = canvas._laid(window.view.lines[-1]).height
    say(windows, update(24), update(24, "這是新的地圖。" * 24))
    wrapped = window.view.lines[-1]
    assert canvas._tall(wrapped) >= canvas._laid(wrapped).height > 2 * normal
    say(windows, update(24, "地圖"))
    for n in range(25, 28):
        say(windows, update(n), update(n, "地圖"))

    boxes = [(rect.top(), laid.height) for _, laid, rect in canvas.placed]
    boxes.extend(
        (rect.top(), laid.height * scale) for _, laid, rect, scale in canvas.turning
    )
    boxes.sort()
    assert 1 < len(boxes) < len(window.view.lines)
    gaps = [boxes[0][0] - PAD, PAD + canvas._seen_height() - sum(boxes[-1])]
    gaps.extend(top - (before + h) for (before, h), (top, _) in pairwise(boxes))
    assert max(gaps) <= normal


def test_every_card_keeps_the_same_room(windows: CaptionWindows) -> None:
    window = say(windows, *(caption(n) for n in range(1, 4)))
    canvas = window.canvas
    heights = {round(canvas._tall(line), 1) for line in window.view.lines[1:]}
    assert len(heights) == 1  # even gaps: a card takes what any other does


def test_the_wheel_turns_back_and_live_text_waits(windows: CaptionWindows) -> None:
    window = say(windows, *(caption(n) for n in range(1, 9)))
    assert window.view.scroll.following and window.pill.isHidden()
    newest = window.view.lines[-1].caption_id
    assert newest in tops(window)
    wheel(window, 6)
    rest(windows)
    assert not window.view.scroll.following and not window.pill.isHidden()
    held = tops(window)
    assert newest not in held
    say(windows, caption(9))  # more is said: what is being read stays put
    assert {k: v for k, v in tops(window).items() if k in held} == held
    window.go_live()
    rest(windows)
    assert window.view.scroll.following
    assert window.view.lines[-1].caption_id in tops(window)


def test_the_newest_card_sits_at_the_foot(windows: CaptionWindows) -> None:
    window = say(windows, *(caption(n) for n in range(1, 6)))
    line, _, rect = window.canvas.placed[-1]
    assert line is window.view.lines[-1]
    foot = PAD + window.canvas._seen_height()
    assert foot - 2 * window.canvas._tall(line) < rect.top() < foot


def test_timing_switch_rebuilds_the_kept_lines_once(
    windows: CaptionWindows, monkeypatch: pytest.MonkeyPatch
) -> None:
    windows.set_timing(CaptionMode.WHOLE)
    window = say(windows, caption(1), caption(2))
    rebuilds = []
    original = window.view._rebuild

    def rebuild(everything: bool) -> bool:
        rebuilds.append(everything)
        return original(everything)

    monkeypatch.setattr(window.view, "_rebuild", rebuild)
    windows.set_timing(CaptionMode.STEADY)
    assert rebuilds == [True]
    assert all(line.cuts and line.model for line in window.view.lines)


def test_a_narrower_window_lays_the_same_cards_out_again(
    windows: CaptionWindows,
) -> None:
    # the user, 2026-11-21: "resizing screens creates bugs now, resetting
    # the entire window" - every resize withdrew every card and dealt the
    # captions again
    window = say(windows, caption(1), caption(2))
    cards = [line.caption_id for line in window.view.lines]
    wide = said(window)
    window.resize(330, 460)
    rest(windows)
    assert [line.caption_id for line in window.view.lines] == cards
    assert said(window) == wide
    window = say(windows, caption(3))  # new words are dealt at the new width
    for line in window.view.lines[len(cards) :]:
        for row in window.canvas._laid(line).rows:
            assert row.layout.lineCount() == 1


def test_a_resize_at_live_stays_live(windows: CaptionWindows) -> None:
    window = say(windows, *(caption(n) for n in range(1, 7)))
    for size in ((420, 460), (360, 420), (600, 460)):  # a drag, frame by frame
        window.resize(*size)
        window.grab()
        assert window.view.scroll.following
    rest(windows)
    line, _, rect = window.canvas.placed[-1]
    assert line is window.view.lines[-1]  # the newest card at the foot
    foot = PAD + window.canvas._seen_height()
    assert rect.top() + window.canvas._tall(line) <= foot + 0.5


def test_a_resize_scrolled_back_keeps_the_line_read_where_it_is(
    windows: CaptionWindows,
) -> None:
    # the user, 2026-11-21: "... or going back to start of transcript"
    window = say(windows, *(caption(n) for n in range(1, 10)))
    cards = [line.caption_id for line in window.view.lines]
    wheel(window, 3)
    rest(windows)
    assert not window.view.scroll.following
    canvas = window.canvas
    line, _, rect = next(
        each for each in canvas.placed if each[2].top() >= canvas.clear_top - 0.5
    )
    for size in ((470, 440), (400, 420), (440, 460)):  # a drag, frame by frame
        window.resize(*size)
        window.grab()
        assert not window.view.scroll.following
        assert tops(window)[line.caption_id] == pytest.approx(rect.top(), abs=1.0)
    rest(windows)
    assert tops(window)[line.caption_id] == pytest.approx(rect.top(), abs=1.0)
    assert [each.caption_id for each in window.view.lines] == cards


def test_subtitles_draw_only_so_many_cards(windows: CaptionWindows) -> None:
    window = say(windows, *(caption(n) for n in range(1, 6)))
    assert len(window.canvas.placed) > 2
    window.set_card_limit(2)
    rest(windows)
    assert [line for line, _, _ in window.canvas.placed] == list(window.view.lines[-2:])


def test_with_cards_off_steady_has_its_two_zones(windows: CaptionWindows) -> None:
    windows.set_cards(False)
    window = say(windows, caption(1))
    assert window.deck is None and window.zones is not None
    assert [line.caption_id for line in window.view.lines] == ["c1"]
    windows.set_cards(True)
    assert window.deck is not None and window.zones is None


def test_the_scroll_bar_shows_where_the_cards_are_and_moves_them(
    windows: CaptionWindows,
) -> None:
    window = say(windows, caption(1))
    bar = window.scroll_bar
    assert bar.isHidden()  # everything fits: nothing to scroll
    say(windows, *(caption(n) for n in range(2, 9)))
    assert not bar.isHidden() and bar.value() == bar.maximum() > 0
    assert bar.geometry().left() >= PAD + window.canvas._width()  # beside the text
    newest = window.view.lines[-1].caption_id
    bar.setValue(0)  # dragged to the top: the oldest cards
    rest(windows)
    assert not window.view.scroll.following
    assert window.view.lines[1].caption_id in tops(window)
    assert newest not in tops(window)
    bar.setValue(bar.maximum())  # and back down: live again
    rest(windows)
    assert window.view.scroll.following and newest in tops(window)
    wheel(window, 4)  # the wheel moves the bar with the cards
    rest(windows)
    assert bar.value() < bar.maximum()


def test_back_to_live_never_covers_a_card(windows: CaptionWindows) -> None:
    window = say(windows, *(caption(n) for n in range(1, 9)))
    wheel(window, 5)
    rest(windows)
    pill = window.pill.geometry()
    assert not window.pill.isHidden() and window.canvas.placed
    # the cards are drawn down to the pill's top and no further
    assert PAD + window.canvas._seen_height() <= pill.top()


def test_a_labelled_card_keeps_room_for_its_label_too(
    windows: CaptionWindows,
) -> None:
    window = say(
        windows, caption(1), caption(2, translated=False, live=True), step=0.35
    )
    canvas = window.canvas
    first, last = window.view.lines[0], window.view.lines[-1]
    assert first.label and not last.label
    # A later untranslated card may reserve several estimated rows; the
    # labelled card still includes its label rather than being clipped to one.
    assert canvas._tall(first) > window._translation_room()
    before = canvas._tall(last)
    say(windows, caption(2))  # its translation comes
    assert canvas._tall(window.view.lines[-1]) == before


def test_the_stack_glides_to_a_new_card_and_never_from_far(
    windows: CaptionWindows, monkeypatch: pytest.MonkeyPatch
) -> None:
    from polyglotic_desktop.ui_next import caption_window

    monkeypatch.setattr(caption_window, "reduced_motion", lambda: False)
    window = say(windows, caption(1))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    at_rest = tops(window)
    assert not window.arriving
    windows.apply(caption(2))  # more cards, almost at once
    while windows.playout.due() is not None:
        clock.now += 0.005
        windows.release_words()
    window.grab()
    pitch = window._card_pitch()
    assert window.arriving  # gliding
    assert 0.0 < window.glide.px <= 1.5 * pitch  # and from no further than that
    gliding = tops(window)
    last = window.glide.px
    for _ in range(90):  # a second and a half of frames
        clock.now += 1 / 60
        px = window.glide.to(clock.now)
        assert px <= last  # only ever up
        last = px
    rest(windows)
    assert not window.arriving
    home = tops(window)  # no card came back down
    assert all(home[key] <= top for key, top in gliding.items() if key in home)
    # at the foot again (a card's room is first a guess: within 2 px)
    assert abs(max(tops(window).values()) - max(at_rest.values())) < 2.0


def test_a_source_is_named_on_its_first_card_not_on_every_one(
    windows: CaptionWindows,
) -> None:
    from polyglotic_desktop.core.listening.sources import SourceLabel

    window = windows.windows["app"]
    window.set_look(replace(window.look, show_source=True))
    window.set_labels({APP: SourceLabel("Discord", "#4fb6c9")}, "You")
    say(windows, caption(1), caption(2))
    labels = [line.label for line in window.view.lines]
    assert "Discord" in labels[0]
    assert not any(labels[1:])


# -- after 553's first recording of the stack (2026-11-20) ---------------------------


def test_nothing_moves_until_a_card_arrives(windows: CaptionWindows) -> None:
    # 553, third recording: "the reading line floats, and the stack rises
    # with nothing arriving" - room was opened ahead for a card the server
    # had said. The stack moves only when a card arrives.
    window = say(windows, *(caption(n) for n in range(1, 4)))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    at_rest = dict(window.canvas.at_rest)
    window.hear(caption(4))  # the server said it; the playout has yet to show it
    for _ in range(40):
        clock.now += 0.1
        window.check_card_room()
        window.grab()
        assert not window.glide.moving(clock.now)
    assert window.canvas.at_rest == at_rest


def test_pending_translation_cannot_show_a_card_before_its_turn(
    windows: CaptionWindows,
) -> None:
    first = replace(caption(1), clauses=(Clause("A map."),))
    window = say(windows, first)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    front = window.view.lines[-1].key
    window._card_since = clock.now
    second = replace(caption(2), clauses=(Clause("A book."),))
    window.receive(second)
    assert window._kept_back
    window.glide.push(clock.now, 40.0, most=100.0)
    window.receive(replace(second, clauses=(Clause("A book.", {FR: "Un livre."}),)))
    assert window.deck is not None and window.deck.pending()
    window.glide.stop()
    window.check_card_room()
    assert window.view.lines[-1].key == front
    clock.now += CARD_WAIT_SEC.value + 0.01
    window.check_card_room()
    assert any(row.text == "Un livre." for row in window.view.lines[-1].rows)


def test_a_card_waits_for_the_translation_that_just_landed(
    windows: CaptionWindows,
) -> None:
    first = replace(caption(1), clauses=(Clause("A map."),))
    window = say(windows, first)
    window.set_reading_hold(None)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    window.receive(replace(first, clauses=(Clause("A map.", {FR: "Une carte."}),)))
    front = window.view.lines[-1]
    assert any(row.text == "Une carte." for row in front.rows)
    window.receive(replace(caption(2), clauses=(Clause("Next."),)))
    assert window.view.lines[-1].key == front.key
    clock.now += CARD_WAIT_SEC.value + 0.01
    window.check_card_room()
    assert window.view.lines[-1].key != front.key


def test_a_new_card_waits_while_the_line_before_it_is_new(
    windows: CaptionWindows,
) -> None:
    # 553, third recording: 35 of 61 lines were pushed within 1.5 s of
    # being written. A card that would push a line so new is kept back
    # until the line has stood `CARD_READ_SEC` - `CARD_WAIT_SEC` at most.
    window = say(windows, *(caption(n) for n in range(1, 4)))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    lines = len(window.view.lines)
    window._card_since = clock.now - 1.0  # the newest line came a second ago
    short = CaptionUpdate(
        CaptionId("c7"), APP, CaptionKind.FINISHED,
        (Clause(f"7 {SAID}.", {FR: f"7 {MEANT}."}),), EN, (EN,),
    )  # fmt: skip
    windows.apply(short)
    windows.release_words()
    window.grab()
    assert len(window.view.lines) == lines  # kept back: nothing pushed
    assert not window.glide.moving(clock.now)
    clock.now += CARD_WAIT_SEC.value + 0.01  # never later than this
    window.check_card_room()
    assert len(window.view.lines) > lines
    assert window.glide.moving(clock.now + 0.01)
    window._card_since = clock.now - CARD_READ_SEC.value - 0.1  # a line long read
    late = CaptionUpdate(
        CaptionId("c8"), APP, CaptionKind.FINISHED,
        (Clause(f"8 {SAID}.", {FR: f"8 {MEANT}."}),), EN, (EN,),
    )  # fmt: skip
    while (due := windows.playout.due()) is not None:
        clock.now = max(clock.now, due)
        windows.release_words()
    rest(windows)
    lines = len(window.view.lines)
    clock.now += NEW_CARD_AFTER_SEC.value + 0.1
    window._card_since = clock.now - CARD_READ_SEC.value - 0.1
    windows.apply(late)
    windows.release_words()
    assert len(window.view.lines) > lines  # no wait: shown as it comes


def test_scrolled_back_stays_scrolled_back_until_the_learner_goes_live(
    windows: CaptionWindows,
) -> None:
    # 567's filmed runs: three notches back, live again by itself within
    # 4-6 s. The cards below the held one going (a caption set again or
    # withdrawn) let go of it. Only the learner goes back to live.
    window = say(windows, *(caption(n) for n in range(1, 7)))
    wheel(window, 3)
    rest(windows)
    assert not window.view.scroll.following
    held = window.view.scroll.anchor
    for n in (6, 5, 4):  # the newest captions are withdrawn
        windows.apply(CaptionUpdate(CaptionId(f"c{n}"), APP, CaptionKind.WITHDRAWN))
        rest(windows)
    assert not window.view.scroll.following
    assert window.view.scroll.anchor == held
    say(windows, *(caption(n) for n in range(7, 10)))
    assert not window.view.scroll.following
    wheel(window, -40)  # down to the newest: live again
    rest(windows)
    assert window.view.scroll.following


def test_a_burst_of_cards_comes_in_one_at_a_time(windows: CaptionWindows) -> None:
    # 553, third recording: after a hold, "three cards fade in at once"
    window = say(windows, *(caption(n) for n in range(1, 3)))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    lines = len(window.view.lines)
    long = f"3 {SAID} and {SAID}."
    # Feed the entire burst to the card dealer. The word timer now
    # preserves the individual beats even after a long pause.
    clock.now += 30.0
    window.receive(
        CaptionUpdate(
            CaptionId("c3"), APP, CaptionKind.FINISHED, (Clause(long),), EN, (EN,)
        )
    )
    assert len(window.view.lines) == lines + 1  # the first, as it came
    seen = [lines + 1]
    for _ in range(40):
        clock.now += 0.1
        window.check_card_room()
        seen.append(len(window.view.lines))
    assert seen[-1] >= lines + 3  # they all came
    assert all(b - a <= 1 for a, b in pairwise(seen))


def test_the_first_card_after_the_cards_are_dealt_again_glides_too(
    windows: CaptionWindows,
) -> None:
    # 553, third recording, 57.25 s: just after a resize the stack was
    # painted a card higher in one frame (-87 px), then glided from below
    # (+86 px): the first rise after the cards were dealt again wasn't
    # measured from anywhere.
    window = say(windows, *(caption(n) for n in range(1, 4)))
    window.resize(430, 460)
    rest(windows)
    short = CaptionUpdate(
        CaptionId("c9"), APP, CaptionKind.FINISHED,
        (Clause("nine", {FR: "neuf"}),), EN, (EN,),
    )  # fmt: skip
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    before = tops(window)
    windows.apply(short)
    clock.now += 30.0
    windows.release_words()
    window.grab()  # the very next frame: nothing has jumped
    assert window.glide.px > 30.0
    now = tops(window)
    kept = before.keys() & now.keys()
    assert kept and all(abs(now[key] - before[key]) < 12.0 for key in kept)


def test_no_scroll_mark_over_a_film(windows: CaptionWindows) -> None:
    # 556: Video has no panel; the mark showed faintly at the right
    window = say(windows, *(caption(n) for n in range(1, 9)))
    assert not window.scroll_bar.isHidden()
    window.set_look(replace(window.look, opacity=0.0))
    rest(windows)
    assert window.scroll_bar.isHidden()


def test_a_notch_is_a_card_eased_and_the_view_rests_on_whole_cards(
    windows: CaptionWindows,
) -> None:
    window = say(windows, *(caption(n) for n in range(1, 12)))
    canvas = window.canvas
    for _ in range(3):
        drawn = tops(window)
        first = window.view.scroll.anchor
        wheel(window, 1)
        window.grab()  # the very next frame: nothing has jumped
        now = tops(window)
        kept = drawn.keys() & now.keys()
        assert kept and all(abs(now[key] - drawn[key]) < 12.0 for key in kept)
        rest(windows)
        anchor = window.view.scroll.anchor
        assert anchor is not None
        assert first is None or anchor.key < first.key
        foot = PAD + canvas._seen_height()
        for line, _, rect in canvas.placed:  # no card cut at the top or the foot
            assert rect.top() >= canvas.clear_top - 0.5
            assert rect.top() + canvas._tall(line) <= foot + 0.5
        # 553's third recording: scrolled back, the lower half went blank -
        # the last card stands at the foot, as the newest does when live
        last, _, rect = canvas.placed[-1]
        assert rect.top() + canvas._tall(last) >= foot - 1.5
        assert not canvas.turning
    pill = window.pill.geometry()
    assert all(rect.bottom() <= pill.top() for _, _, rect in canvas.placed)


def test_back_to_live_slides_home(windows: CaptionWindows) -> None:
    # 553: Back to live jumped 350 px in a frame
    window = say(windows, *(caption(n) for n in range(1, 12)))
    wheel(window, 1)
    held = tops(rest(windows))
    window.go_live()
    window.grab()  # the next frame: still about where it stood
    now = tops(window)
    kept = held.keys() & now.keys()
    assert kept and all(abs(now[key] - held[key]) < 12.0 for key in kept)
    assert window.glide.moving(window.clock())
    rest(windows)
    assert window.view.lines[-1].caption_id in tops(window)


def test_back_to_live_is_one_slide_and_never_fast(windows: CaptionWindows) -> None:
    # 553, third recording: "Back to live throws the view 310 px in 9 ms
    # through two flashes of unrelated cards"; fourth: 1,128 px a second.
    # It slides the whole way past the cards between, at the glide's pace.
    window = say(windows, *(caption(n) for n in range(1, 12)))
    wheel(window, 4)
    held = tops(rest(windows))
    window.go_live()
    window.grab()  # the next frame: still about where it stood
    now = tops(window)
    kept = held.keys() & now.keys()
    assert kept and all(abs(now[key] - held[key]) < 12.0 for key in kept)
    pitch = window._card_pitch()
    assert 3.2 * pitch < window.glide.px <= HOME_CARDS_MOST * pitch  # the whole way
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    last = window.glide.px
    for _ in range(300):
        clock.now += 1 / 60
        window.grab()
        px = window.glide.to(clock.now)
        assert 0.0 <= last - px <= GLIDE_FASTEST.value / 60 + 0.01  # never fast
        last = px
        drawn = [rect.top() for _, _, rect in window.canvas.placed]
        drawn += [rect.top() for _, _, rect, _ in window.canvas.turning]
        assert drawn and min(drawn) < 2 * pitch  # never an empty band above
    rest(windows)
    assert window.view.lines[-1].caption_id in tops(window)


def test_back_to_live_from_far_comes_home_behind_a_fade(
    windows: CaptionWindows,
) -> None:
    # 553, fifth recording (Mandarin): from further back than it slides,
    # "a cross-fade with ghosts, then a half-empty window", 4,272 px a
    # second. The whole view fades out, comes home unseen, and fades in
    # at rest: no card is drawn anywhere but its place.
    window = say(windows, *(caption(n) for n in range(1, 30)))
    window.scroll_bar.setValue(0)
    held = tops(rest(windows))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    window.go_live()
    assert not window.view.scroll.following and window.arriving
    clock.now += VEIL_SEC / 4
    window.grab()
    assert 0.0 < window.veil(clock.now) < 1.0
    now = tops(window)  # still the cards that were held, where they stood
    assert all(abs(top - held[key]) < 0.5 for key, top in now.items())
    clock.now += VEIL_SEC / 4
    window._veil.timeout.emit()
    assert window.view.scroll.following
    assert not window.glide.moving(clock.now)
    home = tops(rest(windows))
    assert window.veil(clock.now) == 1.0
    assert window.view.lines[-1].caption_id in home
    canvas = window.canvas
    assert len(canvas.placed) + len(canvas.turning) >= 5  # full: not half empty


@pytest.mark.parametrize("timer_after", [VEIL_SEC / 2 - 0.007, VEIL_SEC + 0.05])
def test_back_to_live_finishes_even_if_its_timer_misses_the_midpoint(
    windows: CaptionWindows, timer_after: float
) -> None:
    window = say(windows, *(caption(n) for n in range(1, 30)))
    window.scroll_bar.setValue(0)
    rest(windows)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    window.pill.click()
    assert not window.view.scroll.following
    clock.now += timer_after
    window.grab()  # a paint can precede the delayed timer
    window._veil.timeout.emit()  # the single timer fires only once
    assert window.view.scroll.following
    assert window.view.lines[-1].caption_id in tops(rest(windows))


def test_scrolled_back_the_toolbar_never_hides_the_top_card(
    windows: CaptionWindows,
) -> None:
    # 572's reviews: the bar that appears with the mouse hid the top card,
    # then gave it back in one frame; 553: the old end only half full
    window = say(windows, *(caption(n) for n in range(1, 12)))
    if window.nudge is not None:
        window.nudge.hide()  # the language question: not this test's
    window.scroll_bar.setValue(0)
    hidden = tops(rest(windows))
    assert window.view.lines[0].caption_id in hidden
    assert min(hidden.values()) >= band_height()
    window._show_band(True)
    assert tops(rest(windows)) == hidden


def test_a_new_card_is_never_drawn_over_the_card_before(
    windows: CaptionWindows,
) -> None:
    # 553, fourth recording (English): each new line's original was drawn
    # 3 px or more into the translation above it while the stack rose
    window = say(windows, *(caption(n) for n in range(1, 4)))
    short = CaptionUpdate(
        CaptionId("c9"), APP, CaptionKind.FINISHED,
        (Clause("nine", {FR: "neuf"}),), EN, (EN,),
    )  # fmt: skip
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(short)
    clock.now += 30.0
    windows.release_words()
    new, before = window.view.lines[-1].key, window.view.lines[-2].key
    seen = 0
    for _ in range(90):
        clock.now += 1 / 60
        window.grab()
        at = {line.key: rect for line, _, rect in window.canvas.placed}
        if new in at and before in at:
            seen += 1
            foot = at[before].top() + window.canvas._tall(window.view.lines[-2])
            assert foot - at[new].top() <= 3.0
    assert seen


def test_the_first_notch_shows_a_whole_new_card(windows: CaptionWindows) -> None:
    # 553, fourth recording: the first notch from live moved half a card
    # (48 of 90 px) - Back to live takes a strip of the foot. The first
    # notch goes a card further, and the notch back down returns to live.
    window = say(windows, *(caption(n) for n in range(1, 12)))
    live = tops(window)
    wheel(window, 1)
    held = tops(rest(windows))
    assert not window.view.scroll.following
    pitch = window._card_pitch()
    kept = live.keys() & held.keys()
    assert kept and all(held[key] - live[key] >= pitch - 1.0 for key in kept)
    older: list[str] = [line.caption_id for line in window.view.lines]
    first = min(older.index(key) for key in live)
    assert older[first - 1] in held  # a card that wasn't there, whole
    wheel(window, -1)
    rest(windows)
    assert window.view.scroll.following


def test_no_room_is_kept_for_a_translation_that_will_not_come(
    windows: CaptionWindows,
) -> None:
    # 553, fourth recording (mixed speech): a clause said in the language
    # the window translates into gets no translation from the server; the
    # card kept room for one, an empty band for 17.9 s
    window = say(windows, caption(1))
    window.receive(caption(2, translated=False))
    waiting = window.canvas._tall(window.view.lines[-1])
    french = CaptionUpdate(
        CaptionId("c3"), APP, CaptionKind.FINISHED,
        (Clause("le renard brun saute."),), FR, (FR,),
    )  # fmt: skip
    say(windows, french)
    assert said(window)[-1] == "le renard brun saute."
    assert window.canvas._tall(window.view.lines[-1]) < waiting - 8.0
    # The ordinary pitch remains a pair's rather than inheriting every extra
    # row estimated for this unusually wide untranslated card.
    assert window._card_pitch() >= window._translation_room()


def test_room_is_kept_for_a_second_line_that_will_come(
    windows: CaptionWindows,
) -> None:
    # 572's film of preview 2 (577): with a second language for the
    # window's target (#965: English by default), a clause said in the
    # target is translated into it - a second line comes. No room was
    # kept for it, and the stack stepped up 65 px when it came.
    windows.set_second_languages({FR: EN})
    window = say(windows, caption(1))
    french = CaptionUpdate(
        CaptionId("c3"), APP, CaptionKind.FINISHED,
        (Clause("le renard brun saute."),), FR, (FR,),
    )  # fmt: skip
    window.receive(french)
    line = window.view.lines[-1]
    assert said(window)[-1] == "le renard brun saute."
    bare = window.canvas.laid_at(line, window.canvas._width()).height
    waiting = window.canvas._tall(line)
    assert waiting >= bare + 0.8 * window._translation_room()
    second = CaptionUpdate(
        CaptionId("c3"), APP, CaptionKind.FINISHED,
        (Clause("le renard brun saute.", {EN: "the brown fox jumps."}),),
        FR, (FR,),
    )  # fmt: skip
    say(windows, second)
    line = window.view.lines[-1]
    assert any(row.kind is RowKind.TRANSLATION for row in line.rows)
    assert window.canvas._tall(line) <= waiting + 1.0  # it came into its room


def test_at_the_oldest_cards_the_window_is_full(windows: CaptionWindows) -> None:
    # 553, fourth recording: scrolled to the old end with the bar in a
    # small window, the view rested on one card with 60 % of it empty
    window = say(windows, *(caption(n) for n in range(1, 9)))
    window.resize(520, 250)
    rest(windows)
    window.scroll_bar.setValue(0)
    rest(windows)
    canvas = window.canvas
    foot = PAD + canvas._seen_height()
    last, _, rect = canvas.placed[-1]
    assert rect.top() + canvas._tall(last) >= foot - canvas._gap() - 1.0


def test_cards_dealt_again_start_where_they_started(windows: CaptionWindows) -> None:
    # 553, fourth recording: a resize merged captions into run-on cards
    # that stayed merged at the old width
    window = say(windows, *(caption(n) for n in range(1, 4)))
    window.resize(330, 460)
    rest(windows)
    window.resize(520, 460)
    cards = said(rest(windows))
    for n in range(1, 4):  # each caption came after a pause: its own card
        assert any(card.startswith(f"{n} the quick") for card in cards)


def test_leaving_steady_keeps_the_cards_that_were_read(
    windows: CaptionWindows,
) -> None:
    # 553: a switch of mode laid the whole history out again in one frame
    window = say(windows, *(caption(n) for n in range(1, 5)))
    window.show()
    lines = said(window)
    windows.set_timing(CaptionMode.WHOLE)
    assert window.deck is None
    assert said(window) == lines  # each card as it stood, its translation with it
    say(windows, caption(5))
    assert said(window)[: len(lines)] == lines
    windows.set_timing(CaptionMode.STEADY)  # and back: only new lines are dealt
    say(windows, caption(6))
    assert said(window)[: len(lines)] == lines


def test_a_draft_is_never_left_beside_its_final_lines(
    windows: CaptionWindows,
) -> None:
    # 553: "也是许多游客行程中的…" stood above "…亮点。" - a caption shown
    # as it came, then finished on cards after the mode changed
    windows.set_timing(CaptionMode.WHOLE)
    window = say(windows, caption(1), caption(2, translated=False, live=True))
    windows.set_timing(CaptionMode.STEADY)
    say(windows, caption(2))
    words = " ".join(said(window)).split()
    assert words.count("2") == 1  # said once: the cards took the draft's place
    assert " ".join(said(window)).endswith(f"2 {SAID}.")


def test_a_translation_comes_into_room_tall_enough(windows: CaptionWindows) -> None:
    # 553: the slot was 12-17 px short, so the translation came cut at the
    # foot and the page nudged
    window = say(windows, caption(1, translated=False, live=True), step=0.2)
    canvas = window.canvas
    kept = {line.key: canvas._tall(line) for line in window.view.lines}
    say(windows, caption(1))
    assert any(row.kind is RowKind.TRANSLATION for row in window.view.lines[-1].rows)
    for line in window.view.lines:
        assert canvas._laid(line).height <= kept[line.key] + 0.5
        assert canvas._tall(line) == pytest.approx(kept[line.key], abs=0.5)


def test_translation_with_it_does_not_wait_for_an_unseen_caption(
    windows: CaptionWindows,
) -> None:
    first = replace(caption(1), clauses=(Clause("A map."),))
    window = say(windows, first)
    _, _, before = window.canvas.placed[-1]
    window.hear(caption(2))
    window.receive(replace(first, clauses=(Clause("A map.", {FR: "Une carte."}),)))
    window.grab()
    assert any(row.text == "Une carte." for row in window.view.lines[-1].rows)
    _, _, after = window.canvas.placed[-1]
    # The reserved space expired while the card was at rest. The late
    # translation fits by growing the card up from the same live edge.
    assert after.height() > before.height()
    assert after.bottom() == pytest.approx(before.bottom())
    assert not window.glide.moving(window.clock())


@pytest.mark.parametrize(
    "mode",
    [CaptionMode.STEADY, CaptionMode.CALM, CaptionMode.INSTANT, CaptionMode.WHOLE],
)
def test_repainting_during_silence_keeps_the_visible_rows_and_anchor(
    windows: CaptionWindows, mode: CaptionMode
) -> None:
    windows.set_timing(mode)
    window = say(windows, *(caption(n) for n in range(4)))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    positions = tops(window)
    assert positions
    for _ in range(8):
        clock.now += 0.5
        window.check_card_room()
        window.grab()
        assert tops(window) == positions
        assert window.view.scroll.following


def test_a_translation_lands_only_while_the_stack_is_at_rest(
    windows: CaptionWindows,
) -> None:
    # 553's second recording: "the page still lurches when a translation
    # lands" - 17 times. It waits for the glide to end; nothing moves then.
    window = say(windows, *(caption(n) for n in range(1, 4)))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(caption(4))  # words and translation together, mid-glide
    while windows.playout.due() is not None:
        clock.now += 0.001
        windows.release_words()
    window.grab()
    assert window.glide.moving(clock.now)
    newest = window.view.lines[-1]
    assert not any(row.kind is RowKind.TRANSLATION for row in newest.rows)
    assert window.deck is not None and window.deck.pending()
    rest(windows)
    before = tops(window)
    window.check_card_room()  # at rest: it lands, in the room kept for it
    newest = window.view.lines[-1]
    assert any(row.kind is RowKind.TRANSLATION for row in newest.rows)
    assert tops(rest(windows)) == before


def test_a_new_card_stands_in_its_place_while_the_stack_rises_from_under_it(
    windows: CaptionWindows,
) -> None:
    # a line is never pushed as it appears: it doesn't ride the glide
    window = say(windows, *(caption(n) for n in range(1, 4)))
    short = CaptionUpdate(
        CaptionId("c9"), APP, CaptionKind.FINISHED,
        (Clause("nine", {FR: "neuf"}),), EN, (EN,),
    )  # fmt: skip
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(short)
    windows.release_words()
    window.grab()
    assert window.glide.px > 30.0  # the stack has yet to rise for it
    key = window.view.lines[-1].key
    places = []
    for _ in range(90):
        clock.now += 1 / 60
        window.grab()
        places += [
            rect.top() for line, _, rect in window.canvas.placed if line.key == key
        ]
    assert places and max(places) - min(places) < 0.5  # it never moved
    older = window.view.lines[-2].caption_id
    assert tops(rest(windows))[older] < places[-1]


def test_a_new_card_waits_for_the_card_it_takes_out_of_reading(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    window.set_card_limit(3)
    window.set_reading_hold(HOLD_VIDEO_SEC.value)
    window = say(windows, *(caption(n) for n in range(1, 4)))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    oldest = window.view.lines[-3]
    window._card_since = clock.now - 60.0
    window._reading[oldest.key].landed = clock.now  # its translation just came
    lines = len(window.view.lines)
    windows.apply(caption(9))
    windows.release_words()
    window.check_card_room()
    assert len(window.view.lines) == lines  # held: its translation isn't read
    assert window.still_read()  # nor does the window fade meanwhile
    clock.now += HOLD_VIDEO_SEC.value + 0.01  # never longer than this
    window.check_card_room()
    assert len(window.view.lines) > lines


def test_the_mouse_on_the_cards_holds_the_view_never_the_cards(
    windows: CaptionWindows,
) -> None:
    # the user, 2026-11-21: "The mouse shouldn't hold up delivery, could
    # hold up pushing text by introducing back to live / new messages
    # alert right?" - the cards are dealt as they come; the view holds
    # while the mouse is on the words, Back to live counts what came, and
    # a moment after the mouse goes the stack glides to live once
    window = say(windows, *(caption(n) for n in range(1, 4)))
    before = tops(window)
    window._hold()  # the mouse on a card's words
    window = say(windows, caption(9))
    dealt = [line.caption_id for line in window.view.lines]
    assert any(card not in before for card in dealt)  # dealt: not held
    assert tops(window) == before  # nothing moved under the mouse
    pill = window.pill
    assert not pill.isHidden() and "new" in pill.text()
    assert pill.geometry().top() < window.height() / 2  # not over the newest card
    window.let_go()  # the mouse went
    assert window._hold_timer.isActive()  # a moment's grace first
    window._hold_timer.timeout.emit()
    window.grab()  # the first frame: from where the view stood, no jump
    assert all(abs(tops(window)[card] - top) < 12.0 for card, top in before.items())
    assert window.glide.moving(windows.word_clock())  # one glide to the newest
    assert pill.isHidden()
    window = rest(windows)
    assert window.view.lines[-1].caption_id in tops(window)


@pytest.mark.parametrize("pointer", [True, False], ids=["pointer", "scrolled-back"])
def test_cards_that_arrived_while_reading_do_not_roll_through_the_window(
    windows: CaptionWindows,
    pointer: bool,
) -> None:
    def short(n: int) -> CaptionUpdate:
        return replace(caption(n), clauses=(Clause(f"Map {n}.", {FR: f"Carte {n}."}),))

    window = say(windows, *(short(n) for n in range(8)))
    held = window.view.lines[-1].key
    if pointer:
        window._hold()
    else:
        wheel(window, 1)
    say(windows, *(short(n) for n in range(8, 11)))
    if pointer:
        window.let_go()
        window._hold_timer.timeout.emit()
    else:
        window.go_live()
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    positions: dict[int, list[float]] = {}
    for _ in range(150):
        clock.now += 1 / 60
        window.grab()
        for line, _, rect in window.canvas.placed:
            if line.key > held:
                positions.setdefault(line.key, []).append(rect.top())
    assert len(positions) >= 2
    assert all(max(ys) - min(ys) < 0.5 for ys in positions.values())


def test_a_card_all_but_flat_on_the_drum_is_drawn_flat(windows: CaptionWindows) -> None:
    # 584: at rest the drum squashed Everyday's second card to 0.986 and
    # Video's older one to 0.967 - a squash too slight to see but enough
    # to soften its text
    window = say(windows, *(caption(n) for n in range(1, 9)))
    assert window.canvas.placed
    assert all(squash < FLAT_ENOUGH for *_, squash in window.canvas.turning)


def test_translation_moves_continuously_as_its_card_turns(
    windows: CaptionWindows,
) -> None:
    # Follow each painted row through one card's travel. The translation
    # sits well below the top: a sudden change of scale moves it visibly.
    window = say(windows, *(caption(n) for n in range(1, 9)))
    canvas = window.canvas
    before: dict[tuple[int, int], float] = {}
    was_flat: set[int] = set()
    crossed: set[int] = set()
    for offset in range(round(window._card_pitch()), -1, -1):
        window.glide.px = float(offset)
        window.grab()
        flat = {line.key for line, _, _ in canvas.placed}
        crossed.update(was_flat & {line.key for line, _, _, _ in canvas.turning})
        was_flat = flat
        geometry = [(*placed, 1.0) for placed in canvas.placed] + canvas.turning
        current = {
            (line.key, row.index): rect.top() + scale * row.top
            for line, laid, rect, scale in geometry
            for row in laid.rows
        }
        for key in before.keys() & current.keys():
            assert abs(before[key] - current[key]) <= 1.1  # one pixel of travel
        before = current
    assert crossed


def test_server_continuation_keeps_the_first_card_and_shown_words(
    windows: CaptionWindows,
) -> None:
    feed = CaptionFeed(CaptionHistory(), None)
    feed.applied.connect(lambda update: say(windows, update))
    window = windows.windows["app"]

    def send(cid: str, text: str, translation: str, **fields: object) -> None:
        msg = protocol.validate(
            protocol.CaptionUpdate,
            dict(
                caption_id=cid,
                source_id=APP,
                kind="finished",
                language="en",
                clauses=[
                    {"original": text, "translations": {"fr": translation}, "links": {}}
                ],
                **fields,
            ),
        )
        feed.apply(listening.caption_update(msg))

    send("a", "Currently in.", "A present.")
    key = window.view.lines[0].key
    send("b", "Currently in Paris.", "A Paris.", continues="a")
    assert said(window) == ["Currently in Paris."]
    assert window.view.lines[0].key == key
    assert [
        row.text for row in window.view.lines[0].rows if row.kind is RowKind.TRANSLATION
    ] == ["A Paris."]
    send("b", "Currently in Paris again.", "De retour a Paris.", continues="a")
    assert said(window) == ["Currently in Paris again."]
    assert window.view.lines[0].key == key
    send("b", "Elsewhere.", "Ailleurs.")
    assert [c.original for c in feed.history.captions] == [
        "Currently in.",
        "Elsewhere.",
    ]
    assert said(window) == ["Currently in.", "Elsewhere."]


def advance_video(window: CaptionWindow, clock: Clock, seconds: float) -> None:
    """Paint the arrival, its intermediate frames and its last frame."""
    window.grab()
    finish = clock.now + seconds
    while clock.now < finish:
        clock.now = min(finish, clock.now + 0.04)
        window.grab()


@pytest.mark.parametrize("finished", [False, True])
@pytest.mark.parametrize("arrival", [Arrival.STEP_AND_SLIDE, Arrival.STEP])
def test_video_instant_shows_each_packet_word_on_its_own_paint(
    windows: CaptionWindows, finished: bool, arrival: Arrival
) -> None:
    from polyglotic_desktop.core.listening.playout import MIN_GAP_SEC
    from polyglotic_desktop.ui_next.video import INSTANT_WORD_INTERVAL

    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window = windows.windows["app"]
    window.resize(1000, 420)
    window.set_look(
        replace(window.look, show_source=False, show_language=False, arrival=arrival)
    )
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    original, translation = "One two three four.", "Un deux trois quatre."
    windows.apply(
        replace(
            caption(1, live=not finished),
            clauses=(Clause(original, {FR: translation}),),
        )
    )
    assert INSTANT_WORD_INTERVAL.value < MIN_GAP_SEC

    def visible() -> dict[RowKind, str]:
        window.grab()
        return {
            row.row.kind: row.row.text
            for _, laid, _ in window.canvas.placed
            for row in laid.rows
        }

    first = {RowKind.ORIGINAL: "One", RowKind.TRANSLATION: "Un"}
    assert visible() == first
    assert visible() == first  # dirty paints at the same instant
    for words in range(2, 5):
        clock.now += 0.3 if words == 2 else INSTANT_WORD_INTERVAL.value
        assert visible() == {
            RowKind.ORIGINAL: " ".join(original.split()[:words]),
            RowKind.TRANSLATION: " ".join(translation.split()[:words]),
        }
    if finished and arrival is Arrival.STEP:
        flow = window.canvas.video.flow
        assert flow is not None
        assert len(flow.slots) == 2
        assert all(slot.lift is None for slot in flow.slots.values())


def test_video_instant_reveals_translation_word_by_word_in_one_row(
    windows: CaptionWindows,
) -> None:
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window = windows.windows["app"]
    window.set_text_size(2)
    window.set_translation_size(2)
    window.set_look(replace(window.look, show_source=False, show_language=False))
    window.resize(560, 100)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(
        replace(caption(1), clauses=(Clause("One.", {FR: "Un deux trois."}),))
    )

    seen: list[str] = []
    for _ in range(140):
        window.grab()
        flow = window.canvas.video.flow
        assert flow is not None and flow.one_row
        rows = flow.rows()
        assert len(rows) <= 1
        if rows and rows[0].translation and (not seen or seen[-1] != rows[0].text):
            seen.append(rows[0].text)
        clock.now += 1 / 60
    assert seen == ["Un", "Un deux", "Un deux trois."]


def test_video_scrolling_reveals_translation_before_the_original_finishes(
    windows: CaptionWindows,
) -> None:
    windows.set_timing(CaptionMode.SCROLLING)
    windows.set_subtitles((0.045, 0.8))
    window = windows.windows["app"]
    window.resize(900, 400)
    clock = windows.word_clock
    assert isinstance(clock, Clock)

    def shown() -> list[RowKind]:
        advance_video(window, clock, 0.5)
        return [r.row.kind for _, laid, _ in window.canvas.placed for r in laid.rows]

    pair = (Clause("Good evening", {FR: "Bonsoir"}),)
    windows.apply(replace(caption(1, live=True), clauses=pair))
    assert shown() == [RowKind.ORIGINAL, RowKind.TRANSLATION]
    windows.apply(replace(caption(1), clauses=pair))
    assert shown() == [RowKind.ORIGINAL, RowKind.TRANSLATION]


def test_switching_to_video_starts_beyond_the_transcript(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    for n in range(1, 5):
        windows.apply(caption(n))
    windows.set_subtitles((0.045, 0.8))
    window.resize(900, 400)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    advance_video(window, clock, 0.5)
    assert len(window.view.lines) == 4
    assert not window.canvas.placed

    windows.apply(caption(5, live=True))
    advance_video(window, clock, 0.5)
    assert {line.caption_id for line, _, _ in window.canvas.placed} == {"c5"}

    windows.set_subtitles(None)
    windows.apply(caption(6))
    windows.set_subtitles((0.045, 0.8))
    advance_video(window, clock, 0.5)
    assert not window.canvas.placed


def test_late_translation_of_a_steady_card_stays_out_of_live_video(
    windows: CaptionWindows,
) -> None:
    window = say(windows, caption(1))
    assert window.canvas.placed
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.resize(900, 400)
    windows.apply(
        replace(caption(1), clauses=(Clause("Earlier line", {FR: "Ancienne ligne"}),))
    )
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    advance_video(window, clock, 0.5)
    assert not window.canvas.placed
    wheel(window, 1)
    window.grab()
    assert window.canvas.placed
    assert not window.view.scroll.following


def test_video_pages_keep_whole_subtitles_in_reading_order_through_scroll_and_resize(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.set_text_size(1)
    window.set_translation_size(1)
    window.resize(1000, 360)

    def visible() -> list[int]:
        clock = windows.word_clock
        assert isinstance(clock, Clock)
        advance_video(window, clock, HOLD_VIDEO_SEC.value + 2.0)
        return [line.key for line, _, _ in window.canvas.placed]

    for n in range(1, 9):
        windows.apply(caption(n))
        shown = visible()
        assert shown == sorted(shown)
        assert shown[-1] == window.view.lines[-1].key
    newest = window.view.lines[-1].key
    # Keep the most recent whole blocks that fit and browse earlier ones.
    recent = visible()
    assert recent == sorted(set(recent))
    assert 1 < len(recent) < 8 and recent[-1] == newest
    wheel(window, 1)
    history = visible()
    assert history == sorted(history) and any(key < newest for key in history)
    assert not window.view.scroll.following
    windows.apply(caption(9))
    assert visible() == history
    window.go_live()
    assert visible()[-1] == window.view.lines[-1].key

    window.set_text_size(4)
    window.resize(440, 200)
    assert visible() == [window.view.lines[-1].key]
    _, _, rect = window.canvas.placed[-1]
    assert rect.bottom() <= PAD + window.canvas._seen_height()
    assert window.view.text_size == 4


def test_video_releases_the_old_translation_slot_when_a_phrase_splits(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.set_text_size(3)
    window.resize(1000, 420)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    update = caption(1, live=True)
    windows.apply(
        replace(update, clauses=(Clause("a longer phrase " * 5, {FR: "ici"}),))
    )
    advance_video(window, clock, COVER_FADE_SEC)
    windows.apply(
        replace(
            update,
            clauses=(
                Clause("a phrase", {FR: "la premiere phrase"}),
                Clause("a second", {FR: "la seconde"}),
            ),
        )
    )
    window.grab()
    _, laid, _ = window.canvas.placed[-1]
    original = next(row for row in laid.rows if row.row.kind is RowKind.ORIGINAL)
    translation = next(row for row in laid.rows if row.row.kind is RowKind.TRANSLATION)
    for kind in RowKind:
        group = [row for row in laid.rows if row.row.kind is kind]
        assert len({row.top for row in group}) == 1
        for left, right in pairwise(group):
            assert (
                left.layout.lineAt(0).naturalTextRect().right()
                <= right.layout.lineAt(0).naturalTextRect().left()
            )
    font_height = original.layout.lineAt(0).height()
    assert (
        translation.top - (original.top + original.layout.boundingRect().height())
        < font_height
    )


def test_video_keeps_accepted_translation_until_the_finished_translation(
    windows: CaptionWindows,
) -> None:
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window = windows.windows["app"]
    live = replace(caption(1, live=True), clauses=(Clause("Good", {FR: "Bon"}),))
    windows.apply(live)
    assert [row.text for row in window.view.lines[-1].rows] == ["Good", "Bon"]
    finished = replace(caption(1), clauses=(Clause("Good evening."),))
    windows.apply(finished)
    assert [row.text for row in window.view.lines[-1].rows] == ["Good evening.", "Bon"]
    windows.apply(
        replace(finished, clauses=(Clause("Good evening.", {FR: "Bonsoir."}),))
    )
    assert [row.text for row in window.view.lines[-1].rows] == [
        "Good evening.",
        "Bonsoir.",
    ]


@pytest.mark.parametrize("height", [96, 210])
def test_live_video_reserves_its_translation_at_the_foot(
    windows: CaptionWindows,
    height: int,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((28 / 1080, 760 / 1920))
    window.set_text_size(28 / window.text_px())
    window.set_translation_size(22 / window.text_px())
    window.set_look(replace(window.look, show_source=False, show_language=False))
    window.resize(760, height)
    window.set_show_mic(False)
    window._show_band(False)
    live = caption(1, live=True)
    for clause in (Clause("Bonjour"), Clause("Bonjour", {FR: "Hello"})):
        windows.apply(replace(live, clauses=(clause,)))
        window.grab()
        _, laid, rect = window.canvas.placed[-1]
        original = next(r for r in laid.rows if r.row.kind is RowKind.ORIGINAL)
        box = (
            original.layout.lineAt(0)
            .naturalTextRect()
            .translated(
                rect.topLeft() + QPointF(0, original.top) + original.layout.position()
            )
        )
        assert box.x() == pytest.approx(10, abs=2)
        assert box.y() == pytest.approx(height - 78.1, abs=2)


def test_tiny_video_can_paint_a_caption_with_the_toolbar_and_footer_closed(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((28 / 1080, 560 / 1920))
    window.set_text_size(28 / window.text_px())
    window.set_translation_size(22 / window.text_px())
    window.set_look(replace(window.look, show_source=False, show_language=False))
    window.resize(560, 96)
    window.set_show_mic(False)
    window._show_band(False)
    windows.apply(replace(caption(1), clauses=(Clause("Bonjour", {FR: "Hello"}),)))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    advance_video(window, clock, 1.0)
    visible = [r for _, laid, _ in window.canvas.placed for r in laid.rows]
    assert {r.row.text for r in visible} == {"Bonjour", "Hello"}


def test_video_shows_every_subtitle_that_arrives_between_paints(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.set_text_size(1.0)
    window.set_translation_size(1.0)
    window.resize(440, 200)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(replace(caption(1), clauses=(Clause("One.", {FR: "Un."}),)))
    advance_video(window, clock, COVER_FADE_SEC)
    seen = [window.canvas.placed[-1][0].key]
    for n in range(2, 5):
        windows.apply(
            replace(caption(n), clauses=(Clause(f"Line {n}.", {FR: f"Ligne {n}."}),))
        )
    # At most Video's bounded reading hold per arrival, plus its entry.
    until = (
        clock.now + 3 * (HOLD_VIDEO_SEC.value + COVER_FADE_SEC) + CARD_READ_SEC.value
    )
    while len(seen) < 4 and clock.now < until:
        advance_video(window, clock, 0.1)
        for ln, _, _ in window.canvas.placed:
            if ln.key not in seen:
                seen.append(ln.key)
    assert seen == [line.key for line in window.view.lines]


@pytest.mark.parametrize("visible_captions", [1, 5])
def test_back_to_live_deals_the_waiting_subtitles_after_the_reader_returns(
    windows: CaptionWindows,
    visible_captions: int,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.resize(1000, 420)
    clock = windows.word_clock
    assert isinstance(clock, Clock)

    def add(n: int) -> None:
        windows.apply(
            replace(caption(n), clauses=(Clause(f"Word {n}.", {FR: f"Mot {n}."}),))
        )

    for n in range(1, visible_captions + 1):
        add(n)
        advance_video(window, clock, 4)
    wheel(window, 1)
    assert not window.view.scroll.following
    for n in (6, 7, 8):
        add(n)
    advance_video(window, clock, 4)
    window.go_live()
    pending = [line.key for line in window.view.lines][-3:]
    seen = []
    for _ in range(150):
        advance_video(window, clock, 0.1)
        for line, _, _ in window.canvas.placed:
            if line.key in pending and line.key not in seen:
                seen.append(line.key)
        if seen == pending:
            break
    assert seen == pending


def test_video_hover_return_wraps_a_finished_caption_without_a_ghost(
    windows: CaptionWindows,
) -> None:
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window = windows.windows["app"]
    window.set_look(
        replace(
            window.look,
            show_source=False,
            show_language=False,
            faces=(("en", "Arial"), ("fr", "Courier New")),
        )
    )
    window.set_text_size(63 / window.text_px())
    window.set_translation_size(61 / window.text_px())
    window.resize(1600, 645)
    clock = windows.word_clock
    assert isinstance(clock, Clock)

    original = "The report warns that nobody can guarantee the outcome of any action."
    translation = (
        "Le rapport avertit que personne ne peut garantir le resultat des mesures."
    )
    live = replace(caption(1, live=True), clauses=(Clause(original),))
    windows.apply(live)
    advance_video(window, clock, 0.5)
    assert window.canvas.tracks_visible
    window._hold()
    windows.apply(replace(caption(1), clauses=(Clause(original, {FR: translation}),)))
    windows.apply(replace(caption(2, live=True), clauses=(Clause("Next words."),)))
    window.grab()
    assert not window.canvas.tracks_visible
    window.leaveEvent(None)
    assert window._hold_timer.isActive()
    window._hold_timer.timeout.emit()

    saw_wrapped = False
    for _ in range(65):
        advance_video(window, clock, 0.04)
        flow = window.canvas.video.flow
        assert flow is not None and window.canvas.tracks_visible
        rows = [row for row in flow.rows() if row.copy.line.caption_id == "c1"]
        assert all(row.phase != "ghost" for row in rows)
        settled = [
            row.text for row in rows if row.translation and row.phase == "settled"
        ]
        if len(settled) > 1:
            assert "".join(settled) == translation
            saw_wrapped = True
    assert saw_wrapped


@pytest.mark.parametrize("mode", [CaptionMode.INSTANT, CaptionMode.SCROLLING])
def test_video_settles_a_caption_started_in_history_as_one_copy(
    windows: CaptionWindows, monkeypatch: pytest.MonkeyPatch, mode: CaptionMode
) -> None:
    windows.set_timing(mode)
    windows.set_subtitles((0.045, 0.8))
    window = windows.windows["app"]
    window.set_look(
        replace(
            window.look,
            show_source=False,
            show_language=False,
            faces=(("en", "Arial"), ("fr", "Courier New")),
        )
    )
    window.set_text_size(1)
    window.set_translation_size(1)
    window.resize(440, 220)
    clock = windows.word_clock
    assert isinstance(clock, Clock)

    for n in range(1, 9):
        windows.apply(replace(caption(n), clauses=(Clause(f"Line {n}."),)))
        advance_video(window, clock, 4)
    wheel(window, 1)
    window.grab()
    assert not window.view.scroll.following
    current = caption(9, live=True)
    windows.apply(current)
    advance_video(window, clock, 0.5)
    window.go_live()
    advance_video(window, clock, 1)

    video = window.canvas.video
    paint = CaptionLayout.paint
    probe = PaintInk()

    def observed(engine, painter, line, laid, at, ink, marks=None):
        paint(engine, painter, line, laid, at, ink, marks)
        if engine is window.canvas.engine and video.phase:
            probe.observe(
                painter,
                laid,
                at,
                ink,
                line.key,
                video.phase,
                video.fade_width,
                video.right_fade_width,
                video.row_start,
            )

    monkeypatch.setattr(CaptionLayout, "paint", observed)
    windows.apply(caption(9))
    key = window.view.lines[-1].key
    saw_settled = False
    duplicate_frames = overlap_frames = 0
    for _ in range(100):
        clock.now += 0.04
        probe.rows.clear()
        window.grab()
        duplicate_frames += probe.duplicates()
        overlap_frames += probe.overlaps()
        saw_settled |= any(
            r.caption == key and r.phase == "settled" for r in probe.rows
        )
    assert saw_settled
    assert overlap_frames == duplicate_frames == 0, (overlap_frames, duplicate_frames)


def test_video_keeps_the_translation_in_place_as_the_live_original_wraps(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.set_text_size(3)
    window.resize(1000, 420)
    update = caption(1, live=True)
    clock = windows.word_clock
    assert isinstance(clock, Clock)

    def translation_y(original: str) -> float:
        windows.apply(
            replace(update, clauses=(Clause(original, {FR: "La traduction."}),))
        )
        advance_video(window, clock, COVER_FADE_SEC)
        _, laid, rect = window.canvas.placed[-1]
        return rect.y() + next(
            row.top for row in laid.rows if row.row.kind is RowKind.TRANSLATION
        )

    first = translation_y("A short line")
    assert translation_y(
        "A short line which became a considerably longer sentence while it was being read."
    ) == pytest.approx(first)


@pytest.mark.parametrize("mode", [CaptionMode.SCROLLING, CaptionMode.INSTANT])
def test_video_own_speech_keeps_subtitle_slots_and_font(
    windows: CaptionWindows, mode: CaptionMode
) -> None:
    window = windows.windows["app"]
    windows.set_timing(mode)
    windows.set_subtitles((0.045, 0.8))
    window.resize(1000, 420)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(caption(1))
    advance_video(window, clock, 3.0)

    def geometry() -> list[tuple[int, float, float, list[int]]]:
        return [
            (
                line.key,
                rect.x(),
                rect.y(),
                [r.layout.font().pixelSize() for r in laid.rows],
            )
            for line, laid, rect in window.canvas.placed
        ]

    before = geometry()
    assert before
    ink = window.canvas.placed[-1][2].toAlignedRect()
    original_pixels = window.canvas.grab(ink).toImage()
    window.set_show_mic(True)
    windows.apply(replace(caption(2), source_id=MIC))
    # Compare the same instant, including when the film itself is panning.
    window.grab()
    assert geometry() == before
    assert window.canvas.own_subtitle() == window.view.lines[-1]
    assert window.canvas.grab(ink).toImage() == original_pixels
    window.set_show_mic(False)
    window.grab()
    assert window.canvas.own_subtitle() is None
    assert geometry() == before


def test_video_window_growth_keeps_the_existing_reading_baseline(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.set_text_size(2.0)
    window.resize(800, 360)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(replace(caption(1), clauses=(Clause("Bonjour", {FR: "Hello"}),)))
    advance_video(window, clock, 1.0)
    _, before, box = window.canvas.placed[-1]
    start = box.topLeft()
    window.resize(1200, 620)
    window.grab()
    _, after, box = window.canvas.placed[-1]
    assert after.rows[0].layout.font() == before.rows[0].layout.font()
    assert box.topLeft() == start
    positions = [start]
    for _ in range(100):
        clock.now += 0.02
        window.grab()
        positions.append(window.canvas.placed[-1][2].topLeft())
    distances = [hypot(b.x() - a.x(), b.y() - a.y()) for a, b in pairwise(positions)]
    assert all(b.y() <= a.y() + 0.01 for a, b in pairwise(positions))
    assert max(distances) <= GLIDE_FASTEST.value * 0.02


def test_late_clause_waits_for_clear_room_without_jumping_the_visible_words(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    windows.set_look(replace(window.look, show_source=False, show_language=False))
    window.resize(1000, 500)
    window.set_text_size(2.0)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    windows.apply(replace(caption(1), clauses=(Clause("One.", {FR: "Un."}),)))
    advance_video(window, clock, COVER_FADE_SEC)
    short = Clause("Two.", {FR: "Deux."})
    windows.apply(replace(caption(2), clauses=(short,)))
    second = window.view.lines[-1].key
    for _ in range(90):
        advance_video(window, clock, 0.02)
        if window.canvas.placed[-1][0].key == second:
            break
    assert window.canvas.placed[-1][0].key == second
    previous_y = window.canvas.placed[-1][2].y()
    windows.apply(replace(caption(2), clauses=(short, Clause("Three."))))
    window.grab()
    assert window.canvas.placed[-1][2].y() == pytest.approx(previous_y, abs=0.01)
    saw_extra = False
    for _ in range(80):
        advance_video(window, clock, 0.02)
        line, laid, box = window.canvas.placed[-1]
        assert line.key == second
        distance = previous_y - box.y()
        assert distance >= -0.01
        assert box.bottom() <= PAD + window.canvas._seen_height() + 0.5
        previous_y = box.y()
        saw_extra |= any(row.row.text == "Three." for row in laid.rows)
    assert saw_extra


def test_appended_subtitle_keeps_the_page_and_time_already_being_read(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.SCROLLING)
    windows.set_subtitles((0.045, 0.8))
    window.resize(440, 200)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    original = Clause("a long original " * 90, {FR: "sa traduction " * 100})
    windows.apply(replace(caption(1), clauses=(original,)))
    # The live track reveals its words and glides to the tail.
    for _ in range(800):
        advance_video(window, clock, 0.04)
        flow = window.canvas.video.flow
        if (
            flow is not None
            and len(flow.slots) == 2
            and flow.read_until is not None
            and not flow.animating
        ):
            break
    advance_video(window, clock, 1.0)
    flow = window.canvas.video.flow
    assert flow is not None and len(flow.slots) == 2
    before = {r.translation: r.x for r in flow.rows()}
    assert all(x > 0 for x in before.values())
    deadline = flow.read_until
    assert deadline is not None
    windows.apply(replace(caption(1), clauses=(original, Clause("The last sentence."))))
    window.grab()
    assert {r.translation: r.x for r in flow.rows()} == pytest.approx(before)
    assert flow.read_until == deadline


def test_shrinking_video_with_two_occupied_tracks_preserves_one_reading_slot(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.set_look(replace(window.look, show_source=False, show_language=False))
    window.set_text_size(3)
    window.set_translation_size(2)
    window.resize(1100, 660)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    first = replace(
        caption(1), clauses=(Clause("First sentence.", {FR: "Première phrase."}),)
    )
    second = replace(caption(2, live=True), clauses=(Clause("Another sentence."),))
    windows.apply(first)
    advance_video(window, clock, 0.45)
    windows.apply(second)
    advance_video(window, clock, 1.3)
    assert len(window.canvas.placed) == 2
    assert {row.row.kind for row in window.canvas.placed[0][1].rows} == {
        RowKind.ORIGINAL,
        RowKind.TRANSLATION,
    }

    window.resize(440, 200)
    seen: set[int] = set()
    for _ in range(45):
        advance_video(window, clock, 0.04)
        slots = window.canvas.placed
        seen.update(line.key for line, _, _ in slots)
        for (_, _, upper), (_, _, lower) in pairwise(slots):
            assert upper.bottom() <= lower.top() + 0.01
    assert max(seen) == window.view.lines[-1].key


def test_resize_keeps_the_font_of_a_translation_still_being_read(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["app"]
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_subtitles((0.045, 0.8))
    window.set_look(
        replace(
            window.look,
            show_source=False,
            show_language=False,
            faces=(("en", "Courier New"), ("fr", "Arial")),
        )
    )
    window.resize(1200, 600)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    first = replace(
        caption(1),
        clauses=(
            Clause("The river.", {FR: "Le fleuve."}),
            Clause("Its width.", {FR: "Sa largeur."}),
        ),
    )
    windows.apply(first)
    advance_video(window, clock, 0.4)
    tracks = window.canvas.video
    text = "Le fleuve. Sa largeur."
    expected = tracks.measure(text, True)
    windows.apply(
        replace(caption(2, translated=False, live=True), clauses=(Clause("Next."),))
    )
    window.grab()
    assert tracks.measure(text, True) == pytest.approx(expected)
    window.resize(850, 500)
    window.grab()
    assert tracks.flow is not None
    assert any(row.translation and row.text == text for row in tracks.flow.rows())
    assert tracks.measure(text, True) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("mode", "path"),
    [
        (CaptionMode.INSTANT, ReadingPath.BOTH),
        (CaptionMode.INSTANT, ReadingPath.ACQUISITION),
        (CaptionMode.STEADY, ReadingPath.ACQUISITION),
    ],
    ids=["everyday", "learning-instant", "learning-steady"],
)
def test_arriving_translation_keeps_the_caption_stack_in_place(
    windows: CaptionWindows, mode: CaptionMode, path: ReadingPath
) -> None:
    windows.set_timing(mode)
    windows.set_path(path)
    window = windows.windows["app"]
    first = replace(caption(1), clauses=(Clause("Good morning.", {FR: "Bonjour."}),))
    original = replace(caption(2), clauses=(Clause("Good evening."),))
    translated = replace(original, clauses=(Clause("Good evening.", {FR: "Bonsoir."}),))
    say(windows, first)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    clock.now += NEW_CARD_AFTER_SEC.value + 0.5
    window.receive(original)
    # Capture the destination from the first scroll, even if it is still moving.
    before = window.canvas.rest_rows()
    key = window.view.lines[-1].key
    assert any(line_key < key for line_key, _ in before)
    clock.now += 0.35
    window.receive(translated)
    clock.now += 1
    window.check_card_room()
    after = window.canvas.rest_rows()
    assert any(row.kind is RowKind.TRANSLATION for row in window.view.lines[-1].rows)
    assert {row: after[row] for row in before} == pytest.approx(before, abs=1)
    assert window.canvas._laid(window.view.lines[-1]).height <= window.canvas._tall(
        window.view.lines[-1]
    )


@pytest.mark.parametrize("mode", [CaptionMode.INSTANT, CaptionMode.STEADY])
def test_unfilled_translation_space_closes_gradually(
    windows: CaptionWindows, mode: CaptionMode
) -> None:
    windows.set_timing(mode)
    first = replace(caption(1), clauses=(Clause("Good morning.", {FR: "Bonjour."}),))
    window = say(windows, first)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    window.receive(replace(caption(2), clauses=(Clause("Good evening."),)))
    canvas = window.canvas
    line = window.view.lines[-1]
    bare = canvas.laid_at(line, canvas._width()).height
    reserved = canvas._tall(line)
    assert window._translation_expiry.isActive()
    assert reserved > bare
    clock.now += TRANSLATION_WAIT_SEC.value
    assert canvas._tall(line) == pytest.approx(reserved)
    clock.now += 0.1
    window._close_translation_gaps()
    assert bare < canvas._tall(line) < reserved
    clock.now += 1
    window._close_translation_gaps()
    assert canvas._tall(line) == pytest.approx(bare)


@pytest.mark.parametrize("mode", [CaptionMode.INSTANT, CaptionMode.STEADY])
def test_live_caption_keeps_room_until_its_finished_translation(
    windows: CaptionWindows, mode: CaptionMode
) -> None:
    """A long live caption must not lose its slot before translation arrives."""
    windows.set_timing(mode)
    window = say(windows, caption(1))
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    live = replace(
        caption(2, translated=False, live=True),
        clauses=(Clause("Good evening."),),
    )
    window.receive(live)
    line = window.view.lines[-1]
    reserved = window.canvas._tall(line)
    bare = window.canvas.laid_at(line, window.canvas._width()).height
    assert reserved > bare

    clock.now += TRANSLATION_WAIT_SEC.value + 1.0
    window._close_translation_gaps()
    assert window.canvas._tall(window.view.lines[-1]) == pytest.approx(reserved)

    before = window.canvas.rest_rows()
    finished = replace(
        live,
        kind=CaptionKind.FINISHED,
        clauses=(Clause("Good evening.", {FR: "Bonsoir."}),),
    )
    window.receive(finished)
    after = window.canvas.rest_rows()
    assert any(row.kind is RowKind.TRANSLATION for row in window.view.lines[-1].rows)
    assert {row: after[row] for row in before} == pytest.approx(before, abs=1)


@pytest.mark.parametrize("mode", [CaptionMode.INSTANT, CaptionMode.STEADY])
def test_new_caption_enters_with_every_estimated_translation_row(
    windows: CaptionWindows, mode: CaptionMode
) -> None:
    """The first slide reserves the translation, not a later reflow."""
    windows.set_timing(mode)
    window = windows.windows["app"]
    window.resize(360, 460)
    original = "A deliberately long opening caption " * 2
    window.receive(
        replace(
            caption(1, translated=False),
            clauses=(Clause(original),),
        )
    )

    line = window.view.lines[-1]
    shown = " ".join(row.text for row in line.rows if row.kind is RowKind.ORIGINAL)
    bare = window.canvas.laid_at(line, window.canvas._width()).height
    room = window._translation_room()
    estimated = max(
        1,
        ceil(
            window._measure(shown, False)
            * TRANSLATION_WIDTH_RATIO.value
            / window.canvas._width()
        ),
    )
    expected = min(estimated, int((window.canvas._seen_height() - bare) // room))
    reserved = window.canvas._tall(line)

    assert expected >= 2
    assert reserved >= bare + expected * room - 1


def test_original_only_arrival_has_no_translation_gap(windows: CaptionWindows) -> None:
    windows.set_timing(CaptionMode.INSTANT)
    window = windows.windows["app"]
    window.set_language("")
    window.receive(caption(1, translated=False))
    canvas = window.canvas
    line = window.view.lines[-1]
    assert canvas._tall(line) == canvas._laid(line).height
    assert not window._translation_expiry.isActive()


def test_wrapped_translation_fills_the_space_below_its_own_clause(
    windows: CaptionWindows,
) -> None:
    windows.set_timing(CaptionMode.INSTANT)
    first = replace(caption(1), clauses=(Clause("Good morning.", {FR: "Bonjour."}),))
    window = say(windows, first)
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    long_original = "One two three four five six seven."
    long_translation = "Un, deux, trois, quatre, cinq, six, sept. " * 2
    original = replace(
        caption(2), clauses=(Clause(long_original), Clause("Good evening."))
    )
    translated = replace(
        original,
        clauses=(
            Clause(long_original, {FR: long_translation}),
            Clause("Good evening.", {FR: "Bonsoir."}),
        ),
    )

    def positions() -> tuple[float, dict[str, float]]:
        line = window.view.lines[-1]
        laid = window.canvas._laid(line)
        return laid.height, {
            row.row.text: row.top
            for row in laid.rows
            if row.row.kind is RowKind.ORIGINAL
        }

    window.receive(original)
    height, row_tops = positions()
    clock.now += 0.35
    window.receive(translated)
    laid = window.canvas._laid(window.view.lines[-1])
    wrapped = next(row for row in laid.rows if row.row.kind is RowKind.TRANSLATION)
    assert wrapped.layout.lineCount() == 2
    assert positions() == (height, row_tops)
