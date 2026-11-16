"""The new interface's states (`ui_next`), held to their budgets.

So far the caption surface - what every caption window, transcript and
joined window stands on - with 0 and 1,000 captions, captions only,
"You" beside the app, scrolled back, and three side by side. The
windows around it come with the rebuild's part 2 (project 109's
structure); their states join this list then.
"""

from dataclasses import replace
from functools import partial

from PySide6.QtWidgets import QHBoxLayout, QWidget

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC, recorded_captions
from polyglotic_desktop.ui_next.caption_surface import CaptionSurface
from polyglotic_desktop.ui_next.views.captions import (
    CAPTION_WINDOW_LINES,
    TRANSCRIPT_LINES,
    CaptionLines,
)
from tools.ui_lab.lab import Lab, State

EN = Language("en")
CAPTIONS = 1_000
CAPTION_WINDOW = (800, 260)
TRANSCRIPT = (900, 600)


def finished(count: int, source: SourceId = APP, start: int = 0) -> list[CaptionUpdate]:
    """`count` finished captions from the made-up conversation, each its own."""
    pool = [
        u
        for _, u in recorded_captions()
        if u.kind is CaptionKind.FINISHED and u.source_id == APP
    ]
    return [
        replace(
            pool[n % len(pool)],
            caption_id=CaptionId(f"{source}-{n:05d}"),
            source_id=source,
            replaces=(),
        )
        for n in range(start, start + count)
    ]


def surface(
    lab: Lab,
    size: tuple[int, int],
    keep: int,
    captions: int,
    target: Language | None = EN,
    with_you: bool = False,
) -> CaptionSurface:
    sources = (APP, MIC) if with_you else (APP,)
    view = CaptionLines(sources, target, keep=keep, yours=(MIC,))
    for n, update in enumerate(finished(captions)):
        if with_you and n % 4 == 3:
            update = replace(update, source_id=MIC)
        view.apply(update)
    shown = CaptionSurface(view)
    shown.resize(*size)
    shown.show()
    lab.pump()
    return shown


def resize_steps(lab: Lab, widget: QWidget, action: str = "resize_step") -> None:
    width, height = widget.width(), widget.height()

    def step(n: int) -> None:
        widget.resize(width - 150 + n * 9, height + n)
        widget.repaint()

    for n in range(30):
        lab.time(action, partial(step, n), budget=budgets.FRAME)
    widget.resize(width, height)


def text_sizes(lab: Lab, shown: CaptionSurface) -> None:
    def size(scale: float) -> None:
        shown.view.set_text_size(scale)
        shown.repaint()

    for scale in (1.3, 1.0, 1.6, 0.8, 1.0):
        lab.time("text_size", partial(size, scale), budget=budgets.DISPLAY_CHANGE)


def new_captions(lab: Lab, shown: list[CaptionSurface], budget: budgets.Budget) -> None:
    arriving = iter(finished(10, start=CAPTIONS))

    def arrive() -> None:
        update = next(arriving)
        for each in shown:
            each.view.apply(update)
            each.repaint()

    lab.time("new_caption", arrive, repeat=10, budget=budget)


def caption_window_empty(lab: Lab) -> QWidget:
    shown = surface(lab, CAPTION_WINDOW, CAPTION_WINDOW_LINES, 0)
    new_captions(lab, [shown], budgets.NEW_CAPTION)
    return shown


def caption_window_1000(lab: Lab) -> QWidget:
    shown = surface(lab, CAPTION_WINDOW, CAPTION_WINDOW_LINES, CAPTIONS)
    resize_steps(lab, shown)
    text_sizes(lab, shown)
    new_captions(lab, [shown], budgets.NEW_CAPTION)
    return shown


def caption_window_captions_only(lab: Lab) -> QWidget:
    shown = surface(lab, CAPTION_WINDOW, CAPTION_WINDOW_LINES, CAPTIONS, target=None)
    resize_steps(lab, shown)
    return shown


def caption_window_with_you(lab: Lab) -> QWidget:
    shown = surface(lab, CAPTION_WINDOW, CAPTION_WINDOW_LINES, CAPTIONS, with_you=True)
    resize_steps(lab, shown)
    return shown


def transcript_1000(lab: Lab) -> QWidget:
    shown = surface(lab, TRANSCRIPT, TRANSCRIPT_LINES, CAPTIONS)
    window = surface(lab, CAPTION_WINDOW, CAPTION_WINDOW_LINES, CAPTIONS)
    resize_steps(lab, shown)
    text_sizes(lab, shown)
    for _ in range(20):
        lab.time("scroll_step", partial(_scrolled, shown, 48), budget=budgets.FRAME)
    shown.view.scroll.follow()
    new_captions(lab, [window, shown], budgets.NEW_CAPTION_WITH_TRANSCRIPT)
    window.close()
    return shown


def transcript_scrolled_back(lab: Lab) -> QWidget:
    shown = surface(lab, TRANSCRIPT, TRANSCRIPT_LINES, CAPTIONS)
    _scrolled(shown, 2_000)
    new_captions(lab, [shown], budgets.NEW_CAPTION)
    return shown


def joined_three(lab: Lab) -> QWidget:
    joined = QWidget()
    row = QHBoxLayout(joined)
    shown = []
    for _ in range(3):
        each = surface(lab, CAPTION_WINDOW, CAPTION_WINDOW_LINES, CAPTIONS)
        row.addWidget(each)
        shown.append(each)
    joined.resize(1500, 260)
    joined.show()
    lab.pump()
    resize_steps(lab, joined)
    new_captions(lab, shown, budgets.NEW_CAPTION)
    return joined


def _scrolled(shown: CaptionSurface, dy: float) -> None:
    shown.scroll_by(dy)
    shown.repaint()


STATES = [
    State("ui_next.caption_window_empty", caption_window_empty, gated=True, scene=True),
    State("ui_next.caption_window_1000", caption_window_1000, gated=True, scene=True),
    State(
        "ui_next.caption_window_captions_only",
        caption_window_captions_only,
        gated=True,
        scene=True,
    ),
    State(
        "ui_next.caption_window_with_you",
        caption_window_with_you,
        gated=True,
        scene=True,
    ),
    State("ui_next.transcript_1000", transcript_1000, gated=True, scene=True),
    State(
        "ui_next.transcript_scrolled_back",
        transcript_scrolled_back,
        gated=True,
        scene=True,
    ),
    State("ui_next.joined_three", joined_three, gated=True, scene=True),
]
