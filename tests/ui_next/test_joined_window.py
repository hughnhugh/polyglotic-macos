"""W1j, the joined window (project 109's structure, 2a and 10.6), offscreen:
join and separate with the windows' own places kept, a column each with
its own choices, the window's own place and mode, a column removed or
added, the last column becoming a window, the hover band, the popovers,
lock, hide and the notice line - and its budgets (DECISIONS.md #53)."""

import sys
from collections.abc import Iterator
from dataclasses import replace
from functools import partial

import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget
from tests.budget_judge import sampled, within
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import SEPARATE, arriving, finished_updates
from tests.ui_next.test_caption_window import _on_words

from polyglotic_desktop.core.listening.sources import SourceId, SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui.recorded_captions import APP, MIC, OKAY, finished
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import (
    CAPTION_TEXT_SIZES,
    MIN_PANEL,
    CaptionWindow,
    _Drag,
    to_rect,
)
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.joined_window import JoinedWindow
from polyglotic_desktop.ui_next.settings_popover import COLUMN_ROWS, WINDOW_ROWS
from polyglotic_desktop.ui_next.views import placement
from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    JoinedChoices,
    Notice,
)
from polyglotic_desktop.ui_next.views.placement import (
    CORNER_ZONE,
    MIN_COLUMN,
    Edge,
    Preset,
    Rect,
)

AREA = Rect(0, 0, 1920, 1040)
SECOND_APP = SourceId("app-2")
THIRD_APP = SourceId("app-3")
FOURTH_APP = SourceId("app-4")
THREE = [("a", APP), ("b", SECOND_APP), ("c", THIRD_APP)]


def areas() -> list[Rect]:
    return [AREA]


class Store:
    """The settings port, in memory."""

    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = dict(values or {})

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


@pytest.fixture
def store() -> Store:
    return Store({"targets": ["en"]})


@pytest.fixture
def windows(qapp: QApplication, store: Store) -> Iterator[CaptionWindows]:
    found = CaptionWindows(store, MIC, areas)
    found.stored.joined = SEPARATE  # on their own: windows start joined (554)
    found.set_labels(
        {
            APP: SourceLabel("Discord", "#4dd0e1"),
            SECOND_APP: SourceLabel("Video Player", "#a5d66f"),
            THIRD_APP: SourceLabel("Web Browser", "#f5a97f"),
        },
        "You",
    )
    found.set_captioned(THREE)
    for source in (APP, SECOND_APP):
        for update in finished_updates(30, source):
            found.apply(update)
    qapp.processEvents()
    yield found
    found.close()


def joined(windows: CaptionWindows) -> JoinedWindow:
    assert windows.joined_window is not None
    return windows.joined_window


def place(widget: CaptionWindow | JoinedWindow) -> Rect:
    return to_rect(widget.geometry())


def enter(widget: JoinedWindow) -> None:
    point = QPointF(50, 50)
    widget.enterEvent(QEnterEvent(point, point, point))


def mouse(widget: CaptionWindow, kind: str, pos: QPointF) -> None:
    types = {
        "press": QMouseEvent.Type.MouseButtonPress,
        "move": QMouseEvent.Type.MouseMove,
        "release": QMouseEvent.Type.MouseButtonRelease,
    }
    held = Qt.MouseButton.NoButton if kind == "release" else Qt.MouseButton.LeftButton
    event = QMouseEvent(
        types[kind], pos, widget.mapToGlobal(pos), Qt.MouseButton.LeftButton,
        held, Qt.KeyboardModifier.NoModifier,
    )  # fmt: skip
    {
        "press": widget.mousePressEvent,
        "move": widget.mouseMoveEvent,
        "release": widget.mouseReleaseEvent,
    }[kind](event)


# -- join and separate ------------------------------------------------------------------


def test_join_puts_every_window_in_one_a_column_each_in_the_apps_order(
    windows: CaptionWindows,
) -> None:
    changed: list[bool] = []
    windows.joined_changed.connect(changed.append)
    windows.join("b")
    window = joined(windows)
    assert window.columns == [windows.windows[k] for k in ("a", "b", "c")]
    assert all(not c.isWindow() and c.parent() is window for c in window.columns)
    assert all(c.isVisible() for c in window.columns)
    assert window.isVisible() and changed == [True]
    widths = [c.width() for c in window.columns]
    assert max(widths) - min(widths) <= 1 and sum(widths) == window.width()
    flags = window.windowFlags()
    if sys.platform == "win32":
        assert flags & Qt.WindowType.WindowMinimizeButtonHint
    else:
        assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_join_takes_the_commanding_windows_place_and_height_and_the_widths_together(
    windows: CaptionWindows,
) -> None:
    second = windows.windows["b"]
    second.setGeometry(600, 300, 500, 150)
    windows.windows["a"].resize(400, 180)
    windows.windows["c"].resize(450, 180)
    second.set_preset(Preset.TOP_CENTRE)  # centred: the joined window keeps its centre
    commanding = place(second)
    windows.join("b")
    window = place(joined(windows))
    assert window.height == commanding.height
    assert window.width == 400 + 500 + 450
    assert window.centre[0] == pytest.approx(commanding.centre[0], abs=1)
    assert joined(windows).choices.preset is Preset.TOP_CENTRE


def test_pace_and_largest_text_do_not_grow_a_joined_caption_surface(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.join("b")
    whole = joined(windows)
    whole.resize(whole.width(), MIN_PANEL.height)
    requested = whole.size()
    column = whole.columns[1]
    canvas = column.canvas.size()

    column.set_text_size(CAPTION_TEXT_SIZES[-1])
    column.set_translation_size(CAPTION_TEXT_SIZES[-1])
    column.set_pace(142, 135, 118, 110)
    qapp.processEvents()

    assert whole.size() == requested
    assert column.height() == requested.height()
    assert column.canvas.size() == canvas


def test_join_is_clamped_to_the_screen(windows: CaptionWindows) -> None:
    windows.join()  # three default windows: 2,880 px together
    window = place(joined(windows))
    assert window.width == AREA.width and window.x == AREA.x


def test_separate_puts_each_window_back_at_its_own_place(
    windows: CaptionWindows,
) -> None:
    before = {key: place(w) for key, w in windows.windows.items()}
    windows.join("b")
    windows.separate()
    assert windows.joined_window is None
    assert all(w.isWindow() and w.isVisible() for w in windows.windows.values())
    assert {key: place(w) for key, w in windows.windows.items()} == before


def test_captions_and_scroll_back_stay_with_their_column(
    windows: CaptionWindows,
) -> None:
    second = windows.windows["b"]
    second.canvas.scroll_by(200)
    windows.join()
    assert not second.view.scroll.following  # its scroll-back kept
    windows.apply(finished_updates(1, THIRD_APP, start=99)[0])
    assert [len(w.view.lines) for w in joined(windows).columns] == [30, 30, 1]
    windows.separate()
    assert not second.view.scroll.following


def test_each_column_keeps_its_own_language_text_size_and_my_speech(
    windows: CaptionWindows,
) -> None:
    windows.join()
    first, second, _ = joined(windows).columns
    second.set_language("")  # Original only, in that column
    first.set_text_size(1.5)
    first.set_show_mic(True)
    assert second.choices.target is None and first.choices.target is not None
    assert first.view.text_size == 1.5 and second.view.text_size == 1.0
    assert windows.targets()[SECOND_APP] == ()
    assert windows.targets()[MIC] == (first.choices.target,)


def test_joined_or_separate_is_remembered_across_restarts(
    qapp: QApplication, windows: CaptionWindows, store: Store
) -> None:
    windows.join()
    joined(windows).set_preset(Preset.TOP_CENTRE)
    windows.save_now()
    again = CaptionWindows(store, MIC, areas)
    again.set_captioned(THREE)
    try:
        assert again.joined_window is not None
        assert again.joined_window.choices.preset is Preset.TOP_CENTRE
        assert [c.key for c in again.joined_window.columns] == ["a", "b", "c"]
    finally:
        again.close()
    windows.separate()
    windows.save_now()
    stored = store.values[STORED_KEY]
    assert isinstance(stored, dict) and stored["joined"]["on"] is False


def test_a_new_window_joins_the_first_until_the_learner_separates_them(
    qapp: QApplication,
) -> None:
    """The user, 2026-11-20 (polyglotic-hq 554): "windows should start
    joined by default when new windows are added". One window shows on its
    own; a second app's window joins it as it opens. Separating is the
    learner's choice, kept: a third app's window then opens on its own, and
    so after a restart."""
    store = Store({"targets": ["en"]})
    windows = CaptionWindows(store, MIC, areas)
    again: CaptionWindows | None = None
    try:
        windows.set_captioned(THREE[:1])
        assert windows.joined_window is None  # one window: its own
        assert windows.windows["a"].isVisible()
        windows.set_captioned(THREE[:2])  # a second app: joined at once
        assert [c.key for c in joined(windows).columns] == ["a", "b"]
        windows.separate()
        windows.set_captioned(THREE)  # the learner's choice holds
        assert windows.joined_window is None
        windows.save_now()
        again = CaptionWindows(store, MIC, areas)
        again.set_captioned(THREE)
        assert again.joined_window is None
        again.join()  # until they join them again
        assert again.joined_window is not None
    finally:
        windows.close()
        if again is not None:
            again.close()


def test_joined_is_the_default_unless_the_learner_chose_separate() -> None:
    """Versions before 554 saved "on": false for everyone who never joined
    the windows: they follow the new default. Separate counts as chosen
    only where the windows had been joined (a joined window's place or its
    columns' widths kept), or where the record says so."""
    assert JoinedChoices().on and not JoinedChoices().chosen
    never_joined = {"on": False, "position": "bottom_centre", "geometry": None}
    assert JoinedChoices.from_stored(never_joined).on
    separated = {**never_joined, "geometry": [480, 650, 1920, 300]}
    assert not JoinedChoices.from_stored(separated).on
    assert not JoinedChoices.from_stored({**never_joined, "shares": [0.5, 0.5]}).on
    assert JoinedChoices.from_stored({"on": True}).chosen
    for choices in (JoinedChoices(), JoinedChoices(on=False, chosen=True)):
        assert JoinedChoices.from_stored(choices.to_stored()) == choices
    untouched = {**JoinedChoices(on=False).to_stored(), "chosen": False}
    assert JoinedChoices.from_stored(untouched).on  # follows the default


# -- columns removed and added ----------------------------------------------------------


def test_stopping_an_app_removes_its_column_then_the_last_is_a_window(
    windows: CaptionWindows,
) -> None:
    windows.join()
    window = joined(windows)
    windows.set_captioned(THREE[:2])
    assert [c.key for c in window.columns] == ["a", "b"]
    widths = [c.width() for c in window.columns]
    assert sum(widths) == window.width() and abs(widths[0] - widths[1]) <= 1
    alone = windows.windows["a"]
    own = alone.choices.geometry
    windows.set_captioned(THREE[:1])
    assert windows.joined_window is None
    assert alone.isWindow() and alone.isVisible()
    if own is not None:
        assert place(alone) == own  # its own place
    # still joined as a choice: a new app adds a column again
    windows.set_captioned(THREE[:2])
    assert windows.joined_window is not None
    assert len(joined(windows).columns) == 2


def test_a_new_app_adds_a_column_and_never_a_fourth(windows: CaptionWindows) -> None:
    windows.set_captioned(THREE[:2])
    windows.join()
    window = joined(windows)
    window.resize(2 * MIN_COLUMN, window.height())
    windows.set_captioned([*THREE, ("d", FOURTH_APP)])
    assert [c.key for c in window.columns] == ["a", "b", "c"]  # at most 3
    assert window.width() >= 3 * MIN_COLUMN  # widened for the third


# -- the window's own place and mode ----------------------------------------------------


def test_a_resize_step_divides_the_width_equally_and_stops_at_its_columns_least(
    windows: CaptionWindows,
) -> None:
    """At least MIN_COLUMN a column, and as wide as its strip needs - the
    last one's beside the window's controls, 351 px at 100 % (polyglotic-hq
    524: at 320 its buttons were squashed)."""
    windows.join()
    window = joined(windows)
    start = place(window)
    drag = _Drag(Edge.RIGHT, QPointF(), start)
    window.resize_by(drag, -2000, 0)
    least = window._minimum().width
    assert least >= 3 * MIN_COLUMN
    assert window.width() == least
    assert all(c.width() == least // 3 for c in window.columns)
    top = _Drag(Edge.TOP, QPointF(), place(window))
    window.resize_by(top, 0, -60)
    assert window.height() == start.height + 60
    assert all(c.height() == window.height() for c in window.columns)


def test_every_edge_and_corner_of_the_window_resizes_from_any_column(
    windows: CaptionWindows,
) -> None:
    windows.join()
    window = joined(windows)
    first, middle, last = window.columns
    assert first._edges(QPointF(2, 50)) == Edge.LEFT
    assert last._edges(QPointF(last.width() - 2, 50)) == Edge.RIGHT
    assert middle._edges(QPointF(2, 50)) == Edge.NONE  # between columns: none
    assert middle._edges(QPointF(50, 2)) == Edge.TOP
    corner = QPointF(last.width() - 2, last.height() - 2)
    assert last._edges(corner) == Edge.RIGHT | Edge.BOTTOM


def test_a_drag_on_a_column_moves_the_whole_window_and_snaps(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned(THREE[:2])
    windows.join()
    window = joined(windows)
    window.resize(1000, 180)
    window.set_preset(Preset.BOTTOM_CENTRE)
    middle = window.columns[1]
    start = QPointF(middle.width() / 2, middle.height() / 2)
    mouse(middle, "press", start)
    mouse(middle, "move", start + QPointF(-300, -200))
    assert place(window).x < 460 - 200  # moved
    mouse(middle, "release", start + QPointF(-300, -200))
    assert window.choices.preset is Preset.CUSTOM  # where I put it
    assert window.choices.geometry == place(window)
    assert middle.isWindow() is False  # the column didn't move on its own


def test_the_window_has_its_own_presets(windows: CaptionWindows) -> None:
    windows.join()
    window = joined(windows)
    window.resize(1200, 160)
    window.set_preset(Preset.TOP_CENTRE)
    assert place(window).y == 40 and place(window).centre[0] == AREA.width / 2
    assert window.choices.preset is Preset.TOP_CENTRE
    assert windows.stored.joined.preset is Preset.TOP_CENTRE


def test_reset_positions_puts_the_joined_window_back_too(
    windows: CaptionWindows,
) -> None:
    """Home's Reset positions and the look's Reset to defaults (115)."""
    windows.join()
    window = joined(windows)
    window.set_preset(Preset.TOP_CENTRE)
    windows.reset_places()
    assert window.choices.preset is Preset.BOTTOM_CENTRE
    assert place(window).bottom > AREA.height / 2


# -- the band and the popovers ------------------------------------------------------------


def test_hover_shows_every_columns_strip_and_the_windows_controls(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.join()
    window = joined(windows)
    enter(window)
    assert all(c.hovered for c in window.columns)
    window.show_bands(True)
    qapp.processEvents()
    assert window.bar.isVisible() and all(c.band_shown for c in window.columns)
    # a column's strip has no lock: the window's is at the right of the last
    assert all(not c.buttons["lock"].isVisibleTo(c) for c in window.columns)
    last = window.columns[-1]
    bar_left = window.bar.geometry().left() - last.x()
    assert last.band.geometry().right() < bar_left
    assert window.bar.geometry().right() < window.width() - CORNER_ZONE + 1


def on_words(column: CaptionWindow) -> QPointF:
    """A point on the text of the newest caption drawn in `column` where the
    mouse can be on it (`test_caption_window._on_words`, polyglotic-hq 578)."""
    return _on_words(column)


def move(column: CaptionWindow, point: QPointF) -> None:
    column.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.MouseMove, point, column.mapToGlobal(point),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )  # fmt: skip


def test_captions_held_under_the_mouse_come_in_when_it_leaves_the_joined_window(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    """Bug (polyglotic-hq 543; the user, 2026-11-20: live captions "often
    delay and then process it all at once"): while the mouse moves over a
    column's words, new captions wait (158's "nothing moves under the
    mouse") - and come in when it leaves, as in a window of its own. A
    column left that to its joined window, which never did: they waited
    for `HOLD_SEC` (4 s) after the mouse's last move, however soon it
    left, then came at once."""
    windows.join()
    window = joined(windows)
    column = window.columns[0]
    enter(window)
    move(column, on_words(column))
    for update in finished_updates(2, APP, start=30):
        windows.apply(update)
    shown = [str(line.caption_id) for line in column.view.lines]
    assert shown[-2:] == [f"{APP}-00030", f"{APP}-00031"]  # in: never held (583)
    assert not column.view.scroll.following  # the view holds instead
    column.leaveEvent(None)  # the mouse leaves: Qt tells the column ...
    window.leaveEvent(None)  # ... and the joined window
    column._hold_timer.timeout.emit()  # a moment later
    assert column.view.scroll.following


def test_only_the_column_under_the_mouse_holds_its_captions_and_leaving_it_lets_them_in(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    """polyglotic-hq 554 (DECISIONS #242's C): the mouse over a joined
    window held every column's captions, wherever it was - over the band,
    another column, the panel. Now only the words under it wait: the
    other columns' come in, and moving on to the next column lets the
    first's in at once."""
    windows.join()
    window = joined(windows)
    first, second = window.columns[0], window.columns[1]
    enter(window)
    move(first, on_words(first))
    for update in (
        *finished_updates(1, APP, start=30),
        *finished_updates(1, SECOND_APP, start=30),
    ):
        windows.apply(update)
    # only the column pointed at holds its view; every caption is in (583)
    assert not first.view.scroll.following and second.view.scroll.following
    assert [str(line.caption_id) for line in second.view.lines][
        -1
    ] == f"{SECOND_APP}-00030"
    assert [str(line.caption_id) for line in first.view.lines][-1] == f"{APP}-00030"
    first.leaveEvent(None)  # on to the next column: live a moment later
    first._hold_timer.timeout.emit()
    assert first.view.scroll.following


def test_a_columns_popover_has_its_own_rows_and_the_windows_the_rest(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.join()
    window = joined(windows)
    window.show_bands(True)
    column = window.columns[1]
    column.toggle_settings()
    assert column.popover is not None
    rows = list(column.popover.rows)
    # 655: languages stay on the bar chip (bar_languages shows only when folded)
    assert rows == list(COLUMN_ROWS)
    column.close_settings()
    window.toggle_settings()
    assert window.popover is not None and tuple(window.popover.rows) == WINDOW_ROWS
    window.controls["separate"].trigger()
    assert windows.joined_window is None
    # separated: the column is a window again, with W1's own popover
    column.toggle_settings()
    assert column.popover is not None and "join" in column.popover.rows


def test_after_joining_a_windows_controls_still_work_without_errors(
    windows: CaptionWindows, qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Joining (or separating) deletes a window's popover, built when it was
    first opened; its buttons stayed connected to the window's actions, so
    every later change - A+, Panel or Strip, a position - raised an uncaught
    error on a deleted button (each one logged, and a crash report offered
    at the next start; polyglotic-hq 141)."""
    errors: list[BaseException] = []
    monkeypatch.setattr(
        sys, "excepthook", lambda _kind, error, _tb: errors.append(error)
    )
    first = windows.windows["a"]
    first.toggle_settings()  # its popover built
    first.close_settings()
    windows.join()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)  # the popover gone
    windows.separate()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    first.set_preset(Preset.TOP_CENTRE)
    first.step_text(4)
    first.set_show_mic(True)
    assert errors == []
    first.toggle_settings()  # a new one, which follows its window
    assert first.popover is not None and first.controls["show_mic"].isChecked()


def test_join_windows_is_in_each_windows_popover_once_there_are_two(
    windows: CaptionWindows,
) -> None:
    first = windows.windows["a"]
    first.toggle_settings()
    assert first.popover is not None and first.popover.rows["join"].isVisibleTo(
        first.popover
    )
    first.controls["join"].trigger()
    assert windows.joined_window is not None


def test_caption_bar_shortcut_can_reach_each_joined_column(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.join()
    columns = joined(windows).columns
    for column in columns:
        windows.open_bar_controls()
        qapp.processEvents()
        assert [w for w in columns if w.keyboard_bar_open] == [column]
        if sys.platform != "win32":
            assert (
                column.window().windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
            )


# -- lock, hide, the notice line ---------------------------------------------------------


def test_locked_the_whole_window_lets_clicks_through_and_has_no_band(
    windows: CaptionWindows,
) -> None:
    windows.join()
    window = joined(windows)
    window.show_bands(True)
    windows.set_locked(True)
    assert window.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert not window.band_shown and window.isVisible()
    windows.set_locked(False)
    windows.separate()  # back on their own, unlocked
    assert not any(
        w.windowFlags() & Qt.WindowType.WindowTransparentForInput
        for w in windows.windows.values()
    )


def test_locked_while_joined_stays_locked_when_separated(
    windows: CaptionWindows,
) -> None:
    windows.join()
    windows.set_locked(True)
    windows.separate()
    assert all(
        w.windowFlags() & Qt.WindowType.WindowTransparentForInput
        for w in windows.windows.values()
    )


def test_hidden_hides_the_joined_window(windows: CaptionWindows) -> None:
    windows.join()
    windows.set_hidden(True)
    assert not joined(windows).isVisible()
    windows.set_hidden(False)
    assert joined(windows).isVisible()
    assert all(c.isVisible() for c in joined(windows).columns)


def test_the_notice_line_shows_once_over_the_whole_window(
    windows: CaptionWindows,
) -> None:
    windows.join()
    window = joined(windows)
    windows.set_connection(Notice.RECONNECTING, None)
    for column in window.columns:
        column._tick()
    assert window.notice.isVisible() and window.notice.text() == "Reconnecting"
    assert not any(c.notice.isVisible() for c in window.columns)
    area = window.notice.geometry()
    assert abs(area.center().x() - window.width() / 2) <= 2
    assert any(area.intersects(column.geometry()) for column in window.columns)
    for column in window.columns:
        if area.intersects(column.geometry()):
            assert column.notice_foot() > area.bottom()
        else:
            assert column.notice_foot() == 0
    windows.separate()
    for column in windows.windows.values():
        column._tick()
    assert all(c.notice.isVisible() for c in windows.windows.values())


def test_paused_once_over_the_joined_window_and_signed_out_it_goes(
    windows: CaptionWindows,
) -> None:
    windows.join()
    window = joined(windows)
    windows.set_paused(True)
    for column in window.columns:
        column._tick()
    assert window.notice.text() == "Paused"
    assert not any(c.notice.isVisible() for c in window.columns)
    windows.set_paused(False)
    windows.set_connection(Notice.NOT_SIGNED_IN, None)
    windows._going.timeout.emit()
    assert not window.isVisible()
    windows.set_connection(None, None)
    assert window.isVisible()


def test_the_lookup_works_over_any_column(qapp: QApplication) -> None:
    tools = chinese_tools()
    found = CaptionWindows(None, MIC, areas, learner=tools)
    try:
        found.set_captioned(THREE[:2])
        for update in finished_updates(20, SECOND_APP):
            found.apply(update)
        found.join()
        window = joined(found)
        column = window.columns[1]
        qapp.processEvents()
        column.canvas.repaint()
        assert column.card is found.card
        for _line, laid, rect in reversed(column.canvas.placed):
            row = laid.rows[-1]
            point = QPointF(rect.x() + 20, rect.y() + row.top + 8)
            marked = column._marked_at(point)
            if marked is not None:
                break
        else:
            raise AssertionError("no word drawn in the second column")
        word = column.word_at(marked)
        assert word is not None
        top_left = column.canvas.mapToGlobal(rect.topLeft().toPoint())
        assert word.rect.x >= top_left.x() >= window.x() + column.x()  # on screen
        before = place(window)
        mouse(column, "press", point)  # a click on a word pins its lookup
        mouse(column, "release", point)
        assert found.card is not None and found.card.pinned
        assert place(window) == before and not window.dragging  # nothing moved
    finally:
        found.close()


# -- budgets ---------------------------------------------------------------------------------
# Timed as tests/budget_judge.py does: a warm-up pass, the garbage collector held off, the
# median and any one run judged, one retry that reports both tries.


@pytest.fixture
def full(qapp: QApplication) -> Iterator[CaptionWindows]:
    """Three windows of 1,000 captions each (they keep their 150)."""
    found = CaptionWindows(None, MIC, areas)
    found.set_captioned(THREE)
    for source in (APP, SECOND_APP, THIRD_APP):
        for update in finished_updates(1_000, source):
            found.apply(update)
    qapp.processEvents()
    yield found
    found.close()


def test_a_resize_step_with_three_columns(
    full: CaptionWindows, qapp: QApplication
) -> None:
    full.join()
    window = joined(full)
    window.repaint()
    drag = _Drag(Edge.RIGHT, QPointF(), place(window))
    top = _Drag(Edge.TOP, QPointF(), place(window))
    steps = [partial(window.resize_by, drag, -15 * n, 0) for n in range(20)]
    steps += [partial(window.resize_by, top, 0, -4 * n) for n in range(20)]
    within(budgets.FRAME, lambda: sampled(qapp, steps))


class Paints(QObject):
    """How many times each watched widget painted."""

    def __init__(self, watched: list[QWidget]) -> None:
        super().__init__()
        self.count = {id(w): 0 for w in watched}
        for widget in watched:
            widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint and id(watched) in self.count:
            self.count[id(watched)] += 1
        return False


def test_a_joined_resize_keeps_each_card_and_its_rows_while_they_fit(
    windows: CaptionWindows,
) -> None:
    windows.join()
    host = joined(windows)
    host.resize(1500, 220)
    windows.set_look(replace(windows.look, show_source=False, show_language=False))
    windows.set_timing(CaptionMode.STEADY)
    for column in host.columns:
        column.always_shown = True
        for name in ("first", "second"):
            update = finished(name, OKAY, source=column.source)
            column.hear(update)
            column.receive(update)
    host.grab()
    cards = []
    for column in host.columns:
        line = column.view.lines[-1]
        assert line.caption_id.startswith("card:") and not line.label
        cards.append((column.deck, column.view.lines, column.canvas._laid(line)))
    host.resize(1470, 220)
    host.grab()
    for column, (deck, lines, old) in zip(host.columns, cards, strict=True):
        assert column.deck is deck and column.view.lines is lines
        now = column.canvas._laid(lines[-1])
        assert now.width < old.width
        assert now.rows is old.rows


def test_a_resize_step_paints_each_column_once(
    full: CaptionWindows, qapp: QApplication
) -> None:
    """The window resized, then painted once: one column's repaint had
    painted all three - the resize had left the whole window to paint - and
    the next two painted again, five paints a step for three columns, over
    the frame on the Linux runner (polyglotic-hq 355)."""
    full.join()
    window = joined(full)
    window.repaint()
    qapp.processEvents()
    canvases: list[QWidget] = [column.canvas for column in window.columns]
    paints = Paints(canvases)
    drag = _Drag(Edge.RIGHT, QPointF(), place(window))
    for n in range(1, 4):
        paints.count = dict.fromkeys(paints.count, 0)
        window.resize_by(drag, -15 * n, 0)
        assert list(paints.count.values()) == [1, 1, 1], n
    for canvas in canvases:
        canvas.removeEventFilter(paints)


def test_a_divider_step_paints_each_column_once(
    full: CaptionWindows, qapp: QApplication
) -> None:
    """A divider step lays the columns out and paints the window once: each
    column's own repaint painted a neighbour that had moved too - four
    paints a step for three columns (polyglotic-hq 355, 360)."""
    full.join()
    window = joined(full)
    window.repaint()
    qapp.processEvents()
    canvases: list[QWidget] = [column.canvas for column in window.columns]
    paints = Paints(canvases)
    divider = window.width() // 3
    window.press_divider(0, QPointF(divider, 10))
    for n in range(1, 4):
        paints.count = dict.fromkeys(paints.count, 0)
        window.drag_to(QPointF(divider + 10 * n, 10))
        assert list(paints.count.values()) == [1, 1, 1], n
    window.release()
    for canvas in canvases:
        canvas.removeEventFilter(paints)


def test_join_and_separate(full: CaptionWindows, qapp: QApplication) -> None:
    def join() -> None:
        full.join()
        joined(full).repaint()

    def separate() -> None:
        full.separate()
        for window in full.windows.values():
            window.repaint()

    within(budgets.CLICK, lambda: sampled(qapp, [join, separate] * 4))


def test_a_new_caption_in_one_column(full: CaptionWindows, qapp: QApplication) -> None:
    full.join()
    joined(full).repaint()
    updates = arriving(10, SECOND_APP, start=2_000)

    def arrive() -> None:
        full.apply(next(updates))
        full.windows["b"].canvas.repaint()

    within(budgets.NEW_CAPTION, lambda: sampled(qapp, [arrive] * 10))


def test_the_mouse_over_a_joined_window_holds_no_column_off_its_words(
    windows: CaptionWindows,
) -> None:
    """New captions waited in every column while the mouse was anywhere on
    the joined window (polyglotic-hq 158), until its strip went; only a
    column's words hold its own now (554, DECISIONS #242's C)."""
    windows.join()
    window = joined(windows)
    enter(window)
    windows.apply(finished_updates(1, THIRD_APP, start=99)[0])
    assert [len(c.view.lines) for c in window.columns] == [30, 30, 1]


def test_a_joined_windows_own_words_are_in_the_interfaces_fonts(
    windows: CaptionWindows,
) -> None:
    """176, 198: its notice and its band named no font, so their Chinese came
    from whatever face Windows found (MS UI Gothic in an English locale)."""
    windows.join("b")
    window = joined(windows)
    assert window.font().families() == style.UI_FAMILIES
    assert window.notice.font().families() == style.UI_FAMILIES


# -- each column's width (polyglotic-hq 284) ---------------------------------------------
# The user's live testing, 270's FEEDBACK.md: "For joint windows, you should
# be able to select the size of each window": a drag on the divider between
# two columns gives one's width to the other - neither under MIN_COLUMN -
# kept across a resize and a restart.


def test_columns_follow_their_shares_and_are_equal_without() -> None:
    assert placement.columns(1000, 2) == [(0, 500), (500, 500)]
    assert placement.columns(1000, 2, (0.7, 0.3)) == [(0, 700), (700, 300)]
    assert placement.columns(1000, 3, (0.7, 0.3)) == placement.columns(1000, 3)
    assert placement.shares_of((), 2) == (0.5, 0.5)
    assert placement.shares_of((2.0, 1.0, 1.0), 3) == (0.5, 0.25, 0.25)


def test_a_divider_moves_between_its_columns_and_stops_at_the_narrowest() -> None:
    moved = placement.moved_divider((0.5, 0.5), 0, 100, 1000, MIN_COLUMN)
    assert moved == pytest.approx((0.6, 0.4))
    assert placement.moved_divider((0.5, 0.5), 0, 900, 1000, MIN_COLUMN) == (
        pytest.approx((1 - MIN_COLUMN / 1000, MIN_COLUMN / 1000))
    )
    three = placement.moved_divider((1 / 3,) * 3, 1, -50, 1200, MIN_COLUMN)
    assert three[0] == pytest.approx(1 / 3) and sum(three) == pytest.approx(1.0)
    assert placement.divider_at(503, 1000, (), 2) == 0
    assert placement.divider_at(520, 1000, (), 2) is None


def test_the_shares_are_stored_and_read_back_leniently() -> None:
    choices = JoinedChoices(True, shares=(0.6, 0.4))
    assert JoinedChoices.from_stored(choices.to_stored()).shares == (0.6, 0.4)
    for odd in ([0.6], [1.2, -0.2], ["a", "b"], [0.5, 0.25, 0.125, 0.125], "x"):
        assert JoinedChoices.from_stored({"shares": odd}).shares == ()


def test_a_drag_on_the_divider_gives_one_column_the_others_width(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned(THREE[:2])
    windows.join()
    window = joined(windows)
    window.resize(1200, 200)
    first, second = window.columns
    assert first.width() == second.width() == 600
    edge = QPointF(2, 100)  # the second column's left edge: the divider
    second._hover(edge)
    assert second.cursor().shape() == Qt.CursorShape.SplitHCursor
    mouse(second, "press", edge)
    mouse(second, "move", edge + QPointF(200, 0))
    assert (first.width(), second.width()) == (800, 400)
    assert window.width() == 1200  # the window itself keeps its size
    mouse(second, "move", edge + QPointF(600, 0))
    assert second.width() == MIN_COLUMN  # no narrower
    mouse(second, "release", edge + QPointF(600, 0))
    assert windows.stored.joined.shares == window.choices.shares
    window.resize(1500, 200)  # a resize keeps the proportions
    assert first.width() == round(1500 * (1 - MIN_COLUMN / 1200))


def test_the_widths_are_remembered_across_restarts(
    windows: CaptionWindows, store: Store
) -> None:
    windows.set_captioned(THREE[:2])
    windows.join()
    window = joined(windows)
    window.resize(1000, 200)
    first, second = window.columns
    mouse(second, "press", QPointF(2, 100))
    mouse(second, "move", QPointF(-198, 100))
    mouse(second, "release", QPointF(-198, 100))
    assert first.width() == MIN_COLUMN  # 300 asked, 320 at least
    windows.save_now()
    stored = store.values[STORED_KEY]
    assert isinstance(stored, dict) and len(stored["joined"]["shares"]) == 2
    again = CaptionWindows(store, MIC, areas)
    again.set_captioned(THREE[:2])
    try:
        assert again.joined_window is not None
        assert again.joined_window.choices.shares == pytest.approx(
            window.choices.shares, abs=1e-4
        )
    finally:
        again.close()


def test_a_locked_window_has_no_divider_to_drag(windows: CaptionWindows) -> None:
    windows.set_captioned(THREE[:2])
    windows.join()
    window = joined(windows)
    window.set_locked(True)
    assert window.divider_at(QPointF(window.width() / 2, 50)) is None


def test_its_notice_is_measured_again_at_a_new_text_size(
    windows: CaptionWindows,
) -> None:
    """A text size change while it's open (polyglotic-hq 292): the notice
    line restyled and measured again - its old width cut the larger text."""
    windows.join()
    window = joined(windows)
    windows.set_paused(True)
    for column in window.columns:
        column._tick()
    assert window.notice.isVisible()
    try:
        style.use_text_scale(2.0)
        window.restyle()
        assert window.notice.width() >= window.notice.sizeHint().width()
    finally:
        style.use_text_scale(1.0)


def test_no_column_is_narrower_than_its_strip_needs(qapp: QApplication) -> None:
    """At Windows' 200 % and the app's Normal (2.25, decision 0244), three
    columns at 500 px left the last one's strip - its buttons beside the
    window's controls - 343 px for 378 (the UI lab, polyglotic-hq 524).
    The window fits every column's strip, including all three chip icons."""
    style.use_text_scale(2.0)  # before the windows are made: they're styled then
    style.use_app_text_size("normal")
    windows = CaptionWindows(Store({"targets": ["en"]}), MIC, areas)
    windows.set_labels(
        {
            APP: SourceLabel("Discord", "#4dd0e1"),
            SECOND_APP: SourceLabel("Video Player", "#a5d66f"),
            THIRD_APP: SourceLabel("Web Browser", "#f5a97f"),
        },
        "You",
    )
    windows.set_captioned(THREE)
    windows.join()
    window = joined(windows)
    # 1,500 px before the strip's four toggles went into the preset chip's
    # dropdown (polyglotic-hq 556): its strip needs less now
    window.resize(1000, window.height())
    for column in window.columns:
        column.hovered = True
        column._show_band(True)
    qapp.processEvents()
    for column in window.columns:
        assert all(
            chip.isVisible()
            for chip in (column.chip, column.preset_chip, column.timing_chip)
        )
        assert column.band.width() >= column.band.minimumSizeHint().width()
    assert window.width() > 1000
    windows.close()
