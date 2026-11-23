"""W2, the transcript window's states (polyglotic-hq project 109's
structure, section 3), held to their budgets: 1,000 lines with the rail
closed and open, searching (with matches, and none), empty, scrolled back,
my speech with a line checked by the best model, paused, at its minimum
size, the rail as a popover there, and a word looked up (the card the
caption windows share, on the sample dictionary).

Every window is over 1,000 made-up captions unless empty. Timed: a resize
step, a scroll step, a text size step, a new caption with its caption
window showing too, a search, the rail opened or closed (a click), each
frame of the rail sliding, the window opened, its rail's panels made (one per turn of the event
loop, each held to the 50 ms slot), and the lookup from it (after the
hover delay, and pinned).
"""

import gc
import itertools
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial

from PySide6.QtCore import QElapsedTimer, QPoint
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QRegion
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, Marked
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import LanguagesPanel, LookPanel, TimingPanel
from polyglotic_desktop.ui_next.transcript_window import TranscriptWindow
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, Notice
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    Timing,
    TimingView,
    WindowLanguage,
    WindowLanguageView,
)
from polyglotic_desktop.ui_next.views.transcript import (
    RAIL_WIDTH,
    Transcript,
    TranscriptChoices,
)
from tools.ui_lab.caption_window import LABELS, _areas
from tools.ui_lab.caption_window import window as caption_window
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.lookup import sample_tools
from tools.ui_lab.new_parts import CAPTIONS, finished
from tools.ui_lab.panels import SESSION, margin_dark

EN = Language("en")
SIZE = (900, 600)


def made_up_clock() -> Callable[[], datetime]:
    """Made-up times, the same every run (the goldens compare pixels): from
    09:30 on the day the lab was written, 4 s apart."""
    ticks = itertools.count()
    start = datetime(2026, 11, 7, 9, 30, tzinfo=UTC)
    return lambda: start + timedelta(seconds=4 * next(ticks))


def transcript(
    captions: int = CAPTIONS, show_mic: bool = False, source: SourceId = APP
) -> Transcript:
    found = Transcript(source, EN, mic=MIC, show_mic=show_mic, clock=made_up_clock())
    for n, update in enumerate(finished(captions, source)):
        if show_mic and n % 4 == 3:
            update = replace(update, source_id=MIC)
        found.apply(update)
    return found


def window(
    lab: Lab,
    captions: int = CAPTIONS,
    size: tuple[int, int] = SIZE,
    rail_open: bool = False,
    show_mic: bool = False,
    lines: Transcript | None = None,
    panels: bool = True,
) -> TranscriptWindow:
    """A transcript window over `lines` (made here if not given)."""
    theme = margin_dark()
    style.use(theme)
    shown = TranscriptWindow(
        "lab",
        lines or transcript(captions, show_mic),
        LABELS[APP],
        TranscriptChoices(rail_open=rail_open),
        theme=theme,
        you=LABELS[MIC],
        panels=rail_panels(show_mic) if panels else (),
    )
    shown.animate = False
    shown.list.zone = UTC  # the times as made up, wherever the lab runs
    shown.follow(LABELS[APP], "en", show_mic, shown.timing, LABELS[MIC])
    shown.resize(*size)
    shown.show()
    lab.pump()
    return shown


def rail_panels(show_mic: bool) -> list[Callable[[], QWidget]]:
    """What makes the session's panels, as a transcript's rail shows them:
    Languages with "This window", Timing and Look."""
    own = WindowLanguageView(WindowLanguage("Discord", "en", show_mic))
    return [
        partial(LanguagesPanel, LanguagesView(SESSION), own),
        partial(TimingPanel, TimingView(Timing(CaptionMode.WHOLE, 2.0))),
        partial(LookPanel, LookView(CaptionLook())),
    ]


def resize_steps(lab: Lab, shown: TranscriptWindow) -> None:
    width, height = shown.width(), shown.height()

    def step(n: int) -> None:
        shown.resize(width - 150 + n * 9, height + n)
        shown.repaint()

    for n in range(30):
        lab.time("resize_step", partial(step, n), budget=budgets.FRAME)
    shown.resize(width, height)


def scroll_steps(lab: Lab, shown: TranscriptWindow) -> None:
    def step(dy: float) -> None:
        shown.list.scroll_by(dy)
        shown.list.repaint()

    for n in range(20):
        lab.time(
            "scroll_step", partial(step, 60 if n < 15 else -60), budget=budgets.FRAME
        )


def text_steps(lab: Lab, shown: TranscriptWindow) -> None:
    def step(steps: int) -> None:
        shown.step_text(steps)
        shown.list.repaint()

    for steps in (3, -2, 4, -5, 2, -2):
        lab.time("text_size", partial(step, steps), budget=budgets.DISPLAY_CHANGE)


def new_captions(lab: Lab, shown: TranscriptWindow, beside: CaptionWindow) -> None:
    """A new caption to the caption window and its transcript, both drawn."""
    arriving = iter(finished(10, start=CAPTIONS))

    def arrive() -> None:
        update = next(arriving)
        if beside.view.apply(update):
            beside.apply_changed(new_caption=True)
        beside.canvas.repaint()
        if shown.transcript.apply(update):
            shown.refresh()
        shown.list.repaint()

    lab.time(
        "new_caption", arrive, repeat=10, budget=budgets.NEW_CAPTION_WITH_TRANSCRIPT
    )


def searches(lab: Lab, shown: TranscriptWindow, queries: tuple[str, ...]) -> None:
    def search(query: str) -> None:
        shown.search.setText(query)
        shown.list.repaint()

    for query in queries:
        lab.time("search", partial(search, query), budget=budgets.CLICK)


def rail_toggles(lab: Lab, shown: TranscriptWindow) -> None:
    gc.collect()  # a collection due from earlier work isn't the rail's

    def toggle() -> None:
        shown.toggle_rail()
        shown.repaint()

    for _ in range(6):
        lab.time("rail", toggle, budget=budgets.CLICK)

    def slide(width: int) -> None:  # a frame of the rail sliding in
        shown._rail_width(width)
        layout = shown.layout()
        if layout is not None:
            layout.activate()  # the list narrowed in this frame
        shown.repaint()

    shown.rail.show()
    for n in range(1, 11):
        lab.time(
            "rail_slide_step",
            partial(slide, RAIL_WIDTH * n // 10),
            budget=budgets.FRAME,
        )
    shown._show_rail(shown.choices.rail_open, animate=False)


# -- the states --------------------------------------------------------------------------


def lines_1000(lab: Lab) -> QWidget:
    beside = caption_window(lab)
    lab.closing.append(beside.close)

    collected = [transcript(), transcript()]  # collected before it opens

    def open_window() -> TranscriptWindow:  # its rail's panels timed above
        return window(lab, lines=collected.pop(), panels=False)

    unshown = TranscriptWindow(
        "lab",
        collected[0],
        LABELS[APP],
        TranscriptChoices(),
        theme=margin_dark(),
        panels=rail_panels(False),
    )
    gc.collect()  # a collection due from earlier work isn't the rail's
    for _ in range(3):  # the rail's panels, one per turn; then laid out, drawn
        lab.time("rail_prepare_step", unshown._make_panel, budget=budgets.SLOT)
    lab.time("rail_prepare_step", unshown._predraw_rail, budget=budgets.SLOT)
    lab.time("rail_prepare_step", unshown._predraw_rail, budget=budgets.SLOT)
    unshown.deleteLater()
    lab.time("open_first", open_window)  # recorded: the first window's first show
    lab.time("open", open_window, budget=budgets.CLICK)  # another app's
    shown = window(lab)
    resize_steps(lab, shown)
    scroll_steps(lab, shown)
    shown.go_live()
    text_steps(lab, shown)
    shown.set_text_size(1.0)
    new_captions(lab, shown, beside)
    searches(lab, shown, ("f", "fr", "fru", "fruit", "", "水果", ""))
    rail_toggles(lab, shown)
    settled(lab)  # the search's clear button has faded out
    return shown


def rail_open(lab: Lab) -> QWidget:
    shown = window(lab, rail_open=True)
    resize_steps(lab, shown)
    scroll_steps(lab, shown)
    shown.go_live()
    return shown


def settled(lab: Lab, ms: int = 400) -> None:
    """The event loop run for `ms`: the search field's clear button has
    faded in (Qt animates it), so its picture is the same every run."""
    clock = QElapsedTimer()
    clock.start()
    while clock.elapsed() < ms:
        lab.pump()


def searching(lab: Lab) -> QWidget:
    shown = window(lab)
    searches(lab, shown, ("c", "co", "com", "comp", "computer"))
    scroll_steps(lab, shown)
    shown.go_live()
    settled(lab)
    return shown


def no_matches(lab: Lab) -> QWidget:
    shown = window(lab)
    searches(lab, shown, ("x", "xy", "xyz"))
    settled(lab)
    return shown


def empty(lab: Lab) -> QWidget:
    return window(lab, captions=0)


def scrolled_back(lab: Lab) -> QWidget:
    beside = caption_window(lab)
    lab.closing.append(beside.close)
    shown = window(lab)
    shown.list.scroll_by(2_000)
    shown.refresh()
    new_captions(lab, shown, beside)
    scroll_steps(lab, shown)
    return shown


def respoken(lab: Lab) -> QWidget:
    """Lines the learner said again for the app (polyglotic-hq 567): theirs,
    marked re-spoken in the heading."""
    found = Transcript(APP, EN, mic=MIC, clock=made_up_clock())
    updates = finished(CAPTIONS, APP)
    for n, update in enumerate(updates):
        found.apply(replace(update, respoken=n % 3 == 1))
    return window(lab, lines=found)


def my_speech(lab: Lab) -> QWidget:
    shown = window(lab, show_mic=True)
    newest = shown.transcript.all_lines[-2]
    first = finished(1, start=7)[0]
    shown.transcript.use_checked(
        newest.caption_id,
        first.clauses,
        first.language,
        first.languages_heard,
    )
    shown.refresh()
    shown.list.repaint()
    lab.pump()
    return shown


def paused(lab: Lab) -> QWidget:
    shown = window(lab)
    shown.set_notice(Notice.PAUSED)
    lab.pump()
    return shown


def minimum(lab: Lab) -> QWidget:
    shown = window(lab, size=(520, 320), rail_open=True)
    resize_steps(lab, shown)
    shown.resize(520, 320)
    lab.pump()
    return shown


def rail_popover(lab: Lab) -> QWidget:
    shown = window(lab, size=(600, 460))

    def toggle() -> None:
        shown.toggle_rail()

    for _ in range(4):  # open, close, ...: each a click
        lab.time("rail_popover", toggle, budget=budgets.CLICK)
    shown.toggle_rail()
    lab.pump()
    return shown


def _word(shown: TranscriptWindow, text: str) -> Marked:
    """`text` in the newest lines drawn."""
    for line, laid, _ in reversed(shown.list.drawn):
        for row in laid.rows:
            at = row.row.text.find(text)
            if at >= 0:
                return Marked(line.key, row.index, at, at + len(text))
    raise LookupError(text)


def lookup(lab: Lab) -> QWidget:
    """A word in the transcript looked up: hovered (the delay gone by),
    then pinned - in the card the caption windows share."""
    tools = sample_tools()
    windows = CaptionWindows(None, MIC, _areas, learner=tools)
    windows.set_labels(LABELS, "You")
    found = Transcripts(
        windows, None, learner=tools, areas=_areas, clock=made_up_clock()
    )
    windows.set_captioned([("lab", APP)])
    for update in finished(60):
        found.apply(update)
    found.show("lab")
    shown = found.shown["lab"]
    shown.animate = False
    shown.list.zone = UTC
    shown.setGeometry(200, 200, *SIZE)
    lab.pump()
    shown.list.repaint()
    card = windows.card
    assert card is not None
    words = iter(["电脑", "游戏", "这个"] * 8)

    def hovered() -> None:
        word = _word(shown, next(words))
        shown.list._hover(word)
        card._show_pending()  # the hover delay, gone by

    def pinned() -> None:
        request = shown.list.word_at(_word(shown, next(words)))
        assert request is not None
        card.pin(request)

    for _ in range(9):
        card.close_card()
        lab.time("lookup_hover", hovered, budget=budgets.LOOKUP_HOVER)
    for _ in range(9):
        card.close_card()
        lab.time("lookup_pinned", pinned, budget=budgets.LOOKUP_PINNED)
    lab.closing.append(found.close)
    lab.closing.append(windows.close)
    return _Together([shown, card])


class _Together(QWidget):
    """The transcript and the card over it, as on the screen."""

    def __init__(self, shown: list[QWidget]) -> None:
        super().__init__()
        self.shown = shown
        left = min(w.x() for w in shown)
        top = min(w.y() for w in shown)
        right = max(w.x() + w.width() for w in shown)
        bottom = max(w.y() + w.height() for w in shown)
        self.origin = QPoint(left, top)
        self.resize(right - left, bottom - top)

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        """Each window showing and where it's drawn (`checks.place_in`)."""
        return [
            (each, each.pos() - self.origin, 1.0)
            for each in self.shown
            if each.isVisible()
        ]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        for each, at, _scale in self.places():
            each.render(painter, at, QRegion(), QWidget.RenderFlag.DrawChildren)
        painter.end()


STATES = [
    State(f"ui_next.w2_{name}", run, gated=True)
    for name, run in (
        ("1000", lines_1000),
        ("rail_open", rail_open),
        ("searching", searching),
        ("no_matches", no_matches),
        ("empty", empty),
        ("scrolled_back", scrolled_back),
        ("my_speech", my_speech),
        ("respoken", respoken),
        ("paused", paused),
        ("minimum", minimum),
        ("rail_popover", rail_popover),
        ("lookup", lookup),
    )
]
