"""Steady in the caption windows (polyglotic-hq 526, decisions 0245 and
0246): a paced mode's caption updates go through the playout, so a
window shows each word when its time comes; the other modes show every
update as it comes."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_lookup_card import AREA

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    SpeechTimes,
)
from polyglotic_desktop.core.listening.display import LIVE_TRAIL, RowKind
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.playout import Ahead, PlayoutRules
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.ui.captions import CaptionFeed
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows

EN = Language("en")
ONE = CaptionId("one")


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def said(windows: CaptionWindows) -> list[str]:
    """What the window shows: each caption's original text."""
    lines = windows.windows["app"].view.lines
    return [
        "".join(
            row.text for row in line.rows if row.kind is RowKind.ORIGINAL
        ).removesuffix(LIVE_TRAIL)
        for line in lines
    ]


def live(text: str, start: float, end: float) -> CaptionUpdate:
    return CaptionUpdate(
        ONE, APP, CaptionKind.LIVE, (Clause(text),), EN, (EN,),
        times=SpeechTimes(start, end, end, end + 0.1),
    )  # fmt: skip


def finished(text: str, start: float, end: float) -> CaptionUpdate:
    return CaptionUpdate(
        ONE, APP, CaptionKind.FINISHED, (Clause(text, {EN: "..."}),), EN, (EN,),
        times=SpeechTimes(start, end, end, end + 0.1),
    )  # fmt: skip


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def windows(qapp: QApplication, clock: Clock) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, lambda: [AREA])
    found.set_cards(False)  # the playout through the one list; cards: test_card_stack
    found.word_clock = clock
    found.set_captioned([("app", APP)])
    found.set_playout(PlayoutRules(delay=2.0))
    yield found
    found.close()


def test_steady_shows_a_word_when_its_time_comes(
    windows: CaptionWindows, clock: Clock
) -> None:
    windows.set_timing(CaptionMode.STEADY)
    windows.apply(live("cat dog bird fish", 98.0, 100.0))  # said over the last 2 s
    assert (
        said(windows) == []
    )  # nothing yet: the first word is due 2 s after it was said
    assert windows._word_due.isActive()
    clock.now = 100.3
    windows.release_words()
    assert said(windows) == ["cat"]
    clock.now = 100.8
    windows.release_words()
    assert said(windows) == ["cat dog"]
    clock.now = 101.5
    windows.release_words()
    assert said(windows) == [
        "cat dog bird"
    ]  # the newest word waits for the next update
    assert not windows._word_due.isActive()
    windows.apply(finished("cat dog bird fish.", 98.0, 100.2))
    clock.now = 103.0
    windows.release_words()
    assert said(windows) == ["cat dog bird fish."]
    assert (
        not windows.windows["app"].view.lines[0].live
    )  # the server's finished caption


def test_karaoke_shows_the_waiting_words_at_once(
    windows: CaptionWindows, clock: Clock
) -> None:
    windows.set_timing(CaptionMode.STEADY)
    windows.set_playout(PlayoutRules(delay=2.0, ahead=Ahead.WAITING))
    windows.apply(live("cat dog bird fish", 98.0, 100.0))
    assert said(windows) == ["cat dog bird"]


@pytest.mark.parametrize("mode", [CaptionMode.WHOLE, CaptionMode.INSTANT])
def test_the_other_modes_show_every_update_as_it_comes(
    windows: CaptionWindows, mode: CaptionMode
) -> None:
    windows.set_timing(mode)
    windows.apply(live("cat dog bird fish", 98.0, 100.0))
    assert said(windows) == ["cat dog bird fish"]
    assert not windows._word_due.isActive()


def test_leaving_steady_shows_what_was_waiting(
    windows: CaptionWindows, clock: Clock
) -> None:
    windows.set_timing(CaptionMode.STEADY)
    windows.apply(live("cat dog bird fish", 98.0, 100.0))
    windows.set_timing(CaptionMode.INSTANT)
    assert said(windows) == ["cat dog bird fish"]
    assert not windows._word_due.isActive()
    assert windows.playout.due() is None


def test_calm_shows_only_established_words(
    windows: CaptionWindows, clock: Clock
) -> None:
    windows.set_timing(CaptionMode.CALM)
    windows.set_playout(PlayoutRules(delay=2.0, established_only=True))
    update = live("cat dog bird fish", 98.0, 100.0)
    windows.apply(replace(update, established=len("cat dog")))
    clock.now = 110.0
    windows.release_words()
    assert said(windows) == ["cat"]
    clock.now += 0.5
    windows.release_words()
    assert said(windows) == ["cat dog"]


def trails(windows: CaptionWindows) -> bool:
    lines = windows.windows["app"].view.lines
    return any(row.text.endswith(LIVE_TRAIL) for line in lines for row in line.rows)


def test_a_paced_modes_live_caption_doesnt_trail_off(
    windows: CaptionWindows, clock: Clock
) -> None:
    """Steady's words come one by one, the next always on its way: no " …"
    after the newest (the coordinator, 2026-11-20). Instant still trails."""
    windows.set_timing(CaptionMode.STEADY)
    windows.apply(live("one two three four", 100.0, 101.0))
    clock.now = 110.0
    windows.release_words()
    assert said(windows) and not trails(windows)
    windows.set_timing(CaptionMode.INSTANT)
    windows.apply(live("one two three four five", 100.0, 102.0))
    assert trails(windows)
    windows.set_timing(CaptionMode.STEADY)
    assert not trails(windows)


def test_a_paced_continuation_retires_its_live_line_when_cards_are_off(
    windows: CaptionWindows,
    clock: Clock,
) -> None:
    windows.set_timing(CaptionMode.STEADY)
    feed = CaptionFeed(CaptionHistory(), None)
    feed.applied.connect(windows.apply)
    feed.apply(finished("Currently in.", 90.0, 91.0))
    while (due := windows.playout.due()) is not None:
        clock.now = max(clock.now, due)
        windows.release_words()
    clock.now = 105
    later = CaptionId("later")
    feed.apply(replace(live("Paris again", 105, 106), caption_id=later))
    clock.now = 110
    windows.release_words()
    assert len(said(windows)) == 2
    feed.apply(
        replace(
            finished("Currently in Paris again.", 105, 111),
            caption_id=later,
            continues=ONE,
        )
    )
    while (due := windows.playout.due()) is not None:
        clock.now = max(clock.now, due)
        windows.release_words()
    assert said(windows) == ["Currently in Paris again."]
