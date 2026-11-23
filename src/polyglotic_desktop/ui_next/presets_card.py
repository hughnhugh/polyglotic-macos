"""Settings > Presets (polyglotic-hq 556, desktop decision 0264): the
presets, and the chosen one's own card.

- **Presets:** a row per preset - its name and its line of what it's for;
  the chosen one says "In use", the others have Use - and New preset (named
  on the line, `PresetLine`: up to five of the learner's own).
- **The chosen preset:** its name to rename (a built-in's own comes back
  when it's emptied), what it changes as saved - each setting in words -
  Restore its defaults for a built-in with changes saved in it, and Delete
  for one of the learner's own.
- **The preset line** (`PresetLine`, polyglotic-hq 587, decision 0283) at
  the top of the sections that hold a preset's settings: which preset is
  in use and how many of its settings aren't saved, with Save to it, Save
  as new preset… (its name typed in the line) and Discard changes; and,
  for a few seconds after a step that lost something, Undo.

A change in a caption section shows at once and leaves the preset edited
until it's saved (`main`, through `ui.use_presets`). Bound to a
`PresetsView`.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.controls import label
from polyglotic_desktop.ui_next.panels import Panel
from polyglotic_desktop.ui_next.preset_popover import (
    discard,
    not_saved,
    preset_note,
    restore_defaults,
    save_as_new,
    undo_note,
)
from polyglotic_desktop.ui_next.views.preset_menu import PresetsView


def _tr(text: str) -> str:
    return QApplication.translate("Presets", text)


def line_text(name: str, edited: int) -> str:
    """The preset line's words: the preset in use, and how many of its
    settings aren't saved (587) - never "changes here are saved", which
    read as covering the app's language beside it."""
    if edited:
        return _tr("Preset: {name} · {not_saved}").format(
            name=name, not_saved=not_saved(edited)
        )
    return _tr("Using the preset {name}").format(name=name)


class _NameField(QLineEdit):
    """The new preset's name: Enter saves it, Esc puts the line back."""

    def __init__(self, line: "PresetLine") -> None:
        super().__init__(line)
        self._line = line

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._line.view.naming.change(False)
            return
        super().keyPressEvent(event)


class PresetLine(QFrame):
    """The preset in use, on Settings' sections that hold its settings
    (587): "Using the preset Learning" with Save as new preset…, or
    "Preset: Learning · 3 changes not saved" with Save to Learning, Save as
    new preset… and Discard changes; while naming a new one, its name -
    "Learning 2" to start - with Save and Cancel; and for a few seconds
    after a step that lost something, what it lost and Undo."""

    def __init__(self, view: PresetsView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settings.preset_line")
        self.setProperty("banner", True)
        self.view = view
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 6, 6, 6)
        row.setSpacing(8)
        self.words = label("", "Dim", wrap=True)
        self.words.setObjectName("presets.line")
        row.addWidget(self.words, 1)
        self.name = _NameField(self)
        self.name.setObjectName("presets.new_name")
        self.name.setAccessibleName(_tr("The new preset's name"))
        self.name.setMaxLength(40)
        self.name.returnPressed.connect(self._named)
        row.addWidget(self.name, 1)
        self.save = self._button("presets.line.save", lambda: self.view.save())
        self.save.setProperty("kind", "primary")
        self.save_as = self._button(
            "presets.line.save_as", lambda: self.view.naming.change(True)
        )
        self.save_as.setText(save_as_new())
        self.discard = self._button("presets.line.discard", lambda: self.view.discard())
        self.discard.setText(discard())
        self.discard.setProperty("kind", "ghost")
        self.undo = self._button("presets.line.undo", lambda: self.view.undo())
        self.undo.setText(_tr("Undo"))
        self.done = self._button("presets.line.named", self._named)
        self.done.setText(_tr("Save"))
        self.done.setProperty("kind", "primary")
        self.cancel = self._button(
            "presets.line.cancel", lambda: self.view.naming.change(False)
        )
        self.cancel.setText(_tr("Cancel"))
        self.cancel.setProperty("kind", "ghost")
        for button in (
            self.save,
            self.save_as,
            self.discard,
            self.undo,
            self.done,
            self.cancel,
        ):
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        stops = (view.subscribe(self.refresh), view.naming.subscribe(self._naming))
        self.destroyed.connect(lambda *_: [stop() for stop in stops])
        self.refresh()

    def _button(self, name: str, step: Callable[[], None]) -> QPushButton:
        button = QPushButton(self)
        button.setObjectName(name)
        button.clicked.connect(lambda _=False: step())
        return button

    def refresh(self) -> None:
        menu = self.view.value
        naming = self.view.naming.value and menu.can_add
        undo = menu.undo is not None and not naming
        edited = bool(menu.edited) and not naming and not undo
        if naming:
            self.words.setText(_tr("Save as new preset:"))
        elif undo:
            self.words.setText(undo_note(menu))
        else:
            self.words.setText(line_text(menu.name, menu.edited))
        self.save.setText(
            style.button_text(_tr("Save to {name}").format(name=menu.name))
        )
        self.name.setVisible(naming)
        self.done.setVisible(naming)
        self.cancel.setVisible(naming)
        self.undo.setVisible(undo)
        self.save.setVisible(edited)
        self.discard.setVisible(edited)
        self.save_as.setVisible(not naming and not undo)
        self.save_as.setEnabled(menu.can_add)
        self.save_as.setToolTip(
            "" if menu.can_add else _tr("Five of your own at most: delete one first")
        )

    def _naming(self) -> None:
        """Save as new preset… asked: the name field, suggested and chosen,
        with the keyboard - or the line back."""
        self.refresh()
        if self.view.naming.value and self.view.value.can_add:
            self.name.setText(self.view.value.new_name)
            self.name.setFocus()
            self.name.selectAll()

    def _named(self) -> None:
        name = self.name.text().strip() or self.view.value.new_name
        self.view.naming.change(False)
        self.view.add(name)


def _on(value: object) -> str:
    return _tr("On") if value else _tr("Off")


def _percent(value: object) -> str:
    return _tr("{percent}%").format(percent=round(float(value) * 100))  # type: ignore[arg-type]


def _seconds(value: object) -> str:
    if value is None:
        return _tr("Never")
    return _tr("{seconds} s").format(seconds=f"{float(value):g}")  # type: ignore[arg-type]


def _words_for(name: str, value: object) -> str:
    """A setting's value in words, as the presets' card lists it."""
    if name == "word_links":
        return {
            "off": _tr("Off"),
            "hover": _tr("On hover only"),
            "colours": _tr("Colours"),
            "arrows": _tr("With arrows"),
        }.get(str(value), str(value))
    if name == "reading_lines":
        return _tr("None") if not value else ", ".join(str(v) for v in value)  # type: ignore[attr-defined]
    if name == "caption_path":
        return {
            "follow": _tr("Follow (the translation leads)"),
            "acquisition": _tr("Acquisition (each line first)"),
            "both": _tr("Both together"),
        }.get(str(value), str(value))
    if name == "caption_mode_chosen":
        return {
            "words": _tr("Steady"),
            "steady": _tr("Whole captions"),
            "live": _tr("Instant"),
            "calm": _tr("Calm"),
        }.get(str(value), _tr("The default"))
    if name == "caption_edge":
        return {
            "none": _tr("None"),
            "shadow": _tr("A shadow"),
            "outline": _tr("An outline"),
        }.get(str(value), str(value))
    if name == "steady_words_ahead":
        return {
            "none": _tr("None"),
            "waiting": _tr("The words waiting"),
            "all": _tr("All, the newest too"),
        }.get(str(value), str(value))
    if name == "marks_off":  # its title says what it is; the value is on or off
        return _on(not value)
    if name == "common_words_only":
        return _tr("A few") if value else _tr("Every new word")
    if name == "my_speech":
        return _tr("Each window's own") if value is None else _on(value)
    if name in ("opacity", "subtitle_size", "subtitle_width"):
        return _percent(value)
    if name in ("fade_after", "translation_after"):
        return _seconds(value)
    if name in ("caption_contrast", "caption_vibrance", "caption_weight"):
        return str(value)
    if name in ("preset_languages", "preset_second_languages"):
        return _tr("Custom choices") if value else _tr("Default choices")
    if isinstance(value, bool):
        return _on(value)
    return str(value)


def setting_title(name: str) -> str:
    """A preset setting's name, as the presets' card lists it."""
    titles = {
        "show_original": _tr("What was said"),
        "show_translation": _tr("The translation"),
        "show_language": _tr("The language over each caption"),
        "show_source": _tr("The source over each caption"),
        "fade_after": _tr("Fade after quiet"),
        "word_links": _tr("Word links"),
        "quiet_view": _tr("Quiet view"),
        "reading_lines": _tr("Readings"),
        "reading_past": _tr("Readings only past what you know"),
        "marks_off": _tr("Word introductions"),
        "common_words_only": _tr("How many word introductions"),
        "opacity": _tr("Panel"),
        "original_color": _tr("What was said's colour"),
        "translation_color": _tr("The translation's colour"),
        "background_color": _tr("The panel's colour"),
        "caption_edge": _tr("Around the letters"),
        "caption_weight": _tr("Thickness"),
        "caption_contrast": _tr("Contrast"),
        "caption_vibrance": _tr("Vibrance"),
        "caption_mode_chosen": _tr("Caption mode"),
        "caption_path": _tr("Path"),
        "translation_after": _tr("Translation after"),
        "steady_newest_word": _tr("The newest word shown"),
        "steady_words_ahead": _tr("Words ahead"),
        "steady_two_zones": _tr("Two zones"),
        "steady_cards": _tr("Card stack"),
        "subtitles": _tr("Subtitles along the bottom"),
        "subtitle_size": _tr("Subtitles' text size"),
        "subtitle_width": _tr("Subtitles' width"),
        "my_speech": _tr("My speech"),
        "lyrics": _tr("Lyrics"),
        "preset_languages": _tr("Window languages"),
        "preset_second_languages": _tr("Second languages"),
    }
    return titles.get(name, name)


def change_words(changes: dict[str, object]) -> tuple[tuple[str, str], ...]:
    """What a preset changes, each setting's name and its value in words."""
    return tuple(
        (setting_title(name), _words_for(name, value))
        for name, value in changes.items()
    )


class PresetsPanel(Panel):
    """The presets, each to use, and New preset."""

    def __init__(self, view: PresetsView) -> None:
        super().__init__(
            _tr("Presets"),
            _tr(
                "Pick how captions work for what you're doing - here or from a "
                "caption window's bar. Bar changes save automatically. "
                "Use Save here to keep your Settings edits."
            ),
        )
        self.setObjectName("settings.presets")
        self.view = view
        self.rows = QVBoxLayout()
        self.rows.setSpacing(2)
        self.add(self.rows)
        self.new = QPushButton(_tr("New preset"))
        self.new.setObjectName("presets.new")
        self.new.setToolTip(
            _tr("The captions as they are now, as a preset of your own")
        )
        self.new.clicked.connect(lambda: self.view.naming.change(True))
        line = QHBoxLayout()
        line.addWidget(self.new)
        line.addStretch(1)
        self.add(line)
        self.bind(view)
        self.refresh()

    def refresh(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            assert item is not None
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        menu = self.view.value
        for each in menu.items:
            self.rows.addWidget(self._row(each.key, each.name, each.own, menu.chosen))
        self.new.setEnabled(menu.can_add)

    def _row(self, key: str, name: str, own: bool, chosen: str) -> QWidget:
        row = QWidget()
        row.setObjectName(f"presets.row.{key}")
        line = QHBoxLayout(row)
        line.setContentsMargins(8, 4, 0, 4)
        line.setSpacing(12)
        words = QVBoxLayout()
        words.setSpacing(1)
        words.addWidget(label(name, "RowTitle", wrap=True))
        note = preset_note(key)
        words.addWidget(label(note, "Faint", wrap=True))
        line.addLayout(words, 1)
        if key == chosen:
            line.addWidget(
                label(_tr("In use"), "Dim"), 0, Qt.AlignmentFlag.AlignVCenter
            )
        else:
            use = QPushButton(_tr("Use"))
            use.setObjectName(f"presets.use.{key}")
            use.setAccessibleName(_tr("Use {name}").format(name=name))
            use.clicked.connect(lambda _=False, k=key: self.view.chose(k))
            line.addWidget(use, 0, Qt.AlignmentFlag.AlignVCenter)
        return row


class PresetPanel(Panel):
    """The preset in use: its name, what it changes, Reset and Delete."""

    def __init__(self, view: PresetsView) -> None:
        super().__init__(_tr("The preset in use"))
        self.setObjectName("settings.preset")
        self.view = view
        self.name = QLineEdit()
        self.name.setObjectName("presets.name")
        self.name.setAccessibleName(_tr("Its name"))
        self.name.setMaxLength(40)
        self.name.editingFinished.connect(self._renamed)
        named = QVBoxLayout()
        named.setSpacing(4)
        named.addWidget(label(_tr("Its name"), "RowTitle"))
        named.addWidget(self.name)
        self.add(named)
        self.changes_title = label(_tr("What it changes"), "RowTitle")
        self.add(self.changes_title)
        self.changes = label("", "Dim", wrap=True)
        self.changes.setObjectName("presets.changes")
        self.add(self.changes)
        self.reset = QPushButton()
        self.reset.setObjectName("presets.reset")
        self.reset.clicked.connect(lambda: self.view.reset(self.view.value.chosen))
        self.delete = QPushButton(_tr("Delete"))
        self.delete.setObjectName("presets.delete")
        self.delete.clicked.connect(lambda: self.view.delete(self.view.value.chosen))
        buttons = QHBoxLayout()
        buttons.addWidget(self.reset)
        buttons.addWidget(self.delete)
        buttons.addStretch(1)
        self.add(buttons)
        self.bind(view)
        self.refresh()

    def refresh(self) -> None:
        menu = self.view.value
        if not self.name.hasFocus():
            self.name.setText(menu.name)
        everyday = menu.chosen == "everyday"
        self.changes_title.setText(
            _tr("What it changes from the app's defaults")
            if everyday
            else _tr("What it changes from Everyday")
        )
        self.changes.setText(
            "\n".join(f"{title}: {value}" for title, value in menu.changes)
            or _tr("Nothing yet.")
        )
        self.delete.setVisible(menu.chosen_own)
        # a built-in's: its defaults back, once changes are saved in it (587)
        self.reset.setText(style.button_text(restore_defaults(menu.name)))
        self.reset.setVisible(not menu.chosen_own)
        self.reset.setEnabled(menu.restorable)
        self.reset.setToolTip(
            _tr("Back to the app's defaults")
            if everyday
            else _tr("What you saved in it goes; its own settings stay")
        )

    def _renamed(self) -> None:
        name = self.name.text()
        if name != self.view.value.name:
            self.view.rename(self.view.value.chosen, name)
