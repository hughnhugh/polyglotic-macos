"""A caption window's timing chip's dropdown: the bar's "Steady ▾", after
the preset chip, opens it (polyglotic-hq 593; the user, 2026-11-21:
"Timing should probably be its own nav bar setting right? So language
detection, preset, timing").

It offers only the timings the chosen preset's use allows
(`core.listening.offers`, 585's rule 11): Video's Instant and Scrolling; Conversation's Instant and Steady; Learning's Instant, Steady and Calm, and
whether the translation comes after the line has been read or with it;
Everyday's four. Each row is the timing's name and, under it in dim, one
line of what it does. Video uses its nearest offered timing and explains the change once.
For other presets, the chip names a saved timing outside the list and
offers a replacement.

The timing is every window's, as in Settings > Timing: a pick here changes
them all (and, through `main`, is saved in the chosen preset), so a joined
window's columns' chips all say the same. A pick closes the dropdown.

Where the bar is too narrow for the chip, the gear menu opens the same
dropdown. Esc or a click elsewhere closes it.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.offers import Use, offered, use_of
from polyglotic_desktop.core.listening.playout import ReadingPath
from polyglotic_desktop.core.listening.preset_reading import recommendation_for
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import INSET, TICK, Flow, TickButton
from polyglotic_desktop.ui_next.settings_popover import INK, SettingsPopover
from polyglotic_desktop.ui_next.views.preset_menu import PresetMenu, Show

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow

WIDTH = 280
"""At 100 % text size, as the settings popover: each timing's line fits on
one or two rows."""
MARGIN = 12
"""The popover's own margin each side (`SettingsPopover`'s column)."""
ROW_PAD = (4, 8, 5)
"""A timing row's padding above, at its right and below, in pixels at
100 %: as the preset dropdown's rows."""
RECOMMENDED_TAG_GAP = 6
"""Logical px (2..12): gap between a timing's name and its quiet Recommended tag (638)."""


def _tr(text: str) -> str:
    # the caption window's words: its timings' names are translated there
    return QApplication.translate("CaptionWindow", text)


def timing_name(mode: CaptionMode) -> str:
    return {
        CaptionMode.STEADY: _tr("Steady"),
        CaptionMode.WHOLE: _tr("Whole captions"),
        CaptionMode.INSTANT: _tr("Instant"),
        CaptionMode.CALM: _tr("Calm"),
        CaptionMode.SCROLLING: _tr("Scrolling"),
        CaptionMode.PREVIEW: _tr("Steady"),  # retired: never offered (decision 0246)
    }[mode]


def timing_tip(mode: CaptionMode, *, video: bool = False) -> str:
    """What a caption timing does, in plain words, on hover - wherever it's
    chosen (the user's rehearsal feedback F22, 249), with what project 145
    measured on the real models (as the Timing panel's sentence)."""
    if video and mode is CaptionMode.INSTANT:
        return _tr("Words fill each line and continue on the next.")
    steady = _tr(
        "Words appear one by one at the speaker's own pace, a moment "
        "behind, and rarely change once shown."
    )
    return {
        CaptionMode.SCROLLING: _tr("Words scroll sideways as the line fills."),
        CaptionMode.STEADY: steady,
        CaptionMode.PREVIEW: steady,  # retired: never offered (decision 0246)
        CaptionMode.CALM: _tr(
            "Like Steady, but only words the speech model is sure of: later, "
            "and almost nothing changes once shown."
        ),
        CaptionMode.WHOLE: _tr(
            "Each sentence appears once, finished, about half a second after it "
            "ends. Nothing changes while you read."
        ),
        CaptionMode.INSTANT: _tr(
            "Words appear as they're said and rewrite themselves until the "
            "sentence ends - the quickest, but the words move."
        ),
    }[mode]


def timing_line(mode: CaptionMode) -> str:
    """The one line under a timing's name in the dropdown."""
    return {
        CaptionMode.SCROLLING: _tr("Words scroll sideways as the line fills."),
        CaptionMode.STEADY: _tr("Word by word at the speaker's pace, a moment behind"),
        CaptionMode.PREVIEW: _tr("Word by word at the speaker's pace, a moment behind"),
        CaptionMode.CALM: _tr(
            "Only words the speech model is sure of: later, and still"
        ),
        CaptionMode.WHOLE: _tr(
            "Each sentence once, finished: nothing moves as you read"
        ),
        CaptionMode.INSTANT: _tr(
            "Words as they're said: the quickest, but they change"
        ),
    }[mode]


def path_name(path: ReadingPath) -> str:
    return {
        ReadingPath.ACQUISITION: _tr("Translation after I've read it"),
        ReadingPath.BOTH: _tr("Translation with it"),
        ReadingPath.FOLLOW: _tr("Translation with it"),  # not offered on the chip
    }[path]


def path_line(path: ReadingPath) -> str:
    return {
        ReadingPath.ACQUISITION: _tr("Each line first, its translation a moment later"),
        ReadingPath.BOTH: _tr("Each line and its translation together"),
        ReadingPath.FOLLOW: _tr("Each line and its translation together"),
    }[path]


def fallback_note(requested: CaptionMode, effective: CaptionMode) -> str:
    return _tr("Video uses {effective} when {requested} is selected.").format(
        effective=timing_name(effective),
        requested=timing_name(requested),
    )


def chip_label(mode: CaptionMode, preset: str) -> str:
    """The bar's timing chip: the timing's name, as the preset's use names it."""
    return timing_name(mode)


def chip_name(mode: CaptionMode, preset: str) -> str:
    """The timing chip in words, for a screen reader - never its arrow:
    "Timing: Instant" (593)."""
    return _tr("Timing: {timing}").format(timing=chip_label(mode, preset))


def recommended_tag() -> str:
    """The quiet tag shown on the timing recommended for the active preset (638)."""
    #: Quiet tag shown beside the timing option recommended for the active preset
    return _tr("Recommended")


def recommended_reason(reason: str) -> str:
    """Translate a built-in preset's one-line recommendation reason (638)."""
    return _tr(reason)


def recommended_note(preset: str, reason: str) -> str:
    """Tip and screen-reader text for a preset's recommended timing (638)."""
    #: {preset} is the active preset's name; {reason} is why this timing is recommended for it
    return _tr("Recommended for {preset}: {reason}").format(
        preset=preset, reason=recommended_reason(reason)
    )


def _fallback_preset_name(key: str) -> str:
    names = {
        "everyday": QApplication.translate("Presets", "Everyday"),
        "conversation": QApplication.translate("Presets", "Conversation"),
        "video": QApplication.translate("Presets", "Video, film & TV"),
        "learning": QApplication.translate("Presets", "Learning"),
    }
    return names.get(key, key)


def menu_recommendation(menu: PresetMenu) -> tuple[CaptionMode, str] | None:
    """The active preset's recommended timing and tip/screen-reader note, or None."""
    rec = recommendation_for(menu.chosen, menu.chosen_parent)
    if rec is None:
        return None
    preset = menu.name or _fallback_preset_name(rec.preset)
    return rec.recommended_timing, recommended_note(preset, rec.reason)


def _recommended_badge(parent: QWidget, object_name: str) -> QLabel:
    badge = QLabel(recommended_tag(), parent)
    badge.setObjectName(object_name)
    badge.setProperty("recommended", True)
    badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return badge


class _TimingRow(TickButton):
    """A timing's row: its tick beside its name, its line under it in dim,
    however many rows that wraps to."""

    name_bottom = 0
    """Where the name's line ends, from the row's top."""

    def paintEvent(self, event: QPaintEvent) -> None:
        QPushButton.paintEvent(self, event)
        if not (self.isCheckable() and self.isChecked() and self.ink):
            return
        painter = QPainter(self)
        painter.setPen(QColor(self.ink[0]))
        painter.drawText(
            QRectF(INSET, 0, style.px(TICK), self.name_bottom or self.height()),
            Qt.AlignmentFlag.AlignVCenter,
            "✓",
        )
        painter.end()


class TimingPopover(SettingsPopover):
    """The timing dropdown of one caption window (or a joined window's
    column): made from the window's preset, timing and translation path
    each time one changes."""

    def __init__(self, window: "CaptionWindow") -> None:
        self._shown: tuple[object, ...] | None = None
        super().__init__(window, window.keys, ("timings",))
        self.setObjectName("caption_window.timings")
        self.width_at_100 = WIDTH
        self.setFixedWidth(style.px(WIDTH))

    def _timings_row(self) -> QWidget:
        self.body = QWidget(self)
        self.column = QVBoxLayout(self.body)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(2)
        return self.body

    @property
    def _caption_window(self) -> "CaptionWindow":
        return self.owner  # type: ignore[return-value]

    def refresh(self) -> None:
        window = self._caption_window
        shown = (window.preset_menu, window.timing, window.path, window.video_enabled)
        if shown != self._shown:
            self._shown = shown
            self._make()
        self._fit()

    def _make(self) -> None:
        """Its rows afresh: the preset's timings, and its translation's."""
        while self.column.count():
            item = self.column.takeAt(0)
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)  # not found among its rows meanwhile
                widget.deleteLater()
        window = self._caption_window
        use = (
            Use.WATCHING if window.video_enabled else use_of(window.preset_menu.chosen)
        )
        offer = offered(use)
        if not offer.allows(window.timing):
            note = QLabel(
                _tr("{timing} doesn't suit {preset}: pick one of these").format(
                    timing=timing_name(window.timing),
                    preset=window.preset_menu.name,
                ),
                self.body,
            )
            note.setObjectName("timings.not_offered")
            note.setProperty("note", True)
            note.setWordWrap(True)
            self.column.addWidget(note)
        rec = menu_recommendation(window.preset_menu)
        for mode in offer.timings:
            rec_note = rec[1] if rec is not None and rec[0] is mode else ""
            video = use is Use.WATCHING
            line = timing_tip(mode, video=True) if video else timing_line(mode)
            row = self._row(
                timing_name(mode),
                line,
                mode is window.timing,
                recommended=rec_note,
                badge_name=f"timings.recommended.{mode.value}",
            )
            row.setObjectName(f"timings.timing.{mode.value}")
            tip = line if video else timing_tip(mode)
            row.setToolTip(f"{rec_note}\n{tip}" if rec_note else tip)
            row.clicked.connect(lambda _=False, m=mode: self._chose_timing(m))
            self.column.addWidget(row)
        if use is Use.WATCHING:
            self.column.addSpacing(6)
            for side, name, other in (
                (Show.ORIGINAL, _tr("Show original"), Show.TRANSLATION),
                (Show.TRANSLATION, _tr("Show translation"), Show.ORIGINAL),
            ):
                show = window.preset_menu.show
                toggle = TickButton(self.body, INK[:2])
                toggle.setText(name)
                toggle.setObjectName(f"timings.show.{side.value}")
                toggle.setProperty("tick", True)
                toggle.setCheckable(True)
                toggle.setChecked(show is not other)
                toggle.setEnabled(show is not side)
                toggle.clicked.connect(
                    lambda checked, alternative=other: window.lines_wanted.emit(
                        (Show.BOTH if checked else alternative).value
                    )
                )
                self.column.addWidget(toggle)
        paths = offer.paths if window.timing.paced else ()
        if paths:
            self.column.addSpacing(6)
        for path in paths:
            row = self._row(path_name(path), path_line(path), path is window.path)
            row.setObjectName(f"timings.path.{path.value}")
            row.clicked.connect(lambda _=False, p=path: self._chose_path(p))
            self.column.addWidget(row)
        for child in self.body.findChildren(QWidget):
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # nothing takes the keyboard

    def _row(
        self,
        name: str,
        line: str,
        on: bool,
        recommended: str = "",
        badge_name: str = "timings.recommended",
    ) -> _TimingRow:
        """A choice's row: a tick while chosen, its name (with a quiet
        Recommended tag when `recommended` is set), and under it in dim its
        line."""
        button = _TimingRow(self.body, INK[:2])
        button.setProperty("tick", True)
        button.setCheckable(True)
        button.setChecked(on)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(
            f"{name}. {recommended}. {line}" if recommended else f"{name}. {line}"
        )
        if recommended:
            button.setAccessibleDescription(recommended)
        top, right, bottom = ROW_PAD
        left = INSET + style.px(TICK)
        lines = QVBoxLayout(button)
        lines.setContentsMargins(left, top, right, bottom)
        lines.setSpacing(2 if recommended else 0)
        # wrapped at the dropdown's width: a long language's line runs to a
        # second row, never past the edge (as the preset dropdown's, 572)
        wide = style.px(self.width_at_100) - 2 * MARGIN - left - right
        tall = top + bottom
        if recommended:
            header = QWidget(button)
            header.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            flow = Flow(header, spacing=RECOMMENDED_TAG_GAP, line_spacing=2)
            title = QLabel(name, header)
            title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            title.setStyleSheet("padding-left: 0px;")
            title.setWordWrap(True)
            title.ensurePolished()
            badge = _recommended_badge(header, badge_name)
            badge.ensurePolished()
            flow.addWidget(title)
            flow.addWidget(badge)
            header_height = flow.heightForWidth(wide)
            button.name_bottom = top + max(
                title.sizeHint().height(), badge.sizeHint().height()
            )
            tall += header_height + 2
            lines.addWidget(header)
        else:
            title = QLabel(name, button)
            title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            title.setStyleSheet("padding-left: 0px;")
            title.setWordWrap(True)
            title.ensurePolished()
            tall += title.heightForWidth(wide)
            button.name_bottom = tall  # the tick beside the name
            lines.addWidget(title)
        detail = QLabel(line, button)
        detail.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        detail.setProperty("note", True)  # the popover's dim notes, on its scale
        detail.setStyleSheet("padding-left: 0px;")
        detail.setWordWrap(True)
        detail.ensurePolished()
        tall += detail.heightForWidth(wide)
        lines.addWidget(detail)
        button.setMinimumHeight(tall)
        return button

    def _chose_timing(self, mode: CaptionMode) -> None:
        """A timing picked: every window changes under it, so it closes."""
        self.close()
        # Choosing the effective fallback explicitly also saves it as the preference.
        self._caption_window.timing_wanted.emit(mode.value)

    def _chose_path(self, path: ReadingPath) -> None:
        self.close()
        if path is not self._caption_window.path:
            self._caption_window.path_wanted.emit(path.value)
