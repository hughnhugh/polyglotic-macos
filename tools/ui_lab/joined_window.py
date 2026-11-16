"""W1j, the joined window's states (polyglotic-hq project 109's structure,
section 2a and 10.6), held to their budgets: idle (three columns), hovered
(every column's strip and the window's controls; the third column empty),
two apps, Strip, a column's settings popover open, and the window's;
paused and a notice - each once, over the whole window (109's 2a, part 3).

The windows are made by `CaptionWindows` on a 1920 x 1040 work area, each
over 1,000 made-up captions (it keeps its 150), then joined. Timed: a
resize step with three columns (the right edge, then the top), join and
separate, a new caption in one column (and its slide into place, 267),
the hover band (every strip at once), a move step, and the column's
popover opening.
"""

from functools import partial

from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QPainter, QPaintEvent, QRegion
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import _Drag, to_rect
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.joined_window import JoinedWindow
from polyglotic_desktop.ui_next.views.caption_window import Notice, Notices
from polyglotic_desktop.ui_next.views.placement import Edge
from tools.ui_lab.caption_window import LABELS, _areas, sliding_in
from tools.ui_lab.lab import SCENE, Lab, State
from tools.ui_lab.new_parts import CAPTIONS, finished

SOURCES = [APP, SourceId("app-2"), SourceId("app-3")]


def joined(lab: Lab, apps: int = 3, empty: int = -1) -> CaptionWindows:
    """`apps` windows (the `empty`-th without captions), joined; the second
    Original only with bigger text, so each column's own choices show."""
    windows = CaptionWindows(None, MIC, _areas)
    windows.set_labels(LABELS, "You")
    windows.set_captioned([(f"app{n}", s) for n, s in enumerate(SOURCES[:apps])])
    for n, each in enumerate(windows.windows.values()):
        each.always_shown = True  # never faded in a photograph
        if n == 1:
            each.set_language("")
            each.set_text_size(1.2)
    for n, source in enumerate(SOURCES[:apps]):
        if n != empty:
            for update in finished(CAPTIONS, source):
                windows.apply(update)
    windows.join()
    lab.pump()
    lab.closing.append(windows.close)
    return windows


def window_of(windows: CaptionWindows) -> JoinedWindow:
    assert windows.joined_window is not None
    return windows.joined_window


def resize_steps(lab: Lab, window: JoinedWindow) -> None:
    start = to_rect(window.geometry())
    side, top = _Drag(Edge.RIGHT, QPointF(), start), _Drag(Edge.TOP, QPointF(), start)
    for n in range(20):
        lab.time(
            "resize_step",
            partial(window.resize_by, side, -24 * n, 0),
            budget=budgets.FRAME,
        )
    for n in range(20):
        lab.time(
            "resize_step",
            partial(window.resize_by, top, 0, -4 * n),
            budget=budgets.FRAME,
        )
    window.resize_by(side, 0, 0)


def move_steps(lab: Lab, window: JoinedWindow) -> None:
    drag = _Drag(Edge.NONE, QPointF(), to_rect(window.geometry()))
    for n in range(20):
        lab.time(
            "move_step",
            partial(window.move_by, drag, -6 * n, -8 * n),
            budget=budgets.FRAME,
        )
    window.move_by(drag, 0, 0)


def join_and_separate(lab: Lab, windows: CaptionWindows) -> None:
    def join() -> None:
        windows.join()
        window_of(windows).repaint()

    def separate() -> None:
        windows.separate()
        for each in windows.windows.values():
            each.repaint()

    for _ in range(4):
        lab.time("separate", separate, budget=budgets.CLICK)
        lab.time("join", join, budget=budgets.CLICK)


def new_captions(lab: Lab, windows: CaptionWindows, column: int = 0) -> None:
    source = SOURCES[column]
    shown = list(windows.windows.values())[column]
    arriving = iter(finished(10, source, start=CAPTIONS))

    def arrive() -> None:
        windows.apply(next(arriving))
        shown.canvas.repaint()

    lab.time("new_caption", arrive, repeat=10, budget=budgets.NEW_CAPTION)


def band_toggles(lab: Lab, window: JoinedWindow) -> None:
    def band(on: bool) -> None:
        window.show_bands(on)
        window.repaint()

    band(True)  # the first show polishes its widgets
    band(False)
    for n in range(10):
        lab.time("hover_band", partial(band, n % 2 == 0), budget=budgets.FRAME)


def hovered(lab: Lab, window: JoinedWindow) -> None:
    for column in window.columns:
        column.set_hovered(True)
    window.show_bands(True)
    lab.pump()


# -- the states --------------------------------------------------------------------------


def idle(lab: Lab) -> QWidget:
    windows = joined(lab)
    window = window_of(windows)
    resize_steps(lab, window)
    join_and_separate(lab, windows)
    new_captions(lab, windows)
    return window_of(windows)


def hovered_state(lab: Lab) -> QWidget:
    windows = joined(lab, empty=2)
    window = window_of(windows)
    band_toggles(lab, window)
    move_steps(lab, window)
    window.columns[0].notices = Notices()  # the snap's name, gone for the photograph
    window.columns[0]._tick()
    hovered(lab, window)
    return window


def two_apps(lab: Lab) -> QWidget:
    windows = joined(lab, apps=2)
    window = window_of(windows)
    window.resize(1280, window.height())
    lab.pump()
    resize_steps(lab, window)
    join_and_separate(lab, windows)
    new_captions(lab, windows, column=1)
    window = window_of(windows)
    window.resize(1280, window.height())
    lab.pump()
    column = list(windows.windows.values())[1]
    sliding_in(lab, column, finished(2, SOURCES[1], start=CAPTIONS + 20))  # 267
    return window


class _Together(QWidget):
    """The joined window and an open popover where they are on the screen,
    over the stand-in video."""

    def __init__(self, window: JoinedWindow, popover: QWidget) -> None:
        super().__init__()
        self.window_, self.popover = window, popover
        self.box = window.geometry().united(popover.geometry())
        self.resize(self.box.size())

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        """Each window and where it's drawn (`checks.place_in`)."""
        return [
            (shown, shown.geometry().topLeft() - self.box.topLeft(), 1.0)
            for shown in (self.window_, self.popover)
        ]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), SCENE)
        for shown, at, _scale in self.places():
            shown.render(painter, at, QRegion(), QWidget.RenderFlag.DrawChildren)
        painter.end()


def column_popover(lab: Lab) -> QWidget:
    windows = joined(lab)
    window = window_of(windows)
    window.resize(1500, window.height())
    hovered(lab, window)
    column = window.columns[1]

    def toggle() -> None:
        column.toggle_settings()

    for _ in range(6):  # open, close, open, ...: each a click
        lab.time("settings_popover", toggle, budget=budgets.CLICK)
    column.toggle_settings()
    lab.pump()
    assert column.popover is not None
    return _Together(window, column.popover)


def window_popover(lab: Lab) -> QWidget:
    windows = joined(lab)
    window = window_of(windows)
    hovered(lab, window)

    def toggle() -> None:
        window.toggle_settings()

    for _ in range(6):
        lab.time("settings_popover", toggle, budget=budgets.CLICK)
    window.toggle_settings()
    assert window.popover is not None
    lab.pump()
    return _Together(window, window.popover)


def _ticked(window: JoinedWindow) -> None:
    for column in window.columns:
        column._tick()


def paused(lab: Lab) -> QWidget:
    windows = joined(lab)
    window = window_of(windows)

    def toggle() -> None:
        windows.set_paused(not windows.paused)
        _ticked(window)

    lab.time("pause", toggle, repeat=11, budget=budgets.FRAME)  # ends paused
    lab.pump()
    return window


def notice(lab: Lab) -> QWidget:
    windows = joined(lab, apps=2)
    window = window_of(windows)
    window.resize(1280, window.height())

    def change() -> None:
        reconnecting = windows.connection[0] is not Notice.RECONNECTING
        windows.set_connection(Notice.RECONNECTING if reconnecting else None, 4.0)
        _ticked(window)

    lab.time("notice_change", change, repeat=11, budget=budgets.FRAME)
    lab.pump()
    return window


STATES = [
    State(f"ui_next.w1j_{name}", run, gated=True, scene=scene)
    for name, run, scene in (
        ("idle", idle, True),
        ("hovered", hovered_state, True),
        ("two_apps", two_apps, True),
        ("column_popover", column_popover, False),
        ("window_popover", window_popover, False),
        ("paused", paused, True),
        ("notice", notice, True),
    )
]
