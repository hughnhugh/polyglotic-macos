"""Settings, in the new main window, at the sidebar's foot with Help: one
page with six sections side by side at its top - **Look · Timing ·
Speech · Dictation · App · Lab** - each named for what a learner comes to
change, the most reached first and the experimental Lab last; nothing
nested, so every setting is one click from the top (the user,
2026-11-13: "Categorise the settings better"; polyglotic-hq 304, which
replaced 248's Captions · Learning · App - Captions had grown to five
windows' height). A caption window's "All caption settings..." opens it
on Look; the tray's "More languages…" on Dictation.

The caption windows' settings are the panels of `ui_next.panels`, bound
to the same views as a transcript's rail, each with a line under its name
where the name isn't enough (248's section 2.4, F18):

- **Look** - how the captions look: the preview, the preset, the colours,
  the panel, the font, what each caption shows; Word links (and the way
  to the Learning page, where which words are new is chosen); Reset;
- **Timing** - when captions come and go: Timing (Steady, Quick preview,
  Live updates and their waits) and Behaviour (how a new caption
  arrives, fading after quiet);
- **Speech** - what's heard: the speakers and the mic (Home's Sound, the
  same view: polyglotic-hq 372), the spoken language, second languages,
  names and slang;
- **Lab** - experimental caption settings, tried by feel (284), last.

**Dictation** - dictation's card (below): a feature of its own, not a
setting of the app (the user's #129, point 11, would give it a page of
its own beside Home; here it's one click away until then).

**App** - things about the app on this PC (project 109's structure,
sections 1.1 and 7; today's page, project 096):

- **Text size:** Smaller, Normal, Larger or Largest - every window of the
  app, at once; the captions keep their own size (polyglotic-hq 292,
  decision 0084). First: it's what a reader who can't read the rest
  comes for;
- **Appearance:** the window's theme (Margin, Glaze or Signal) and light
  or dark - this window and the transcripts; the caption windows stay as
  they are (decision 0029);
- **Language:** the app's own words - like Windows, or one offered - from
  the next start (decision 0034); also under the page's title, in every
  section (284), the same setting;
- **Transcripts:** how far back a transcript window scrolls and searches -
  the newest 1,000 lines (as before), the last 3 hours or the whole
  session; Copy all and Save have the whole session whichever - and
  whether Quit asks to save a long one (334);
- **Hotkeys:** the four, read-only - "another program has it" when one
  couldn't be had;
- **Updates:** Check now; the version and channel; what the last look
  found - up to date, a version ready (with Restart now), the update
  server out of reach, a download that failed (`show_update`;
  polyglotic-hq 299);
- **About:** the machine-translation line, "Want to help build
  Polyglotic? Tell us", the third-party notices.

**Dictation (preview)**: on or off (off until turned on), the key held to
speak - pressed in a box that listens for it, with Reset, refused with
why when it can't be (polyglotic-hq 289, decision 0081) - the language it
hears (Detect or one), Australian spelling (polyglotic-hq 283, decision
0073).

Things about the account live on Account; what's learned, the level and
word introductions on Learning (248's section 3.6), which Look's Word
links points to. The page only shows: `main`
hands over the themes, the hotkeys' commands, "Tell us" and the caption
settings' views, and connects what the page asks for.
"""

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QEvent, QLocale, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.dictation import DICTATION_LANGUAGES
from polyglotic_desktop.core.listening.dictation_keys import (
    DEFAULT_KEY,
    DictationKey,
    refusal,
)
from polyglotic_desktop.ui_next.controls import (
    Card,
    Combo,
    Flow,
    Row,
    Segmented,
    SwitchRow,
    label,
    right_row,
)
from polyglotic_desktop.ui_next.dictation_key import KeyBox, key_words, refusal_words
from polyglotic_desktop.ui_next.home import Page
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.languages import detect_name, dictation_choices
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.panels import (
    BehaviourPanel,
    LanguagesPanel,
    LookPanel,
    ReadingLinesPanel,
    ResetCard,
    TimingPanel,
    WordLinksPanel,
)
from polyglotic_desktop.ui_next.sound_card import SoundCard
from polyglotic_desktop.ui_next.views.panels import LanguagesView, LookView, TimingView
from polyglotic_desktop.ui_next.views.sound import SoundView

SECTIONS = ("look", "timing", "speech", "dictation", "app", "lab")
"""The page's six sections, left to right at its top (304)."""
FORMER = {"captions": "look", "learning": "look"}
"""The sections' names before 304, still taken by `show_section`, so a way
in written for them lands: Captions' first part was Look; Learning only
pointed to the Learning page, as Look's Word links does."""


def _tr(text: str) -> str:
    return QApplication.translate("Settings", text)


def hotkey_name(key: str, action: QAction) -> str:
    """What a hotkey does, in the new interface's words (today's commands
    still say "overlays" until the switch-over); the command's own words
    for any other."""
    names = {
        "L": _tr("Lock all caption windows"),
        "P": _tr("Pause captions"),
        "H": _tr("Hide all caption windows"),
    }
    return names.get(key) or action.text().replace("&", "")


def _button(text: str, name: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class NoticesDialog(QDialog):
    """The third-party notices, read-only (today's dialog)."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NoticesDialog")
        self.setWindowTitle(_tr("Third-party notices"))
        self.resize(640, 520)
        column = QVBoxLayout(self)
        view = QPlainTextEdit(text)
        view.setObjectName("notices.text")
        view.setAccessibleName(_tr("Third-party notices"))
        view.setReadOnly(True)
        column.addWidget(view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        column.addWidget(buttons)


class SettingsPage(Page):
    """Captions, Learning and the app on this PC."""

    learning_wanted = Signal()
    """The Learning page (its section points there)."""
    check_for_updates = Signal()
    restart_wanted = Signal()
    """Updates' Restart now: `main` quits and installs it (299)."""
    theme_chosen = Signal(str)
    """A window theme's key ("margin", "glaze", "signal")."""
    window_theme_chosen = Signal(str)
    """"system", "light" or "dark"."""
    text_size_chosen = Signal(str)
    """The app's own text size: a `style.APP_TEXT_SIZES` key ("larger")."""
    transcript_length_chosen = Signal(str)
    """How far back the transcripts' lists go (`TranscriptLength`'s value)."""
    transcript_ask_chosen = Signal(bool)
    """Whether Quit asks to save a long transcript not saved."""
    interface_language_chosen = Signal(str)
    """An interface language's code ("zh_CN"), or "": like Windows."""
    translation_feedback_wanted = Signal()
    """"Tell us what reads wrong", beside a machine draft's language
    (decision 0087): `main` opens the feedback form."""
    dictation_changes = Signal(dict)
    """Dictation's settings the learner changed, as `AppSettings` names
    them ({"dictation": True}, {"dictation_language": "zh"}...)."""
    dictation_key_wanted = Signal(str)
    """A key the learner pressed for dictation and nothing refuses, as
    `DictationKey` keeps it ("ctrl+alt+d"): `main` tries to take it, and
    keeps the one before if another program has it
    (`dictation_key_not_taken`)."""
    dictation_key_listening = Signal(bool)
    """The key box listens for a key: dictation's own key must let keys
    through meanwhile."""

    def __init__(
        self,
        themes: Sequence[tuple[str, str]],
        hotkeys: Mapping[str, QAction],
        work_with_us: QAction,
        languages: Sequence[tuple[str, str]] = (),
        *,
        look: LookView,
        timing: TimingView,
        speech: LanguagesView,
        sound: SoundView | None = None,
    ) -> None:
        """`themes`: each window theme's key and name; `hotkeys`: today's
        hotkeys' commands, by their letter (Ctrl+Alt+ L, P, H, W);
        `work_with_us`: "Tell us"; `languages`: each interface language's
        code and its own name ("简体中文"); `look`, `timing` and `speech`:
        the caption settings' views (`main`'s `Panels`); `sound`: Home's
        Sound, shown again in Speech (polyglotic-hq 372)."""
        super().__init__(_tr("Settings"))
        self._sound = sound
        self._hotkeys = hotkeys
        self._notices: str | None = None
        self._sheet = ""
        """The main window's stylesheet (`use_sheet`), on the parts shown."""
        # no stylesheet above the parts to paint them the theme's background
        # (`use_sheet`): the window's own shows through, as beside a column
        self.viewport().setAutoFillBackground(False)
        inner = self.widget()
        assert inner is not None
        inner.setAutoFillBackground(False)
        # the title, its sections' switch and the language lines in one part,
        # which takes the window's stylesheet once (`use_sheet`)
        top = QWidget()
        top.setObjectName("settings.top")
        rows = QVBoxLayout(top)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(self.content.spacing())
        self._head(rows)
        self._language_line(rows, languages)
        self.content.insertWidget(0, top)
        self.section: dict[str, QWidget] = {}
        for key in SECTIONS:
            box = QWidget()
            box.setObjectName(f"settings.{key}")
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(16)
            self.section[key] = box
            self.content.addWidget(box)
        self._captions(look, timing, speech)
        self._section_layout("dictation").addWidget(self._dictation())
        app = self._section_layout("app")
        app.addWidget(self._text_size())

        appearance = Card(
            _tr("Appearance"),
            _tr(
                "This window and the transcripts. The caption windows stay as they are."
            ),
        )
        self.theme = Segmented(list(themes))
        self.theme.setObjectName("settings.theme")
        self.theme.changed.connect(lambda v: self.theme_chosen.emit(str(v)))
        appearance.add(Row(_tr("Theme"), _tr("Its colours and headings."), self.theme))
        self.window_theme = Segmented(
            [
                ("system", pc_or_mac(_tr("Like this PC"), _tr("Like this Mac"))),
                ("light", _tr("Light")),
                ("dark", _tr("Dark")),
            ]
        )
        self.window_theme.setObjectName("settings.window_theme")
        self.window_theme.changed.connect(
            lambda v: self.window_theme_chosen.emit(str(v))
        )
        appearance.add(
            Row(
                _tr("Light or dark"),
                _tr("A few parts change at the next start."),
                self.window_theme,
            )
        )
        app.addWidget(appearance)

        language = Card(_tr("Language"))
        # a list, not buttons: every main language (polyglotic-hq 294)
        self.interface_language = Combo()
        self.interface_language.setObjectName("settings.interface_language")
        self.interface_language.setAccessibleName(_tr("The app's language"))
        for code, name in [
            ("", pc_or_mac(_tr("Like this PC"), _tr("Like this Mac"))),
            *languages,
        ]:
            self.interface_language.addItem(name, code)
        # as wide as its longest name, not the card
        self.interface_language.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.interface_language.currentIndexChanged.connect(self._language_chosen)
        language.add(
            Row(
                _tr("The app's language"),
                _tr(
                    "Menus, buttons and help - not your captions. It changes "
                    "the next time Polyglotic starts."
                ),
                self.interface_language,
            )
        )
        app.addWidget(language)
        app.addWidget(self._transcripts())

        keys = Card(
            _tr("Hotkeys"), _tr("They work from any program, including a game.")
        )
        self.hotkey_values: dict[str, QLabel] = {}
        for key, action in hotkeys.items():
            line = QHBoxLayout()
            line.setSpacing(12)
            line.addWidget(label(hotkey_name(key, action), wrap=True), 1)
            value = label("", "Dim")
            line.addWidget(value)
            self.hotkey_values[key] = value
            keys.add(line)
        app.addWidget(keys)

        updates = Card(
            _tr("Updates"),
            _tr("Updates download quietly and apply the next time Polyglotic starts."),
        )
        self.version = label("", "Dim", wrap=True)
        self.version.setHidden(True)
        updates.add(self.version)
        self.update_found = label("", "Dim", wrap=True)
        self.update_found.setObjectName("settings.update_found")
        self.update_found.setHidden(True)
        updates.add(self.update_found)
        self.update_now = _button(_tr("Check now"), "settings.check_updates")
        self.update_now.clicked.connect(self._check_now)
        self.restart_now = _button(_tr("Restart now"), "settings.restart_update")
        self.restart_now.clicked.connect(self.restart_wanted)
        self.restart_now.setHidden(True)
        buttons = right_row(self.update_now)
        buttons.addWidget(self.restart_now)
        updates.add(buttons)
        app.addWidget(updates)

        about = Card(_tr("About Polyglotic"))
        about.add(
            label(
                _tr("Captions and translations are made by machine and can be wrong."),
                "Dim",
                wrap=True,
            )
        )
        self.notices = _button(_tr("Third-party notices"), "settings.notices")
        self.notices.setHidden(True)
        self.notices.clicked.connect(self._show_notices)
        about.add(right_row(self.notices))
        row = Flow(spacing=4)
        row.addWidget(label(_tr("Want to help build Polyglotic?"), "Faint"))
        tell_us = QToolButton()
        tell_us.setDefaultAction(work_with_us)
        tell_us.setProperty("kind", "ghost")
        tell_us.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(tell_us)
        about.add(row)
        app.addWidget(about)
        self.content.addStretch(1)
        self.show_section("look")
        self.refresh()

    # -- text size (polyglotic-hq 292) -------------------------------------------------

    def _text_size(self) -> Card:
        """The app's own text size: four steps, applied at once. A choice
        goes out as `text_size_chosen`."""
        card = Card(
            _tr("Text size"),
            _tr(
                "Polyglotic's own words: this window, a word's card, menus, and"
                " the buttons on caption windows and transcripts. Captions keep"
                " their own size: A- and A+ on each caption window and transcript."
            ),
        )
        self.text_size = Segmented(
            [
                ("smaller", _tr("Smaller")),
                ("normal", _tr("Normal")),
                ("larger", _tr("Larger")),
                ("largest", _tr("Largest")),
            ],
            "normal",
        )
        self.text_size.setObjectName("settings.text_size")
        self.text_size.setAccessibleName(_tr("Text size"))
        self.text_size.changed.connect(lambda v: self.text_size_chosen.emit(str(v)))
        card.add(self.text_size)
        return card

    def show_text_size(self, size: str) -> None:
        """The app's text size as the settings have it ("normal")."""
        self.text_size.set_value(size)

    # -- transcripts (polyglotic-hq 334) ----------------------------------------------

    def _transcripts(self) -> Card:
        """How far back each transcript window's list goes: the newest
        1,000 lines (as before), the last three hours or the whole session.
        A choice goes out as `transcript_length_chosen`."""
        card = Card(
            _tr("Transcripts"),
            _tr(
                "How far back a transcript window scrolls and searches. Copy all"
                " and Save always have the whole session."
            ),
        )
        #: {count} is always 1,000
        newest = _tr("Newest {count} lines").format(count=QLocale().toString(1000))
        self.transcript_length = Segmented(
            [
                ("newest", newest),
                ("three_hours", _tr("Last 3 hours")),
                ("session", _tr("Whole session")),
            ],
            "newest",
        )
        self.transcript_length.setObjectName("settings.transcript_length")
        self.transcript_length.setAccessibleName(_tr("How far back transcripts go"))
        self.transcript_length.changed.connect(
            lambda v: self.transcript_length_chosen.emit(str(v))
        )
        card.add(self.transcript_length)
        self.transcript_ask = SwitchRow(
            _tr("Ask to save before quitting"),
            _tr(
                "With Last 3 hours or Whole session: Quit asks about a transcript"
                " of more than 300 lines that isn't saved."
            ),
            "settings.transcript_ask",
        )
        self.transcript_ask.switch.set_quietly(True)
        self.transcript_ask.switch.toggled.connect(self.transcript_ask_chosen)
        card.add(self.transcript_ask)
        return card

    def show_transcript_length(self, length: str, ask: bool = True) -> None:
        """How far back the transcripts go, and whether Quit asks to save
        one, as the settings have them."""
        self.transcript_length.set_value(length)
        self.transcript_ask.switch.set_quietly(ask)

    # -- dictation (polyglotic-hq 283) -------------------------------------------------

    def _dictation(self) -> Card:
        """Dictation's card: on or off, its key, the language it hears, and
        Australian spelling. A change goes out as `dictation_changes`; a
        key pressed, as `dictation_key_wanted`."""
        self._key_taken_shown = False
        card = Card(
            _tr("Dictation (preview)"),
            _tr(
                "Hold a key and speak; let go, and your words are typed where your"
                " cursor is, in any program. Your voice goes to our server only"
                " while you hold the key, and nothing is kept."
            ),
        )
        self.dictation_on = SwitchRow(
            _tr("Dictation"), self._hold_words(str(DEFAULT_KEY)), "settings.dictation"
        )
        self.dictation_on.switch.toggled.connect(
            lambda on: self.dictation_changes.emit({"dictation": on})
        )
        card.add(self.dictation_on)
        # the key: press the one you want (polyglotic-hq 289, decision 0081)
        self.dictation_key = KeyBox(str(DEFAULT_KEY))
        self.dictation_key.pressed_key.connect(self._dictation_key_pressed)
        self.dictation_key.listening_changed.connect(self.dictation_key_listening)
        self.dictation_key_reset = _button(_tr("Reset"), "settings.dictation_key_reset")
        self.dictation_key_reset.setToolTip(
            _tr("Back to {key}").format(key=key_words(DEFAULT_KEY))
        )
        self.dictation_key_reset.clicked.connect(
            lambda: self._dictation_key_pressed(str(DEFAULT_KEY))
        )
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self.dictation_key, 1)
        key_row.addWidget(self.dictation_key_reset)
        key_box = QWidget()
        key_box.setLayout(key_row)
        key_row.setContentsMargins(0, 0, 0, 0)
        card.add(
            Row(
                _tr("Key"),
                _tr(
                    "Click, then press the key or combination you want to hold:"
                    " Right Ctrl, F9, Ctrl + Alt + D… A key on its own, or with"
                    " Ctrl, Alt or Win, is Polyglotic's while dictation is on;"
                    " Right Ctrl alone still works in other programs."
                ),
                key_box,
            )
        )
        self.dictation_key_note = label("", "Faint", wrap=True)
        self.dictation_key_note.setObjectName("settings.dictation_key_note")
        card.add(self.dictation_key_note)
        self.dictation_key_note.hide()  # after its parent: never a window of its own
        self.dictation_language = Combo()
        self.dictation_language.setObjectName("settings.dictation_language")
        self.dictation_language.setAccessibleName(_tr("Dictation's language"))
        # Detect, said as every spoken-language list says it (317)
        self.dictation_language.addItem(detect_name(), "")
        for code, name in dictation_choices(DICTATION_LANGUAGES):
            self.dictation_language.addItem(name, code)
        self.dictation_language.activated.connect(
            lambda _i: self.dictation_changes.emit(
                {"dictation_language": self.dictation_language.currentData() or None}
            )
        )
        card.add(
            Row(
                _tr("Language"),
                _tr(
                    "Detect types whatever language you speak, each time you hold"
                    " the key. Set one - English, Mandarin… - and it's always"
                    " heard as that: a short phrase is never taken for another."
                    " The tray's menu switches it too."
                ),
                self.dictation_language,
            )
        )
        self.dictation_australian = SwitchRow(
            _tr("Australian spelling"),
            _tr("English comes out as colour, centre and organise."),
            "settings.dictation_australian",
        )
        self.dictation_australian.switch.toggled.connect(
            lambda on: self.dictation_changes.emit({"dictation_australian": on})
        )
        card.add(self.dictation_australian)
        return card

    def show_dictation(
        self,
        on: bool,
        key: str,
        language: str | None,
        australian: bool,
        taken: bool = False,
    ) -> None:
        """Dictation's settings as they are now (changed here or in the
        tray); `taken`: another program has the key."""
        self.dictation_on.switch.set_quietly(on)
        self.dictation_australian.switch.set_quietly(australian)
        index = self.dictation_language.findData(language or "")
        if index >= 0 and index != self.dictation_language.currentIndex():
            blocked = self.dictation_language.blockSignals(True)
            self.dictation_language.setCurrentIndex(index)
            self.dictation_language.blockSignals(blocked)
        self.dictation_key.show_key(key)
        self.dictation_on.detail.setText(self._hold_words(key))
        self.dictation_key_reset.setEnabled(key != str(DEFAULT_KEY))
        if on and taken:
            self._dictation_note(
                _tr("Another program has {key}: choose another.").format(
                    key=key_words(key)
                )
            )
        elif self._key_taken_shown:
            self._dictation_note("")
        self._key_taken_shown = on and taken

    def dictation_key_not_taken(self, wanted: str) -> None:
        """Another program has the key the learner pressed: the one before
        is kept."""
        self._dictation_note(
            _tr("Another program has {key}: kept {kept}.").format(
                key=key_words(wanted), kept=key_words(self.dictation_key.key)
            )
        )

    def _dictation_key_pressed(self, pressed: str) -> None:
        """A key pressed in the box (or Reset): refused with why, or asked
        for (`dictation_key_wanted`) - unless it's the key already."""
        key = DictationKey.parse(pressed) if pressed else None
        own = (DictationKey.parse(f"ctrl+alt+{k.lower()}") for k in self._hotkeys)
        refused = refusal(key, [k for k in own if k]) if key else None
        if key is None or refused is not None:
            self._dictation_note(refusal_words(refused))
            return
        self._dictation_note("")
        if pressed != self.dictation_key.key:
            self.dictation_key_wanted.emit(pressed)

    def _dictation_note(self, text: str) -> None:
        self.dictation_key_note.setText(text)
        self.dictation_key_note.setHidden(not text)

    @staticmethod
    def _hold_words(key: str) -> str:
        return _tr("Hold {key} and speak; let go, and it's typed.").format(
            key=key_words(key)
        )

    # -- the sections ------------------------------------------------------------------

    def _head(self, rows: QVBoxLayout) -> None:
        """The title, with the sections' switch at its right."""
        title = self.content.takeAt(0)
        assert title is not None
        heading = title.widget()
        assert heading is not None
        head = Flow(spacing=16)  # the sections under it when they don't fit
        head.addWidget(heading)
        self.sections = Segmented(
            [
                ("look", _tr("Look")),
                ("timing", _tr("Timing")),
                ("speech", _tr("Speech")),
                ("dictation", _tr("Dictation")),
                ("app", _tr("App")),
                ("lab", _tr("Lab")),
            ],
            "look",
        )
        self.sections.setObjectName("settings.sections")
        self.sections.setAccessibleName(_tr("Settings sections"))
        self.sections.changed.connect(lambda key: self.show_section(str(key)))
        head.addWidget(self.sections)
        rows.addLayout(head)

    def _language_line(
        self, rows: QVBoxLayout, languages: Sequence[tuple[str, str]]
    ) -> None:
        """The app's language under the title, in every section - not only
        at App's foot (the user's live testing, polyglotic-hq 270: "App
        language should also be more obvious rather than hid in 2 layers";
        284). The same setting as App's Language; each language by its own
        name, so it's found whatever language the app is in now."""
        line = Flow()
        line.addWidget(label(_tr("App language"), "Dim"))
        self.language_picker = Combo()
        self.language_picker.setObjectName("settings.language_picker")
        self.language_picker.setAccessibleName(_tr("The app's language"))
        self.language_picker.setToolTip(
            _tr(
                "Menus, buttons and help - not your captions. It changes the "
                "next time Polyglotic starts."
            )
        )
        for code, name in [
            ("", pc_or_mac(_tr("Like this PC"), _tr("Like this Mac"))),
            *languages,
        ]:
            self.language_picker.addItem(name, code)
        # connected once filled: adding the first item would pick it
        self.language_picker.currentIndexChanged.connect(self._language_picked)
        line.addWidget(self.language_picker)
        self.language_later = label(_tr("From the next start"), "Faint")
        self.language_later.setObjectName("settings.language_later")
        self.language_later.setHidden(True)
        line.addWidget(self.language_later)
        rows.addLayout(line)
        # a machine draft says so, and asks (decision 0087; `show_draft`) - on
        # a line of its own, so a long language's words fit at the Largest
        # text size beside the picker's (polyglotic-hq 294)
        draft = Flow()
        self.language_draft = label(_tr("Machine draft"), "Faint")
        self.language_draft.setObjectName("settings.language_draft")
        self.language_draft.setToolTip(
            _tr("No native speaker has checked the app's text in this language yet.")
        )
        draft.addWidget(self.language_draft)
        self.language_wrong = QToolButton()
        self.language_wrong.setObjectName("settings.language_wrong")
        self.language_wrong.setText(_tr("Tell us what reads wrong"))
        self.language_wrong.setProperty("kind", "ghost")
        self.language_wrong.setCursor(Qt.CursorShape.PointingHandCursor)
        self.language_wrong.clicked.connect(self.translation_feedback_wanted)
        draft.addWidget(self.language_wrong)
        self.show_draft(False)
        rows.addLayout(draft)

    def show_draft(self, draft: bool) -> None:
        """Whether the app's text is a machine draft in the language it's
        in now (`ui.interface_language.DRAFTS`): if so, the line under the
        title says so, with "Tell us what reads wrong"."""
        self.language_draft.setHidden(not draft)
        self.language_wrong.setHidden(not draft)

    def _language_picked(self, index: int) -> None:
        code = str(self.language_picker.itemData(index) or "")
        self._show_chosen(self.interface_language, code)
        self.language_later.setHidden(False)
        self.interface_language_chosen.emit(code)

    def _section_layout(self, key: str) -> QVBoxLayout:
        column = self.section[key].layout()
        assert isinstance(column, QVBoxLayout)
        return column

    def _captions(
        self, look: LookView, timing: TimingView, speech: LanguagesView
    ) -> None:
        """Every caption window's settings, in 248's order (section 2.2),
        each group in the section a learner comes to it for (304)."""
        self.look = LookPanel(look, notes=True, preview=True, languages=speech)
        self.word_links = WordLinksPanel(look, notes=True, learning=True)
        self.word_links.learning_wanted.connect(self.learning_wanted)
        self.reading = ReadingLinesPanel(look, notes=True)
        self.timing = TimingPanel(timing, languages=speech)
        self.behaviour = BehaviourPanel(look, notes=True, hidden_windows=True)
        # Spoken language here sets every window's own, and the second
        # languages are the ones each window's "Lines already in ..." sets
        # (248's F28; polyglotic-hq 263: each caption window has its own)
        self.speech = LanguagesPanel(speech, speech=True)
        self.sound = SoundCard(self._sound) if self._sound is not None else None
        self.reset = ResetCard(look)  # the look's: Look's last
        # experimental: a section of its own, last (284)
        self.lab = LabPanel(look, languages=speech)
        placed: dict[str, tuple[QWidget, ...]] = {
            "look": (self.look, self.word_links, self.reading, self.reset),
            "timing": (self.timing, self.behaviour),
            # the speakers and the mic first, as Home's Sound (372): one view
            "speech": (
                (self.sound, self.speech) if self.sound is not None else (self.speech,)
            ),
            "lab": (self.lab,),
        }
        for key, panels in placed.items():
            column = self._section_layout(key)
            for panel in panels:
                column.addWidget(panel)

    def show_section(self, key: str) -> None:
        """Section `key` (one of `SECTIONS`, or a former name: `FORMER`),
        at the top."""
        key = FORMER.get(key, key)
        if key not in self.section:
            raise ValueError(key)
        self.sections.set_value(key)
        self._styled(self.section[key])  # before it's shown: polished once
        for each, box in self.section.items():
            box.setVisible(each == key)
        self.verticalScrollBar().setValue(0)

    # -- the window's stylesheet (decision 0152) -----------------------------------

    def use_sheet(self, sheet: str) -> None:
        """The main window's stylesheet (`main_window.InParts`) on the page's
        parts - its head, its scroll bars and the section on show - not on
        the page: Qt restyles every widget under a changed stylesheet, shown
        or not, and the six sections are 481 widgets, one section on show
        (polyglotic-hq 355, 360; decision 0152). Another section gets it
        when shown. The page and its column paint nothing of their own: the
        window paints the background beneath them."""
        if sheet == self._sheet:
            return
        self._sheet = sheet
        sections = set(self.section.values())
        column = self.content.parentWidget()
        assert column is not None
        parts = [
            *(w for w in self.children() if w is not self.viewport()),
            *(w for w in column.children() if w not in sections),
            *(box for box in sections if not box.isHidden()),
        ]
        for part in parts:
            if isinstance(part, QWidget):
                self._styled(part)
        # what a stylesheet on the page told it, and nothing now does: its
        # parts' sizes changed - its column's width (`Page`) and its scroll
        # range (Qt's scroll area). Posted, so it comes once the page is
        # shown, at its width: sent at once, the first frame laid Look out
        # at the hidden page's size, squashed, and nothing scrolled
        QApplication.postEvent(self, QEvent(QEvent.Type.StyleChange))

    def _styled(self, part: QWidget) -> None:
        if self._sheet and part.styleSheet() != self._sheet:
            part.setStyleSheet(self._sheet)

    def show_theme(self, theme: str, window_theme: str) -> None:
        """The theme and light or dark as the settings have them now."""
        self.theme.set_value(theme)
        self.window_theme.set_value(window_theme)

    def _language_chosen(self, index: int) -> None:
        """App's Language: the picker under the title shows it too."""
        code = str(self.interface_language.itemData(index) or "")
        self._show_chosen(self.language_picker, code)
        self.language_later.setHidden(False)
        self.interface_language_chosen.emit(code)

    @staticmethod
    def _show_chosen(picker: QComboBox, code: str) -> None:
        index = max(0, picker.findData(code))
        blocked = picker.blockSignals(True)
        picker.setCurrentIndex(index)
        picker.blockSignals(blocked)

    def show_interface_language(self, code: str) -> None:
        """The interface language as the settings have it ("": like Windows)."""
        self._show_chosen(self.interface_language, code)
        self._show_chosen(self.language_picker, code)

    def showEvent(self, event: QShowEvent) -> None:
        self.refresh()  # a hotkey another program had is shown as not available
        super().showEvent(event)

    def refresh(self) -> None:
        """Each hotkey as Windows writes it in the app's language - "Strg+Alt+L"
        in German, as Home and the dictation card have it (polyglotic-hq 300)."""
        native = QKeySequence.SequenceFormat.NativeText
        for key, value in self.hotkey_values.items():
            shortcut = self._hotkeys[key].shortcut().toString(native)
            value.setText(shortcut or _tr("another program has it"))

    def set_version(self, version: str, channel: str, store: bool = False) -> None:
        """This copy's version and update channel - or, for the Microsoft
        Store's copy, that the Store keeps it up to date (decision 0056):
        then there's nothing for Check now to look for."""
        text = (
            _tr(
                "Version {version}, from the Microsoft Store, which keeps it up to "
                "date."
            )
            if store
            else _tr("Version {version} ({channel}).")
        )
        self.version.setText(text.format(version=version, channel=channel))
        self.version.setHidden(False)
        self.update_now.setHidden(store)

    def _check_now(self) -> None:
        self.update_found.setText(_tr("Checking for updates…"))
        self.update_found.setHidden(False)
        self.check_for_updates.emit()

    def show_update(self, found: str, version: str | None = None) -> None:
        """What the last look for an update found (`core.releases.updates.
        Found`'s value) and, when one is ready, its version - with Restart
        now (polyglotic-hq 299)."""
        texts = {
            "up_to_date": _tr("Polyglotic is up to date."),
            "ready": _tr("Version {version} is ready. Restart to install it."),
            "no_feed": _tr(
                "Couldn't reach the update server. Polyglotic looks again later."
            ),
            "not_downloaded": _tr(
                "The update couldn't be downloaded. Polyglotic tries again later."
            ),
            "metered": _tr(
                "Version {version} is available. Your connection is metered, so "
                "it waits: Home offers to download it anyway."
            ),
            "not_installed": _tr(
                "This copy wasn't installed by the installer, so it can't update "
                "itself."
            ),
        }
        text = texts.get(found, "").format(version=version or "")
        self.update_found.setText(text)
        self.update_found.setHidden(not text)
        self.restart_now.setHidden(found != "ready" or version is None)

    def set_notices(self, text: str | None) -> None:
        """The third-party notices' text, or None if this copy has none."""
        self._notices = text
        self.notices.setHidden(not text)

    def _show_notices(self) -> None:
        if self._notices:
            dialog = NoticesDialog(self._notices, self)
            self._styled(dialog)  # the page has no stylesheet of its own
            dialog.exec()
