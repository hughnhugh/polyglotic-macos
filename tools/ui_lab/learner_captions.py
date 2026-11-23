"""Timed learner caption operations, based on polyglotic-hq 590's ops590.py."""

from functools import partial

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from tests.ui.fakes import Built, MemorySettingsStore

from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import OFFERED_MODES, CaptionMode
from polyglotic_desktop.main import follow_settings
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.recorded_captions import APP
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from tools.ui_lab.caption_window import _Clock
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.new_parts import finished

APP_NAME = "Discord"
HISTORY = 150  # finished captions before the operation, as in ops590
WINDOW = (480, 560, 960, 400)  # x, y, width, height in pixels, as in ops590
CORNER_INSET_PX = 3  # inside the bottom-right resize handle
DRAGS = (1, -1, 1, -1)  # grow, then return to the original size, twice
DRAG_STEPS = 10  # mouse moves per drag
DRAG_STEP_PX = (15, 6)  # horizontal, vertical
CAPTION_PAIRS = 6  # one caption starts the glide, the next is timed during it
CAPTION_GAP_SEC = 2.0  # between pairs, enough for the playout and glide to settle
GLIDE_FRAME_SEC = 1 / 60  # draw the first moving frame before the timed arrival
SWITCH_ROUNDS = 3  # measure each timing mode and preset on multiple transitions


class _RecordedSource:
    """The app named in settings supplies only the lab's recorded captions."""

    per_app = True
    sample_shown = False

    def app_id(self, name: str) -> SourceId:
        assert name == APP_NAME
        return APP

    def shown(self) -> dict[SourceId, tuple[str, str]]:
        return {APP: (APP_NAME, APP_NAME)}


def _window(lab: Lab) -> tuple[Built, CaptionWindow, _Clock]:
    # The timed path uses normal motion even on a host with animations off.
    reduced_motion = caption_window_module.reduced_motion
    caption_window_module.reduced_motion = lambda: False
    lab.closing.append(
        lambda: setattr(caption_window_module, "reduced_motion", reduced_motion)
    )
    # Exercise paced motion explicitly, even when the app starts in Instant.
    built = Built(
        MemorySettingsStore(
            {
                "apps": [APP_NAME],
                "preset": use_presets.EVERYDAY,
                "caption_mode_chosen": CaptionMode.STEADY.value,
                "changed": ["caption_mode_chosen"],
            }
        ),
        tools=True,
        caption_learning=True,
    )
    lab.closing.append(built.close)
    windows, desktop = built.windows, built.desktop
    sources = _RecordedSource()

    def follow() -> None:
        follow_settings(windows, desktop, sources)  # type: ignore[arg-type]

    desktop.settings.changed.connect(follow)
    follow()
    shown = windows.windows[APP_NAME]
    shown.setGeometry(*WINDOW)
    clock = _Clock()
    clock.now = shown.clock()
    shown.clock = windows.word_clock = clock
    assert shown.deck is not None and shown.sliding, "learner's card glide is off"
    # Deliver the already-read history at the window's playout boundary.
    # Seed the deck itself, so resizing has all the cards a learner would have.
    for update in finished(HISTORY):
        clock.now += CAPTION_GAP_SEC
        shown.receive(update)
    clock.now += CAPTION_GAP_SEC
    lab.pump()
    shown.canvas.repaint()
    return built, shown, clock


def resize_drag(lab: Lab) -> CaptionWindow:
    _, shown, _ = _window(lab)
    left, none = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    def mouse(
        kind: QEvent.Type, at: QPointF, button: Qt.MouseButton, held: Qt.MouseButton
    ) -> None:
        local = QPointF(shown.mapFromGlobal(at.toPoint()))
        lab.app.sendEvent(
            shown,
            QMouseEvent(kind, local, at, button, held, Qt.KeyboardModifier.NoModifier),
        )

    original = shown.size()
    for direction in DRAGS:
        corner = QPoint(
            shown.width() - CORNER_INSET_PX, shown.height() - CORNER_INSET_PX
        )
        origin = QPointF(shown.mapToGlobal(corner))
        mouse(QEvent.Type.MouseButtonPress, origin, left, left)
        for step in range(1, DRAG_STEPS + 1):
            dx, dy = (px * direction * step for px in DRAG_STEP_PX)
            at = origin + QPointF(dx, dy)
            before = shown.size()
            lab.time(
                "resize_drag_step",
                partial(mouse, QEvent.Type.MouseMove, at, none, left),
                budget=budgets.FRAME,
            )
            assert direction * (shown.width() - before.width()) > 0, (
                "the move did not resize the window"
            )
        mouse(QEvent.Type.MouseButtonRelease, at, left, none)
        lab.pump()
    assert shown.size() == original, "the drag did not return to the starting size"
    return shown


def caption_during_glide(lab: Lab) -> CaptionWindow:
    built, shown, clock = _window(lab)
    windows = built.windows
    updates = iter(finished(2 * CAPTION_PAIRS, start=HISTORY))

    for _ in range(CAPTION_PAIRS):
        clock.now += CAPTION_GAP_SEC
        windows.release_words()
        shown.canvas.repaint()
        windows.apply(next(updates))
        while not shown.glide.moving(clock.now):
            due = windows.playout.due()
            assert due is not None, "the first caption did not start a glide"
            clock.now = due
            windows.release_words()
            shown.canvas.repaint()
        clock.now += GLIDE_FRAME_SEC
        shown.canvas.repaint()
        assert shown.glide.moving(clock.now), "the glide ended before the next caption"
        lab.time(
            "caption_during_glide",
            partial(windows.apply, next(updates)),
            budget=budgets.NEW_CAPTION,
        )

    clock.now += CAPTION_GAP_SEC
    windows.release_words()
    shown.canvas.repaint()
    clock.now += CAPTION_GAP_SEC
    return shown


def timing_switch(lab: Lab) -> CaptionWindow:
    built, shown, _ = _window(lab)
    settings = built.desktop.settings
    # The fixture starts in Steady; switch to Instant first.
    modes = OFFERED_MODES
    for mode in modes * SWITCH_ROUNDS:

        def switch(mode: CaptionMode = mode) -> None:
            settings.update(caption_mode_chosen=mode.value)
            shown.canvas.repaint()

        lab.time("timing_switch", switch, budget=budgets.CLICK)
        assert shown.timing is mode, "the timing change did not reach the window"
    return shown


def preset_switch(lab: Lab) -> CaptionWindow:
    built, shown, _ = _window(lab)
    for key in (
        use_presets.VIDEO,
        use_presets.CONVERSATION,
        use_presets.LEARNING,
        use_presets.EVERYDAY,
    ) * SWITCH_ROUNDS:

        def switch(key: str = key) -> None:
            built.panels.choose_preset(key)
            shown.canvas.repaint()

        lab.time("preset_switch", switch, budget=budgets.CLICK)
        assert built.desktop.settings.value.preset == key, "the preset did not change"
        assert (built.windows.subtitles is not None) == (key == use_presets.VIDEO)
    return shown


STATES = [
    State(
        "ui_next.w1_learner_resize_drag",
        resize_drag,
        gated=True,
        scene=True,
        visual_checks=False,
    ),
    State(
        "ui_next.w1_learner_caption_during_glide",
        caption_during_glide,
        gated=True,
        scene=True,
        visual_checks=False,
    ),
    State(
        "ui_next.w1_learner_timing_switch",
        timing_switch,
        gated=True,
        scene=True,
        visual_checks=False,
    ),
    State(
        "ui_next.w1_learner_preset_switch",
        preset_switch,
        gated=True,
        scene=True,
        visual_checks=False,
    ),
]
