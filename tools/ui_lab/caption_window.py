"""W1, the caption window's states (polyglotic-hq project 109's structure,
section 2; the user's minimal strip and settings popover, 2026-11-07),
held to their budgets: idle, hovered, narrow (320 px: the label
shortens), the settings popover,
Original only, locked, scrolled back, paused, a notice, every notice
(087 section 5.5's words, one window each), empty, its first
seconds (new, or put back by Reset position: DECISIONS.md #56), Strip, my
speech shown, the listening mark (in each timing - Steady, under Quick
preview's line, under a live update - and still, with Windows' animations
off: polyglotic-hq 260), Quick preview's line, three windows at the
start, the first window's set-up (and its spoken languages open), the
bar's language chip open (polyglotic-hq 465), and the line a few minutes
before a planned maintenance window, its times in the PC's zone, named
(polyglotic-hq 542).

Every window is over 1,000 made-up captions (it keeps its 150), at the
default size on a 1920 x 1040 work area. Timed: a resize step (the top
edge, then a side), a text size step, a new caption, a language switch,
the hover band, a move step, the listening mark's frame and a new
caption while it shows, and new captions sliding into place - each
arrival and every frame of its slide, in Panel and in Strip (step and
slide, polyglotic-hq 267).
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial

from PySide6.QtCore import QByteArray, QLocale, QPoint, QPointF, Qt, QTimeZone
from PySide6.QtGui import QPainter, QPaintEvent, QRegion, QWheelEvent
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import chinese_tools

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.display import LongLines, RowKind, WordLinks
from polyglotic_desktop.core.listening.maintenance import Maintenance
from polyglotic_desktop.core.listening.selection import Place, Selection
from polyglotic_desktop.core.listening.sources import (
    WHOLE_SYSTEM,
    SourceId,
    SourceLabel,
)
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC, clause
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next import maintenance as maintenance_words
from polyglotic_desktop.ui_next.caption_window import (
    MIN_PANEL,
    CaptionWindow,
    _Drag,
    least_size,
    notice_text,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.toast import current_toast
from polyglotic_desktop.ui_next.views.app_choices import AppChoice, AppState
from polyglotic_desktop.ui_next.views.caption_window import (
    CAPTION_TEXT_SIZES,
    CaptionLook,
    JoinedChoices,
    Notice,
    Notices,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.lab import CaptionLab, Fill, Placing, Unfinished
from polyglotic_desktop.ui_next.views.placement import Edge, Rect
from polyglotic_desktop.ui_next.views.presets import BY_KEY
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.new_parts import CAPTIONS, finished

AREA = Rect(0, 0, 1920, 1040)
LABELS = {
    APP: SourceLabel("Discord", "#4dd0e1"),
    SourceId("app-2"): SourceLabel("Video Player", "#a5d66f"),
    SourceId("app-3"): SourceLabel("Web Browser", "#f5a97f"),
    MIC: SourceLabel("You", "#7c9cff"),
    WHOLE_SYSTEM: SourceLabel("Everything the PC plays", "#f5a97f"),
}

LAB_ZONE = QTimeZone(
    QByteArray(b"Polyglotic/Lab"),
    11 * 3600,
    "Australian Eastern Daylight Time",
    "AEDT",
    QLocale.Country.Australia,
    "",
)
"""Melbourne's summer zone, made up: a planned maintenance window's
times and zone are pictured alike whatever the PC's zone and the
season (polyglotic-hq 542)."""
PLANNED = Maintenance(
    datetime(2026, 11, 20, 19, tzinfo=UTC),  # 06:00-07:30 AEDT on the 21st
    datetime(2026, 11, 20, 20, 30, tzinfo=UTC),
)


def in_lab_zone(lab: Lab) -> None:
    """Maintenance's times written in `LAB_ZONE` until the state ends."""
    real = maintenance_words.pc_zone
    maintenance_words.pc_zone = lambda: LAB_ZONE
    lab.closing.append(lambda: setattr(maintenance_words, "pc_zone", real))


def _areas() -> list[Rect]:
    return [AREA]


def window(
    lab: Lab,
    captions: int = CAPTIONS,
    source: SourceId = APP,
    look: CaptionLook | None = None,
    **choices: object,
) -> CaptionWindow:
    shown = CaptionWindow(
        "lab",
        source,
        replace(WindowChoices(), **choices),  # type: ignore[arg-type]
        LABELS[source],
        look,
        mic=MIC,
        areas=_areas,
    )
    shown.set_labels(LABELS, "You")
    shown.always_shown = True  # never faded in a photograph
    for n, update in enumerate(finished(captions, source)):
        if shown.choices.show_mic and n % 4 == 3:
            update = replace(update, source_id=MIC)
        shown.view.apply(update)
    shown.apply_changed(new_caption=True)
    shown.show()
    lab.pump()
    return shown


def hovered(lab: Lab, shown: CaptionWindow) -> None:
    shown.hovered = True
    shown._show_band(True)
    lab.pump()


def resize_steps(lab: Lab, shown: CaptionWindow) -> None:
    start = Rect(shown.x(), shown.y(), shown.width(), shown.height())
    top, side = _Drag(Edge.TOP, QPointF(), start), _Drag(Edge.RIGHT, QPointF(), start)
    for n in range(20):
        lab.time(
            "resize_step",
            partial(shown.resize_by, top, 0, -4 * n),
            budget=budgets.FRAME,
        )
    for n in range(20):
        lab.time(
            "resize_step",
            partial(shown.resize_by, side, -9 * n, 0),
            budget=budgets.FRAME,
        )
    shown.resize_by(top, 0, 0)


def move_steps(lab: Lab, shown: CaptionWindow) -> None:
    start = Rect(shown.x(), shown.y(), shown.width(), shown.height())
    drag = _Drag(Edge.NONE, QPointF(), start)
    for n in range(20):
        lab.time(
            "move_step",
            partial(shown.move_by, drag, -12 * n, -6 * n),
            budget=budgets.FRAME,
        )
    shown.move_by(drag, 0, 0)


def text_steps(lab: Lab, shown: CaptionWindow) -> None:
    for steps in (3, -2, 4, -5, 2, -2):
        lab.time(
            "text_size", partial(shown.step_text, steps), budget=budgets.DISPLAY_CHANGE
        )


def new_captions(lab: Lab, shown: list[CaptionWindow], source: SourceId = APP) -> None:
    arriving = iter(finished(10, source, start=CAPTIONS))

    def arrive() -> None:
        update = next(arriving)
        for each in shown:
            if each.view.apply(update):
                each.apply_changed(new_caption=True)
            each.canvas.repaint()

    lab.time("new_caption", arrive, repeat=10, budget=budgets.NEW_CAPTION)


class _Clock:
    """A window's arrivals' clock, stepped a frame at a time."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def sliding_in(lab: Lab, shown: CaptionWindow, updates: list[CaptionUpdate]) -> None:
    """New captions arriving - step and slide, the default (D, polyglotic-hq
    DECISIONS.md #104; 267): each arrival, its slide worked out and its
    first frame drawn, within a new caption's budget; then each frame of
    its slide, a frame's time apart, within a frame's budget, to its rest.
    The lab's windows are always shown, which skips arrivals, so this one
    isn't while it's timed; it's photographed at rest."""
    clock = _Clock()
    shown.clock = clock
    shown.always_shown = False
    shown.canvas.repaint()  # where the text sits: the slide measures from it
    frames = 0
    for update in updates:
        clock.now += 2.0  # captions 2 s apart: a typical pace

        def arrive(update: CaptionUpdate = update) -> None:
            if shown.view.apply(update):
                shown.apply_changed(new_caption=True)
            shown.canvas.repaint()

        lab.time("new_caption", arrive, budget=budgets.NEW_CAPTION)
        assert shown.arriving, (
            f"no caption slide: visible={shown.isVisible()}, exposed="
            f"{bool(shown.windowHandle() and shown.windowHandle().isExposed())}, "
            f"reduced_motion={caption_window_module.reduced_motion()}, "
            f"sliding={shown.sliding}, following={shown.view.scroll.following}, "
            f"rows_painted={len(shown.canvas.at_rest)}, rows={len(shown.canvas.rest_rows())}"
        )

        def frame() -> None:
            clock.now += 1 / 60
            shown.canvas.repaint()

        while shown.arriving:
            lab.time("arrive_frame", frame, budget=budgets.FRAME)
            frames += 1
    assert frames >= len(updates) * 10, "the slides were too short to see"
    shown.always_shown = True
    shown.clock = lambda: caption_window_module.time.monotonic()


def language_switches(lab: Lab, shown: CaptionWindow) -> None:
    for code in ("zh", "", "ja", "en"):
        lab.time(
            "language", partial(shown.set_language, code), budget=budgets.DISPLAY_CHANGE
        )


def band_toggles(lab: Lab, shown: CaptionWindow) -> None:
    def band(on: bool) -> None:
        shown._show_band(on)
        shown.repaint()

    band(True)  # the first show polishes its widgets
    band(False)
    for n in range(10):
        lab.time("hover_band", partial(band, n % 2 == 0), budget=budgets.FRAME)


# -- the states --------------------------------------------------------------------------


def idle(lab: Lab) -> QWidget:
    shown = window(lab)
    resize_steps(lab, shown)
    text_steps(lab, shown)
    new_captions(lab, [shown])
    language_switches(lab, shown)
    shown.set_text_size(1.0)
    return shown


def arriving(lab: Lab) -> QWidget:
    """New captions arriving (step and slide: D, with B's step; 267): every
    frame of their slides timed; photographed once they're in."""
    shown = window(lab)
    sliding_in(lab, shown, finished(3, APP, start=CAPTIONS))
    return shown


def caption_hovered(lab: Lab) -> QWidget:
    """Pointer hovering a caption block (polyglotic-hq 950): soft theme-matched
    tint over that caption alone and floating Save/Copy icon buttons on its
    margin, without shifting caption layout."""
    shown = CaptionWindow(
        "lab",
        APP,
        WindowChoices(),
        LABELS[APP],
        None,
        mic=MIC,
        areas=_areas,
        learner=chinese_tools(),
    )
    shown.set_labels(LABELS, "You")
    shown.always_shown = True
    for update in finished(CAPTIONS, APP):
        shown.view.apply(update)
    shown.apply_changed(new_caption=True)
    shown.show()
    lab.pump()
    shown.canvas.repaint()
    target = shown.canvas.placed[-1][2].center()
    shown._hover(target)
    lab.pump()
    shown.canvas.repaint()
    assert shown.hovered_line is not None and shown.line_actions.isVisible()
    lab.closing.append(shown.close)
    return shown


def copied_toast(lab: Lab) -> QWidget:
    """The themed "Copied to clipboard" toast over a caption window after
    copying a caption (polyglotic-hq 950)."""
    shown = window(lab)
    shown.canvas.repaint()
    target = shown.canvas.placed[-1][2].center()
    shown._hover(target)
    assert shown.copy_hovered_line()
    toast = current_toast()
    assert toast is not None and toast.isVisible()
    toast._hold.stop()
    toast._fade.stop()
    lab.pump()
    lab.closing.append(toast.dismiss)
    lab.closing.append(shown.close)
    return _Together([shown, toast])


def hovered_state(lab: Lab) -> QWidget:
    shown = window(lab)
    band_toggles(lab, shown)
    move_steps(lab, shown)
    shown.notices = Notices()  # the snap's name, gone for the photograph
    shown._tick()
    hovered(lab, shown)
    return shown


def narrow(lab: Lab) -> QWidget:
    shown = window(lab)
    shown.resize(least_size(MIN_PANEL).width, 180)
    hovered(lab, shown)
    resize_steps(lab, shown)
    shown.resize(least_size(MIN_PANEL).width, 180)
    lab.pump()
    return shown


def speaking_pace(
    lab: Lab,
    *,
    width: int = 960,
    narrowest: bool = False,
    short: bool = False,
    hidden: bool = False,
    opacity: float = 0.88,
    caption_pace: int | None = None,
) -> QWidget:
    """Speaking pace in the strip; `narrowest`: at the window's least width
    at the text size now, as `narrow` is - a bare 320 px was under it at
    200 % (polyglotic-hq 999), a width no window takes."""
    if narrowest:
        width = least_size(MIN_PANEL).width
    shown = window(lab, captions=0 if caption_pace is not None else 2)
    if caption_pace is not None:
        for update in finished(2, APP):
            shown.view.apply(replace(update, pace_wpm=caption_pace))
        shown.apply_changed(new_caption=True)
    shown.resize(width, MIN_PANEL.height if short else 200)
    if short:
        shown.set_text_size(CAPTION_TEXT_SIZES[-1])
    shown.set_look(replace(shown.look, opacity=opacity))
    shown.set_pace(165, 187, 120, 98)
    shown.set_show_pace(not hidden)
    hovered(lab, shown)
    return shown


def caption_info_off(lab: Lab) -> QWidget:
    """Captions with Show caption info off: header line hidden, rows reclaim its height."""
    shown = window(lab, captions=0)
    for update in finished(3, APP):
        shown.view.apply(replace(update, pace_wpm=165))
    shown.apply_changed(new_caption=True)
    shown.set_show_caption_info(False)
    hovered(lab, shown)
    return shown


def settings_popover(lab: Lab) -> QWidget:
    shown = window(lab)
    shown.windows = 2  # Join windows shows (a stub until 109's step 8)
    hovered(lab, shown)

    def toggle() -> None:
        shown.toggle_settings()

    for _ in range(6):  # open, close, open, ...: each a click
        lab.time("settings_popover", toggle, budget=budgets.CLICK)
    shown.toggle_settings()
    popover = shown.popover
    assert popover is not None
    lab.pump()
    lab.closing.append(shown.close)
    return popover


def pick_app(lab: Lab) -> QWidget:
    """Its settings with the apps it can caption open - found ones, then
    browsers and the main apps before they play - and what to do when an
    app isn't there (F12, 249). Made-up apps; none of the PC's."""
    shown = window(lab)
    shown.app_choices = lambda: [
        AppChoice("Discord.exe", "Discord", AppState.PLAYING),
        AppChoice("vlc.exe", "VLC", AppState.QUIET),
        AppChoice("msedge.exe", "Microsoft Edge", AppState.NOT_PLAYING_YET),
        AppChoice("chrome.exe", "Google Chrome", AppState.NOT_PLAYING_YET),
        AppChoice("spotify.exe", "Spotify", AppState.NOT_PLAYING_YET),
    ]
    hovered(lab, shown)
    lab.time("pick_app", shown.pick_app, budget=budgets.CLICK)
    lab.pump()
    popover = shown.popover
    assert popover is not None
    lab.closing.append(shown.close)
    return popover


def original_only(lab: Lab) -> QWidget:
    shown = window(lab, translate_into="")
    hovered(lab, shown)
    resize_steps(lab, shown)
    new_captions(lab, [shown])
    return shown


def _long_translation(lab: Lab, text_size: float) -> QWidget:
    """Preview 8's shape: a short made-up Japanese original and a much
    longer English translation in a roughly 450 px caption window."""
    shown = window(lab, captions=0, text_size=text_size)
    shown.resize(450, 360)
    # The label shows local time, including in the screenshot.
    arrived = datetime(2026, 11, 25, 9, 30).astimezone()
    shown.view._history._clock = lambda: arrived
    shown.view.apply(
        CaptionUpdate(
            CaptionId(f"long-translation-{text_size:g}"),
            APP,
            CaptionKind.FINISHED,
            clauses=(
                clause(
                    "この字幕は一行に収まります。",
                    "This made-up translation continues onto another row "
                    "instead of wrapping inside the first row.",
                ),
            ),
            language=Language("ja"),
        )
    )
    shown.apply_changed(new_caption=True)
    lab.pump()
    return shown


def long_translation_100(lab: Lab) -> QWidget:
    """The long-translation regression at 100% caption text size."""
    return _long_translation(lab, 1.0)


def long_translation_200(lab: Lab) -> QWidget:
    """The long-translation regression at 200% caption text size."""
    return _long_translation(lab, 2.0)


def overflow_lines(
    lab: Lab, size: float, choice: LongLines, video: bool = False
) -> QWidget:
    """A Japanese walking route and its English translation, each wider than the window."""
    shown = window(lab, captions=0, text_size=size, translation_size=size)
    clock = _Clock()
    shown.clock = clock
    shown.set_look(replace(shown.look, show_source=False, show_language=False))
    shown.set_video(video)
    shown.set_presets(
        replace(shown.preset_menu, video_lines_shown=6, long_lines=choice)
    )
    shown.resize(600, round(310 * size))
    shown.receive(
        CaptionUpdate(
            CaptionId("mountain-path"),
            APP,
            CaptionKind.FINISHED,
            (
                clause(
                    "川沿いの小さな道を歩いていくと、赤い橋の向こうに古い山の駅が見えてきます。",
                    "Follow the narrow path along the river and cross the red bridge "
                    "to reach the old station at the foot of the mountain.",
                    pairs=(
                        (
                            "川沿いの小さな道を歩いていくと、",
                            "Follow the narrow path along the river",
                            True,
                        ),
                        ("赤い橋の向こうに", "and cross the red bridge", True),
                        (
                            "古い山の駅が見えてきます。",
                            "to reach the old station at the foot of the mountain.",
                            True,
                        ),
                    )
                    if choice is LongLines.DISPLAY_NEW_LINES
                    else (),
                ),
            ),
            Language("ja"),
        )
    )
    for _ in range(40):
        clock.now += 0.5
        shown.grab()
    lab.pump()
    return shown


def locked(lab: Lab) -> QWidget:
    """Just locked: it says how to unlock (F10, 249)."""
    shown = window(lab)
    shown.set_locked(True)
    new_captions(lab, [shown])
    return shown


def locked_later(lab: Lab) -> QWidget:
    """Locked a while: only the corner says the hotkey, faintly (F10, 249)."""
    shown = window(lab)
    shown.set_locked(True)
    shown.show_notice("", 0.0)  # the moment it said so has passed
    new_captions(lab, [shown])
    return shown


def scrolled_back(lab: Lab) -> QWidget:
    shown = window(lab)
    shown.canvas.scroll_by(300)
    shown._refresh()
    new_captions(lab, [shown])
    lab.time(
        "scroll_step",
        partial(shown.canvas.scroll_by, 48),
        repeat=10,
        budget=budgets.FRAME,
    )
    return shown


def scrollbar(lab: Lab) -> QWidget:
    """Overlay scroll bar revealed by scrolling (951): scrolled back with
    the thin theme-coloured bar shown at full opacity on the right edge."""
    shown = window(lab)
    pos = QPointF(shown.width() / 2, shown.height() / 2)
    wheel = QWheelEvent(
        pos,
        pos,
        QPoint(0, 0),
        QPoint(0, 360),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(shown, wheel)
    shown._bar_idle_timer.stop()
    shown._bar_idle_until = None
    shown._bar_fade_start = None
    shown.scroll_bar.set_opacity(1.0)
    lab.pump()
    assert shown.scroll_bar.isVisible() and shown.scroll_bar.maximum() > 0
    return shown


def paused(lab: Lab) -> QWidget:
    shown = window(lab)
    shown.set_paused(True)
    shown._tick()
    lab.pump()
    return shown


def notice(lab: Lab) -> QWidget:
    shown = window(lab)
    shown.set_connection(Notice.RECONNECTING, 4.0)
    shown._tick()
    hovered(lab, shown)
    return shown


def maintenance_soon(lab: Lab) -> QWidget:
    """A few minutes before a planned maintenance window: its line, its
    times in the PC's zone and the zone named once (polyglotic-hq 542)."""
    in_lab_zone(lab)
    shown = window(lab)
    shown.show_notice(maintenance_words.soon_line(PLANNED))
    shown._tick()
    lab.pump()
    return shown


def maintenance_during(lab: Lab) -> QWidget:
    """During a planned maintenance window: the notice says until when, in
    the PC's zone, named (polyglotic-hq 563, 542's proposal) - at a fixed
    time in it, so the picture is the same any day."""
    in_lab_zone(lab)
    real = maintenance_words.wall_clock
    maintenance_words.wall_clock = lambda: (
        PLANNED.starts_at + (PLANNED.ends_at - PLANNED.starts_at) / 3
    )
    maintenance_words.hold(PLANNED)
    lab.closing.append(lambda: maintenance_words.hold(None))
    lab.closing.append(lambda: setattr(maintenance_words, "wall_clock", real))
    shown = window(lab)
    shown.set_connection(Notice.MAINTENANCE, 120.0)
    shown._tick()
    lab.pump()
    return shown


class _Sheet(QWidget):
    """Windows one above another, each at its own size, as each draws."""

    GAP = 8

    def __init__(self, windows: list[CaptionWindow]) -> None:
        super().__init__()
        self.windows = windows
        self.resize(
            max(w.width() for w in windows),
            sum(w.height() + self.GAP for w in windows) - self.GAP,
        )

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        """Each window and where it's drawn (`checks.place_in`)."""
        found: list[tuple[QWidget, QPoint, float]] = []
        y = 0
        for each in self.windows:
            found.append((each, QPoint(0, y), 1.0))
            y += each.height() + self.GAP
        return found

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        for each, at, _scale in self.places():
            each.render(painter, at, QRegion(), QWidget.RenderFlag.DrawChildren)
        painter.end()


NOTICES: list[tuple[Notice | None, float | None, bool, str | None]] = [
    (Notice.RECONNECTING, 4.0, False, None),
    (Notice.SERVER_BUSY, 24.0, False, None),  # the server full (208)
    # why the server can't be reached (251): ours, counting; the learner's, Home
    (Notice.CANT_REACH, 8.0, False, None),
    (Notice.BLOCKED, None, False, None),
    (Notice.NOT_SIGNED_IN, None, False, None),
    (Notice.UPDATE_NEEDED, None, False, None),
    (Notice.STOPPED, None, False, None),
    (Notice.STOPPED, None, True, None),  # why: today's free minutes used
    (Notice.BUSY, None, False, "busy"),  # said briefly: its words when shown
]
"""Each notice a window can show but Paused (its own state): the session's
state, the retry's seconds, today's free minutes used, a brief notice."""


def notices(lab: Lab) -> QWidget:
    """Every notice on its line, a window each (087 section 5.5's words;
    109's section 2, part 5) - the same words as Home's banner and state."""
    shown = []
    for state, retry_in, minutes_used, brief in NOTICES:
        each = window(lab, captions=40)
        each.resize(640, 120)
        each.set_connection(None if brief else state, retry_in)
        each.set_minutes_used(minutes_used)
        if brief:  # translated now, in the lab's language
            each.show_notice(notice_text(Notice.BUSY, None))
        shown.append(each)

    def change() -> None:  # a notice changes on every window at once
        for each in shown:
            each.notices.paused = not each.notices.paused
            each._tick()

    lab.time("notice_change", change, repeat=10, budget=budgets.FRAME)
    for each in shown:
        each._tick()
    lab.pump()
    return _Sheet(shown)


def empty(lab: Lab) -> QWidget:
    shown = window(lab, captions=0)
    hovered(lab, shown)
    return shown


def everything_empty(lab: Lab) -> QWidget:
    """Everything the PC plays before its first caption - a new learner's
    first window (484): anything the PC plays is captioned here."""
    shown = window(lab, captions=0, source=WHOLE_SYSTEM)
    hovered(lab, shown)
    return shown


def new_window(lab: Lab) -> QWidget:
    """Its first seconds, not hovered (DECISIONS.md #56): new, or just put
    back by Reset position, with nothing to read yet, it shows its panel
    and whose captions appear there - then fades as an idle window does."""
    shown = window(lab, captions=0)
    shown.always_shown = False  # as a learner sees it
    lab.time("reset_position", shown.reset_position, repeat=5, budget=budgets.CLICK)
    return shown


def my_speech(lab: Lab) -> QWidget:
    shown = window(lab, show_mic=True)
    resize_steps(lab, shown)
    hovered(lab, shown)
    # photographed taller: at the default height the hover band covers the
    # "You" label, the one mark of the mic's line on the canvas (123)
    shown.resize(shown.width(), 300)
    lab.pump()
    return shown


def respoken(lab: Lab) -> QWidget:
    """Lines the learner said again for the app (polyglotic-hq 567): marked
    re-spoken on their label, under the app's name though labels are off."""
    shown = CaptionWindow(
        "lab", APP, WindowChoices(), LABELS[APP], None, mic=MIC, areas=_areas
    )
    shown.set_labels(LABELS, "You")
    shown.always_shown = True
    updates = finished(CAPTIONS, APP)
    for n, update in enumerate(updates):
        shown.view.apply(replace(update, respoken=n >= len(updates) - 2))
    shown.apply_changed(new_caption=True)
    shown.show()
    shown.resize(shown.width(), 300)
    lab.pump()
    return shown


def filled(lab: Lab) -> QWidget:
    """The Lab's Captions fill the width (polyglotic-hq 309): a caption's
    clauses run on in lines as wide as the window, its translation in the
    lines below - resized and with captions arriving, within the budgets
    a clause a row is held to."""
    look = CaptionLook(lab=CaptionLab(fill=Fill.STACKED))
    shown = window(lab, look=look)
    resize_steps(lab, shown)
    new_captions(lab, [shown])
    return shown


def filled_lines(lab: Lab) -> QWidget:
    """Captions fill the width, line by line (309's placement (b)): a line
    of what was said, the line of its translation under it, cut where
    their word links say both can be - narrower than the conversation's
    clauses, so some are cut and one wraps."""
    look = CaptionLook(lab=CaptionLab(fill=Fill.PAIRED))
    shown = window(lab, look=look)
    shown.resize(round(shown.width() * 0.42), shown.height())
    lab.pump()
    new_captions(lab, [shown])
    return shown


def flow_run_on(lab: Lab) -> QWidget:
    """The Lab's New layout (polyglotic-hq 340, decision 0132): line by
    line with captions running on into each other, word links in colours
    - resized and with captions arriving, within the budgets a clause a
    row is held to."""
    look = CaptionLook(
        lab=CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True),
        word_links=WordLinks.COLOURS,
    )
    shown = window(lab, look=look)
    resize_steps(lab, shown)
    new_captions(lab, [shown])
    return shown


def flow_arrows(lab: Lab) -> QWidget:
    """The New layout with Arrows and parts lined up: a curve from each
    linked word down to its counterpart in the line under it, captions
    running on - Arrows were off whenever captions filled the width."""
    look = CaptionLook(
        lab=CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True, aligned=True),
        word_links=WordLinks.ARROWS,
    )
    shown = window(lab, look=look)
    lab.pump()
    shown.canvas.repaint()
    return shown


def flow_placed(placing: Placing) -> Callable[[Lab], QWidget]:
    """The New layout with Arrows, parts lined up and captions running on,
    its parts placed (polyglotic-hq 458): nearest their links - a part's
    shorter piece over the words it is linked to - or a full line's
    spread evenly."""

    def run(lab: Lab) -> QWidget:
        look = CaptionLook(
            lab=CaptionLab(
                flow=True, fill=Fill.PAIRED, run_on=True, aligned=True, placing=placing
            ),
            word_links=WordLinks.ARROWS,
        )
        shown = window(lab, look=look)
        resize_steps(lab, shown)  # within the budgets packed lines are held to
        new_captions(lab, [shown])
        shown.canvas.repaint()
        return shown

    return run


def _select(lab: Lab, shown: CaptionWindow, to: RowKind) -> CaptionWindow:
    """Words selected from part way through the third caption from the
    end (or the oldest in view) to part way through the newest's first clause on side `to`, as a
    drag leaves them (polyglotic-hq 358)."""
    shown.canvas.repaint()
    lines = [line for line, _, _ in shown.canvas.placed]
    first, last = lines[-min(3, len(lines))], lines[-1]
    shown.held.hold(
        Selection(Place(first.key, 0, 2, RowKind.ORIGINAL), Place(last.key, 0, 4, to))
    )
    lab.pump()
    shown.canvas.repaint()
    return shown


def selected(lab: Lab) -> QWidget:
    """Words selected across three captions, what was said alone, in a
    clause a row with word links in colours (358): the highlight sits
    behind the text and its links."""
    look = CaptionLook(word_links=WordLinks.COLOURS)
    return _select(lab, window(lab, look=look), RowKind.ORIGINAL)


def flow_selected(lab: Lab) -> QWidget:
    """The New layout, captions running on: a selection from what was said
    to a translation takes both sides of every clause between (358)."""
    look = CaptionLook(
        lab=CaptionLab(flow=True, fill=Fill.PAIRED, run_on=True),
        word_links=WordLinks.COLOURS,
    )
    return _select(lab, window(lab, look=look), RowKind.TRANSLATION)


def listening(lab: Lab) -> QWidget:
    shown = window(lab)
    shown.set_listening(True)
    lab.pump()
    mark_frames(lab, shown)
    new_captions(lab, [shown])  # captions keep coming while it shows (260)
    return shown


def mark_frames(lab: Lab, shown: CaptionWindow) -> None:
    """The listening mark's sweep: its frames, each within a frame's
    budget - it's shown in every timing now, over anything (260)."""
    rect = shown.canvas.mark_rect
    assert rect is not None, "the listening mark isn't drawn"
    lab.time(
        "mark_frame",
        partial(shown.canvas.repaint, rect),
        repeat=20,
        budget=budgets.FRAME,
    )


def _live(shown: CaptionWindow) -> None:
    newest = finished(1, start=CAPTIONS)[0]
    live = replace(newest, caption_id=CaptionId("live"), kind=CaptionKind.LIVE)
    shown.view.apply(live)
    shown.apply_changed(new_caption=True)


def listening_preview(lab: Lab) -> QWidget:
    """Quick preview: its dim line, and the mark under it until the
    finished caption lands (260)."""
    shown = window(lab, look=CaptionLook(preview=True))
    _live(shown)
    shown.set_listening(True)
    lab.pump()
    mark_frames(lab, shown)
    return shown


def listening_live(lab: Lab) -> QWidget:
    """Live updates: the caption rewriting itself, the mark under it."""
    shown = window(lab)
    _live(shown)
    shown.set_listening(True)
    lab.pump()
    mark_frames(lab, shown)
    return shown


def listening_still(lab: Lab) -> QWidget:
    """Windows' animations off (reduced motion): the bar's three still dashes."""
    real = caption_window_module.reduced_motion
    caption_window_module.reduced_motion = lambda: True
    lab.closing.append(lambda: setattr(caption_window_module, "reduced_motion", real))
    shown = window(lab)
    shown.set_listening(True)
    lab.pump()
    return shown


def preview_line(lab: Lab) -> QWidget:
    shown = window(lab, look=CaptionLook(preview=True))
    _live(shown)
    lab.pump()
    return shown


FACES = (
    (
        "zh",
        "我们周末一起去打游戏吧，好不好？",
        "Let's play games together this weekend, okay?",
    ),
    ("th", "สุดสัปดาห์นี้เราไปเล่นเกมด้วยกันไหม", "Shall we go and play games this weekend?"),
    (
        "vi",
        "Cuối tuần này mình cùng chơi game nhé?",
        "Shall we play games together this weekend?",
    ),
    (
        "ar",
        "هل نلعب الألعاب معًا في عطلة نهاية الأسبوع؟",
        "Shall we play games this weekend?",
    ),
    (
        "hi",
        "क्या हम इस सप्ताहांत साथ में गेम खेलें?",
        "Shall we play games together this weekend?",
    ),
    (
        "ru",
        "Давай поиграем вместе в эти выходные?",
        "Shall we play together this weekend?",
    ),
    (
        "es",
        "¿Jugamos juntos este fin de semana, vale?",
        "Shall we play together this weekend, okay?",
    ),
)
"""One caption in each default face (polyglotic-hq 482): what was said in
Chinese, Thai, Vietnamese, Arabic, Hindi, Russian and Spanish, each over
its English."""


def _in_every_face(
    updates_kind: CaptionKind = CaptionKind.FINISHED,
) -> list[CaptionUpdate]:
    found = []
    for n, (language, said, meant) in enumerate(FACES):
        update = CaptionUpdate(
            CaptionId(f"face-{n}"),
            APP,
            CaptionKind.FINISHED,
            (clause(said, meant),),
            Language(language),
            (Language(language),),
            processing_ms=400,
        )
        found.append(update)
    if updates_kind is CaptionKind.LIVE:  # the last, Arabic's, still being spoken
        arabic = next(u for u in found if u.language == "ar")
        found = [u for u in found if u is not arabic]
        found.append(
            replace(arabic, caption_id=CaptionId("live"), kind=CaptionKind.LIVE)
        )
    return found


def faces(lab: Lab, look: CaptionLook | None = None, still: bool = False) -> QWidget:
    """Captions in each language's default face (482): Noto Sans SC, Noto
    Sans Thai Looped, Be Vietnam Pro, Noto Naskh Arabic, Noto Sans
    Devanagari, PT Sans and IBM Plex Sans - with `still`, Arabic's line
    still being spoken in italic, which Arabic never is."""
    shown = window(lab, captions=0)
    if look is not None:  # as a learner changes it (the presets' states do)
        shown.set_look(look)
    kind = CaptionKind.LIVE if still else CaptionKind.FINISHED
    for update in _in_every_face(kind):
        shown.view.apply(update)
    shown.apply_changed(new_caption=True)
    shown.resize(720, 640)
    lab.pump()
    return shown


def faces_light(lab: Lab) -> QWidget:
    paper = BY_KEY["paper"]
    look = CaptionLook(
        original=paper.original,
        translation=paper.translation,
        background=paper.background,
        opacity=paper.opacity,
        # its labels are 3.7-3.9:1 on paper, under the 4.5:1 the checks ask:
        # not the faces' (482 reports it); the preset states scroll theirs away
        show_language=False,
        show_source=False,
    )
    return faces(lab, look)


def faces_still_spoken(lab: Lab) -> QWidget:
    look = CaptionLook(lab=CaptionLab(unfinished=Unfinished.ITALIC))
    return faces(lab, look, still=True)


class _Screen(QWidget):
    """The work area at a quarter of its size, with the windows on it."""

    def __init__(self, windows: list[CaptionWindow]) -> None:
        super().__init__()
        self.windows = windows
        self.resize(AREA.width // 2, AREA.height // 2)

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        """Each window and where it's drawn, at half its size
        (`checks.place_in`)."""
        return [(each, each.pos() / 2, 0.5) for each in self.windows]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.scale(0.5, 0.5)
        for each in self.windows:
            each.render(
                painter, QPoint(each.x(), each.y()), QRegion(),
                QWidget.RenderFlag.DrawChildren,
            )  # fmt: skip
        painter.end()


def spoken_question(lab: Lab) -> QWidget:
    """Detect has heard its app speak Mandarin steadily: the window asks
    whether to always hear it as Mandarin (317, decision 0109)."""
    shown = window(lab)
    shown.suggest_spoken("zh")
    lab.pump()
    return shown


class _Together(QWidget):
    """A window and what opens over it or beside it (a top-level window of
    its own), drawn where they are on the screen."""

    def __init__(self, parts: list[QWidget]) -> None:
        super().__init__()
        self.parts = parts
        self.left = min(p.x() for p in parts)
        self.top = min(p.y() for p in parts)
        right = max(p.x() + p.width() for p in parts)
        bottom = max(p.y() + p.height() for p in parts)
        self.resize(right - self.left, bottom - self.top)

    def places(self) -> list[tuple[QWidget, QPoint, float]]:
        return [
            (each, QPoint(each.x() - self.left, each.y() - self.top), 1.0)
            for each in self.parts
        ]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        for each, at, _ in self.places():
            each.render(painter, at, QRegion(), QWidget.RenderFlag.DrawChildren)
        painter.end()


def _first_window(lab: Lab) -> tuple[CaptionWindows, CaptionWindow]:
    """A new PC's first caption window: it asks its languages (465)."""
    windows = CaptionWindows(None, MIC, _areas, offer_set_up=True)
    # A golden is a fresh learner even when an earlier state named languages.
    windows.stored.recent_spoken = ()
    windows.set_labels(LABELS, "You")
    windows.set_captioned([("Discord.exe", APP)])
    shown = windows.windows["Discord.exe"]
    shown.always_shown = True
    shown.show()
    lab.pump()
    lab.closing.append(windows.close)
    return windows, shown


def set_up(lab: Lab) -> QWidget:
    """The first caption window sets itself up (465, 449's 3A): its three
    language choices filled in, and Start captions."""
    _, shown = _first_window(lab)
    asked = shown.set_up
    assert asked is not None
    return _Together([shown, asked])


def first_heard(lab: Lab) -> QWidget:
    """A new PC's first caption window once captions come (478): it shows
    my speech from the start, so the learner's own lines are there, as
    "You", beside the app's - and the first caption closed the set-up."""
    windows, shown = _first_window(lab)
    assert shown.choices.show_mic  # the first window's default
    for n, update in enumerate(finished(CAPTIONS, APP)):
        windows.apply(replace(update, source_id=MIC) if n % 4 == 3 else update)
    lab.pump()
    assert shown.set_up is None  # the first caption closed it
    shown.resize(shown.width(), 300)  # taller, as my_speech: "You" in view
    lab.pump()
    return shown


def set_up_spoken(lab: Lab) -> QWidget:
    """The set-up with They speak's languages open inside it (465)."""
    _, shown = _first_window(lab)
    asked = shown.set_up
    assert asked is not None
    lab.time("set_up_spoken", asked.spoken.click, budget=budgets.CLICK)
    if not asked.spoken_choices.isVisible():
        asked.spoken.click()
    lab.pump()
    return _Together([shown, asked])


def languages_chip(lab: Lab) -> QWidget:
    """A later window's bar: "Detect → English ▾" opened - the three
    language rows and Start new windows like this (465)."""
    shown = window(lab)
    hovered(lab, shown)

    def toggle() -> None:
        shown.toggle_languages()

    for _ in range(6):  # open, close, open, ...: each a click
        lab.time("languages_chip", toggle, budget=budgets.CLICK)
    shown.toggle_languages()
    lab.pump()
    opened = shown.languages
    assert opened is not None
    lab.closing.append(shown.close)
    return _Together([shown, opened])


def lyrics(lab: Lab) -> QWidget:
    """A music player's window on Detect, its language chip opened: the
    Lyrics switch under They speak, on (polyglotic-hq 595, decision 0287) -
    a row no other window has."""
    shown = window(lab)
    shown.set_labels({**LABELS, APP: SourceLabel("Spotify", "#1ed760")}, "You")
    shown.music_player = True
    shown.set_lyrics(True)
    hovered(lab, shown)
    shown.toggle_languages()
    lab.pump()
    opened = shown.languages
    assert opened is not None and not opened.rows["lyrics"].isHidden()
    lab.closing.append(shown.close)
    return _Together([shown, opened])


def three_windows(lab: Lab) -> QWidget:
    windows = CaptionWindows(None, MIC, _areas)
    # three on their own, as a learner who chose Separate windows has them:
    # windows start joined (polyglotic-hq 554; joined: `joined_window.py`)
    windows.stored.joined = JoinedChoices(on=False, chosen=True)
    windows.set_labels(LABELS, "You")
    sources = [APP, SourceId("app-2"), SourceId("app-3")]
    windows.set_captioned([(f"app{n}", s) for n, s in enumerate(sources)])
    for each in windows.windows.values():
        each.always_shown = True
    for source in sources[:2]:
        for update in finished(40, source):
            windows.apply(update)
    lab.pump()
    shown = list(windows.windows.values())
    new_captions(lab, shown, sources[1])
    lab.closing.append(windows.close)
    return _Screen(shown)


STATES = [
    State(f"ui_next.w1_{name}", run, gated=True, scene=scene)
    for name, run, scene in (
        ("idle", idle, True),
        ("arriving", arriving, True),
        ("hovered", hovered_state, True),
        ("caption_hovered", caption_hovered, True),
        ("copied_toast", copied_toast, True),
        ("narrow", narrow, True),
        ("pace_minimum", partial(speaking_pace, narrowest=True), True),
        ("pace_normal", speaking_pace, True),
        ("pace_short", partial(speaking_pace, narrowest=True, short=True), True),
        ("pace_hidden", partial(speaking_pace, hidden=True), True),
        ("pace_transparent", partial(speaking_pace, opacity=0), True),
        ("pace_30", partial(speaking_pace, opacity=0.30, caption_pace=165), True),
        ("pace_82", partial(speaking_pace, opacity=0.82, caption_pace=165), True),
        ("caption_info_off", caption_info_off, True),
        ("settings_popover", settings_popover, False),
        ("pick_app", pick_app, False),
        ("original_only", original_only, True),
        ("long_translation_100", long_translation_100, True),
        ("long_translation_200", long_translation_200, True),
        ("locked", locked, True),
        ("locked_later", locked_later, True),
        ("scrolled_back", scrolled_back, True),
        ("scrollbar", scrollbar, True),
        ("paused", paused, True),
        ("notice", notice, True),
        ("notices", notices, True),
        ("maintenance_soon", maintenance_soon, True),
        ("maintenance_during", maintenance_during, True),
        ("empty", empty, True),
        ("everything_empty", everything_empty, True),
        ("new", new_window, True),
        ("my_speech", my_speech, True),
        ("respoken", respoken, True),
        ("filled", filled, True),
        ("filled_lines", filled_lines, True),
        ("flow_run_on", flow_run_on, True),
        ("flow_arrows", flow_arrows, True),
        ("flow_nearest", flow_placed(Placing.NEAREST), True),
        ("flow_evenly", flow_placed(Placing.EVENLY), True),
        ("selected", selected, True),
        ("flow_selected", flow_selected, True),
        ("listening", listening, True),
        ("listening_preview", listening_preview, True),
        ("listening_live", listening_live, True),
        ("listening_still", listening_still, True),
        ("preview_line", preview_line, True),
        ("three_windows", three_windows, True),
        ("spoken_question", spoken_question, True),
        ("faces", faces, True),
        ("faces_light", faces_light, True),
        ("faces_still_spoken", faces_still_spoken, True),
        ("set_up", set_up, False),
        ("set_up_spoken", set_up_spoken, False),
        ("first_heard", first_heard, False),
        ("languages_chip", languages_chip, False),
        ("lyrics", lyrics, False),
    )
] + [
    State(
        f"ui_next.w1_overflow_{'carry' if choice is LongLines.GROUPED else choice.value}{'_video' if video else ''}_{percent}",
        partial(overflow_lines, size=percent / 100, choice=choice, video=video),
        gated=True,
        scene=True,
    )
    for choice in (LongLines.DISPLAY_NEW_LINES, LongLines.GROUPED)
    for video in (False, True)
    for percent in (100, 200)
]
