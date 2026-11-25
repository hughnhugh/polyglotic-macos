"""W1j, the joined window: up to three apps' caption windows side by side in
one window (polyglotic-hq project 109's structure, section 2a, and 10.6;
the user, 2026-11-07: "the caption window per app could be joined into a
unified window too, where they display 3 side by side").

**Its columns are the apps' own caption windows** (`CaptionWindow`), held
as child widgets in the apps' order, equal widths, a 1 px divider. Each
keeps what is its own - its captions and scroll-back, label, language (or
Original only), text size, Show my speech here, Back to live, empty text,
listening mark, the lookup over its words, and its strip: dot and label,
A- / A+, its settings and close (stop captioning that app). They are the
same objects, so joining and separating lose nothing and lay nothing out
again.

**The window has what is the window's:**
- one place and preset. Each window's own place is kept, for separating;
- at the right of the band, its controls: lock (every window), and its
  settings - Separate windows and All caption settings...
  (no Position:
  it's moved by hand, F8, 249)
  (`settings_popover.WINDOW_ROWS`);
- the hover band as one band: every column's strip and its controls
  together, 80 ms after the mouse comes and 300 ms after it leaves;
- the notice line, once (its first column's: every window hears the
  same notices); and the fade - it fades when every column would.

Every edge and corner resizes as W1 (10.1): anchored, clamped, laid out
again in the same frame, the width divided equally - or as the learner
dragged the dividers between columns (polyglotic-hq 284), kept in its
choices - at least `placement.MIN_COLUMN` a column. Moving snaps to the presets with the
joined width (10.3). Like W1 it never takes the focus.

`CaptionWindows` joins and separates (`join`, `separate`); this window
says what changed (`changed`) and what the learner asked for. Holds
caption text through its columns: never log it.
"""

import logging
import math
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QCursor,
    QEnterEvent,
    QKeyEvent,
    QMouseEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from polyglotic_desktop.perf import spans
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.above_all import (
    CAPTION_TASKBAR,
    CaptionTopLevel,
    set_click_through,
)
from polyglotic_desktop.ui_next.caption_window import (
    BAND_IN_MS,
    BAND_OUT_MS,
    GLYPH_PX,
    MIN_PANEL,
    STILL_OVER_MS,
    BarInk,
    CaptionWindow,
    _Drag,
    band_height,
    band_style,
    bar_ink,
    fit_glyph,
    least_size,
    lock_tip,
    notice_style,
    preset_name,
    restore_minimised,
    say_resized,
    to_qrect,
    to_rect,
    work_areas,
)
from polyglotic_desktop.ui_next.glyphs import Glyph, icon
from polyglotic_desktop.ui_next.resize_handle import CURSORS, GRIP, PanelResizeCursor
from polyglotic_desktop.ui_next.settings_popover import (
    WINDOW_ROWS,
    KeyState,
    SettingsPopover,
)
from polyglotic_desktop.ui_next.strip_tips import StripTips
from polyglotic_desktop.ui_next.views import placement
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook, JoinedChoices
from polyglotic_desktop.ui_next.views.placement import Edge, Preset, Rect, Size

CONTROLS = ("lock", "settings", "minimise") if CAPTION_TASKBAR else ("lock", "settings")
"""The window's controls at the right of the band, left to right."""
GLYPHS = {"lock": Glyph.LOCK, "settings": Glyph.MORE, "minimise": Glyph.MINIMISE}
"""The controls' icons; the window's settings are "More" (the wireframe's
"..."), so they aren't taken for the last column's own settings beside them."""
GAP = 10
"""Pixels between the last column's strip and the window's controls."""

log = logging.getLogger(__name__)


def _tr(text: str) -> str:
    return QApplication.translate("JoinedWindow", text)


class JoinedWindow(CaptionTopLevel):
    """The caption windows as one: a column each (`columns`), in order."""

    changed = Signal()
    """Its place changed: saved."""
    separate_wanted = Signal()
    lock_wanted = Signal()
    all_settings_wanted = Signal()
    opacity_wanted = Signal(float)

    def __init__(
        self,
        choices: JoinedChoices,
        areas: Callable[[], list[Rect]] = work_areas,
        keys: KeyState | None = None,
    ) -> None:
        """`choices`: its place (set by `place_at`
        once it has its columns); `keys`: Esc and the mouse buttons, for
        closing its settings popover (as W1's)."""
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # on a Mac a tool window hides while the app isn't active - and the
        # app is never active while the learner is in another (polyglotic-hq 429)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setObjectName("joined_window")
        self.setFont(style.ui_font())  # its own words, painted or not
        self.setWindowTitle(_tr("Captions"))
        self.setMouseTracking(True)
        self.choices = choices
        self.columns: list[CaptionWindow] = []
        self.locked = False
        self.band_shown = False
        self.keys = keys
        self.popover: SettingsPopover | None = None
        self._areas = areas
        self.resize_hint: PanelResizeCursor | None = None
        self._drag: _Drag | None = None
        self._divider: tuple[int, float, tuple[float, ...]] | None = None
        """A divider being dragged: its index, where the press was (x on the
        screen) and the columns' shares then."""
        self._build_controls()
        self._build_bar()
        self.notice = QLabel(self)
        self.notice.setObjectName("joined_window.notice")
        self.notice.setStyleSheet(notice_style())
        self.notice.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.notice.hide()
        self._band_in = QTimer(self, singleShot=True, interval=BAND_IN_MS)
        self._band_in.timeout.connect(lambda: self.show_bands(True))
        self._band_out = QTimer(self, singleShot=True, interval=BAND_OUT_MS)
        self._band_out.timeout.connect(self._band_left)
        self._still_over = QTimer(self, interval=STILL_OVER_MS)
        self._still_over.timeout.connect(self._check_still_over)
        self.pointer: Callable[[], QPoint] = QCursor.pos
        """Where the mouse is on the screen (a test's own)."""

    @property
    def dragging(self) -> bool:
        return self._drag is not None or self._divider is not None

    def _shares(self) -> tuple[float, ...]:
        """The columns' shares of the width as dragged - () for equal."""
        shares = self.choices.shares
        return shares if len(shares) == len(self.columns) else ()

    # -- its columns ----------------------------------------------------------------------

    def set_columns(self, windows: list[CaptionWindow]) -> None:
        """Its columns, in order: a window new to it becomes a column; one
        it held and not in `windows` is a window of its own again (not
        shown). At least MIN_COLUMN a column: it widens if it must."""
        with spans.span("joined_window.columns"):
            leaving = [w for w in self.columns if w not in windows]
            self.columns = list(windows)
            for window in leaving:
                if window.host is self:
                    window.set_host(None)
            for window in windows:
                window.set_host(self)
                window.set_locked(self.locked)
            self._widen()
            self.restyle()  # its controls on its columns' panel
            self._keep_minimum()
            self.lay_out()
            for window in windows:
                window.show()
                window.host_changed()  # its neighbours, its strip's room

    def remove(self, window: CaptionWindow) -> None:
        """A column whose window is closing goes, as it is: no window of its
        own is made for it."""
        if window in self.columns:
            self.columns.remove(window)
            window.host = None

    def lay_out(self) -> None:
        """Each column its share of the width - equal, or as the learner
        dragged the dividers - the full height; the controls and the notice
        line over them."""
        for (x, width), column in zip(
            placement.columns(self.width(), len(self.columns), self._shares()),
            self.columns,
            strict=True,
        ):
            column.setGeometry(x, 0, width, self.height())
        self._place_bar()
        self.place_notice()

    def controls_width(self, column: CaptionWindow) -> int:
        """The room its controls take on `column`'s strip: on the last
        column's, at the right."""
        if not self.columns or self.columns[-1] is not column:
            return 0
        return self.bar.sizeHint().width() + 4

    def follow_alpha(self) -> None:
        """Faded as its least faded column: shown while any column is."""
        alpha = max((c.alpha for c in self.columns), default=1.0)
        if not math.isclose(alpha, self.windowOpacity(), abs_tol=0.002):
            self.setWindowOpacity(alpha)

    # -- the controls ---------------------------------------------------------------------

    def _action(
        self,
        name: str,
        text: str,
        slot: Callable[[], object] | None = None,
        tip: str = "",
        checkable: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        action.setObjectName(f"joined_window.{name}")
        action.setToolTip(tip or text)
        action.setCheckable(checkable)
        if slot is not None:
            action.triggered.connect(slot)
        self.controls[name] = action
        return action

    def _build_controls(self) -> None:
        """The window's controls as named actions: lock and settings on the
        band; the rest in its settings popover."""
        self.controls: dict[str, QAction] = {}
        self._action(
            "lock",
            _tr("Lock all windows"),
            self.lock_wanted.emit,
            lock_tip("Ctrl+Alt+L"),
        )
        self._action(
            "settings",
            _tr("This window"),
            self.toggle_settings,
            _tr("This window: Separate windows, all caption settings"),
        )
        self._action("minimise", _tr("Minimise"), self.showMinimized)
        self._action(
            "all_settings",
            _tr("All caption settings…"),
            self.all_settings_wanted.emit,
            _tr(
                "Colours, font, word links, timing and the rest - for every "
                "window, in Settings"
            ),
        )
        self._action(
            "separate",
            _tr("Separate windows"),
            self.separate_wanted.emit,
            _tr("Each app's caption window back at its own place"),
        )
        self._sync_controls()

    def _build_bar(self) -> None:
        bar = self.bar = QWidget(self)
        bar.setObjectName("joined_window.controls")
        bar.setMouseTracking(True)
        bar.setStyleSheet(band_style(self._ink()))
        row = QHBoxLayout(bar)
        row.setContentsMargins(GAP, 0, 0, 0)
        row.setSpacing(3)
        self.buttons: dict[str, QToolButton] = {}
        for name in CONTROLS:
            button = QToolButton(bar)
            button.setObjectName(f"joined_window.band.{name}")
            button.setDefaultAction(self.controls[name])
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMouseTracking(True)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            # what a screen reader says: the action's words, not the glyph
            button.setAccessibleName(self.controls[name].text())
            self.buttons[name] = button
            row.addWidget(button)
        # never active, so Qt never shows their tooltips (polyglotic-hq 395)
        self.tips = StripTips(self)
        for button in self.buttons.values():
            self.tips.watch(button)
        self._draw_glyphs()
        bar.adjustSize()
        bar.hide()

    def _sync_controls(self) -> None:
        if self.popover is not None and self.popover.isVisible():
            self.popover.refresh()

    def _ink(self) -> BarInk:
        """Its controls' colours: on its columns' panel (one look for all)."""
        return bar_ink(self.look.background)

    @property
    def look(self) -> CaptionLook:
        return self.columns[0].look if self.columns else CaptionLook()

    def refresh_settings(self) -> None:
        self._sync_controls()

    def restyle(self) -> None:
        """Its controls at the text size now and in its columns' panel's
        colours (its columns restyle as caption windows)."""
        self.bar.setStyleSheet(band_style(self._ink()))
        self.notice.setStyleSheet(notice_style())
        self._draw_glyphs()
        self.bar.adjustSize()
        self._keep_minimum()  # its columns' strips, at the text size now
        self._place_bar()
        self.place_notice()  # measured again, at the text size now

    def _draw_glyphs(self) -> None:
        """The controls' icons, at the text size now (as wide as the glyphs
        were: `caption_window.fit_glyph`)."""
        side = style.px(GLYPH_PX)
        ink = self._ink()
        for name in self.buttons:
            self.controls[name].setIcon(icon(GLYPHS[name], ink.text, side))
            fit_glyph(self.buttons[name], side)

    def _place_bar(self) -> None:
        size = self.bar.sizeHint()
        self.bar.setGeometry(
            self.width() - placement.CORNER_ZONE - size.width(),
            placement.EDGE_ZONE - 1,
            size.width(),
            band_height() - placement.EDGE_ZONE,
        )
        if self.bar.isVisible():
            self.bar.raise_()

    def place_notice(self) -> None:
        """The notice line, once, over the window's top band."""
        if self.notice.isVisible():
            self.notice.adjustSize()
            top = band_height() + 4 if self.band_shown else 6
            self.notice.move((self.width() - self.notice.width()) // 2, top)
            self.notice.raise_()
        for column in self.columns:
            column.sync_notice_foot()

    # -- its settings popover -------------------------------------------------------------

    @property
    def settings_open(self) -> bool:
        return self.popover is not None and self.popover.isVisible()

    def toggle_settings(self) -> None:
        """The window's settings popover, beside its settings button - or
        closed."""
        if self.settings_open:
            self.close_settings()
            return
        if self.locked or not self.isVisible():
            return
        with spans.span("joined_window.settings"):
            if self.popover is None:
                self.popover = SettingsPopover(self, self.keys, WINDOW_ROWS)
            button = self.buttons["settings"]
            anchor = QRect(button.mapToGlobal(QPoint(0, 0)), button.size())
            self.popover.open_beside(anchor)

    def close_settings(self) -> None:
        if self.popover is not None:
            self.popover.close()

    def area_at(self, rect: QRect) -> Rect:
        """The work area holding `rect` (global), or this window's."""
        return placement.area_for(to_rect(rect), self._areas()) or self._area()

    # -- the band -------------------------------------------------------------------------

    def show_bands(self, shown: bool) -> None:
        """Every column's strip and the window's controls, together."""
        shown = shown and not self.locked
        if shown == self.band_shown:
            return
        self.band_shown = shown
        self.bar.setVisible(shown)
        if shown:
            self._place_bar()
        else:
            self.close_settings()
        for column in self.columns:
            column.show_band(shown)
        self.place_notice()

    def _band_left(self) -> None:
        if self.settings_open or any(c.settings_open for c in self.columns):
            self._band_out.start()  # the strips stay while a popover is open
            return
        for column in self.columns:
            column.set_hovered(False)
        self.show_bands(False)

    def enterEvent(self, event: QEnterEvent) -> None:
        self.came_over()

    def came_over(self) -> None:
        """The mouse came over it - or moved over a column not hovered: its
        arrival lost, as after locking and unlocking Windows (a caption
        window's `came_over`, polyglotic-hq 272)."""
        if self.locked:
            return
        self._band_out.stop()
        for column in self.columns:
            column.set_hovered(True)
        if not self.band_shown:
            self._band_in.start()
        self._still_over.start()

    def _check_still_over(self) -> None:
        """While hovered: the mouse left without Qt saying so - as if it had."""
        if self.locked or not self.isVisible():
            self._still_over.stop()
        elif not self.geometry().contains(self.pointer()):
            self._still_over.stop()
            self.leaveEvent(None)

    def leaveEvent(self, event: object) -> None:
        if self.resize_hint is not None:
            self.resize_hint.hide()
        self._still_over.stop()
        for column in self.columns:  # a view the mouse held goes live
            column.let_go()  # (as each column's own leave does: 543, 554, 583)
        self._band_in.stop()
        if self._drag is None:
            self._band_out.start()

    # -- where it is ------------------------------------------------------------------------

    def _primary(self) -> Rect:
        areas = self._areas()
        return areas[0] if areas else Rect(0, 0, 1920, 1040)

    def _area(self, rect: Rect | None = None) -> Rect:
        found = placement.area_for(rect or self._place(), self._areas())
        return found or self._primary()

    def _place(self) -> Rect:
        return to_rect(self.geometry())

    def _minimum(self) -> Size:
        least = least_size(MIN_PANEL)
        count = max(1, len(self.columns))
        column = max(
            [placement.MIN_COLUMN, *(self._column_least(c) for c in self.columns)]
        )
        height = max(
            (
                c.subtitle_height(c.choices.text_size, c.choices.translation_size)
                if c.video_enabled
                else least.height
                for c in self.columns
            ),
            default=least.height,
        )
        return Size(max(least.width, column * count), height)

    def _column_least(self, column: CaptionWindow) -> int:
        """`column`'s narrowest: its strip's least width inside the corner
        zones, and the window's controls beside it on the last column
        (`controls_width`) - at Windows' 200 % and the app's Normal (2.25,
        decision 0244) the last column's buttons were squashed past its
        MIN_COLUMN (polyglotic-hq 524). The minimum includes the chip icons.
        Columns share the width equally unless dragged, so each gets at
        least as much as the widest one needs."""
        return column.strip_least() + self.controls_width(column)

    def strips_changed(self) -> None:
        """Keep the window and Qt's minimum wide enough for all columns
        when the mic mark or report button changes (polyglotic-hq 635)."""
        self._widen()
        self._keep_minimum()

    def _keep_minimum(self) -> None:
        """Qt keeps it at least `_minimum` wide - a resize of the lab's or
        Windows' own too - but no wider than its screen's work area: a strip
        too big for any screen is squashed rather than off it."""
        least = min(self._minimum().width, self._area().width)
        if self.minimumWidth() != least:
            self.setMinimumWidth(least)

    def _set_place(self, rect: Rect) -> None:
        if rect != self._place():
            self.setGeometry(to_qrect(rect))

    def place_at(self, rect: Rect) -> None:
        """At `rect` (kept on the screen holding it, or its preset's place on
        the primary screen if no screen does), at least MIN_COLUMN a column."""
        area = self._primary()
        default = placement.slot(
            self.choices.preset if self.choices.preset is not Preset.CUSTOM
            else Preset.BOTTOM_CENTRE,
            area,
            Size(rect.width, rect.height),
        )  # fmt: skip
        start = placement.at_start(rect, self.choices.preset, self._areas(), default)
        self._set_place(start)
        self._widen()

    def _widen(self) -> None:
        """As wide as its columns need, at least (a new column may need more)."""
        least = self._minimum().width
        place = self._place()
        if place.width < least:
            self._set_place(
                placement.joined(place, self.choices.preset, least, self._area())
            )

    # -- the window's choices ---------------------------------------------------------------

    def set_preset(self, preset: Preset) -> None:
        """At a preset's place; the size kept."""
        rect = placement.slot(preset, self._area(), Size(self.width(), self.height()))
        self.choices = replace(self.choices, preset=preset)
        self._set_place(rect)
        self._saved()
        self._sync_controls()
        self.changed.emit()

    def reset_position(self) -> None:
        """Bottom centre, at the default height; as wide as it is."""
        area = self._primary()
        height = min(placement.DEFAULT_HEIGHT, area.height)
        self.choices = replace(self.choices, preset=Preset.BOTTOM_CENTRE)
        self._set_place(
            placement.slot(Preset.BOTTOM_CENTRE, area, Size(self.width(), height))
        )
        for column in self.columns:  # shown where it now is (DECISIONS.md #56)
            column.introduce()
        self._saved()
        self._sync_controls()
        self.changed.emit()

    def _saved(self) -> None:
        self.choices = replace(self.choices, geometry=self._place())

    def set_unlock_keys(self, keys: str) -> None:
        """The hotkey that unlocks now ("" if it doesn't work here): the
        lock button's tip says it, or how else to unlock (398)."""
        self.controls["lock"].setToolTip(lock_tip(keys))

    def set_locked(self, locked: bool) -> None:
        """Locked: clicks pass through the whole window; no band."""
        if locked == self.locked:
            return
        self.locked = locked
        set_click_through(self, locked)  # re-mapped, never live (550)
        if locked:
            if self.resize_hint is not None:
                self.resize_hint.hide()
            self._band_in.stop()
            self.show_bands(False)
            for column in self.columns:
                column.set_hovered(False)

    # -- moving and resizing ----------------------------------------------------------------

    def edges_at(self, pos: QPointF) -> Edge:
        """The edges a press at `pos` (in the window) resizes."""
        zone = GRIP if QApplication.platformName() == "cocoa" else placement.EDGE_ZONE
        return placement.edges_at(pos.x(), pos.y(), self.width(), self.height(), zone)

    def divider_at(self, pos: QPointF) -> int | None:
        """The divider between two columns at `pos` (in the window), which
        a drag moves (284: "For joint windows, you should be able to
        select the size of each window") - None elsewhere, or locked."""
        if self.locked or len(self.columns) < 2:
            return None
        return placement.divider_at(
            pos.x(), self.width(), self._shares(), len(self.columns)
        )

    def press_divider(self, index: int, at: QPointF) -> None:
        """A press on divider `index`: a drag gives one column's width to the
        other, neither narrower than MIN_COLUMN."""
        if not self.locked:
            shares = placement.shares_of(self._shares(), len(self.columns))
            self._divider = (index, at.x(), shares)

    def press(self, edges: Edge, at: QPointF) -> None:
        """A press on a column, off its words: a drag of the whole window."""
        if not self.locked:
            self._drag = _Drag(edges, at, self._place())

    def drag_to(self, at: QPointF) -> None:
        if self._divider is not None:
            index, origin, shares = self._divider
            moved = placement.moved_divider(
                shares, index, at.x() - origin, self.width(), placement.MIN_COLUMN
            )
            if moved != self.choices.shares:
                self.choices = replace(self.choices, shares=moved)
                with spans.span("joined_window.divider_step"):
                    self.lay_out()
                    # the window painted once, as a resize step is: a
                    # column's own repaint painted its neighbour too (both
                    # moved), so three columns were four paints (355)
                    self.repaint()
            return
        drag = self._drag
        if drag is None:
            return
        delta = at - drag.origin
        dx, dy = round(delta.x()), round(delta.y())
        if not drag.moved and abs(dx) + abs(dy) < 3:
            return
        drag.moved = True
        with spans.span("joined_window.drag_step"):
            if drag.edges:
                self.resize_by(drag, dx, dy)
            else:
                self.move_by(drag, dx, dy)

    def resize_by(self, drag: _Drag, dx: int, dy: int) -> None:
        """A resize step: the dragged edges moved, the width shared equally,
        every column laid out again and painted in this frame - the window
        painted once: a column's own repaint painted all three (the resize
        left the whole window to paint), so three of them were five paints
        (polyglotic-hq 355)."""
        area = self._area(drag.start)
        rect = placement.resized(
            drag.start, drag.edges, dx, dy, self.choices.preset, self._minimum(), area
        )
        self._set_place(rect)
        self.repaint()

    def move_by(self, drag: _Drag, dx: int, dy: int) -> None:
        """A move step: kept on the screen; near a preset, snapped to it."""
        raw = Rect(
            drag.start.x + dx, drag.start.y + dy, drag.start.width, drag.start.height
        )
        area = self._area(raw)
        rect, preset = placement.snapped(
            placement.moved(drag.start, dx, dy, area), area
        )
        if preset is not Preset.CUSTOM and preset is not drag.snapped and self.columns:
            self.columns[0].show_notice(preset_name(preset), seconds=1.0)
        drag.snapped = preset
        self._set_place(rect)

    def release(self) -> None:
        if self._divider is not None:
            self._divider = None
            self.changed.emit()  # the columns' widths, saved
            return
        drag, self._drag = self._drag, None
        if drag is None or not drag.moved:
            return
        if drag.edges:
            say_resized("joined window", drag, self._place(), self._minimum())
        else:
            self.choices = replace(self.choices, preset=drag.snapped)
        self._saved()
        self._sync_controls()
        for column in self.columns:
            column.host_changed()
        self.changed.emit()

    # -- events -----------------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.lay_out()

    def moveEvent(self, event: object) -> None:
        """A column's set-up still asked goes with the window (554): the
        column itself doesn't move in it, so it hears no move of its own."""
        for column in self.columns:
            if column.set_up is not None:
                column.set_up.follow()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            not CAPTION_TASKBAR
            and event.type() is QEvent.Type.WindowStateChange
            and self.isMinimized()
        ):
            # as a caption window: no taskbar button to come back from (272)
            log.info("joined caption window minimised by Windows: restored")
            QTimer.singleShot(0, self, restore_minimised(self))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """A press on the band's controls' gaps (the columns take the rest)."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.press(self.edges_at(event.position()), event.globalPosition())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.dragging and self.columns and not self.columns[0].hovered:
            self.came_over()  # its arrival lost (272)
        if not self.dragging and not self.locked:
            edges = self.edges_at(event.position())
            self.setCursor(CURSORS.get(edges, Qt.CursorShape.SizeAllCursor))
            if self.resize_hint is not None:
                self.resize_hint.follow(event.position(), edges)
        self.drag_to(event.globalPosition())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.release()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.locked and self.columns:
            local = self.mapFromGlobal(self.pointer())
            target = next(
                (col for col in self.columns if col.geometry().contains(local)),
                None,
            )
            targets = (target,) if target is not None else tuple(self.columns)
            handled = False
            for column in targets:
                if column._navigation_key(event):
                    handled = True
            if handled:
                return
        super().keyPressEvent(event)
