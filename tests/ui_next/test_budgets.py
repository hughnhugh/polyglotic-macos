"""The new caption surfaces against the interface's budgets (polyglotic-hq
DECISIONS.md #53, `perf.budgets`), offscreen, with 1,000 captions: a
resize step, a text-size change and a new caption - W1, the caption
window: a resize step, a text size step, a new caption, a language switch
and the hover band - and W3, the lookup, on the sample dictionary: shown
after the hover delay, pinned, and a Learning action.

Each action is timed as the interface thread does it - the change and
the paint it causes - after a warm-up pass, with the garbage collector held
off; its median is held to the budget and any one run to the slot budget
(50 ms), with one retry that reports both tries (`tests/budget_judge.py`).
"""

import itertools
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QWidget
from tests import budget_judge
from tests.budget_judge import Sampled, sampled, within
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import EN, finished_updates

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_surface import PAD, CaptionSurface
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, Marked, _Drag
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.lookup_card import LookupCard
from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
from polyglotic_desktop.ui_next.views.captions import (
    CAPTION_WINDOW_LINES,
    TRANSCRIPT_LINES,
    CaptionLines,
)
from polyglotic_desktop.ui_next.views.lookup import WordAt
from polyglotic_desktop.ui_next.views.placement import Edge, Rect
from tools import busy_pc

CAPTIONS = 1_000
CAPTION_WINDOW = (800, 260)
TRANSCRIPT = (900, 600)


def surface_of(keep: int, size: tuple[int, int], qapp: QApplication) -> CaptionSurface:
    view = CaptionLines((APP,), EN, keep=keep)
    for update in finished_updates(CAPTIONS):
        view.apply(update)
    surface = CaptionSurface(view)
    surface.resize(*size)
    surface.show()
    qapp.processEvents()
    surface.repaint()
    return surface


@pytest.fixture
def caption_window(qapp: QApplication) -> Iterator[CaptionSurface]:
    surface = surface_of(CAPTION_WINDOW_LINES, CAPTION_WINDOW, qapp)
    yield surface
    surface.close()


@pytest.fixture
def transcript(qapp: QApplication) -> Iterator[CaptionSurface]:
    surface = surface_of(TRANSCRIPT_LINES, TRANSCRIPT, qapp)
    yield surface
    surface.close()


ARRIVING = 40
"""New captions for 10 timed arrivals: a warm-up pass and the timed one,
in each of two tries."""


def resize_steps(surface: CaptionSurface, qapp: QApplication) -> Sampled:
    """A drag: 30 resize steps, each painted, every one a new width."""
    width, height = surface.width(), surface.height()

    def step(n: int) -> None:
        surface.resize(width - 150 + n * 9, height + n)
        surface.repaint()

    return sampled(qapp, [partial(step, n) for n in range(30)])


def test_a_resize_step_of_a_caption_window(
    caption_window: CaptionSurface, qapp: QApplication
) -> None:
    within(budgets.FRAME, lambda: resize_steps(caption_window, qapp))


def test_a_resize_step_of_a_transcript(
    transcript: CaptionSurface, qapp: QApplication
) -> None:
    within(budgets.FRAME, lambda: resize_steps(transcript, qapp))


def test_a_text_size_change(transcript: CaptionSurface, qapp: QApplication) -> None:
    def change(size: float) -> None:
        transcript.view.set_text_size(size)
        transcript.repaint()

    changes = [partial(change, s) for s in (1.3, 1.0, 1.6, 0.8, 1.1)]
    within(budgets.DISPLAY_CHANGE, lambda: sampled(qapp, changes))


def test_a_new_caption_in_a_caption_window(
    caption_window: CaptionSurface, qapp: QApplication
) -> None:
    updates = iter(finished_updates(ARRIVING, start=CAPTIONS))

    def arrive() -> None:
        caption_window.view.apply(next(updates))
        caption_window.repaint()

    within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 10))


def test_a_new_caption_with_its_transcript_showing(
    caption_window: CaptionSurface, transcript: CaptionSurface, qapp: QApplication
) -> None:
    updates = iter(finished_updates(ARRIVING, start=CAPTIONS))

    def arrive() -> None:
        update = next(updates)
        for surface in (caption_window, transcript):
            surface.view.apply(update)
            surface.repaint()

    within(budgets.NEW_CAPTION_WITH_TRANSCRIPT, lambda: sampled(qapp, [arrive] * 10))


# -- W1, the caption window (project 109's structure, section 2) -------------------


@contextmanager
def a_caption_window(qapp: QApplication) -> Iterator[CaptionWindow]:
    """A caption window over 1,000 captions (it keeps its 150)."""
    window = CaptionWindow(
        "Discord.exe",
        APP,
        WindowChoices(),
        SourceLabel("Discord", "#4dd0e1"),
        areas=lambda: [Rect(0, 0, 1920, 1040)],
    )
    for update in finished_updates(CAPTIONS):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    window.show()
    qapp.processEvents()
    window.canvas.repaint()
    try:
        yield window
    finally:
        window.close()


@pytest.fixture
def w1(qapp: QApplication) -> Iterator[CaptionWindow]:
    with a_caption_window(qapp) as window:
        yield window


def test_w1_a_resize_step(w1: CaptionWindow, qapp: QApplication) -> None:
    """Dragging the top edge, then a side: each step re-laid and painted."""
    start = Rect(w1.x(), w1.y(), w1.width(), w1.height())
    top = _Drag(Edge.TOP, QPointF(), start)
    side = _Drag(Edge.RIGHT, QPointF(), start)
    steps = [partial(w1.resize_by, top, 0, -4 * n) for n in range(20)]
    steps += [partial(w1.resize_by, side, -9 * n, 0) for n in range(20)]
    within(budgets.FRAME, lambda: sampled(qapp, steps))


def test_w1_a_text_size_step(w1: CaptionWindow, qapp: QApplication) -> None:
    steps = [partial(w1.step_text, s) for s in (3, -2, 4, -5, 2, -2)]
    within(budgets.DISPLAY_CHANGE, lambda: sampled(qapp, steps))


def test_w1_a_new_caption(w1: CaptionWindow, qapp: QApplication) -> None:
    updates = iter(finished_updates(ARRIVING, start=CAPTIONS))

    def arrive() -> None:
        w1.view.apply(next(updates))
        w1.apply_changed(new_caption=True)
        w1.canvas.repaint()

    within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 10))


def test_w1_a_language_switch(w1: CaptionWindow, qapp: QApplication) -> None:
    switches = [partial(w1.set_language, c) for c in ("zh", "", "ja", "en", "", "fr")]
    within(budgets.DISPLAY_CHANGE, lambda: sampled(qapp, switches))


def test_w1_the_hover_band(w1: CaptionWindow, qapp: QApplication) -> None:
    """The band's first show and hide polish its widgets: within a click,
    timed cold (a retry is on a new window, so it's a first time too).
    Once shown, each show or hide is a frame's."""

    def band(window: CaptionWindow, shown: bool) -> None:
        window._show_band(shown)
        window.repaint()

    def first_time() -> Sampled:
        with a_caption_window(qapp) as window:
            first = [partial(band, window, True), partial(band, window, False)]
            return sampled(qapp, first, warm=False)

    within(budgets.CLICK, first_time)
    shows = [partial(band, w1, n % 2 == 0) for n in range(8)]
    within(budgets.FRAME, lambda: sampled(qapp, shows))


# -- W3, the lookup (project 109's structure, section 6) ----------------------------------


@pytest.fixture
def w3(qapp: QApplication) -> Iterator[CaptionWindows]:
    """A caption window over 1,000 captions, with the lookup card and the
    sample dictionary."""
    tools = chinese_tools()
    windows = CaptionWindows(None, MIC, lambda: [Rect(0, 0, 1920, 1040)], learner=tools)
    tools.changed.connect(windows.learning_changed)
    windows.set_captioned([("app", APP)])
    for update in finished_updates(CAPTIONS):
        windows.apply(update)
    shown = windows.windows["app"]
    shown.setGeometry(480, 600, 960, 360)
    qapp.processEvents()
    shown.canvas.repaint()
    yield windows
    windows.close()


def _requests(windows: CaptionWindows, *texts: str) -> list[WordAt]:
    shown = windows.windows["app"]
    found = []
    for text in texts:
        for line, laid, rect in reversed(shown.canvas.placed):
            row = next(
                (
                    r
                    for r in laid.rows
                    if text in r.row.text and rect.top() + r.top >= PAD
                ),
                None,
            )
            if row is not None:
                at = row.row.text.index(text)
                request = shown.word_at(Marked(line.key, row.index, at, at + len(text)))
                assert request is not None
                found.append(request)
                break
    assert len(found) == len(texts)
    return found


def test_w3_the_lookup_after_the_hover_delay(
    w3: CaptionWindows, qapp: QApplication
) -> None:
    card = w3.card
    assert card is not None
    requests = _requests(w3, "电脑", "游戏", "这个")

    def shown(n: int) -> None:
        card.close_card()
        card.hover(requests[n % len(requests)])
        card._show_pending()  # the delay, gone by
        card.repaint()

    hovers = [partial(shown, n) for n in range(9)]
    within(budgets.LOOKUP_HOVER, lambda: sampled(qapp, hovers))


def pins(windows: CaptionWindows) -> list[Callable[[], None]]:
    """Nine lookups pinned open, three words in turn, each after the last
    is closed."""
    card = windows.card
    assert card is not None
    requests = _requests(windows, "电脑", "游戏", "这个")

    def pinned(n: int) -> None:
        card.close_card()
        card.pin(requests[n % len(requests)])
        card.repaint()

    return [partial(pinned, n) for n in range(9)]


def test_w3_the_lookup_pinned(w3: CaptionWindows, qapp: QApplication) -> None:
    actions = pins(w3)
    within(budgets.LOOKUP_PINNED, lambda: sampled(qapp, actions))


@pytest.mark.parametrize("slow_every", [1, 9], ids=["every pin", "one pin in nine"])
@pytest.mark.parametrize(
    ("load", "tries"),
    [((0.4,), "both tries"), ((0.95, 0.4), "all 3 tries")],
    ids=["a calm PC", "a PC saturated for a moment"],
)
def test_a_slower_pin_still_fails_its_budget(
    w3: CaptionWindows,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    slow_every: int,
    load: tuple[float, ...],
    tries: str,
) -> None:
    """The warm-up, the garbage collector held off and the retry don't
    weaken the judge (project 140): a pin 60 ms slower fails in every try,
    whether every pin is (the median) or one in nine (any one run) - in
    both tries on a calm PC, and in a third as well when the PC measures
    saturated after the second (decision 0040). The PC's load is set
    here, the readings in turn: a busy CI runner gave this test a third try
    it didn't expect, and failed it, twice on 2026-11-09 (polyglotic-hq
    260, 267)."""
    readings = iter(load)
    monkeypatch.setattr(
        busy_pc, "busy_share", lambda seconds=0.0: next(readings, load[-1])
    )
    real = LookupCard.pin
    calls = itertools.count(1)

    def slower(self: LookupCard, word: WordAt, origin: QWidget | None = None) -> None:
        real(self, word, origin)
        if next(calls) % slow_every == 0:
            time.sleep(0.06)

    monkeypatch.setattr(LookupCard, "pin", slower)
    monkeypatch.setattr(budget_judge, "JUDGED", [])  # not in the run's summary
    actions = pins(w3)
    with pytest.raises(AssertionError, match=f"lookup_pinned over .* {tries}: try 1"):
        within(budgets.LOOKUP_PINNED, lambda: sampled(qapp, actions))


def test_w3_a_learning_action_shown(w3: CaptionWindows, qapp: QApplication) -> None:
    """Add to deck and Known: the card and the captions holding the word."""
    card = w3.card
    assert card is not None
    card.pin(_requests(w3, "电脑")[0])
    shown = w3.windows["app"]

    def act(what: str) -> None:
        card.do(what)
        card.repaint()
        shown.canvas.repaint()

    actions = [partial(act, w) for w in ("deck", "known") * 5]
    within(budgets.CLICK, lambda: sampled(qapp, actions))
