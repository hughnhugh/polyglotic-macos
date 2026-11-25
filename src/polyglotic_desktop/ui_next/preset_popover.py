"""A caption window's preset dropdown: the bar's preset chip ("Video ▾")
opens it (polyglotic-hq 556, desktop decision 0264).

In three groups and a link, top to bottom - and first, while the chosen
preset has changes not saved (polyglotic-hq 587, decision 0283), Save
changes to it, Save as new preset… and Discard changes; while a step that
lost something can be undone, its note and Undo:
- **Preset** - one choice, a template: Conversation, Video, film & TV,
  Learning, Custom and the learner's own, each with its line of what it's
  for. A click picks it and closes the dropdown;
- **Show** - one choice: Both, Original only or Translation only (the
  user's "captions only" and "translations only", in the app's words);
- **Add** - several on top: Word links or the quiet view (one or the
  other, as the strip's two buttons were: DECISIONS #205), Readings, My
  speech (in every window);
- under a rule, the chosen preset's own steps - Save as new preset… while
  it has nothing to save; Restore its defaults for a built-in with changes
  saved in it; Rename… and Delete for one of the learner's - and
  **Customise presets…**: Settings > Presets.

What is ticked in Show and Add shows at once and leaves the preset edited -
the chip's dot - until it's saved (`main`, through `ui.use_presets`); the
dropdown stays open for another. Naming a new preset and renaming one
happen on Settings' line. The dropdown uses `SettingsPopover` for
keyboard access on request, and closes on Esc or a click elsewhere.
"""

from typing import TYPE_CHECKING

from PySide6.QtCore import QLocale, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.preset_reading import VIDEO_LINE_CHOICES
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import INSET, TICK, TickButton
from polyglotic_desktop.ui_next.settings_popover import (
    INK,
    LINE,
    SettingsPopover,
    long_lines_name,
)
from polyglotic_desktop.ui_next.views.preset_menu import PresetMenu, Show, Undo

if TYPE_CHECKING:
    from polyglotic_desktop.ui_next.caption_window import CaptionWindow

WIDTH = 300
MARGIN = 12
"""The popover's own margin each side (`SettingsPopover`'s column)."""
"""At 100 % text size, a little wider than the settings popover: the
presets' lines fit on one line each."""


def _tr(text: str) -> str:
    return QApplication.translate("Presets", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("Presets", text, None, n)


"""The chip's mark while the chosen preset has changes not saved (587)."""


def preset_name(key: str) -> str:
    """A built-in preset's own name, in the interface's language."""
    names = {
        "everyday": _tr("Everyday"),
        "conversation": _tr("Conversation"),
        "video": _tr("Video, film & TV"),
        "learning": _tr("Learning"),
        "custom": _tr("Custom"),
    }
    return names.get(key, key)


def preset_note(key: str) -> str:
    """The line under a preset's name: what it's for."""
    notes = {
        "everyday": _tr("Every helper on: the app's defaults"),
        "conversation": _tr("Calls and chats: your speech too"),
        "video": _tr("Subtitles along the bottom, large"),
        "learning": _tr("Word links and fewer word introductions"),
        "custom": _tr("Your settings from before presets"),
    }
    return notes.get(key, _tr("One of your own"))


def show_name(show: Show) -> str:
    return {
        Show.BOTH: _tr("Both"),
        Show.ORIGINAL: _tr("Original only"),
        Show.TRANSLATION: _tr("Translation only"),
    }[show]


def chip_label(menu: PresetMenu) -> str:
    """The active preset's name."""
    return menu.name or preset_name("everyday")


def chip_name(menu: PresetMenu) -> str:
    """The preset chip in words for a screen reader."""
    return _tr("Preset: {name}").format(name=chip_label(menu))


def not_saved(n: int) -> str:
    """How many of the chosen preset's settings it hasn't saved."""
    return _trn("%n change(s) not saved", n)


def undo_note(menu: PresetMenu) -> str:
    """What a step that can be undone lost, in words (587) - "" if none."""
    if menu.undo is None:
        return ""
    kind, was = menu.undo
    if kind is Undo.SWITCHED:
        return _tr("Now {name}. Changes to {before} weren't saved.").format(
            name=menu.name, before=was
        )
    if kind is Undo.DISCARDED:
        return _tr("Changes to {name} discarded.").format(name=was)
    if kind is Undo.LONG_LINES:
        return long_lines_name(menu.long_lines)
    if kind is Undo.RESTORED:
        return _tr("{name} is back to its defaults.").format(name=was)
    return _tr("{name} deleted.").format(name=was)


def save_to(name: str) -> str:
    return _tr("Save changes to {name}").format(name=name)


def save_as_new() -> str:
    return _tr("Save as new preset…")


def discard() -> str:
    return _tr("Discard changes")


def restore_defaults(name: str) -> str:
    return _tr("Restore {name}'s defaults").format(name=name)


class _PresetRow(TickButton):
    """A preset's row: its tick beside its name's line, however many rows
    the line under the name wraps to."""

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


class PresetPopover(SettingsPopover):
    """The preset dropdown of one caption window (or a joined window's
    column): made from the window's `preset_menu` each time it changes."""

    def __init__(self, window: "CaptionWindow") -> None:
        self._shown: tuple[PresetMenu, bool] | None = None
        super().__init__(window, window.keys, ("presets",))
        self.setObjectName("caption_window.presets")
        self.width_at_100 = WIDTH
        self.setFixedWidth(style.px(WIDTH))

    def _presets_row(self) -> QWidget:
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
        shown = window.preset_menu, window.video_enabled
        if shown != self._shown:
            self._shown = shown
            self._make(*shown)
        self._fit()

    def _make(self, menu: PresetMenu, video: bool) -> None:
        """Its rows afresh, from `menu`."""
        while self.column.count():
            item = self.column.takeAt(0)
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        window = self._caption_window
        if menu.undo is not None:
            said = self._heading(undo_note(menu))
            said.setObjectName("presets.undo_note")
            said.setWordWrap(True)
            self.column.addWidget(said)
            self.column.addWidget(self._step(_tr("Undo"), "undo"))
            self._rule()
        self.column.addWidget(self._heading(_tr("Preset")))
        for each in menu.items:
            note = preset_note(each.key)
            row = self._preset(each.name, note, each.key == menu.chosen)
            row.setObjectName(f"presets.preset.{each.key}")
            row.clicked.connect(lambda _=False, key=each.key: self._chose(key))
            self.column.addWidget(row)
        self.column.addSpacing(6)
        show_choices = self._preset_segments(_tr("Show"))
        for show in Show:
            button = self._segment(
                show_choices,
                show_name(show),
                f"presets.show.{show.value}",
                show is menu.show,
            )
            button.clicked.connect(
                lambda _=False, chosen=show: window.lines_wanted.emit(chosen.value)
            )
        if video:
            self.column.addSpacing(6)
            #: How many subtitle lines remain on screen in Video mode.
            line_choices = self._preset_segments(_tr("Lines shown"))
            for count in VIDEO_LINE_CHOICES:
                button = self._segment(
                    line_choices,
                    QLocale().toString(count),
                    f"presets.video_lines.{count}",
                    count == menu.video_lines_shown,
                )
                button.clicked.connect(
                    lambda _=False, chosen=count: window.video_lines_wanted.emit(chosen)
                )
        self.column.addSpacing(6)
        self.column.addWidget(self._heading(_tr("Helpers")))
        links = self._tick(_tr("Word links"), menu.links, "links")
        links.setEnabled(
            menu.show is not Show.TRANSLATION
        )  # they join to what was said
        links.clicked.connect(
            lambda on: window.links_wanted.emit(on, window.readings())
        )
        quiet = self._tick(_tr("Quiet view"), menu.quiet, "quiet")
        quiet.clicked.connect(
            lambda on: window.quiet_wanted.emit(on, window.readings())
        )
        readings = self._tick(_tr("Readings"), menu.readings, "readings")
        readings.setToolTip(_tr("Pinyin, Jyutping or a respelling over the words"))
        readings.clicked.connect(
            lambda on: window.readings_wanted.emit(on, window.readings())
        )
        for tick in (links, quiet, readings):
            self.column.addWidget(tick)
        self._rule()
        if menu.restorable:
            self.column.addWidget(self._step(restore_defaults(menu.name), "restore"))
        if menu.chosen_own:
            self.column.addWidget(self._step(_tr("Rename…"), "rename"))
            self.column.addWidget(self._step(_tr("Delete"), "delete"))
        customise = QPushButton(_tr("Customise presets…"), self.body)
        customise.setObjectName("presets.customise")
        customise.setCursor(Qt.CursorShape.PointingHandCursor)
        customise.setToolTip(_tr("Edit, rename, reset or add presets in Settings"))
        customise.clicked.connect(self._customise)
        self.column.addWidget(customise)
        for child in self.body.findChildren(QWidget):
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # nothing takes the keyboard

    def _preset_segments(self, title: str) -> QButtonGroup:
        self.column.addWidget(self._heading(title))
        holder = QWidget(self.body)
        segments = QHBoxLayout(holder)
        segments.setContentsMargins(INSET - 1, 0, 0, 0)
        segments.setSpacing(4)
        segments.addStretch(1)
        self.column.addWidget(holder)
        return QButtonGroup(holder)

    @staticmethod
    def _segment(
        group: QButtonGroup, text: str, name: str, selected: bool
    ) -> QPushButton:
        holder = group.parent()
        assert isinstance(holder, QWidget)
        segments = holder.layout()
        assert isinstance(segments, QHBoxLayout)
        button = QPushButton(text, holder)
        button.setObjectName(name)
        button.setProperty("segment", True)
        button.setCheckable(True)
        button.setChecked(selected)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        group.addButton(button)
        segments.insertWidget(segments.count() - 1, button)
        return button

    def _rule(self) -> None:
        rule = QFrame(self.body)
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"background: {LINE};")
        self.column.addSpacing(4)
        self.column.addWidget(rule)
        self.column.addSpacing(2)

    def _step(self, text: str, step: str) -> QPushButton:
        """A step on the chosen preset (587): its button, which closes the
        dropdown and hands the step to `main` by the window."""
        button = QPushButton(style.button_text(text), self.body)
        button.setObjectName(f"presets.step.{step}")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _=False: self._stepped(step))
        return button

    def _stepped(self, step: str) -> None:
        self.close()
        self._caption_window.preset_step.emit(step)

    def _heading(self, text: str) -> QLabel:
        heading = QLabel(text, self.body)
        heading.setProperty("note", True)
        return heading

    def _preset(self, name: str, note: str, on: bool) -> _PresetRow:
        """A preset's row: a tick while chosen, its name, and under it in
        dim its line."""
        button = _PresetRow(self.body, INK[:2])
        button.setProperty("tick", True)
        button.setCheckable(True)
        button.setChecked(on)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(f"{name}. {note}")
        left, top, right, bottom = INSET + style.px(TICK), 4, 8, 5
        lines = QVBoxLayout(button)
        lines.setContentsMargins(left, top, right, bottom)
        lines.setSpacing(0)
        # the row's words wrap at the dropdown's width: a long language's
        # line runs to a second row, never past the edge (572: Everyday's
        # note was cut by 17 px in French and Russian)
        wide = style.px(self.width_at_100) - 2 * MARGIN - left - right
        tall = top + bottom
        for text, dim in ((name, False), (note, True)):
            line = QLabel(text, button)
            line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            line.setProperty("note", dim)  # the popover's dim notes, on its scale
            line.setStyleSheet("padding-left: 0px;")
            line.setWordWrap(True)
            line.ensurePolished()  # its font from the popover's sheet, measured
            tall += line.heightForWidth(wide)
            if not dim:
                button.name_bottom = tall  # the tick beside the name
            lines.addWidget(line)
        button.setMinimumHeight(tall)
        return button

    def _tick(self, text: str, on: bool, name: str) -> TickButton:
        button = TickButton(self.body, INK[:2])
        button.setText(text)
        button.setObjectName(f"presets.add.{name}")
        button.setProperty("tick", True)
        button.setCheckable(True)
        button.setChecked(on)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _chose(self, key: str) -> None:
        """A preset picked: the windows change under it, so it closes."""
        self.close()
        self._caption_window.preset_wanted.emit(key)

    def _customise(self) -> None:
        self.close()
        self._caption_window.customise_wanted.emit()
