"""Steady's two zones (polyglotic-hq 526, decision 0251): the live reading
lines at the foot of a caption window and the settled transcript above; a
caption hands off when its last line has rolled out of the live zone."""

import itertools
import math
from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from tests.ui_next.test_lookup_card import AREA

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    SpeechTimes,
)
from polyglotic_desktop.core.listening.playout import Ahead, PlayoutRules
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.lab import CAPTION_GAP_RANGE
from polyglotic_desktop.ui_next.views.zones import (
    LIVE_LINES_CONVERSATION,
    LIVE_LINES_MONOLOGUE,
    Zones,
)

EN = Language("en")
FR = Language("fr")
SAID = "the quick brown fox jumps over the lazy dog and runs far away again"


def caption(n: int, source: SourceId = APP, text: str = SAID) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(f"c{n}"), source, CaptionKind.FINISHED,
        (Clause(f"{n} {text}.", {FR: f"{n} le renard brun saute par-dessus le chien."}),),
        EN, (EN,), times=SpeechTimes(n, n + 1.0, n + 1.0, n + 1.1),
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
    found.set_cards(False)  # the card stack takes their place (decision 0260)
    found.set_timing(CaptionMode.STEADY)
    found.windows["app"].resize(900, 460)
    yield found
    found.close()


def say(windows: CaptionWindows, *updates: CaptionUpdate) -> CaptionWindow:
    clock = windows.word_clock
    assert isinstance(clock, Clock)
    for update in updates:
        windows.apply(update)
        while windows.playout.due() is not None:  # every word's moment comes
            clock.now += 1.0
            windows.release_words()
    window = windows.windows["app"]
    window.grab()  # painted: what is placed is what is drawn
    return window


def test_a_paced_mode_shows_two_zones_and_the_others_one_list(
    windows: CaptionWindows,
) -> None:
    window = say(windows, caption(1))
    assert window.zones is not None and not window.zone.isHidden()
    assert window.zone.geometry().bottom() <= window.height()
    # the caption being read is in the live zone, not the transcript
    assert [ln.caption_id for ln, _, _ in window.zone.placed] == ["c1"]
    assert window.canvas.placed == []
    windows.set_timing(CaptionMode.WHOLE)
    window.grab()
    assert window.zones is None and window.zone.isHidden()
    assert [ln.caption_id for ln, _, _ in window.canvas.placed] == ["c1"]
    assert window.zone_room() == 0.0


def test_steadys_layout_names_the_language_once(windows: CaptionWindows) -> None:
    window = say(windows, caption(1), caption(2), caption(3))
    assert [bool(line.label) for line in window.view.lines] == [True, False, False]
    windows.set_timing(CaptionMode.WHOLE)  # the other modes: over each, as before
    assert [bool(line.label) for line in window.view.lines] == [True, True, True]


def test_the_learner_can_turn_two_zones_off(windows: CaptionWindows) -> None:
    windows.set_two_zones(False)
    window = say(windows, caption(1))
    assert window.zones is None
    assert [ln.caption_id for ln, _, _ in window.canvas.placed] == ["c1"]
    windows.set_two_zones(True)
    assert window.zones is not None


def test_a_caption_settles_when_its_last_line_has_rolled_out(
    windows: CaptionWindows,
) -> None:
    window = say(windows, *(caption(n) for n in range(1, 13)))
    zones = window.zones
    assert zones is not None
    above = [ln.caption_id for ln, _, _ in window.canvas.placed]
    below = [ln.caption_id for ln, _, _ in window.zone.placed]
    assert above and below
    assert not set(above) & set(below)  # never drawn twice
    assert below[0] == "c12"  # newest first, at the foot
    # in order: everything in the transcript is older than everything live
    number = lambda caption_id: int(caption_id[1:])
    assert max(map(number, above)) < min(map(number, below))
    # the handoff is by line: a live caption still has a line in the zone,
    # and no settled one has
    for line, laid, rect in window.zone.placed:
        assert rect.y() + laid.height > 0.5
        assert line.key not in zones.settled
    # the live zone holds its lines and no more
    # Font metrics are fractional on Cocoa. A QWidget occupies whole logical pixels.
    limit = window.zone.line_height() * LIVE_LINES_MONOLOGUE + 3
    assert window.zone.height() <= math.ceil(limit)


def test_each_live_caption_starts_a_line_and_a_pause_settles_them(
    windows: CaptionWindows,
) -> None:
    """548's picture, 2026-11-20: a caption began in the middle of a line,
    after the one it ran on from had settled."""
    window = say(windows, caption(1, text="short"), caption(2, text="one"))
    assert [laid.lead for _, laid, _ in window.zone.placed] == [0.0, 0.0]
    window._zone_paused()  # nothing new for 5 s
    assert window.zones is not None
    assert {ln.key for ln in window.view.lines} <= window.zones.settled
    window = say(windows, caption(3, text="after"))
    (third,) = (laid for _, laid, _ in window.zone.placed)
    assert third.lead == 0.0
    assert [ln.caption_id for ln, _, _ in window.canvas.placed] == ["c1", "c2"]


def test_after_a_pause_the_transcript_has_the_window(windows: CaptionWindows) -> None:
    """548's pictures, 2026-11-20: at the end of speech the live zone was
    empty and still took its lines, and the transcript above showed only
    the last caption's translation."""
    window = windows.windows["app"]
    window.set_language("fr")
    say(windows, *(caption(n) for n in range(1, 6)))
    window._zone_paused()
    window.grab()
    assert window.zone.height() == 0 and window.zone_room() == 0.0
    drawn = window.canvas.placed
    assert [ln.caption_id for ln, _, _ in drawn][-3:] == ["c3", "c4", "c5"]
    clear = window.canvas.clear_top
    for _, laid, rect in drawn[-3:]:  # each with what was said and its translation
        assert rect.top() >= clear - 0.5 and rect.bottom() <= window.height()
        assert {row.row.kind.value for row in laid.rows} == {"original", "translation"}
    window = say(windows, caption(6))  # speech again: the zone is back
    assert window.zone.height() > 0


def test_a_long_captions_first_line_stays_until_it_hands_off(
    windows: CaptionWindows,
) -> None:
    """548's picture, 2026-11-20: a long caption's first row had scrolled
    out of the live zone before the caption handed off. The zone is taller
    while a caption that began above its lines is still read."""
    window = windows.windows["app"]
    window.set_language("fr")
    window.resize(520, 620)
    long = " ".join([SAID] * 3)
    zones = window.zones
    assert zones is not None
    for n in range(1, 7):
        window = say(windows, caption(n, text=long if n % 2 else SAID))
        top = window.zone.clear_top
        for line, _, rect in window.zone.placed:  # none with its start cut off
            assert rect.top() >= top - 0.5, (n, line.caption_id)
        shown = {ln.key for ln, _, _ in window.zone.placed}
        assert shown | zones.settled >= {ln.key for ln in window.view.lines}
    assert window.zone.height() >= window.zone.lines_tall
    assert zones.settled  # and they do hand off


def test_a_word_in_the_live_zone_can_be_pointed_at(windows: CaptionWindows) -> None:
    window = say(windows, caption(1))
    ((line, laid, rect),) = window.placed()
    assert rect.y() >= window.zone.y()  # in the window's coordinates
    row = laid.rows[0]
    found = window.canvas.hit(QPointF(rect.x() + 12.0, rect.y() + row.top + 8.0))
    assert found is not None and found[0].key == line.key
    assert window.canvas.shown_row(line.key, row.index) is not None


def test_two_speakers_make_the_live_zone_a_line_shorter() -> None:
    zones = Zones()
    zones.heard(("app", False), 10.0)
    assert zones.live_lines(12.0) == LIVE_LINES_MONOLOGUE
    zones.heard(("mic", True), 20.0)
    assert zones.live_lines(21.0) == LIVE_LINES_CONVERSATION
    assert zones.live_lines(75.0) == LIVE_LINES_MONOLOGUE  # the app's turn was long ago


def test_zones_forget_what_left_the_window() -> None:
    zones = Zones()
    assert zones.settle([1, 2]) and not zones.settle([2])
    assert zones.pause({1, 2, 3}) and zones.ended == {3}
    assert not zones.pause({1, 2, 3})
    zones.keep({3, 4})
    assert zones.settled == {3} and zones.ended == {3}


def test_karaoke_draws_the_waiting_words_faint(windows: CaptionWindows) -> None:
    window = windows.windows["app"]
    assert not window.faint_ahead
    windows.set_playout(PlayoutRules(delay=0.0, ahead=Ahead.WAITING))
    assert window.faint_ahead
    say(windows, caption(1))  # painted with it
    windows.set_timing(CaptionMode.INSTANT)  # only the paced modes' words wait
    assert not window.faint_ahead


def test_a_line_in_the_live_zone_only_grows(windows: CaptionWindows) -> None:
    """Lines only grow (DECISIONS #230 item 3): as a caption's words come,
    the rows already there stay where they are."""
    words = (SAID + " " + SAID + " " + SAID).split()
    window = windows.windows["app"]
    tops: dict[int, float] = {}
    for n in range(4, len(words) + 1, 3):
        update = CaptionUpdate(
            CaptionId("grows"), APP, CaptionKind.LIVE, (Clause(" ".join(words[:n])),),
            EN, (EN,), times=SpeechTimes(0.0, 9.0, 9.0, 9.1), established=10_000,
        )  # fmt: skip
        say(windows, update)
        ((_, laid, _),) = window.zone.placed
        now = {row.index: row.top for row in laid.rows}
        for index, top in tops.items():
            assert now[index] == top
        assert len(now) >= len(tops)
        tops = now
    assert len(laid.breaks) > 1  # it ran over a line


ZH = Language("zh")
LONG = (
    "the quick brown fox jumps over the lazy dog and runs far away again and "
    "again until the night comes down over the hills"
)


def spoken(
    n: int, kind: CaptionKind = CaptionKind.FINISHED, words: int = 99
) -> CaptionUpdate:
    """A long caption, every third in another language: its label comes
    again in the live paragraph, which is then no whole number of lines."""
    language = EN if n % 3 == 0 else ZH
    text = " ".join(LONG.split()[:words])
    return CaptionUpdate(
        CaptionId(f"c{n}"), APP, kind,
        (Clause(f"{n} {text}.", {FR: f"{n} le renard brun saute et court loin."}),),
        language, (language,), times=SpeechTimes(n, n + 1.0, n + 1.0, n + 1.1),
    )  # fmt: skip


def text_lines(window: CaptionWindow) -> list[tuple[float, float]]:
    """Every line of text the live zone lays out: its top and foot there."""
    found = []
    for _, laid, rect in window.zone.placed:
        for row in laid.rows:
            for n in range(row.layout.lineCount()):
                line = row.layout.lineAt(n)
                top = rect.top() + row.top + line.y()
                found.append((top, top + line.height()))
    return found


@pytest.mark.parametrize("size", [(1000, 420), (900, 460), (640, 380)])
def test_the_live_zone_never_shows_a_line_cut_through(
    windows: CaptionWindows, size: tuple[int, int]
) -> None:
    """The coordinator on 346's pictures, 2026-11-20: half a line of text
    showed at the divider. The zone's text starts at a whole line, and a
    caption wholly above that has handed off."""
    windows.windows["app"].resize(*size)
    cut_at = []
    for n in range(1, 10):
        for words in (3, 9, 15):
            say(windows, spoken(n, CaptionKind.LIVE, words))
        window = say(windows, spoken(n))
        top = window.zone.clear_top
        cut_at += [
            (n, round(a), round(b)) for a, b in text_lines(window) if a < top - 0.5 < b - 1
        ]  # fmt: skip
        zones = window.zones
        assert zones is not None
        hidden = [
            line.key
            for line, laid, rect in window.zone.placed
            if rect.bottom() <= top and not line.live
        ]
        assert set(hidden) <= zones.settled, (n, hidden)
    assert not cut_at


def settled_drawn(window: CaptionWindow) -> list[tuple[int, float, float]]:
    """Each settled caption drawn: its key, top and foot in the window."""
    return [
        (line.key, rect.top(), rect.bottom()) for line, _, rect in window.canvas.placed
    ]


@pytest.mark.parametrize("size", [(900, 460), (1000, 420), (700, 600), (960, 395)])
def test_the_transcript_fills_the_space_above_the_live_zone_with_whole_captions(
    windows: CaptionWindows, size: tuple[int, int]
) -> None:
    """The coordinator on 346's pictures, 2026-11-20: a settled caption was
    cut off at the divider, and the top of the window was empty while
    earlier captions existed."""
    windows.windows["app"].resize(*size)
    windows.windows["app"].set_language("fr")  # two rows a caption
    window = say(windows, *(caption(n) for n in range(1, 13)))
    zones = window.zones
    assert zones is not None and len(zones.settled) >= 6
    drawn = settled_drawn(window)
    top_of_zone = float(window.zone.y())
    assert drawn
    # whole captions: none starts above where the transcript's text does
    clear = window.canvas.clear_top
    showing = [(key, top) for key, top, foot in drawn if foot > clear + 0.5]
    assert all(top >= clear - 0.5 for _, top in showing), (showing, clear)
    drawn = [each for each in drawn if each[2] > clear + 0.5]
    # never one cut off at the divider: each drawn caption ends above it
    assert all(foot <= top_of_zone + 0.5 for _, _, foot in drawn), (drawn, top_of_zone)
    # the newest settled caption is the one just above the divider
    assert drawn[-1][0] == max(zones.settled)
    assert top_of_zone - drawn[-1][2] < window.zone.line_height()
    # never an empty top while earlier captions exist: they reach up to
    # within a caption of where captions may start (under the bar's band)
    tallest = max(foot - top for _, top, foot in drawn)
    assert drawn[0][1] - window.canvas.clear_top < tallest + 12, drawn


@pytest.mark.parametrize("caption_gap", [None, CAPTION_GAP_RANGE[1]])
def test_a_live_line_is_a_whole_pair_tall(
    windows: CaptionWindows, caption_gap: float | None
) -> None:
    """The zone's height is so many lines: a line is what was said and
    its translation with the gap under them - it was a pair less its gap,
    and three "lines" held 2.2 (the lab's picture, 2026-11-20). The gap
    under a caption's last pair is the one between captions, the Lab's
    own (559: 66 for a pitch of 68 once Latin took the Latin face)."""
    if caption_gap is not None:  # the Lab's widest space between captions
        lab = replace(windows.look.lab, caption_gap=caption_gap)
        windows.set_look(replace(windows.look, lab=lab))
    window = windows.windows["app"]
    window.set_language("fr")
    say(windows, *(spoken(n) for n in range(1, 6)))
    said = sorted(
        rect.top() + row.top + row.layout.lineAt(n).y()
        for _, laid, rect in window.zone.placed
        for row in laid.rows
        if row.row.kind.value == "original"
        for n in range(row.layout.lineCount())
    )
    pitch = max(b - a for a, b in itertools.pairwise(said))
    assert window.zone.line_height() >= pitch - 0.5


def test_no_room_above_the_live_zone_shows_no_part_of_a_caption(
    windows: CaptionWindows,
) -> None:
    """The lab's picture, 2026-11-20: with room for less than a caption
    above the live zone, the newest settled caption's translation stood
    there alone."""
    window = windows.windows["app"]
    window.set_language("fr")
    say(windows, *(caption(n) for n in range(1, 8)))
    for height in range(240, 480, 3):  # every room there could be above it
        window.resize(900, height)
        window.grab()
        clear = window.canvas.clear_top
        for line, _, rect in window.canvas.placed:
            if rect.bottom() > clear + 0.5:  # drawn at all: from its start
                assert rect.top() >= clear - 0.5, (height, line.caption_id)
