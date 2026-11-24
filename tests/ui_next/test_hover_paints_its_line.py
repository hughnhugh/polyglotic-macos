"""A mouse move over a caption window with thick arrows repaints only the
lines a hover touched, and stays within the hover budget (the user's
live testing, polyglotic-hq 272: 13 stalls painting the whole window from
`mouseMoveEvent`, up to 487 ms; and dictionary reads from hover, up to
297 ms - a hover card following the mouse now looks up after FOLLOW_MS,
not in the move itself: tests/ui_next/test_lookup_card.py)."""

import time
from collections.abc import Iterator
from dataclasses import replace
from functools import partial

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QPaintEvent
from PySide6.QtWidgets import QApplication
from tests.budget_judge import sampled, within
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import finished_updates
from tests.ui_next.test_lookup_card import AREA, find, mouse

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.display import LinkGap, LinkLine, WordLinks
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook

THICK_ARROWS = replace(
    CaptionLook(),
    opacity=0.94,
    background="#f6f1e6",
    original="#1a1a1a",
    translation="#7a3e00",
    word_links=WordLinks.ARROWS,
    link_line=LinkLine.THICK,
    link_gap=LinkGap.CLOSE,
)
"""The user's look while it happened (246's live profile): Paper's colours,
thick arrows, close."""


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    found = CaptionWindows(None, MIC, lambda: [AREA], learner=chinese_tools())
    found.set_look(THICK_ARROWS)
    found.set_second_languages({Language("en"): Language("zh")})
    found.set_captioned([("app", APP)])
    for update in finished_updates(40):
        found.apply(update)
    shown = found.windows["app"]
    shown.setGeometry(480, 100, 688, 900)
    shown.hovered = True
    qapp.processEvents()
    _at_rest(shown, qapp)
    shown.canvas.repaint()
    yield shown
    found.close()


def _at_rest(window: CaptionWindow, qapp: QApplication, limit: float = 5.0) -> None:
    """Until the window's frames stop: the captions just added slide in, a
    frame each tick, painting all of it (they move every line). A hover is
    measured against a window at rest - on a slow machine the slide was
    still running when the hover's paint was noted (polyglotic-hq 821)."""
    end = time.monotonic() + limit
    while window._tick_timer.isActive() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
    assert not window._tick_timer.isActive(), "the window never came to rest"


def _painted(window: CaptionWindow, qapp: QApplication) -> list[QRect]:
    """What the canvas's paints were asked to draw, until the next is done."""
    asked: list[QRect] = []
    paint = window.canvas.paintEvent

    def noted(event: QPaintEvent) -> None:
        asked.append(event.rect())
        paint(event)

    window.canvas.paintEvent = noted  # type: ignore[method-assign]
    qapp.processEvents()
    window.canvas.paintEvent = paint  # type: ignore[method-assign]
    return asked


def test_a_hovered_word_repaints_its_line_not_the_window(
    qapp: QApplication, window: CaptionWindow
) -> None:
    _, first = find(window, "电脑")
    mouse(window, "move", first, held=False)
    qapp.processEvents()
    word, second = find(window, "游戏")
    mouse(window, "move", second, held=False)
    assert window.canvas.hovered == word
    asked = _painted(window, qapp)
    assert asked, "the hover wasn't painted"
    whole = window.canvas.rect()
    for rect in asked:
        assert rect != whole and rect.height() < whole.height() / 2


def test_a_mouse_move_across_words_is_within_the_hover_budget(
    qapp: QApplication, window: CaptionWindow
) -> None:
    points = [find(window, text)[1] for text in ("电脑", "游戏", "这个", "画面")]
    moves = [
        partial(mouse, window, "move", points[i % 4], held=False) for i in range(20)
    ]
    within(budgets.LOOKUP_HOVER, lambda: sampled(qapp, moves))  # each and its paint
