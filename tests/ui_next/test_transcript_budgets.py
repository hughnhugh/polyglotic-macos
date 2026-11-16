"""W2, the transcript window, against the interface's budgets
(polyglotic-hq DECISIONS.md #53, `perf.budgets`), offscreen, at 1,000
lines: a resize step, a scroll step (and one past the layouts it keeps), a new caption with its caption
window showing too, a search, a text size step and the rail opened or
closed (project 116's brief) - and each again at three hours of a
lecture's lines, 4,000, kept when the learner chooses (polyglotic-hq 334),
with the window opened on them.

As `test_budgets`: each action timed with the paint it causes, after a
warm-up pass, with the garbage collector held off; its median held to the
budget and any one run to the slot budget (50 ms), with one retry that
reports both tries (`tests/budget_judge.py`).
"""

from collections.abc import Iterator
from functools import partial

import pytest
from PySide6.QtWidgets import QApplication
from tests.budget_judge import sampled, within
from tests.ui_next.made_up import EN, finished_updates

from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.transcript_window import (
    LINES_LAID_OUT,
    TranscriptWindow,
)
from polyglotic_desktop.ui_next.views.caption_window import WindowChoices
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.transcript import (
    Transcript,
    TranscriptChoices,
    TranscriptLength,
)

LINES = 1_000
THREE_HOURS = 4_000
"""A three-hour lecture's lines: a caption every 2.7 s (334's brief:
3,000-4,000)."""
DISCORD = SourceLabel("Discord", "#4dd0e1")


def kept(count: int) -> Transcript:
    """A transcript listing `count` lines - past 1,000, as the learner who
    keeps the whole session has it."""
    length = TranscriptLength.NEWEST if count <= LINES else TranscriptLength.SESSION
    lines = Transcript(APP, EN, mic=MIC, length=length)
    for update in finished_updates(count):
        lines.apply(update)
    assert len(lines.lines) == count
    return lines


@pytest.fixture(params=[LINES, THREE_HOURS], ids=["1000-lines", "three-hours"])
def window(
    qapp: QApplication, request: pytest.FixtureRequest
) -> Iterator[TranscriptWindow]:
    lines = kept(request.param)
    shown = TranscriptWindow("Discord.exe", lines, DISCORD, TranscriptChoices())
    shown.animate = False
    shown.resize(900, 600)
    shown.show()
    qapp.processEvents()
    shown.list.repaint()
    yield shown
    shown.close()


def test_w2_a_resize_step(window: TranscriptWindow, qapp: QApplication) -> None:
    def step(n: int) -> None:
        window.resize(750 + n * 9, 600 + n)
        window.repaint()

    steps = [partial(step, n) for n in range(30)]
    within(budgets.FRAME, lambda: sampled(qapp, steps))


def test_w2_a_scroll_step(window: TranscriptWindow, qapp: QApplication) -> None:
    def step(dy: float) -> None:
        window.list.scroll_by(dy)
        window.list.repaint()

    steps = [partial(step, 60 if n < 15 else -60) for n in range(20)]
    within(budgets.FRAME, lambda: sampled(qapp, steps))


def test_w2_a_scroll_step_past_the_lines_kept_laid_out(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    """Back at the oldest of the 1,000 lines, far past the layouts it keeps
    (`LINES_LAID_OUT`, polyglotic-hq 239): each step towards the newest
    lays out the lines it brings into view for the first time - judged as
    first times, never warmed up."""
    window.list.go_to_oldest()
    window.list.repaint()
    assert window.list.engine.held <= LINES_LAID_OUT

    def step() -> None:
        window.list.scroll_by(-60)
        window.list.repaint()

    within(budgets.FRAME, lambda: sampled(qapp, [step] * 20, warm=False))


def test_w2_a_new_caption_with_its_caption_window_showing(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    caption = CaptionWindow(
        "Discord.exe",
        APP,
        WindowChoices(),
        DISCORD,
        areas=lambda: [Rect(0, 0, 1920, 1040)],
    )
    for update in finished_updates(LINES):
        caption.view.apply(update)
    caption.apply_changed(new_caption=True)
    caption.show()
    qapp.processEvents()
    listed = len(window.transcript.lines)
    updates = iter(finished_updates(40, start=listed))  # warm-up and timed, twice

    def arrive() -> None:
        update = next(updates)
        if caption.view.apply(update):
            caption.apply_changed(new_caption=True)
        caption.canvas.repaint()
        if window.transcript.apply(update):
            window.refresh()
        window.list.repaint()

    try:
        within(
            budgets.NEW_CAPTION_WITH_TRANSCRIPT, lambda: sampled(qapp, [arrive] * 10)
        )
    finally:
        caption.close()


def test_w2_a_search(window: TranscriptWindow, qapp: QApplication) -> None:
    def search(query: str) -> None:
        window.search.setText(query)
        window.list.repaint()

    queries = ("f", "fr", "fru", "fruit", "", "水果", "x", "")
    searches = [partial(search, q) for q in queries]
    within(budgets.CLICK, lambda: sampled(qapp, searches))


def test_w2_a_text_size_step(window: TranscriptWindow, qapp: QApplication) -> None:
    def step(steps: int) -> None:
        window.step_text(steps)
        window.list.repaint()

    steps = [partial(step, s) for s in (3, -2, 4, -5, 2, -2)]
    within(budgets.DISPLAY_CHANGE, lambda: sampled(qapp, steps))


def test_w2_opened_on_three_hours_of_lines(qapp: QApplication) -> None:
    """Opened from a caption window (a click), on a three-hour lecture's
    4,000 lines: made, shown and painted within a click's budget - only
    the lines in view are laid out."""
    lines = kept(THREE_HOURS)
    opened: list[TranscriptWindow] = []

    def open_it() -> None:
        shown = TranscriptWindow("Discord.exe", lines, DISCORD, TranscriptChoices())
        shown.animate = False
        shown.resize(900, 600)
        shown.show()
        shown.list.repaint()
        opened.append(shown)

    try:
        within(budgets.CLICK, lambda: sampled(qapp, [open_it] * 4))
    finally:
        for shown in opened:
            shown.close()
            shown.deleteLater()
        qapp.processEvents()


def test_w2_the_rail_opened_or_closed(
    window: TranscriptWindow, qapp: QApplication
) -> None:
    def toggle() -> None:
        window.toggle_rail()
        window.repaint()

    within(budgets.CLICK, lambda: sampled(qapp, [toggle] * 6))
