"""W1, the caption window, offscreen (project 109's structure, section 2;
the interaction specs 10.1-10.4): its parts and states, and the windows
kept one per app."""

import logging
import time
from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import (
    QAccessible,
    QCursor,
    QEnterEvent,
    QKeyEvent,
    QMouseEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QPushButton, QWidget
from tests.ui_next.made_up import (
    EN,
    SEPARATE,
    ZH,
    at_one_moment,
    finished_updates,
    live_update,
)

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
)
from polyglotic_desktop.core.listening.display import RowKind
from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionId, CaptionMode
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_window as caption_window_module
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import (
    BAND_HEIGHT,
    MIN_PANEL,
    POINT_POLL_MS,
    POINT_REST,
    STRIP,
    VIEW_GRACE_SEC,
    CaptionWindow,
    _Drag,
    notice_text,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.languages import not_offered_note
from polyglotic_desktop.ui_next.os_words import pc_mac_or_linux
from polyglotic_desktop.ui_next.settings_popover import ROWS, beside
from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    CaptionLook,
    Notice,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.captions import (
    CAPTION_TEXT_SIZES,
    CAPTION_WINDOW_LINES,
)
from polyglotic_desktop.ui_next.views.placement import Edge, Preset, Rect

AREA = Rect(0, 0, 1920, 1040)
SECOND_APP = SourceId("app-2")
THIRD_APP = SourceId("app-3")
FOURTH_APP = SourceId("app-4")


def areas() -> list[Rect]:
    return [AREA]


class Store:
    """The settings port, in memory."""

    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = dict(values or {})
        self.saves = 0

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)
        self.saves += 1


FADING = CaptionLook(fade_after=8.0)
"""A look that fades after quiet: off by default since F15 (249)."""


def window_of(
    qapp: QApplication,
    captions: int = 40,
    look: CaptionLook | None = None,
    **choices: object,
) -> CaptionWindow:
    chosen = replace(WindowChoices(), **choices)  # type: ignore[arg-type]
    window = CaptionWindow(
        "Discord.exe", APP, chosen, SourceLabel("Discord", "#4dd0e1"), mic=MIC,
        areas=areas,
    )  # fmt: skip
    if look is not None:
        window.set_look(look)
    for update in finished_updates(captions):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    window.show()
    qapp.processEvents()
    return window


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    shown = window_of(qapp)
    at_one_moment(shown)  # never a slide begun by a busy runner's pause (578)
    yield shown
    shown.close()


def place(window: CaptionWindow) -> Rect:
    g = window.geometry()
    return Rect(g.x(), g.y(), g.width(), g.height())


def test_it_opens_at_its_default_slot(window: CaptionWindow) -> None:
    assert place(window) == Rect(480, 650, 960, 300)
    assert window.windowTitle() == "Discord captions"


REAL_LENGTH = (
    (
        "周末的时候，我们一家人常常去城外的山上走走，呼吸新鲜空气，也顺便看看路边的风景。",
        (
            "On weekends my family often goes for a walk in the hills outside the"
            " city to breathe fresh air and enjoy the scenery along the way."
        ),
    ),
    (
        "这家小餐馆的老板每天早上五点就起床准备食材，所以他做的饺子总是特别新鲜好吃。",
        (
            "The owner of this small restaurant gets up at five every morning to"
            " prepare the ingredients, so his dumplings are always fresh."
        ),
    ),
)
"""Made-up lines of a real sentence's length: FLEURS's median is about 40
characters of Chinese, or 120 of English (polyglotic-hq 158)."""


def test_a_new_window_shows_two_real_sentences_whole(qapp: QApplication) -> None:
    """145: a default window held about one real sentence, a long one's
    original cut at the top."""
    window = window_of(qapp, captions=0)
    for n, (original, translation) in enumerate(REAL_LENGTH):
        clause = Clause(original, {EN: translation})
        update = CaptionUpdate(
            CaptionId(f"real-{n}"), APP, CaptionKind.FINISHED, (clause,), ZH, (ZH,)
        )
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    window.canvas.grab()  # painted: what it placed
    placed = window.canvas.placed
    assert len(placed) == 2
    assert all(rect.top() >= window.canvas.clear_top for _, _, rect in placed)
    window.close()


def test_the_hover_band_is_drawn_over_the_captions_which_dont_move(
    window: CaptionWindow, qapp: QApplication
) -> None:
    """108's bug 4: today's header pushed the captions down."""
    before = window.canvas.geometry()
    tops = {line.key: rect.top() for line, _, rect in window.canvas.placed}
    window.hovered = True
    window._show_band(True)
    window.canvas.repaint()
    assert window.band.isVisible()
    assert window.canvas.geometry() == before == window.rect()
    after = {line.key: rect.top() for line, _, rect in window.canvas.placed}
    assert after and all(after[key] == tops[key] for key in after)  # none moved
    assert window.band.geometry().bottom() < BAND_HEIGHT


def test_the_band_shows_80_ms_after_the_mouse_comes_and_goes_300_ms_after_it_leaves(
    window: CaptionWindow,
) -> None:
    QApplication.sendEvent(window, _enter())
    assert not window.band_shown
    assert window._band_in.interval() == 80 and window._band_in.isActive()
    window._band_in.timeout.emit()
    assert window.band_shown
    window.leaveEvent(None)
    assert window._band_out.interval() == 300 and window._band_out.isActive()
    window._band_out.timeout.emit()
    assert not window.band_shown


def _shown(window: CaptionWindow) -> list[tuple[int, float]]:
    window.canvas.repaint()
    return [(line.key, rect.top()) for line, _, rect in window.canvas.placed]


def _on_words(window: CaptionWindow) -> QPointF:
    """A point on the text of the newest caption drawn where the mouse can
    be on it: in the window, on no edge and not under the hover band. A
    caption sliding in is drawn from below the window's foot: a point on it
    there was on the bottom edge, which never holds (polyglotic-hq 578: on
    GitHub's slower machines a pause between two arrivals made the second
    slide, and the hold tests failed 3 runs in 9)."""
    window.canvas.repaint()
    band = window.band.geometry() if window.band.isVisible() else QRect()
    refused = []
    for line, laid, rect in reversed(window.placed()):
        for row in laid.rows:
            box = row.layout.lineAt(0).naturalTextRect()
            point = QPointF(
                rect.x() + box.center().x(), rect.y() + row.top + box.center().y()
            )
            why = {
                "outside": not window.rect().contains(point.toPoint()),
                "edge": bool(window._edges(point)),
                "band": band.contains(point.toPoint()),
                "no hit": window.canvas.hit(point) is None,
            }
            if not any(why.values()):
                return point
            refused.append(
                (
                    line.key,
                    round(point.x()),
                    round(point.y()),
                    *(k for k, v in why.items() if v),
                )
            )
    raise AssertionError(
        f"no caption's words drawn where the mouse can be, in {window.size()}"
        f" (clear_top {window.canvas.clear_top}, moving"
        f" {window.motion.moving(window.clock())}): {refused[:8]}"
    )


def _off_words(window: CaptionWindow) -> QPointF:
    """A point on the panel around the text: on no caption's words, the
    hover band or an edge."""
    window.canvas.repaint()
    for x in range(window.width() - 40, 40, -20):
        for y in range(BAND_HEIGHT + 20, window.height() - 20, 4):
            point = QPointF(x, y)
            if window.canvas.hit(point) is None and not window._edges(point):
                return point
    raise AssertionError("no panel without words")


def _move(window: CaptionWindow, pos: QPointF) -> None:
    """The mouse moved to `pos`, no button held."""
    window.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.MouseMove, pos, window.mapToGlobal(pos),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )  # fmt: skip


def _ids(window: CaptionWindow) -> list[str]:
    return [str(line.caption_id) for line in window.view.lines]


def _still(before: list[tuple[int, float]], now: list[tuple[int, float]]) -> bool:
    """Every line shown `before` is where it was."""
    at = dict(now)
    return all(key in at and abs(at[key] - top) < 0.5 for key, top in before)


@pytest.mark.parametrize("skip", [False, True])
def test_leaving_a_busy_instant_window_shows_the_next_missed_caption(
    window: CaptionWindow,
    skip: bool,
) -> None:
    from polyglotic_desktop.core.listening.timing import CaptionMode

    now = [window.clock()]
    window.clock = lambda: now[0]
    window.set_timing(CaptionMode.INSTANT)
    window.grab()
    QApplication.sendEvent(window, _enter())
    _move(window, _on_words(window))
    before = max(key for key, _ in _shown(window))
    first, second, third = finished_updates(3, start=80)
    for update in (first, second, third):
        window.receive(update)
    window.leaveEvent(None)
    window._hold_timer.timeout.emit()
    assert window.motion.moving(window.clock())
    now[0] += 2.0
    visible = _shown(window)
    assert visible[-1][0] == before + 1
    assert window.view.lines[-1].caption_id == third.caption_id
    assert not window.pill.isHidden() and "2 new" in window.pill.text()
    if skip:
        window.go_live()
    else:
        window._resume_timer.stop()
        window._resume_timer.timeout.emit()
    now[0] += 2.0
    assert _shown(window)[-1][0] == window.view.lines[-1].key


def test_the_mouse_on_the_words_holds_the_view_not_the_captions(
    window: CaptionWindow,
) -> None:
    """109: nothing moves on hover. 145: lines moved under the mouse as
    captions arrived, so a click a moment late landed on another word.
    583 (the user, 2026-11-21: "The mouse shouldn't hold up delivery,
    could hold up pushing text by introducing back to live / new messages
    alert right?"): the caption comes in at once; the view holds, and Back
    to live counts it."""
    QApplication.sendEvent(window, _enter())
    _move(window, _on_words(window))  # reaching for a word
    before = _shown(window)
    (new,) = finished_updates(1, start=40)
    assert window.receive(new)  # in at once
    assert window.view.lines[-1].caption_id == new.caption_id
    assert _still(before, _shown(window))  # nothing moved under the mouse
    assert not window.pill.isHidden() and "1 new" in window.pill.text()
    window.leaveEvent(None)  # off the window: live a moment later
    assert not window.view.scroll.following and window._hold_timer.isActive()
    assert window._hold_timer.interval() == round(VIEW_GRACE_SEC.value * 1000)
    window._hold_timer.timeout.emit()
    assert window.view.scroll.following and window.pill.isHidden()
    assert _shown(window)[-1][0] == window.view.lines[-1].key


def test_only_the_words_hold_the_view(window: CaptionWindow) -> None:
    """polyglotic-hq 554 (DECISIONS #242's C): the mouse coming over the
    window, or moving over the panel around the text, held every new
    caption. Only the words hold now - the view, not the captions (583) -
    and moving off them lets it go."""
    first, second, third, fourth = finished_updates(4, start=40)
    panel = _off_words(window)
    QApplication.sendEvent(window, QEnterEvent(panel, panel, panel))
    assert window.receive(first)  # came over the panel: not held
    _move(window, _off_words(window))
    assert window.receive(second) and window.view.scroll.following
    _move(window, _on_words(window))
    assert window.receive(third)  # on a caption's words: in, the view held
    assert not window.view.scroll.following
    _move(window, _off_words(window))  # off them: live after the grace
    window._hold_timer.timeout.emit()
    assert window.view.scroll.following
    assert _ids(window)[-1] == str(third.caption_id)
    window.hovered, window.band_shown = True, False
    window._show_band(True)
    _move(window, QPointF(window.band.geometry().center()))
    assert window.receive(fourth) and window.view.scroll.following  # the band
    window._show_band(False)


def test_a_busy_runners_pause_never_slides_a_tests_captions(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 578: on GitHub's machines a pause of 0.1 s between two
    arrivals - the runner busy, or collecting garbage - slid the second in,
    drawn below the window's foot with nothing above it, and the hold and
    drag tests missed the words. A test's window (`at_one_moment`) has its
    captions arrive at one moment, whatever the runner does between them."""
    window = window_of(qapp)
    at_one_moment(window)
    paused = [0.0]
    real = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real() + paused[0])
    first, second = finished_updates(2, start=40)
    window.receive(first)
    paused[0] += 0.1  # the runner pauses
    window.receive(second)
    window.canvas.repaint()
    assert not window.motion.moving(window.clock())
    assert any(rect.bottom() <= window.height() for _, _, rect in window.placed())
    window.close()


def test_the_words_of_a_caption_still_sliding_in_hold_the_view(
    window: CaptionWindow,
) -> None:
    """polyglotic-hq 578: a pause between two arrivals - a busy runner's
    0.1 s - and the second slides in from below the window's foot. The
    mouse on visible words holds the view as the next caption arrives."""
    now = [window.clock() + 10.0]  # well after the window opened
    window.clock = lambda: now[0]
    first, second, third = finished_updates(3, start=40)
    panel = _off_words(window)
    QApplication.sendEvent(window, QEnterEvent(panel, panel, panel))
    assert window.receive(first)  # came over the panel: not held
    now[0] += 0.1
    assert window.receive(second)
    window.canvas.repaint()
    assert window.motion.moving(now[0])  # still sliding in
    _move(window, _on_words(window))
    assert window.receive(third)
    assert not window.view.scroll.following


def test_a_mouse_moving_over_the_words_for_20_s_holds_no_caption(
    window: CaptionWindow,
) -> None:
    """polyglotic-hq 554, a tester's report 40f40850 (2026-11-20, "Another
    stall and hang, 5-10+ seconds til text"): with the mouse moving over a
    caption window, its captions waited up to 19.9 s, then came all at
    once. 20 s of a mouse moving over the words every 0.25 s while a
    caption comes each second: every one is in the window as it comes
    (583), and the lines shown never move under the mouse."""
    now = [0.0]
    window.clock = lambda: now[0]
    QApplication.sendEvent(window, _enter())
    _move(window, _on_words(window))
    before = _shown(window)
    updates = iter(finished_updates(20, start=100))
    for tick in range(80):
        now[0] += 0.25
        _move(window, _on_words(window))
        if tick % 4 == 0:
            update = next(updates)
            window.receive(update)
            assert window.view.lines[-1].caption_id == update.caption_id
    assert _still(before, _shown(window))
    assert "20 new" in window.pill.text()


def test_a_mouse_left_on_the_words_keeps_the_view_and_the_captions_come(
    window: CaptionWindow,
) -> None:
    """A parked mouse mustn't stop the captions: they come in, the view
    holds and Back to live counts them; Back to live goes live at once."""
    QApplication.sendEvent(window, _enter())
    _move(window, _on_words(window))
    for update in finished_updates(3, start=40):
        assert window.receive(update)
    assert "3 new" in window.pill.text()
    window.pill.click()
    assert window.view.scroll.following and window.pill.isHidden()


def test_a_locked_window_never_holds_its_captions(window: CaptionWindow) -> None:
    window.set_locked(True)
    QApplication.sendEvent(window, _enter())
    _mouse(window, "move", QPointF(300, 120))
    (new,) = finished_updates(1, start=40)
    assert window.receive(new)
    window.set_locked(False)


def test_the_strip_is_the_label_and_four_buttons_at_every_width(
    window: CaptionWindow, qapp: QApplication
) -> None:
    """The user, 2026-11-07: a minimal strip, no fold; when it's narrow the
    label shortens first."""
    assert list(window.buttons) == list(STRIP)
    assert [b.defaultAction() for b in window.buttons.values()] == [
        window.controls[name] for name in STRIP
    ]
    window.hovered = True
    window._show_band(True)
    window.resize(960, 180)
    qapp.processEvents()
    # "Report a problem" is an alpha tester's only (275): not here; Fill the
    # width isn't on the strip at all (polyglotic-hq 556) and is behind its
    # flag, off (555)
    assert window.buttons["report"].isHidden() and "fill" not in window.buttons
    shown = [b for name, b in window.buttons.items() if name != "report"]
    # each its own width: its words', or an icon's as wide as its glyph was (179)
    hints = [max(b.sizeHint().width(), b.minimumWidth()) for b in shown]
    assert [b.width() for b in shown] == hints
    # the language chip right after the label (465)
    assert window.chip.isVisible()
    assert window.chip.x() >= window.tag.geometry().right()
    assert window.chip.x() - window.tag.geometry().right() <= 8
    window.resize(window._minimum().width, 180)
    qapp.processEvents()
    assert all(not b.isHidden() and b.width() > 0 for b in shown)
    assert window.chip.isVisible() and not window.chip.icon().isNull()
    assert window.tag.width() > 0


def test_an_alpha_testers_strip_reports_a_problem_at_every_width(
    window: CaptionWindow, qapp: QApplication
) -> None:
    """polyglotic-hq 275: one click from where the tester is looking."""
    asked: list[bool] = []
    window.report_wanted.connect(lambda: asked.append(True))
    window.set_reporting(True)
    window.hovered = True
    window._show_band(True)
    window.resize(MIN_PANEL.width, 180)
    qapp.processEvents()
    shown = [b for name, b in window.buttons.items() if name != "fill"]  # 555
    assert all(not b.isHidden() and b.width() > 0 for b in shown)
    window.buttons["report"].click()
    assert asked == [True]
    window.set_reporting(False)
    assert window.buttons["report"].isHidden()


def test_the_settings_popover_has_the_rest_in_order(
    window: CaptionWindow, qapp: QApplication
) -> None:
    window.hovered = True
    window._show_band(True)
    window.buttons["settings"].click()
    popover = window.popover
    assert popover is not None and popover.isVisible()
    assert [name for name in popover.rows if name in ROWS] == list(ROWS)
    shown = [name for name in ROWS if not popover.rows[name].isHidden()]
    order = [popover.rows[name].geometry().top() for name in shown]
    hidden = ("join",)  # one window; lyrics lives in the language popover (655)
    assert order == sorted(order)
    assert all(popover.rows[name].isHidden() for name in hidden)
    stop = popover.rows["stop"]
    assert isinstance(stop, QPushButton) and stop.text() == "Stop captioning Discord"
    window.buttons["settings"].click()  # the button closes it too
    assert not popover.isVisible()


def test_the_popover_never_takes_the_focus(window: CaptionWindow) -> None:
    """A full-screen game can minimise when it loses focus: the popover and
    the window are shown without activating, and on Windows a click on
    them doesn't activate them (WS_EX_NOACTIVATE)."""
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None
    # on Linux the popover takes the keyboard while it's open (570): its test
    # is test_popover_takes_the_keyboard.py
    for shown in (window,) if popover.takes_the_keyboard else (window, popover):
        assert shown.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        assert shown.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert all(
        child.focusPolicy() == Qt.FocusPolicy.NoFocus
        for child in popover.findChildren(QWidget)
    )
    assert not popover.findChildren(QMenu)  # nothing opens a window of its own


def test_the_language_list_says_why_mongolian_and_kazakh_are_not_there(
    window: CaptionWindow,
) -> None:
    """Under the list while it's open, as the transcript rail's Translate
    into row says it (DECISIONS.md #40; polyglotic-hq 132's map, 144)."""
    window.hovered = True
    window._show_band(True)
    window.toggle_languages()
    popover = window.languages
    assert popover is not None
    assert not popover.not_offered.isVisible()  # the list shut
    popover.language.click()
    assert popover.not_offered.isVisible()
    assert popover.not_offered.text() == not_offered_note()
    popover.language.click()
    assert not popover.not_offered.isVisible()


def test_changes_in_the_popover_apply_at_once(window: CaptionWindow) -> None:
    timings: list[str] = []
    stopped: list[bool] = []
    window.timing_wanted.connect(timings.append)
    window.stop_wanted.connect(lambda: stopped.append(True))
    window.hovered = True
    window._show_band(True)
    window.toggle_languages()
    popover = window.languages
    assert popover is not None
    popover.language.click()  # the list opens inside the popover
    assert popover.languages.isVisible()
    original_only = popover.languages.item(0)
    popover._language_chosen(original_only)
    assert window.choices.target is None and not popover.languages.isVisible()
    assert popover.language.text().startswith("Original only")
    window.controls["show_mic"].trigger()
    assert window.choices.show_mic
    window.controls["live"].trigger()
    assert timings == ["live"]
    window.controls["stop"].trigger()
    assert stopped and popover.isVisible()  # it stays open until closed


def test_esc_or_a_click_elsewhere_closes_it(
    window: CaptionWindow, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    held: set[str] = set()
    window.keys = lambda name: name in held
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None and popover._poll.isActive()
    held.add("escape")  # Esc, wherever the keyboard is (a game, say)
    popover._look_at_keys()
    assert not popover.isVisible() and not popover._poll.isActive()
    held.clear()
    window.toggle_settings()
    held.add("mouse")
    inside = popover.frameGeometry().center()
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: inside))
    popover._look_at_keys()
    assert popover.isVisible()  # a click in it
    elsewhere = popover.frameGeometry().bottomRight() + QPoint(300, 300)
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: elsewhere))
    popover._look_at_keys()
    assert not popover.isVisible()  # a click on another app
    held.clear()
    window.toggle_settings()
    QApplication.sendEvent(
        popover,
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        ),
    )
    assert not popover.isVisible()  # Esc while this app has the keyboard


def test_it_keeps_the_strip_and_closes_when_locked_or_hidden(
    window: CaptionWindow,
) -> None:
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None
    window._band_left()
    assert window.band_shown and popover.isVisible()
    window.set_locked(True)
    assert not popover.isVisible() and not window.band_shown
    window.set_locked(False)
    window._show_band(True)
    window.toggle_settings()
    window.hide()
    assert not popover.isVisible()


def test_beside_the_button_flipped_to_stay_on_the_screen() -> None:
    area = Rect(0, 0, 1920, 1040)
    low = QRect(1880, 1000, 26, 22)  # a window at the bottom right
    at = beside(low, (280, 400), area)
    assert at.y() + 400 <= low.top() and at.x() + 280 <= area.right
    high = QRect(900, 100, 26, 22)
    at = beside(high, (280, 400), area)
    assert at.y() >= high.bottom() and at.x() + 280 == high.right() + 1


def test_a_resize_step_lays_out_again_in_the_same_frame_and_keeps_the_preset(
    window: CaptionWindow,
) -> None:
    start = place(window)
    drag = _Drag(Edge.TOP, QPointF(), start)
    window.resize_by(drag, 0, -120)
    assert place(window) == Rect(480, 530, 960, 420)  # the bottom stays
    assert window.choices.preset is Preset.BOTTOM_CENTRE
    width = window.canvas.placed[0][2].width()
    window.resize_by(_Drag(Edge.RIGHT, QPointF(), place(window)), -100, 0)
    assert place(window).centre[0] == start.centre[0]  # centred: both sides
    assert window.canvas.placed[0][2].width() == width - 200  # rewrapped already


def test_a_resize_stops_at_the_minimum_and_a_real_drag_saves_the_place(
    window: CaptionWindow, qapp: QApplication
) -> None:
    changed = []
    window.changed.connect(lambda: changed.append(True))
    top_middle = QPointF(480, 2)
    _mouse(window, "press", top_middle)
    _mouse(window, "move", top_middle + QPointF(0, 400))
    _mouse(window, "release", top_middle + QPointF(0, 400))
    assert window.height() == MIN_PANEL.height
    assert window.choices.geometry == place(window)
    assert window.choices.preset is Preset.BOTTOM_CENTRE and changed


def test_a_resize_drag_says_what_it_did_in_sizes_only(
    window: CaptionWindow, caplog: pytest.LogCaptureFixture
) -> None:
    """The log says each resize drag's edges and sizes - and when nothing
    changed - never a caption or an app (polyglotic-hq 586)."""
    caplog.set_level(logging.INFO, logger="polyglotic_desktop.ui_next.caption_window")
    top_middle = QPointF(480, 2)
    _mouse(window, "press", top_middle)
    _mouse(window, "move", top_middle + QPointF(0, 400))
    _mouse(window, "release", top_middle + QPointF(0, 400))
    _mouse(window, "press", top_middle)
    _mouse(window, "move", top_middle + QPointF(0, 50))  # at the minimum already
    _mouse(window, "release", top_middle + QPointF(0, 50))
    said = [r.getMessage() for r in caplog.records if "resized" in r.getMessage()]
    least = MIN_PANEL.height
    wide = window._minimum().width  # the strip's, or MIN_PANEL's
    shrunk = f"960 x 300 to 960 x {least} (least {wide} x {least})"
    kept = f"960 x {least} to 960 x {least} (least {wide} x {least}) - unchanged"
    assert said == [
        f"caption window 0 resized at TOP: {shrunk}",
        f"caption window 0 resized at TOP: {kept}",
    ]


def test_moving_snaps_to_a_preset_or_is_where_i_put_it(window: CaptionWindow) -> None:
    start = place(window)
    window.move_by(_Drag(Edge.NONE, QPointF(), start), -430, 10)  # near Bottom left
    assert place(window).x == 40
    assert window.notice.text() == "Bottom left"
    window.mouseReleaseEvent(_release_after(window, Preset.BOTTOM_LEFT))
    assert window.choices.preset is Preset.BOTTOM_LEFT
    window.move_by(_Drag(Edge.NONE, QPointF(), place(window)), 300, -300)
    window.mouseReleaseEvent(_release_after(window, Preset.CUSTOM))
    assert window.choices.preset is Preset.CUSTOM
    assert window.choices.geometry == place(window)


def test_moving_is_clamped_to_the_work_area(window: CaptionWindow) -> None:
    window.move_by(_Drag(Edge.NONE, QPointF(), place(window)), 5000, 5000)
    assert place(window).right == AREA.right and place(window).bottom == AREA.bottom


def test_text_size_is_live_and_the_window_keeps_its_size(window: CaptionWindow) -> None:
    before = place(window)
    newest = window.view.lines[-1].key
    window.step_text(3)
    assert window.view.text_size == 1.3 == window.choices.text_size
    assert place(window) == before
    assert window.canvas.placed[-1][0].key == newest  # still at the bottom
    for _ in range(40):
        window.step_text(1)
    assert window.view.text_size == CAPTION_TEXT_SIZES[1] == 4.0  # 305
    for _ in range(40):
        window.step_text(-1)
    assert window.view.text_size == CAPTION_TEXT_SIZES[0] == 0.6


def _wheel(widget: QWidget, delta: int, modifier: Qt.KeyboardModifier) -> None:
    event = QWheelEvent(
        QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(), QPoint(0, delta),
        Qt.MouseButton.NoButton, modifier, Qt.ScrollPhase.NoScrollPhase, False,
    )  # fmt: skip
    QApplication.sendEvent(widget, event)
    assert event.isAccepted()


@pytest.mark.parametrize(
    ("mac", "modifier"),
    [
        (False, Qt.KeyboardModifier.ControlModifier),
        (True, Qt.KeyboardModifier.ControlModifier),
        (True, Qt.KeyboardModifier.MetaModifier),
    ],
)
def test_modified_wheel_scales_both_rows_without_scrolling(
    window: CaptionWindow,
    monkeypatch: pytest.MonkeyPatch,
    mac: bool,
    modifier: Qt.KeyboardModifier,
) -> None:
    monkeypatch.setattr(caption_window_module, "on_a_mac", lambda: mac)
    window.set_translation_size(0.8)
    before = place(window)
    changed: list[tuple[float, float]] = []
    window.changed.connect(
        lambda: changed.append(
            (window.choices.text_size, window.choices.translation_size)
        )
    )
    _wheel(window, 120, modifier)
    _wheel(window, -120, modifier)
    assert changed == [(1.1, 0.88), (1.0, 0.8)]
    assert window.view.scroll.following
    assert place(window) == before
    _wheel(window, 120, Qt.KeyboardModifier.NoModifier)
    assert not window.view.scroll.following
    assert len(changed) == 2


@pytest.mark.parametrize(
    ("cap", "trans", "delta", "expected"),
    [
        (1.98, 3.96, 120, (2.0, 4.0)),
        (2.0, 4.0, 120, (2.0, 4.0)),
        (1.24, 0.62, -120, (1.2, 0.6)),
        (1.2, 0.6, -120, (1.2, 0.6)),
    ],
)
def test_modified_wheel_stops_both_rows_at_one_rows_limit(
    window: CaptionWindow,
    cap: float,
    trans: float,
    delta: int,
    expected: tuple[float, float],
) -> None:
    window.set_text_size(cap)
    window.set_translation_size(trans)
    _wheel(window, delta, Qt.KeyboardModifier.ControlModifier)
    assert (window.view.text_size, window.choices.translation_size) == expected
    assert window.view.scroll.following


def test_ctrl_wheel_over_the_scrollbar_zooms_the_caption_window(
    window: CaptionWindow,
) -> None:
    window.set_timing(CaptionMode.STEADY)
    assert window.scroll_bar.isVisible() and window.scroll_bar.maximum() > 0
    _wheel(window.scroll_bar, 120, Qt.KeyboardModifier.ControlModifier)
    assert window.view.text_size == window.choices.translation_size == 1.1
    assert window.view.scroll.following


def test_repeated_wheel_steps_keep_the_ratio_despite_percentage_rounding(
    window: CaptionWindow,
) -> None:
    window.set_translation_size(1.03)
    for _ in range(10):
        _wheel(window, 120, Qt.KeyboardModifier.ControlModifier)
    assert (window.view.text_size, window.choices.translation_size) == (2.0, 2.06)
    window.set_translation_size(1.6)
    _wheel(window, 120, Qt.KeyboardModifier.ControlModifier)
    assert (window.view.text_size, window.choices.translation_size) == (2.1, 1.68)


def test_a_hint_on_bigger_text_when_few_lines_fit(window: CaptionWindow) -> None:
    window.resize(960, 180)
    window.set_text_size(2.0)
    window.set_translation_size(2.0)
    assert window.controls["bigger"].toolTip() == "Drag the top edge for more lines"


def test_original_only_shows_no_translation(window: CaptionWindow) -> None:
    languages = []
    window.language_changed.connect(lambda: languages.append(True))
    window.set_language("")
    kinds = {row.kind for line in window.view.lines for row in line.rows}
    assert kinds == {RowKind.ORIGINAL} and languages


def test_show_my_speech_here_adds_my_lines(window: CaptionWindow) -> None:
    mine = replace(finished_updates(1, start=900)[0], source_id=MIC)
    assert not window.view.apply(mine)
    window.set_show_mic(True)
    assert window.view.apply(mine)
    assert window.view.lines[-1].by_you
    assert window.view.lines[-1].label == "You  Mandarin"  # always labelled
    assert window.mic_button.isChecked() and not window.tag.mic


def test_scrolled_back_says_how_many_are_new(window: CaptionWindow) -> None:
    window.canvas.scroll_by(400)
    window._refresh()
    assert not window.pill.isHidden() and window.pill.text() == "Back to live"
    for update in finished_updates(3, start=500):
        window.view.apply(update)
    window.apply_changed(new_caption=True)
    assert window.pill.text() == "Back to live · 3 new"
    window.pill.click()
    assert window.view.scroll.following and window.pill.isHidden()


def test_no_looks_wrong_on_a_hovered_finished_caption(window: CaptionWindow) -> None:
    """ "Looks wrong?" left the interface (polyglotic-hq 339; the user,
    2026-11-15: "get rid of the looks wrong report button")."""
    _, _, rect = window.canvas.placed[-1]
    window._hover(QPointF(rect.center().x(), rect.center().y()))
    window.canvas.repaint()
    assert not hasattr(window, "looks_wrong")
    assert not hasattr(window.canvas, "flag_rect")
    assert not hasattr(window.canvas, "flagged")


def test_locked_no_band_no_hover_and_it_follows_live(window: CaptionWindow) -> None:
    window.canvas.scroll_by(400)
    window.set_locked(True)
    window._show_band(True)
    assert not window.band_shown and window.view.scroll.following
    assert window.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_a_full_server_retries_without_a_countdown(window: CaptionWindow) -> None:
    """The notice stays put while capacity is unavailable."""
    window.notices.retry_at = None
    window.set_connection(Notice.SERVER_BUSY, 24.0)
    window._tick()
    assert window.notice.text() == "Polyglotic is busy — try again in a few minutes"
    now = time.monotonic()
    assert window.notices.retry_in(now + 10) is None
    assert window.notices.next_change(now) is None


def test_notices_paused_first_then_brief_ones(window: CaptionWindow) -> None:
    window.set_connection(Notice.RECONNECTING, 4.0)
    window._tick()
    assert window.notice.text() == "Reconnecting - trying again in 4 s"
    window.set_paused(True)
    window._tick()
    assert window.notice.text() == "Paused"
    window.show_notice("The server is restarting")
    assert window.notice.text() == "The server is restarting"


class Clock:
    """The caption window's clock, moved by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def perf_counter(self) -> float:
        return self.now


def test_caption_motion_advances_between_windows_clock_ticks(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    monkeypatch.setattr(clock, "monotonic", lambda: 1000.0)
    window = window_of(qapp)
    try:
        window.glide.push(window.clock(), 104.0)
        clock.now += 0.008  # within one 15.625-ms system clock tick on Windows
        assert window.glide.to(window.clock()) < 104.0
    finally:
        window.close()


def _settle(window: CaptionWindow, clock: Clock) -> None:
    """Its fade run to the end, a frame at a time."""
    for _ in range(40):
        clock.now += 0.1
        window._tick()


@pytest.mark.parametrize("look", [FADING, CaptionLook()], ids=["fading", "never"])
def test_a_new_window_waits_for_audio_until_its_first_captions(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, look: CaptionLook
) -> None:
    """The user (polyglotic-hq 270/272): "Caption screen should open up once
    you connect an app / select from my PC displaying waiting for audio" -
    it stays until captions come, fading on or off, in place of DECISIONS.md
    #56's few seconds for a new window."""
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    new = window_of(qapp, captions=0, look=look)
    painted = new.grab().toImage()  # the panel, and its words in the middle
    assert painted.pixelColor(new.width() // 2, 4).alpha() > 0
    clock.now += 60.0  # a minute with nothing heard: still there
    _settle(new, clock)
    assert new.alpha == 1.0 and new.isVisible()
    new.close()


def test_reset_position_shows_a_window_with_captions_again(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DECISIONS.md #56, still: put somewhere new, a faded window shows
    itself for the fade-after time, then fades as an idle window does."""
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    shown = window_of(qapp, captions=2, look=FADING)
    clock.now += 9.0
    _settle(shown, clock)
    assert shown.alpha == 0.0  # quiet: faded
    shown.reset_position()
    clock.now += 1.0
    shown._tick()
    assert shown.alpha > 0.0  # coming back
    _settle(shown, clock)
    assert shown.alpha == 1.0
    clock.now += 8.0
    _settle(shown, clock)
    assert shown.alpha == 0.0  # then fades again
    shown.close()


def test_its_first_caption_ends_the_waiting(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    new = window_of(qapp, captions=0, look=FADING)
    for update in finished_updates(1):
        new.view.apply(update)
    new.apply_changed(new_caption=True)
    clock.now += 7.0
    new._tick()
    assert new.alpha == 1.0
    _settle(new, clock)  # then quiet for the fade-after time: it fades
    assert new.alpha == 0.0
    new.close()


STOPPED_SAID = pc_mac_or_linux(
    "Stopped - quit from the tray and start again",
    "Stopped - quit from the menu bar and start again",
    "Stopped - quit Polyglotic and start it again",  # no tray on GNOME (571)
)
"""What a stopped caption window says: where the app's icon is, on each OS."""


def test_each_notice_in_087s_words(window: CaptionWindow) -> None:
    """087 section 5.5's words (a busy time: slowed, as the server's pace
    hint does - not paused)."""
    said = {}
    for notice in (Notice.NOT_SIGNED_IN, Notice.UPDATE_NEEDED, Notice.STOPPED):
        window.set_connection(notice, None)
        window._tick()
        said[notice] = window.notice.text()
    assert said == {
        Notice.NOT_SIGNED_IN: "Not signed in - sign in on Home",
        Notice.UPDATE_NEEDED: "Update needed - captions paused; see Home",
        Notice.STOPPED: STOPPED_SAID,
    }
    window.set_minutes_used(True)
    window._tick()
    assert window.notice.text() == "Today's free minutes are used - more at midnight"
    window.set_paused(True)
    window._tick()
    assert window.notice.text() == "Paused"
    assert notice_text(Notice.BUSY, None) == (
        "Busy time - live updates slowed; captions continue"
    )


def test_stopped_says_what_to_do_as_home_does(window: CaptionWindow) -> None:
    """polyglotic-hq 235 (228's note): a caption window's "Stopped" was a
    dead end - the same one #340 fixed on Home - in the window testers
    actually look at. It says what to do, in Home's words, short enough
    for the notice line."""
    from PySide6.QtGui import QAction

    from polyglotic_desktop.ui_next.home import StateCard
    from polyglotic_desktop.ui_next.views.home import HomeState, ListeningState

    window.set_connection(Notice.STOPPED, None)
    window._tick()
    assert window.notice.text() == STOPPED_SAID
    home = StateCard(QAction("Pause captions"))
    home.show_state(HomeState(ListeningState.STOPPED, chosen=True))
    assert home.detail.text().startswith(
        pc_mac_or_linux(
            "quit from the tray and start ",
            "quit from the menu bar and start ",
            "quit Polyglotic and start ",
        )
    )
    assert notice_text(Notice.STOPPED, None) == window.notice.text()


def test_not_signed_in_and_update_needed_say_where_to_go(
    window: CaptionWindow,
) -> None:
    """polyglotic-hq 237 (235's finding): "Not signed in - captions paused"
    and "Update needed - captions paused" were the same dead end as Stopped
    (#357). Home has the Sign in button, and says which step the update
    needs; the windows say to go there."""
    from PySide6.QtGui import QAction

    from polyglotic_desktop.ui_next.home import StateCard
    from polyglotic_desktop.ui_next.views.home import HomeState, ListeningState

    for notice in (Notice.NOT_SIGNED_IN, Notice.UPDATE_NEEDED):
        window.set_connection(notice, None)
        window._tick()
        assert window.notice.text().endswith(" on Home") or (
            window.notice.text().endswith("; see Home")
        )
    home = StateCard(QAction("Pause captions"))
    home.show_state(HomeState(ListeningState.SIGN_IN_NEEDED, chosen=True))
    assert home.sign_in.isVisibleTo(home)  # Home has what the window points to
    home.show_state(HomeState(ListeningState.UPDATE_NEEDED, chosen=True))
    assert home.detail.text()  # and says what to do


def test_paused_it_shows_and_stops_fading(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    shown = window_of(qapp, look=FADING)
    shown.set_paused(True)
    clock.now += 60.0  # long past the fade-after time
    _settle(shown, clock)
    assert shown.alpha == 1.0 and shown.notice.text() == "Paused"
    shown.set_paused(False)
    _settle(shown, clock)
    assert shown.alpha == 0.0  # quiet for a minute: faded
    shown.close()


def _faded(qapp: QApplication, clock: Clock) -> CaptionWindow:
    faded = window_of(qapp, look=FADING)
    clock.now += 60.0  # long past the fade-after time
    _settle(faded, clock)
    assert faded.alpha == 0.0
    return faded


def test_a_faded_window_comes_back_when_the_mouse_rests_on_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """141: Windows passes the mouse through a faded window, so pointing
    where it was never brought it back (109: "fades to 0 except in hover").
    It looks where the mouse is instead; passing over isn't resting."""
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    faded = _faded(qapp, clock)
    assert faded._point_timer.isActive()
    assert faded._point_timer.interval() == POINT_POLL_MS
    inside = faded.geometry().center()
    faded.pointer = lambda: inside
    faded._look_for_pointer()  # passing over: one look
    faded.pointer = lambda: QPoint(5, 5)
    faded._look_for_pointer()
    _settle(faded, clock)
    assert faded.alpha == 0.0
    faded.pointer = lambda: inside
    for _ in range(POINT_REST):
        faded._look_for_pointer()
    _settle(faded, clock)
    assert faded.pointed and faded.alpha == 1.0
    assert faded._point_timer.isActive()  # to see it go
    faded.pointer = lambda: QPoint(5, 5)
    faded._look_for_pointer()
    _settle(faded, clock)
    assert not faded.pointed and faded.alpha == 0.0  # quiet: faded again
    assert faded._point_timer.isActive()
    faded.close()


def test_a_faded_locked_window_stays_click_through_and_faded(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    faded = _faded(qapp, clock)
    inside = faded.geometry().center()
    faded.pointer = lambda: inside
    faded.set_locked(True)
    assert not faded._point_timer.isActive()
    assert faded.windowFlags() & Qt.WindowType.WindowTransparentForInput
    _settle(faded, clock)
    for _ in range(POINT_REST):
        faded._look_for_pointer()  # (as if a look were due)
    _settle(faded, clock)
    assert faded.alpha == 0.0 and not faded.pointed
    faded.set_locked(False)  # unlocked: it looks again
    _settle(faded, clock)
    assert faded._point_timer.isActive()
    faded.close()


def test_a_window_shown_with_a_caption_doesnt_look_for_the_mouse(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shown, Windows gives it the mouse: Qt hears it come and go."""
    clock = Clock()
    monkeypatch.setattr(caption_window_module, "time", clock)
    faded = _faded(qapp, clock)
    for update in finished_updates(1, start=100):
        faded.view.apply(update)
    faded.apply_changed(new_caption=True)
    _settle(faded, clock)
    faded._look_for_pointer()
    assert faded.alpha == 1.0 and not faded._point_timer.isActive()
    faded.hide()
    assert not faded._point_timer.isActive()
    faded.close()


def test_an_empty_window_says_it_waits_and_whose_captions_appear_there(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    said: list[str] = []

    def tr(text: str) -> str:
        said.append(text)
        return text

    monkeypatch.setattr(caption_window_module, "_tr", tr)
    empty = window_of(qapp, captions=0)  # not hovered: it says so anyway
    empty.canvas.repaint()
    assert empty.canvas.shown == 0
    assert "Waiting for audio…" in said
    assert "{app}'s captions appear here" in said
    said.clear()
    empty.set_listening(True)  # speech heard, its caption not here yet
    empty.canvas.repaint()
    assert "Listening…" in said and "Waiting for audio…" not in said
    empty.close()


# -- the windows, one per app --------------------------------------------------------------


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(Store({"targets": ["en"]}), MIC, areas)
    found.stored.joined = SEPARATE  # on their own: windows start joined (554)
    yield found
    found.close()


def test_a_window_per_captioned_app_and_never_a_fourth(windows: CaptionWindows) -> None:
    windows.set_captioned(
        [("a", APP), ("b", SECOND_APP), ("c", THIRD_APP), ("d", FOURTH_APP)]
    )
    assert list(windows.windows) == ["a", "b", "c"]
    tops = [w.geometry().top() for w in windows.windows.values()]
    assert tops[0] > tops[1] > tops[2]  # stacked upwards, not overlapping
    windows.set_captioned([("b", SECOND_APP)])
    assert list(windows.windows) == ["b"]


def test_captions_go_to_their_apps_window(windows: CaptionWindows) -> None:
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.apply(finished_updates(1, source=SECOND_APP)[0])
    assert len(windows.windows["a"].view.lines) == 0
    assert len(windows.windows["b"].view.lines) == 1


def test_each_sources_languages_and_the_mic_only_while_a_window_shows_it(
    windows: CaptionWindows,
) -> None:
    wanted: list[bool] = []
    windows.mic_wanted.connect(wanted.append)
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.windows["b"].set_language("")
    assert windows.targets() == {APP: (EN,), SECOND_APP: ()}
    windows.windows["b"].set_show_mic(True)
    assert windows.targets()[MIC] == () and wanted[-1]
    windows.windows["a"].set_language("zh")
    windows.windows["a"].set_show_mic(True)
    assert windows.targets()[MIC] == (ZH,)
    windows.set_show_mic_everywhere(False)
    assert MIC not in windows.targets() and wanted[-1] is False


def test_choices_are_saved_by_app_and_a_new_window_copies_the_last(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.set_captioned([("a", APP)])
    windows.windows["a"].set_language("ja")
    windows.windows["a"].set_text_size(1.4)
    windows.save_now()
    store = windows._store
    assert isinstance(store, Store)
    saved = store.values[STORED_KEY]
    assert isinstance(saved, dict) and saved["windows"]["a"]["translate_into"] == "ja"
    assert store.values["targets"] == ["en"]  # today's settings kept as they were
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    b = windows.windows["b"].choices
    assert (b.translate_into, b.text_size, b.show_mic) == ("ja", 1.4, False)
    again = CaptionWindows(store, MIC, areas)
    again.set_captioned([("a", APP)])
    assert again.windows["a"].choices.target == Language("ja")
    again.close()


def test_wheel_zoom_saves_both_sizes_for_the_window_and_preset(
    windows: CaptionWindows,
) -> None:
    windows.set_preset_sizes("everyday")
    windows.set_captioned([("a", APP)])
    first = windows.windows["a"]
    first.set_text_size(1.0)
    first.set_translation_size(0.8)
    _wheel(first, 120, Qt.KeyboardModifier.ControlModifier)
    windows.save_now()
    store = windows._store
    assert isinstance(store, Store)
    again = CaptionWindows(store, MIC, areas)
    try:
        again.set_captioned([("a", APP)])
        assert again.current_size_readout() == (1.1, 0.88)
        assert again.stored.preset_sizes["everyday"] == (1.1, 0.88)
    finally:
        again.close()


def test_a_save_when_the_file_cant_be_read_keeps_todays_settings(
    windows: CaptionWindows,
) -> None:
    """Nothing read - the file gone, or locked for a moment - isn't "every
    other key removed": today's settings, as last read, aren't lost (121's
    mirror of 117 Low 9; the rule `Settings.update` follows)."""
    store = windows._store
    assert isinstance(store, Store)
    windows.set_captioned([("a", APP)])
    store.values["targets"] = ["zh"]  # changed since, by today's settings
    windows.save_now()
    store.values = {}  # can't be read at this moment
    windows.windows["a"].set_language("ja")
    windows.save_now()
    assert store.values["targets"] == ["zh"]  # as last read
    saved = store.values[STORED_KEY]
    assert isinstance(saved, dict) and saved["windows"]["a"]["translate_into"] == "ja"


def test_a_stored_language_not_offered_isnt_sent_as_a_sources_targets(
    qapp: QApplication,
) -> None:
    """117 Low 10: the windows read their choices against the languages the
    interface offers - Kazakh (DECISIONS.md #40) falls back to the default."""
    stored = {"windows": {"a": {"translate_into": "kk"}}, "last": {}}
    windows = CaptionWindows(Store({"targets": ["en"], STORED_KEY: stored}), MIC, areas)
    windows.set_captioned([("a", APP)])
    assert windows.windows["a"].choices.target == Language("en")
    assert windows.targets()[APP] == (Language("en"),)
    windows.close()


def test_a_saved_language_taken_off_is_noticed_once(qapp: QApplication) -> None:
    """DECISIONS.md #40 (polyglotic-hq 132's map, 144): a saved Mongolian or
    Kazakh falls back, and the windows say which were taken off - saved
    without them at once, so the next start says nothing. One never offered
    (a newer version's, edited by hand) falls back without a word."""
    stored = {
        "windows": {"a": {"translate_into": "kk"}, "b": {"translate_into": "xx"}},
        "last": {"translate_into": "mn"},
    }
    store = Store({"targets": ["en"], STORED_KEY: stored})
    windows = CaptionWindows(store, MIC, areas)
    assert windows.taken_off == ("mn", "kk")
    windows.close()
    saved = store.values[STORED_KEY]
    assert isinstance(saved, dict)
    kept = [w["translate_into"] for w in [saved["last"], *saved["windows"].values()]]
    assert not {"mn", "kk"} & set(kept)
    again = CaptionWindows(store, MIC, areas)
    assert again.taken_off == ()
    again.close()
    clean = CaptionWindows(Store({"targets": ["zh"]}), MIC, areas)
    assert clean.taken_off == ()
    clean.close()
    # today's settings only, from before the windows had their own: the same
    old = Store({"targets": ["mn", "zh"]})
    for found in [("mn",), ()]:
        windows = CaptionWindows(old, MIC, areas)
        assert windows.taken_off == found
        windows.close()


def test_every_window_reports_a_problem_for_an_alpha_tester(
    windows: CaptionWindows,
) -> None:
    asked: list[bool] = []
    windows.report_wanted.connect(lambda: asked.append(True))
    windows.set_reporting(True)  # before the window opens: it follows
    windows.set_captioned([("a", APP)])
    windows.windows["a"].buttons["report"].click()
    assert asked == [True]
    assert windows.windows["a"].reporting
    windows.set_reporting(False)
    assert not windows.windows["a"].reporting


def test_the_close_button_asks_to_stop_captioning_its_app(
    windows: CaptionWindows,
) -> None:
    stopped: list[str] = []
    windows.stop_wanted.connect(stopped.append)
    windows.set_captioned([("a", APP)])
    windows.windows["a"].buttons["stop"].click()
    assert stopped == ["a"]


@pytest.mark.parametrize("timing", list(CaptionMode))
def test_the_listening_mark_shows_per_window_in_every_timing(
    windows: CaptionWindows, timing: CaptionMode
) -> None:
    """polyglotic-hq 260 (the user's F33): the listening mark in every
    timing, from the moment speech is under way until its finished caption
    lands - a live update (Quick preview's line, Live updates' rewrites)
    doesn't end it."""
    windows.set_timing(timing)
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    first, second = windows.windows["a"], windows.windows["b"]
    windows.heard([SECOND_APP])
    assert second.listening and not first.listening
    windows.apply(live_update("glimpse", SECOND_APP))
    windows.heard([SECOND_APP])
    assert second.listening  # the speech goes on
    windows.heard([])  # it stopped: its finished caption is on its way
    assert second.listening
    windows.captioned(str(SECOND_APP))  # the finished caption lands
    assert not second.listening


@pytest.mark.parametrize("timing", list(CaptionMode))
def test_the_listening_mark_shows_for_my_speech_too(
    windows: CaptionWindows, timing: CaptionMode
) -> None:
    """My speech (the mic) in a window that shows it, as an app's (F33:
    "either through my own mic or others")."""
    windows.set_timing(timing)
    windows.set_captioned([("a", APP)])
    window = windows.windows["a"]
    windows.heard([MIC])
    assert not window.listening  # not shown here: not heard here
    window.set_show_mic(True)
    windows.heard([MIC])
    assert window.listening
    windows.heard([])
    windows.captioned(str(MIC))
    assert not window.listening


def test_with_windows_animations_off_the_mark_stands_still(
    window: CaptionWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reduced motion (Windows' animation effects off): the mark is three
    still dashes along its bar - drawn the same whenever it's drawn - and
    needs no frame timer; with animations on its lit part sweeps (260,
    267)."""
    from PySide6.QtGui import QImage

    def drawn() -> QImage:
        window.canvas.repaint()
        return window.canvas.grab().toImage()

    window.always_shown = True
    window.set_listening(True)
    window._tick()
    assert window._tick_timer.isActive()  # pulsing: a frame each tick
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: True)
    window._tick()
    assert not window._tick_timer.isActive()  # still: nothing moves
    now = [100.0]
    monkeypatch.setattr(caption_window_module.time, "monotonic", lambda: now[0])
    still = drawn()
    now[0] += 0.5  # a third of a sweep later
    assert drawn() == still
    assert window.canvas.mark_rect is not None
    monkeypatch.setattr(caption_window_module, "reduced_motion", lambda: False)
    assert drawn() != still  # sweeping: drawn differently a moment on


def test_hidden_and_locked_for_every_window(windows: CaptionWindows) -> None:
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.set_hidden(True)
    assert not any(w.isVisible() for w in windows.windows.values())
    windows.set_locked(True)
    windows.set_hidden(False)
    assert all(w.locked and w.isVisible() for w in windows.windows.values())


def test_signed_out_the_windows_say_so_then_go_until_signed_in(
    windows: CaptionWindows,
) -> None:
    """109's section 7: signed out, the caption windows close - here they
    say why on their notice line first, and are kept (captions, places,
    transcripts) for when the learner signs in."""
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    windows.apply(finished_updates(1)[0])
    windows.set_connection(Notice.NOT_SIGNED_IN, None)
    shown = list(windows.windows.values())
    for each in shown:
        each._tick()
    assert all(w.isVisible() for w in shown)
    assert shown[0].notice.text() == "Not signed in - sign in on Home"
    assert windows._going.interval() == 6000
    windows._going.timeout.emit()  # the notice's time is up
    assert windows.signed_out and not any(w.isVisible() for w in shown)
    windows.show_window("a")  # Home's Captions: not while signed out
    windows.set_hidden(False)  # nor the learner's Hide all, undone
    windows.set_captioned([("a", APP), ("b", SECOND_APP), ("c", THIRD_APP)])
    assert not any(w.isVisible() for w in windows.windows.values())
    windows.set_connection(None, None)  # signed in: back, as they were
    assert all(w.isVisible() for w in windows.windows.values())
    assert len(windows.windows["a"].view.lines) == 1
    assert windows.windows["c"]._intro_until is not None  # shown where it is


def test_signed_out_and_hidden_stays_hidden_when_signed_in(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([("a", APP)])
    windows.set_hidden(True)
    windows.set_connection(Notice.NOT_SIGNED_IN, None)
    windows._going.timeout.emit()
    windows.set_connection(None, None)
    assert not windows.windows["a"].isVisible()


def test_free_minutes_used_on_every_window_and_new_ones(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([("a", APP)])
    windows.set_minutes_used(True)
    windows.set_captioned([("a", APP), ("b", SECOND_APP)])
    for each in windows.windows.values():
        each._tick()
        assert each.notice.text().startswith("Today's free minutes are used")


def test_a_busy_time_is_said_briefly_over_live_updates_only(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([("a", APP)])
    window = windows.windows["a"]
    windows.set_busy(True)  # Steady: no live updates to slow
    window._tick()
    assert not window.notice.isVisible()
    windows.set_busy(False)
    windows.set_timing(CaptionMode.INSTANT)
    windows.set_busy(True)
    assert window.notice.text() == "Busy time - live updates slowed; captions continue"
    window.notices.brief("", 0.0, 0.0)  # its few seconds over
    windows.set_busy(True)  # still busy: not said again
    window._tick()
    assert not window.notice.isVisible()


def test_live_captions_change_the_window_too(windows: CaptionWindows) -> None:
    windows.set_captioned([("a", APP)])
    windows.apply(live_update("live-1"))
    assert windows.windows["a"].view.lines[-1].live


# -- helpers --------------------------------------------------------------------------------


def _enter() -> QEnterEvent:
    return QEnterEvent(QPointF(50, 50), QPointF(50, 50), QPointF(50, 50))


def _mouse(window: CaptionWindow, kind: str, pos: QPointF) -> None:
    types = {
        "press": QMouseEvent.Type.MouseButtonPress,
        "move": QMouseEvent.Type.MouseMove,
        "release": QMouseEvent.Type.MouseButtonRelease,
    }
    buttons = (
        Qt.MouseButton.NoButton if kind == "release" else Qt.MouseButton.LeftButton
    )
    event = QMouseEvent(
        types[kind], pos, window.mapToGlobal(pos), Qt.MouseButton.LeftButton,
        buttons, Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    if kind == "press":
        window.mousePressEvent(event)
    elif kind == "move":
        window.mouseMoveEvent(event)
    else:
        window.mouseReleaseEvent(event)


def _release_after(window: CaptionWindow, snapped: Preset) -> QMouseEvent:
    """A release ending a move that snapped to `snapped` (or didn't)."""
    window._drag = _Drag(Edge.NONE, QPointF(), place(window), snapped, moved=True)
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, QPointF(5, 5), QPointF(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip


def test_a_renamed_app_is_renamed_on_its_window(window: CaptionWindow) -> None:
    window.set_labels({APP: SourceLabel("Mei's call", "#4dd0e1")}, "You")
    assert window.windowTitle() == "Mei's call captions"
    assert window.buttons["stop"].toolTip() == "Stop captioning Mei's call"


# -- W1's first polish (project 113) ----------------------------------------------------


def test_the_band_covers_whole_rows_never_half_a_label(window: CaptionWindow) -> None:
    """On hover the strip half-covered the top line's label (112's
    screenshots): now what it would cut isn't drawn - whole rows."""
    window.set_labels({APP: SourceLabel("Discord", "#4dd0e1")}, "You")
    line = window.view.lines[-1]
    laid = window.canvas.laid_at(line, window.width() - 28)
    assert laid.label is not None
    straddling = BAND_HEIGHT - 10.0  # the label's top under the band, its foot below
    top = window.canvas._clear_of_band([(line, laid, straddling)])
    assert top >= straddling + laid.rows[0].top  # the label and its gap hidden
    below = window.canvas._clear_of_band([(line, laid, BAND_HEIGHT + 4.0)])
    assert below == BAND_HEIGHT + 1  # nothing under the band: nothing hidden


def test_original_only_says_so_on_the_strip(window: CaptionWindow) -> None:
    """On the language chip, including when it's shown as an icon."""
    window.resize(960, 180)
    assert window.tag.note == ""
    window.set_language("")
    assert window.chip.text().startswith("Detect → Original only")
    assert window.tag.note == ""  # the chip says it
    window.resize(window._minimum().width, 180)
    assert not window.chip.isHidden()
    assert "Original only" in window.chip.toolTip()
    window.set_language("en")
    assert window.tag.note == ""


def test_show_my_speech_here_left_the_menu(
    window: CaptionWindow,
) -> None:
    """polyglotic-hq 593 (585's section 6): the preset chip's My speech does
    it - "two switches for one thing" - and the first window's set-up still
    asks; the window's menu doesn't."""
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None
    switch = popover.findChild(QPushButton, "settings_popover.caption_window.show_mic")
    assert switch is None and "show_mic" not in popover.rows


# -- what the UI lab's checks found (project 119) -----------------------------------------


def test_the_strips_buttons_have_names_a_screen_reader_can_say(
    window: CaptionWindow,
) -> None:
    """Lock, settings and close showed only an icon font's glyph."""
    said = {
        name: QAccessible.queryAccessibleInterface(button).text(QAccessible.Text.Name)
        for name, button in window.buttons.items()
    }
    assert said == {
        "links": "Word links",
        "lock": "Lock all windows",
        "report": "Report a problem",
        "settings": "Settings",
        "stop": "Stop captioning Discord",
    }
    chip = QAccessible.queryAccessibleInterface(window.preset_chip)
    assert chip.text(QAccessible.Text.Name) == "Preset: Everyday"  # in words (593)


def test_notes_are_never_under_12_px(window: CaptionWindow) -> None:
    """The strip's "Original only" and the popover's notes were 11 px."""
    window.set_language("")
    assert window.tag._note_font.pixelSize() >= 12
    window.hovered = True
    window._show_band(True)
    window.toggle_settings()
    popover = window.popover
    assert popover is not None
    notes = [w for w in popover.findChildren(QLabel) if w.property("note")]
    assert notes
    for note in notes:
        note.ensurePolished()
        assert note.font().pixelSize() >= 12


def test_the_top_row_is_never_cut_through_its_glyphs(window: CaptionWindow) -> None:
    """151's W3 (176): with more captions than fit, the oldest row in view
    was drawn cut at the panel's top, half its glyphs showing. Now only
    whole rows show there, as under the band."""
    assert not window.band_shown
    for height in range(180, 420, 7):  # rows land at every offset
        window.resize(window.width(), height)
        window.canvas.grab()  # painted: where it started
        top = window.canvas.clear_top
        for _, laid, rect in window.canvas.placed:
            for row in laid.rows:
                row_top = rect.top() + row.top
                row_foot = row_top + row.layout.boundingRect().height()
                if row_foot > top:  # drawn, wholly or in part
                    assert row_top >= top - 0.01, (height, row_top, top)
    line = window.view.lines[-1]
    laid = window.canvas.laid_at(line, window.width() - 28)
    cut = 14.0 - laid.rows[0].top - 3.0  # its first row straddles the top
    assert window.canvas._clear_of([(line, laid, cut)], 14.0) > 14.0
    assert window.canvas._clear_of([(line, laid, 20.0)], 14.0) == 14.0


LONG_ZH = (
    "我们今天下午要做的是，如果大家休息以后都还在的话，就把整个计划一步一步地过一遍，"
    "然后对预算、时间表或者下周谁做什么有问题的人，可以在最后提出来。"
)
LONG_EN = (
    "So what we're going to do this afternoon, if everyone is still here after "
    "the break, is go through the whole plan step by step, and then anyone who "
    "has questions about the budget, the timeline or who is doing what next "
    "week can ask them at the end."
)


@pytest.mark.parametrize("translation_size", [1.0, 0.5, 2.0])
@pytest.mark.parametrize("text_size", [1.0, 1.3])
def test_a_long_caption_in_a_small_window_shows_its_last_lines(
    qapp: QApplication, text_size: float, translation_size: float
) -> None:
    """polyglotic-hq 278: a long sentence in a small window - its translation
    wrapped taller than the window - left the window blank. Only whole rows
    show at the top (151's W3), and a row taller than the window was never
    whole. Now the newest caption's wrapped lines that fit show, whole -
    still none cut through its glyphs."""
    window = window_of(qapp, captions=1, translation_size=translation_size)
    try:
        window.always_shown = True  # at rest at once, as the lab sees it
        window.resize(MIN_PANEL.width, MIN_PANEL.height)
        window.set_text_size(text_size)
        long = CaptionUpdate(
            CaptionId("long-1"),
            APP,
            CaptionKind.FINISHED,
            (Clause(LONG_ZH, {EN: LONG_EN}),),
            ZH,
            (ZH,),
        )
        window.view.apply(long)
        window.apply_changed(new_caption=True)
        canvas = window.canvas
        canvas.grab()
        top = canvas.clear_top
        newest = [p for p in canvas.placed if p[0].key == window.view.lines[-1].key]
        assert newest, "the newest caption isn't drawn at all"
        _, laid, rect = newest[0]
        shown_lines, clip = 0, canvas.height() - 14
        for row in laid.rows:
            layout = row.layout
            for n in range(layout.lineCount()):
                text_line = layout.lineAt(n)
                line_top = rect.top() + row.top + text_line.y()
                line_foot = line_top + text_line.height()
                # whole, or not drawn: never cut at the top
                assert line_top >= top - 0.01 or line_foot <= top + 0.01
                if line_top >= top - 0.01 and line_foot <= clip + 0.5:
                    shown_lines += 1
        assert shown_lines >= 1, (top, rect.getRect())
    finally:
        window.close()


def test_the_lab_sees_new_captions_whole(window: CaptionWindow) -> None:
    window.always_shown = True  # the lab's photographs
    (new,) = finished_updates(1, start=40)
    window.view.apply(new)
    window.apply_changed(new_caption=True)
    assert not window.arriving


def test_a_caption_windows_own_words_are_in_the_interfaces_fonts(
    window: CaptionWindow,
) -> None:
    """176, 198: what names no font took Qt's own, Segoe UI alone, so the
    Chinese of the labels, notices, Back to live, the empty window's hint,
    Looks wrong? and the whole settings popover came from whatever face
    Windows found - MS UI Gothic, a Japanese one, in an English locale.
    Now the interface's fonts, its Chinese face among them, whatever the
    size."""
    families = style.UI_FAMILIES
    assert window.font().families() == families
    for shown in (window.canvas, window.notice, window.pill, window.band):
        assert shown.font().families() == families, shown.objectName()
    assert window.tag._font.families() == families
    assert window.tag._note_font.families() == families
    assert window.canvas.engine._label_font(1.0).families() == families
    window.toggle_settings()
    popover = window.popover
    assert popover is not None
    assert popover.font().families() == families  # a window: not its owner's
    assert popover.text_size.font().families() == families


def test_it_keeps_layouts_only_for_the_lines_it_keeps(window: CaptionWindow) -> None:
    """An evening's captions, each shown as it comes: the window keeps its
    150 lines, and the layouts of no more than those - not of every line
    it ever showed, which grew the app about 0.5 MB a minute
    (polyglotic-hq 239)."""
    for update in finished_updates(CAPTION_WINDOW_LINES * 3, start=40):
        window.view.apply(update)
        window.apply_changed(new_caption=True)
        window.canvas.repaint()
    assert len(window.view.lines) == CAPTION_WINDOW_LINES
    assert window.canvas.engine.held <= CAPTION_WINDOW_LINES
    window.set_look(replace(window.look, font="Segoe UI"))  # a new engine
    assert window.canvas.engine.lines_kept == CAPTION_WINDOW_LINES


def test_reduced_motion_is_windows_animation_effects_off(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qt's motion preference: on Windows, "Animation effects" (Settings >
    Accessibility > Visual effects; SPI_GETCLIENTAREAANIMATION)."""
    from types import SimpleNamespace

    assert not caption_window_module.reduced_motion()  # this PC, as tests run
    reduced = SimpleNamespace(
        motionPreference=lambda: Qt.MotionPreference.ReducedMotion
    )
    hints = SimpleNamespace(accessibility=lambda: reduced)
    fake = SimpleNamespace(styleHints=lambda: hints)
    monkeypatch.setattr(caption_window_module, "QGuiApplication", fake)
    assert caption_window_module.reduced_motion()


def test_a_look_change_that_leaves_the_labels_keeps_every_line(
    window: CaptionWindow,
) -> None:
    """Polyglotic-hq 367: the labels were made again on each look change
    with a new function naming the language spoken, so they never compared
    equal and every caption's line was rebuilt - on each step of a drag of
    the panel's opacity, half the step's time. A change that leaves the
    labels as they were keeps the lines; one that changes them doesn't."""
    lines = window.view.lines
    window.set_look(replace(window.look, opacity=0.33))
    assert all(a is b for a, b in zip(window.view.lines, lines, strict=True))
    window.set_look(replace(window.look, show_source=not window.look.show_source))
    assert not any(a is b for a, b in zip(window.view.lines, lines, strict=True))
