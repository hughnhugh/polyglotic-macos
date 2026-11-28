"""Settings, in the new main window, at the sidebar's foot with Help: one
page with eight sections side by side at its top - **Look · Word links ·
Readings · Timing · Speech · Dictation · App · Lab** - each named for what
a learner comes to change, the most reached first and the experimental Lab
last; nothing nested, so every setting is one click from the top (the
user, 2026-11-13: "Categorise the settings better"; polyglotic-hq 304,
which replaced 248's Captions · Learning · App - Captions had grown to five
windows' height). A caption window's "All caption settings..." opens it
on Look; the tray's "More languages…" on Dictation.

**Settings you can scan** (polyglotic-hq 470, 449's design 4A; the user,
2026-11-17: "make each setting category very obvious as you scroll the
page"): each section's tab has its mark beside its name; the title and
the tabs stay pinned at the top while the page scrolls, and under them the
name of the card the learner is in, once its own title has scrolled away;
each card's title is a size up, its mark in a soft square at its left
(`settings_marks`). Where the tabs don't fit on one line - a narrow window,
a large text size - they're a dropdown (449's finding 8: eight tabs
wrapped to four rows). Look was 2,557 px with no landmark: Word links and
Readings are sections of their own now.

The caption windows' settings are the panels of `ui_next.panels`, bound
to the same views as a transcript's rail, each with a line under its name
where the name isn't enough (248's section 2.4, F18):

- **Look** - how the captions look: the preview, the preset, the colours,
  the panel, the font, what each caption shows; Reset;
- **Word links** - their style, and the way to the Learning page, where
  which words are new is chosen;
- **Readings** - pinyin above Chinese, Jyutping above Cantonese (369,
  450): their size, words and colour;
- **Timing** - when captions come and go: Timing (Steady, Quick preview,
  Live updates and their waits) and Behaviour (how a new caption
  arrives, fading after quiet);
- **Speech** - what's heard: the speakers and the mic (Home's Sound, the
  same view: polyglotic-hq 372), the spoken language, second languages,
  names and slang;
- **Lab** - experimental caption settings, tried by feel (284), last.

Each of these six sections' cards is made the first time it's shown (or a
card of it is asked for), not with the page: the start makes the page
unseen, and they were about 39 ms of it (polyglotic-hq 544).

**Dictation** - dictation's card (below): a feature of its own, not a
setting of the app (the user's #129, point 11, would give it a page of
its own beside Home; here it's one click away until then).

**App** - things about the app on this PC (project 109's structure,
sections 1.1 and 7; today's page, project 096):

- **Text size:** Smaller, Normal, Larger or Largest - every window of the
  app, at once; the captions keep their own size (polyglotic-hq 292,
  decision 0084; Normal larger since 0244). First: it's what a reader who can't read the rest
  comes for;
- **Appearance:** the window's theme (Margin, Glaze or Signal) and light
  or dark - this window and the transcripts; the caption windows stay as
  they are (decision 0029);
  The app's language - like Windows, or one offered, from the next start
  (decision 0034) - is the line under the page's title, in every section
  (284); App's own Language card, the same setting a second time, went
  (polyglotic-hq 449's finding 9, 470);
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

from collections.abc import Callable, Collection, Mapping, Sequence

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QListView,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.dictation import DICTATION_LANGUAGES
from polyglotic_desktop.core.listening.dictation_keys import (
    DEFAULT_KEY,
    DictationKey,
    refusal,
)
from polyglotic_desktop.core.listening.hotkeys import (
    DICTATE,
    RESPEAK,
    HotkeyScope,
    default_scope,
)
from polyglotic_desktop.ui_next import glyphs, style
from polyglotic_desktop.ui_next.controls import (
    Card,
    Combo,
    FittingCombo,
    Flow,
    Row,
    Segmented,
    SwitchRow,
    label,
    right_row,
)
from polyglotic_desktop.ui_next.dictation_key import KeyBox, key_words, refusal_words
from polyglotic_desktop.ui_next.face_rows import FacesPanel
from polyglotic_desktop.ui_next.glyphs import Glyph
from polyglotic_desktop.ui_next.home import (
    MARGIN,
    Page,
    not_writable_notice,
    open_folder_label,
    quit_now_label,
    update_ready_linux,
)
from polyglotic_desktop.ui_next.hotkeys_card import (
    DictationForOthersCard,
    HoldKeysCard,
    HotkeysCard,
    WindowKeysCard,
)
from polyglotic_desktop.ui_next.lab_panel import LabPanel
from polyglotic_desktop.ui_next.languages import (
    detect_name,
    dictation_choices,
    language_name,
)
from polyglotic_desktop.ui_next.os_words import on_linux, pc_or_mac
from polyglotic_desktop.ui_next.panels import (
    BehaviourPanel,
    LanguagesPanel,
    LookPanel,
    QuietViewPanel,
    ReadingLinesPanel,
    ResetCard,
    TimingPanel,
    WordLinksPanel,
)
from polyglotic_desktop.ui_next.presets_card import (
    PresetLine,
    PresetPanel,
    PresetsPanel,
)
from polyglotic_desktop.ui_next.settings_marks import PinnedCard, mark_card
from polyglotic_desktop.ui_next.settings_popover import SizeSlider, size_badge
from polyglotic_desktop.ui_next.sound_card import SoundCard
from polyglotic_desktop.ui_next.views.caption_window import (
    FINE_STEP,
    TRANSLATION_SIZES,
    stepped,
    stepped_translation,
)
from polyglotic_desktop.ui_next.views.captions import (
    CAPTION_TEXT_SIZES,
    TRANSCRIPT_LINES,
)
from polyglotic_desktop.ui_next.views.panels import (
    DownloadsView,
    JapaneseReadingsView,
    LanguagesView,
    LookView,
    TimingView,
)
from polyglotic_desktop.ui_next.views.preset_menu import PresetsView
from polyglotic_desktop.ui_next.views.sound import SoundView
from polyglotic_desktop.ui_next.views.transcript import ASK_FROM_LINES, TRANSCRIPT_HOURS

SECTIONS = (
    "presets",
    "look",
    "links",
    "readings",
    "timing",
    "speech",
    "dictation",
    "hotkeys",
    "app",
    "lab",
)

"""The page's ten sections, left to right at its top (304; Word links
and Readings out of Look, 470; Presets first, polyglotic-hq 556: the
caption settings' top, where a caption window's "Customise presets…"
lands; Hotkeys after Dictation, 567)."""
MARKS = {
    "presets": Glyph.FILL,
    "look": Glyph.LOOK,
    "links": Glyph.LINKS,
    "readings": Glyph.READINGS,
    "timing": Glyph.TIMING,
    "speech": Glyph.SPEECH,
    "dictation": Glyph.MIC,
    "hotkeys": Glyph.KEYS,
    "app": Glyph.APP,
    "lab": Glyph.LAB,
}
"""Each section's mark, beside its name on its tab (470)."""
CAPTION_CARDS = {
    "presets": ("presets", "preset"),
    "look": ("look", "faces", "reset"),
    "links": ("word_links", "quiet"),
    "readings": ("reading",),
    "timing": ("timing", "behaviour"),
    "speech": ("sound", "speech"),
    "lab": ("lab",),
}
"""The caption windows' sections and their cards, as the page names them:
each section's made the first time it's shown, or one of its cards asked
for (`SettingsPage._make`, polyglotic-hq 544)."""
"""The sections that hold a preset's settings, where the preset line shows
(polyglotic-hq 587): not Speech, Dictation, Hotkeys, App or the Lab, whose
settings are the same in every preset."""
FORMER = {"captions": "look", "learning": "links"}
"""The sections' names before 304, still taken by `show_section`, so a way
in written for them lands: Captions' first part was Look; Learning only
pointed to the Learning page, as Word links does."""
TAB = 16
"""A section's mark on its tab, at 100 % text size."""
PINNED_GAP = 16
"""Between the pinned title and sections and what scrolls under them: the
column's spacing."""


def _tr(text: str) -> str:
    return QApplication.translate("Settings", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("Settings", text, None, n)


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


class TranslationSizeCard(Card):
    """Look's independent Caption size and Translation size controls
    (polyglotic-hq 655): each with A-, a 5 % slider (60 to 400 %) and A+,
    a percentage readout, and a small Match button that sets translation
    equal to caption without touching caption size."""

    caption_chosen = Signal(float)
    chosen = Signal(float)

    def __init__(
        self,
        size: float = 1.0,
        caption_size: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            _tr("Caption text size"),
            _tr("In every language: each script is sized to match."),
            parent,
        )
        self._caption_size = caption_size
        self._translation_size = size

        cap_header = QHBoxLayout()
        cap_header.setContentsMargins(0, 0, 0, 0)
        cap_header.setSpacing(8)  # constant: header spacing matching Card rows
        self.caption_name = label(_tr("Caption size"))
        cap_header.addWidget(self.caption_name)
        self.caption_shown = label("", "Dim")
        cap_header.addWidget(self.caption_shown)
        cap_header.addStretch(1)
        self.add(cap_header)

        cap_line = QHBoxLayout()
        cap_line.setContentsMargins(0, 0, 0, 0)
        cap_line.setSpacing(6)  # constant: matches popover size row spacing
        self.caption_smaller = QPushButton("A-")
        self.caption_smaller.setObjectName("settings.caption_size_smaller")
        self.caption_smaller.setAccessibleName(_tr("Smaller caption size"))
        self.caption_smaller.setCursor(Qt.CursorShape.PointingHandCursor)
        self.caption_slider = SizeSlider(*CAPTION_TEXT_SIZES, FINE_STEP, self)
        self.caption_slider.setObjectName("settings.caption_size")
        self.caption_slider.setAccessibleName(_tr("Caption size"))
        self.caption_slider.setMinimumWidth(160)  # constant: matches Look slider floor
        self.caption_bigger = QPushButton("A+")
        self.caption_bigger.setObjectName("settings.caption_size_bigger")
        self.caption_bigger.setAccessibleName(_tr("Bigger caption size"))
        self.caption_bigger.setCursor(Qt.CursorShape.PointingHandCursor)
        cap_line.addWidget(self.caption_smaller)
        cap_line.addWidget(self.caption_slider, 1)
        cap_line.addWidget(self.caption_bigger)
        self.add(cap_line)

        trans_header = QHBoxLayout()
        trans_header.setContentsMargins(
            0, 4, 0, 0
        )  # constant: slight visual split between the two rows
        trans_header.setSpacing(8)  # constant: header spacing matching Card rows
        self.translation_name = label(_tr("Translation size"))
        trans_header.addWidget(self.translation_name)
        self.shown = label("", "Dim")
        trans_header.addWidget(self.shown)
        trans_header.addStretch(1)
        self.same = QPushButton(_tr("Match"))
        self.same.setObjectName("settings.translation_same")
        self.same.setAccessibleName(_tr("Match translation size to caption size"))
        self.same.setToolTip(_tr("Set the translation size equal to the caption size"))
        self.same.setCursor(Qt.CursorShape.PointingHandCursor)
        trans_header.addWidget(self.same)
        self.add(trans_header)

        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)  # constant: matches popover size row spacing
        self.translation_smaller = QPushButton("A-")
        self.translation_smaller.setObjectName("settings.translation_size_smaller")
        self.translation_smaller.setAccessibleName(_tr("Smaller translation size"))
        self.translation_smaller.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider = SizeSlider(*TRANSLATION_SIZES, FINE_STEP, self)
        self.slider.setObjectName("settings.translation_size")
        self.slider.setAccessibleName(_tr("Translation size"))
        self.slider.setMinimumWidth(160)  # constant: matches Look slider floor
        self.translation_bigger = QPushButton("A+")
        self.translation_bigger.setObjectName("settings.translation_size_bigger")
        self.translation_bigger.setAccessibleName(_tr("Bigger translation size"))
        self.translation_bigger.setCursor(Qt.CursorShape.PointingHandCursor)
        line.addWidget(self.translation_smaller)
        line.addWidget(self.slider, 1)
        line.addWidget(self.translation_bigger)
        self.add(line)

        self.caption_slider.valueChanged.connect(self._caption_moved)
        self.caption_smaller.clicked.connect(lambda: self._step_caption(-1))
        self.caption_bigger.clicked.connect(lambda: self._step_caption(1))
        self.slider.valueChanged.connect(self._moved)
        self.translation_smaller.clicked.connect(lambda: self._step_translation(-1))
        self.translation_bigger.clicked.connect(lambda: self._step_translation(1))
        self.same.clicked.connect(self._match)
        self.show_sizes(caption_size, size)

    def _caption_moved(self, _value: int) -> None:
        size = self.caption_slider.chosen()
        self.show_caption_size(size)
        self.caption_chosen.emit(size)

    def _step_caption(self, steps: int) -> None:
        size = stepped(self._caption_size, steps, CAPTION_TEXT_SIZES)
        self.show_caption_size(size)
        self.caption_chosen.emit(size)

    def _moved(self, _value: int) -> None:
        size = self.slider.chosen()
        self.show_size(size)
        self.chosen.emit(size)

    def _step_translation(self, steps: int) -> None:
        size = stepped_translation(self._translation_size, steps)
        self.show_size(size)
        self.chosen.emit(size)

    def _match(self) -> None:
        size = self._caption_size
        self.show_size(size)
        self.chosen.emit(size)

    def show_caption_size(self, size: float) -> None:
        low, high = CAPTION_TEXT_SIZES
        self._caption_size = round(min(high, max(low, size)), 2)
        self.caption_slider.show_size(self._caption_size)
        self._refresh_labels()

    def show_size(self, size: float) -> None:
        low, high = TRANSLATION_SIZES
        self._translation_size = round(min(high, max(low, size)), 2)
        self.slider.show_size(self._translation_size)
        self._refresh_labels()

    def show_sizes(self, caption: float, translation: float) -> None:
        low, high = CAPTION_TEXT_SIZES
        self._caption_size = round(min(high, max(low, caption)), 2)
        self.caption_slider.show_size(self._caption_size)
        t_low, t_high = TRANSLATION_SIZES
        self._translation_size = round(min(t_high, max(t_low, translation)), 2)
        self.slider.show_size(self._translation_size)
        self._refresh_labels()

    def show_languages(self, sizes: tuple[tuple[Language, float], ...]) -> None:
        if self.subtitle is not None:
            self.subtitle.setText(
                _tr("Text sizes are saved by language on this device.")
            )
        self.same.hide()
        rows = (
            (
                self.caption_name,
                self.caption_shown,
                self.caption_slider,
                self.caption_smaller,
                self.caption_bigger,
            ),
            (
                self.translation_name,
                self.shown,
                self.slider,
                self.translation_smaller,
                self.translation_bigger,
            ),
        )
        for index, (name, badge, slider, smaller, bigger) in enumerate(rows):
            visible = index < len(sizes)
            for widget in (name, badge, slider, smaller, bigger):
                widget.setVisible(visible)
            if visible:
                code, size = sizes[index]
                title = language_name(code)
                name.setText(title)
                slider.setAccessibleName(title)
                if index == 0:
                    self.show_caption_size(size)
                else:
                    self.show_size(size)
        self.setVisible(bool(sizes))

    def _refresh_labels(self) -> None:
        self.caption_shown.setText(size_badge(self._caption_size))
        self.shown.setText(size_badge(self._translation_size))
        cap_low, cap_high = CAPTION_TEXT_SIZES
        self.caption_smaller.setEnabled(self._caption_size > cap_low)
        self.caption_bigger.setEnabled(self._caption_size < cap_high)
        t_low, t_high = TRANSLATION_SIZES
        self.translation_smaller.setEnabled(self._translation_size > t_low)
        self.translation_bigger.setEnabled(self._translation_size < t_high)
        self.same.setEnabled(self._translation_size != self._caption_size)


class SettingsPage(Page):
    """Captions, Learning and the app on this PC."""

    learning_wanted = Signal()
    """The Learning page (its section points there)."""
    lab_load_wanted = Signal()
    """Lab's "Open it on Learning" (its card's `load_wanted`), passed on:
    the card is made when Lab is first shown (`CAPTION_CARDS`)."""
    check_for_updates = Signal()
    restart_wanted = Signal()
    """Updates' Restart now (or Quit now on Linux): `main` quits and installs
    it (299, 640)."""
    open_app_folder_wanted = Signal()
    """Updates' Open folder when the app's folder isn't writable (640)."""
    theme_chosen = Signal(str)
    """A window theme's key ("margin", "glaze", "signal")."""
    window_theme_chosen = Signal(str)
    """"system", "light" or "dark"."""
    text_size_chosen = Signal(str)
    caption_size_chosen = Signal(float)
    """Look's caption size: independent of translation size (polyglotic-hq 655)."""
    translation_size_chosen = Signal(float)
    """Look's translation size: independent of caption size (polyglotic-hq 655)."""
    """The app's own text size: a `style.APP_TEXT_SIZES` key ("larger")."""
    transcript_length_chosen = Signal(str)
    """How far back the transcripts' lists go (`TranscriptLength`'s value)."""
    transcript_ask_chosen = Signal(bool)
    """Whether Quit asks to save a long transcript not saved."""
    start_at_sign_in_chosen = Signal(bool)
    """Start at sign-in turned on or off (polyglotic-hq 571): `main` writes
    it where the OS keeps it."""
    interface_language_chosen = Signal(str)
    """An interface language's code ("zh_CN"), or "": like Windows."""
    language_restart_wanted = Signal()
    """App language's Restart now: `main` quits and relaunches into the
    chosen interface language (polyglotic-hq 658)."""
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
    hotkey_wanted = Signal(str, str)
    """A hotkey's name and the key the learner gave it, as kept ("" for
    none): one nothing refuses (`HotkeysCard`, polyglotic-hq 567)."""
    hotkey_scope_wanted = Signal(str, str)
    """A hotkey's name and its chosen scope ("app" or "everywhere"; 966)."""
    respeak_changes = Signal(dict)
    """Speaker typing settings the learner changed ({"type_theirs": False},
    {"respeak_key": ""}: Settings > Dictation, polyglotic-hq 626)."""
    respeak_key_wanted = Signal(str)
    """A key pressed for re-speaking's own that nothing refuses, as kept:
    `main` tries to take it (`respeak_key_not_taken`)."""
    hotkeys_reset = Signal()
    """Reset all: every hotkey's key its default."""
    hotkey_listening = Signal(bool)
    """A hotkey's key box listens: the app's hotkeys and dictation's key
    must let keys through meanwhile."""
    typing_settings_wanted = Signal()
    """"Open System Settings" beside "isn't allowed to type": `main` opens
    the OS's settings where the learner gives it (a Mac's Accessibility,
    polyglotic-hq 438)."""

    def __init__(
        self,
        themes: Sequence[tuple[str, str]],
        work_with_us: QAction,
        languages: Sequence[tuple[str, str]] = (),
        *,
        look: LookView,
        timing: TimingView,
        speech: LanguagesView,
        sound: SoundView | None = None,
        downloads: DownloadsView | None = None,
        japanese_readings: JapaneseReadingsView | None = None,
        presets: PresetsView | None = None,
    ) -> None:
        """`themes`: each window theme's key and name;
        `work_with_us`: "Tell us"; `languages`: each interface language's
        code and its own name ("简体中文"); `look`, `timing` and `speech`:
        the caption settings' views (`main`'s `Panels`); `sound`: Home's
        Sound, shown again in Speech (polyglotic-hq 372)."""
        super().__init__(_tr("Settings"))
        # Kept as a semantic hook for accessibility/tests; U1 now applies the
        # flat treatment consistently throughout the main window.
        self.setProperty("flatSettings", True)
        self._sound = sound
        self._downloads = downloads
        self._japanese_readings = japanese_readings
        self._presets = presets or PresetsView()
        """The presets (polyglotic-hq 556): their section, and the line
        saying which one is in use and what it hasn't saved (587)."""
        self.typing_allowed: Callable[[], bool] | None = None
        """Whether the OS lets the app type, where it asks (a Mac's
        Accessibility: `main` sets it, polyglotic-hq 438); None: it asks
        nothing, as Windows."""
        self._notices: str | None = None
        self._running_language = ""
        self._system_language = ""
        self._sheet = ""
        """The main window's stylesheet (`use_sheet`), on the parts shown."""
        # no stylesheet above the parts to paint them the theme's background
        # (`use_sheet`): the window's own shows through, as beside a column
        self.viewport().setAutoFillBackground(False)
        inner = self.widget()
        assert inner is not None
        inner.setAutoFillBackground(False)
        # the title and its sections' switch pinned above what scrolls (470):
        # a part of the page's own, over the room the viewport leaves at its
        # top (`_place_head`), lined up with the column
        self._placing = False
        self._head()
        self.pinned = PinnedCard(self)
        self.pinned.hide()
        margins = self._row.contentsMargins()
        margins.setTop(0)  # the head keeps the page's margin above it
        self._row.setContentsMargins(margins)
        self.content.parentWidget().installEventFilter(self)  # type: ignore[union-attr]
        self.verticalScrollBar().valueChanged.connect(self._place_pinned)
        # the language lines in one part, which takes the window's stylesheet
        # once (`use_sheet`)
        top = QWidget()
        top.setObjectName("settings.top")
        rows = QVBoxLayout(top)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(self.content.spacing())
        self._language_line(rows, languages)
        # the preset in use, boxed off from the app's language above it, which
        # no preset holds (587: "Changes here are saved in the preset" read
        # as covering it)
        self.preset_line = PresetLine(self._presets, top)
        rows.addWidget(self.preset_line)
        stops = (
            self._presets.naming.subscribe(self._naming),
            self._presets.subscribe(self._show_preset_line),
        )
        self.destroyed.connect(lambda *_: [stop() for stop in stops])
        self.content.insertWidget(0, top)
        self.section: dict[str, QWidget] = {}
        for key in SECTIONS:
            box = QWidget()
            box.setObjectName(f"settings.{key}")
            column = QVBoxLayout(box)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(32)
            self.section[key] = box
            self.content.addWidget(box)
        self._marks: dict[QWidget, Glyph] = {}
        """Each card's mark, beside its title (`settings_marks`, 470)."""
        self._views = (look, timing, speech)
        self._made: set[str] = set()
        """The caption sections whose cards are made (`_make`)."""
        self._current = "look"
        """The section on show (`show_section`)."""
        self._language_sizes: tuple[tuple[Language, float], ...] | None = None
        self._caption_now = 1.0
        """The caption windows' caption size (`show_caption_sizes`)."""
        self._translation_now = 1.0
        """The caption windows' translation size (`show_caption_sizes`)."""
        self._show_preset_line()
        dictation = self._section_layout("dictation")
        self.dictation_for_others = DictationForOthersCard()
        dictation.addWidget(self._marked(self.dictation_for_others, Glyph.MIC))
        self.dictation_card = self._dictation()
        dictation.addWidget(self._marked(self.dictation_card, Glyph.MIC))
        # every key in one place (polyglotic-hq 567, decision 0273)
        keys = self._section_layout("hotkeys")
        self.hotkeys_card = HotkeysCard()
        self.hotkeys_card.hotkey_wanted.connect(self.hotkey_wanted)
        self.hotkeys_card.hotkey_scope_wanted.connect(self.hotkey_scope_wanted)
        self.hotkeys_card.reset_wanted.connect(self.hotkeys_reset)
        self.hotkeys_card.listening.connect(self.hotkey_listening)
        self._hotkey_keys: dict[str, str] = {}
        self._hotkey_scopes: dict[str, str] = {}
        self._hotkeys_taken: frozenset[str] = frozenset()
        self._hotkeys_shared: frozenset[str] = frozenset()
        self._hotkey_alternatives: dict[str, tuple[str, ...]] = {}
        self._hotkeys_unavailable = False
        self._dictation_offered = True
        self._speaker_typing_offered = True
        keys.addWidget(self._marked(self.hotkeys_card, Glyph.KEYS))
        self.hold_keys = HoldKeysCard()
        self.hold_keys.dictation_wanted.connect(lambda: self.show_section("dictation"))
        keys.addWidget(self._marked(self.hold_keys, Glyph.MIC))
        self.hotkeys_for_others = DictationForOthersCard("settings.hotkeys.respeak")
        self.hotkeys_for_others.setObjectName("settings.hotkeys_for_others")
        keys.addWidget(self._marked(self.hotkeys_for_others, Glyph.MIC))
        self.respeak_cards = (self.dictation_for_others, self.hotkeys_for_others)
        for card in self.respeak_cards:
            card.respeak_changes.connect(self.respeak_changes)
            card.respeak_key_wanted.connect(self.respeak_key_wanted)
            card.listening.connect(self.dictation_key_listening)
        keys.addWidget(self._marked(WindowKeysCard(), Glyph.APP))
        app = self._section_layout("app")
        app.addWidget(self._marked(self._text_size(), Glyph.TEXT_SIZE))

        appearance = Card(
            _tr("Appearance"),
            _tr("This window and the transcripts, not the caption windows."),
        )
        self.theme = Segmented(list(themes))
        self.theme.setObjectName("settings.theme")
        self.theme.changed.connect(lambda v: self.theme_chosen.emit(str(v)))
        appearance.add(
            Row(_tr("Theme"), _tr("This window's colours and headings."), self.theme)
        )
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
        app.addWidget(self._marked(appearance, Glyph.THEME))

        app.addWidget(self._marked(self._transcripts(), Glyph.TRANSCRIPTS))

        updates = Card(
            _tr("Updates"),
            _tr(
                "Updates download in the background and install when you quit "
                "Polyglotic."
            )
            if on_linux()
            else _tr(
                "Updates download in the background and install the next time "
                "Polyglotic starts."
            ),
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
        self.restart_now = _button(
            quit_now_label() if on_linux() else _tr("Restart now"),
            "settings.restart_update",
        )
        self.restart_now.clicked.connect(self.restart_wanted)
        self.restart_now.setHidden(True)
        self.open_app_folder = _button(open_folder_label(), "settings.open_app_folder")
        self.open_app_folder.clicked.connect(self.open_app_folder_wanted)
        self.open_app_folder.setHidden(True)
        buttons = right_row(self.update_now)
        buttons.addWidget(self.restart_now)
        buttons.addWidget(self.open_app_folder)
        updates.add(buttons)
        app.addWidget(self._marked(updates, Glyph.UPDATES))

        # starting at sign-in, where the OS can (`offer_start_at_sign_in`):
        # off by default, the installed app only (polyglotic-hq 571)
        self.start_card = Card(_tr("Start at sign-in"))
        self.start_at_sign_in = SwitchRow(
            _tr("Start Polyglotic when you sign in to your computer"),
            _tr("Ready to caption from the moment you sign in."),
            "settings.start_at_sign_in",
        )
        self.start_at_sign_in.switch.toggled.connect(self.start_at_sign_in_chosen)
        self.start_card.add(self.start_at_sign_in)
        self.start_card.setHidden(True)
        app.addWidget(self._marked(self.start_card, Glyph.START))

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
        tell_us.setObjectName("settings.tell_us")
        tell_us.setProperty("kind", "ghost")
        tell_us.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(tell_us)
        about.add(row)
        app.addWidget(self._marked(about, Glyph.ABOUT))
        self.content.addStretch(1)
        self._show("look", make=False)  # its cards once the page is shown

    # -- text size (polyglotic-hq 292) -------------------------------------------------

    def _text_size(self) -> Card:
        """The app's own text size: four steps, applied at once. A choice
        goes out as `text_size_chosen`."""
        card = Card(
            _tr("Text size"),
            _tr(
                "Menus, buttons, this window and word cards. Captions keep their "
                "own size: A- and A+ on each caption window and transcript."
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

    def show_language_sizes(self, sizes: tuple[tuple[Language, float], ...]) -> None:
        self._language_sizes = sizes
        card = getattr(self, "_translation_size", None)
        if card is not None:
            card.show_languages(sizes)

    def show_caption_sizes(self, caption: float, translation: float) -> None:
        """Show the caption windows' independent sizes once Look is built."""
        self._caption_now = caption
        self._translation_now = translation
        card = getattr(self, "_translation_size", None)
        if card is not None:
            card.show_sizes(caption, translation)

    def show_translation_size(self, size: float) -> None:
        """The caption windows' translation size - on Look's card, once made."""
        self._translation_now = size
        card = getattr(self, "_translation_size", None)
        if card is not None:
            card.show_size(size)

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
        newest = _trn("Newest %Ln line(s)", TRANSCRIPT_LINES)
        self.transcript_length = Segmented(
            [
                ("newest", newest),
                ("three_hours", _trn("Last %Ln hour(s)", TRANSCRIPT_HOURS)),
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
            _trn(
                "With Last %Ln hour(s) or Whole session, Quit asks first if a "
                "transcript of {line_limit} isn't saved.",
                TRANSCRIPT_HOURS,
            ).format(line_limit=_trn("more than %Ln line(s)", ASK_FROM_LINES)),
            "settings.transcript_ask",
        )
        self.transcript_ask.switch.set_quietly(True)
        self.transcript_ask.switch.toggled.connect(self.transcript_ask_chosen)
        card.add(self.transcript_ask)
        return card

    def offer_start_at_sign_in(self, on: bool) -> None:
        """Start at sign-in offered - the OS can, for this copy - as it is
        now (`on`), without saying it was chosen (polyglotic-hq 571)."""
        self.start_card.setHidden(False)
        self.start_at_sign_in.switch.set_quietly(on)

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
                "Hold a key and speak; let go, and it's typed where your cursor "
                "is. While your own speech is captioned, dictation shows in that "
                "caption window too and uses its spoken language. Otherwise it "
                "listens only while you hold the key."
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
        self.dictation_key = KeyBox(str(DEFAULT_KEY), "settings.dictation_key")
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
                pc_or_mac(
                    _tr(
                        "Click, then press the key or combination you want to "
                        "hold: Right Ctrl, F9, Ctrl + Alt + D… While dictation is "
                        "on, the key you choose is Polyglotic's, alone or with "
                        "Ctrl, Alt or Win; Right Ctrl alone still works in other "
                        "programs."
                    ),
                    # a Mac's keys as its menus write them (key_words); the
                    # example is one macOS leaves free: ⌃⌥D is refused (⌥
                    # without ⌘), ⌥⌘D hides the Dock, ⌃⌘D looks a word up (451)
                    _tr(
                        "Click, then press the key or combination you want to "
                        "hold: Right ⌘, F9, ⌃⌘E… While dictation is on, the key "
                        "you choose is Polyglotic's, alone or with ⌃, ⌥ or ⌘; "
                        "Right ⌘ alone still works in other apps."
                    ),
                ),
                key_box,
            )
        )
        self.dictation_key_note = label("", "Faint", wrap=True)
        self.dictation_key_note.setObjectName("settings.dictation_key_note")
        card.add(self.dictation_key_note)
        self.dictation_key_note.hide()  # after its parent: never a window of its own
        card.add(self._typing_permission())
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
                " ".join(
                    (
                        _tr(
                            "Choose a language or use {detect} for when your "
                            "speech isn't captioned."
                        ).format(detect=detect_name()),
                        pc_or_mac(
                            _tr("The tray's menu switches it too."),
                            _tr("The menu bar's menu switches it too."),
                        ),
                    )
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

    def _typing_permission(self) -> QWidget:
        """Where the OS hasn't let the app type (a Mac without the
        Accessibility permission, polyglotic-hq 438): why nothing is typed,
        and the way to System Settings. Hidden until then."""
        self.typing_not_allowed = QWidget()
        self.typing_not_allowed.setObjectName("settings.typing_not_allowed")
        rows = QVBoxLayout(self.typing_not_allowed)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(8)
        why = label(
            #: macOS System Settings' own names: keep them as the Mac shows them
            _tr(
                "Polyglotic isn't allowed to type into other apps, so nothing"
                " you say is typed. In System Settings, open Privacy & Security,"
                " then Accessibility, and turn on Polyglotic."
            ),
            "Faint",
            wrap=True,
        )
        rows.addWidget(why)
        self.typing_settings = _button(
            _tr("Open System Settings"), "settings.typing_settings"
        )
        self.typing_settings.clicked.connect(self.typing_settings_wanted)
        button_row = QHBoxLayout()
        button_row.addWidget(self.typing_settings)
        button_row.addStretch(1)
        rows.addLayout(button_row)
        self.typing_not_allowed.hide()
        return self.typing_not_allowed

    def show_typing_permission(self) -> None:
        """Asks the OS again whether the app may type, and shows why not
        and the way to its settings if it may not."""
        allowed = self.typing_allowed() if self.typing_allowed is not None else True
        self.typing_not_allowed.setHidden(allowed)

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
        self.hold_keys.show_dictation(on, key)
        for card in self.respeak_cards:
            card.show_dictation(on, key, taken)
        self._show_keys()

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
        own = [k for n, k in self.hotkeys_card.keys.items() if k and n != DICTATE]
        # re-speaking's own key is one of the app's too (567)
        refused = refusal(key, own, typing_in_app=True) if key else None
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
        parsed = DictationKey.parse(key)
        if parsed is not None and default_scope(parsed) is HotkeyScope.APP:
            return _tr(
                "Hold {key} and speak in Polyglotic's windows. Let go to type."
            ).format(key=key_words(parsed))
        return _tr("Hold {key} and speak; let go, and it's typed.").format(
            key=key_words(key)
        )

    # -- the sections ------------------------------------------------------------------

    def _head(self) -> None:
        """The title, with the sections' switch at its right - each tab its
        mark beside its name (470) - pinned at the page's top
        (`_place_head`); the sections a dropdown where the tabs don't fit on
        one line (`section_picker`)."""
        title = self.content.takeAt(0)
        assert title is not None
        heading = title.widget()
        assert heading is not None
        self.head = QWidget(self)
        self.head.setObjectName("settings.head")
        head = Flow(self.head, spacing=16)  # the sections under it when they don't fit
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(heading)
        names = {
            #: Settings' section of the presets for use cases (conversation, video...)
            "presets": _tr("Presets"),
            "look": _tr("Look"),
            "links": _tr("Word links"),
            #: Settings' section of reading lines over captions - pinyin above Chinese, Jyutping above Cantonese
            "readings": _tr("Readings"),
            "timing": _tr("Timing"),
            "speech": _tr("Speech"),
            "dictation": _tr("Dictation"),
            #: Settings' section of keys pressed anywhere: lock, pause, back to live...
            "hotkeys": _tr("Hotkeys"),
            "app": _tr("App"),
            "lab": _tr("Lab"),
        }
        self.sections = Segmented([(key, names[key]) for key in SECTIONS], "look")
        self.sections.setObjectName("settings.sections")
        self.sections.setAccessibleName(_tr("Settings sections"))
        self.sections.changed.connect(lambda key: self.show_section(str(key)))
        head.addWidget(self.sections)
        self.section_picker = FittingCombo()  # its width its own (500)
        self.section_picker.setObjectName("settings.section_picker")
        self.section_picker.setAccessibleName(_tr("Settings sections"))
        self.section_picker.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        for key in SECTIONS:
            self.section_picker.addItem(names[key], key)
        self.section_picker.currentIndexChanged.connect(
            lambda index: self.show_section(SECTIONS[index])
        )
        self.section_picker.setHidden(True)
        head.addWidget(self.section_picker)
        self._ink_tabs()
        self.head.installEventFilter(self)

    def _ink_tabs(self) -> None:
        """Each section's mark on its tab and in the dropdown, in the theme
        and at the text size now: dim, as the tab's name is, and the text's
        colour on the chosen one."""
        theme = style.current()
        side = style.px(TAB)
        for key, button in zip(SECTIONS, self.sections.buttons, strict=True):
            button.setIcon(
                glyphs.icon(MARKS[key], theme["TEXT_DIM"], side, on=theme["TEXT"])
            )
            button.setIconSize(QSize(side, side))
        for index, key in enumerate(SECTIONS):
            self.section_picker.setItemIcon(
                index, glyphs.icon(MARKS[key], theme["TEXT"], side)
            )
        self.section_picker.setIconSize(QSize(side, side))

    def _marked(self, card: QWidget, glyph: Glyph) -> QWidget:
        """`card` with `glyph` beside its title (`settings_marks`)."""
        assert isinstance(card, Card)
        mark_card(card, glyph)
        self._marks[card] = glyph
        return card

    # -- pinned while the page scrolls (470) ----------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """The column moved or resized, or the head's layout changed (a text
        size): the head and the pinned card placed again. The wheel over the
        head - outside the viewport - scrolls the page as over the rest."""
        head = self.__dict__.get("head")  # Qt's scroll area asks before it's made
        if head is None or watched not in (head, self.content.parentWidget()):
            return super().eventFilter(watched, event)
        if watched is head and event.type() == QEvent.Type.Wheel:
            QApplication.sendEvent(self.verticalScrollBar(), event)
            return True
        if event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
            QEvent.Type.LayoutRequest,
        ):
            self._place_head()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._place_head()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:  # perhaps another text size
            QTimer.singleShot(0, self, self._place_head)

    def _place_head(self) -> None:
        """The title and the sections over the room the viewport leaves at
        the page's top, as wide as the column and lined up with it; the
        tabs or, where they don't fit on one line, the dropdown."""
        if self._placing or "pinned" not in self.__dict__:
            return
        self._placing = True
        try:
            column = self.content.parentWidget()
            assert column is not None
            left = column.mapTo(self, QPoint(0, 0)).x()
            width = column.width()
            narrow = self.sections.sizeHint().width() > self.head_room()
            if narrow != self.sections.isHidden():
                self.sections.setHidden(narrow)
                self.section_picker.setHidden(not narrow)
            layout = self.head.layout()
            assert layout is not None
            height = layout.heightForWidth(width)
            self.head.setGeometry(left, MARGIN, width, height)
            top = MARGIN + height + PINNED_GAP
            if self.viewportMargins().top() != top:
                self.setViewportMargins(0, top, 0, 0)
        finally:
            self._placing = False
        self._place_pinned()

    def head_room(self) -> int:
        """The column's width once the page has settled - the room the tabs
        are judged by. The scroll bar's room is always kept at the right,
        the bar's or the gutter's (`Page._keep_gutter`), but the column
        passes through other widths as the head's height moves the viewport
        and the bar comes and goes: judged by those, with the tabs a little
        narrower than the column, the tabs and the dropdown took turns 128
        times in one switch to Speech at the window's narrowest - 160 ms
        (polyglotic-hq 567)."""
        column = self.content.parentWidget()
        assert column is not None
        scroll = self.verticalScrollBar()
        # the gutter's (its hint) or the bar's own, the wider: a pixel or two apart
        extent = self.style().pixelMetric(
            QStyle.PixelMetric.PM_ScrollBarExtent, None, scroll
        )
        bar = max(scroll.sizeHint().width(), extent)
        row = self._row  # its margins, and its spacing either side of the column:
        # a few pixels narrower than the column, never wider
        sides = row.contentsMargins().left() + MARGIN + bar + 2 * max(0, row.spacing())
        inside = self.width() - 2 * self.frameWidth() - sides
        return min(column.maximumWidth(), inside)

    def _place_pinned(self) -> None:
        """The card the learner is in, by name, under the sections - once
        its own title has scrolled away under them; hidden at a card's top."""
        card = self._card_scrolled_into()
        if card is None or card.title is None:
            self.pinned.hide()
            return
        self.pinned.show_card(self._marks[card], card.title.text())
        column = self.content.parentWidget()
        assert column is not None
        left = column.mapTo(self, QPoint(0, 0)).x()
        self.pinned.setGeometry(
            left,
            self.viewport().geometry().top(),
            column.width(),
            self.pinned.sizeHint().height(),
        )
        self.pinned.show()
        self.pinned.raise_()

    def _card_scrolled_into(self) -> Card | None:
        """The section's last card whose top is under the pinned name's
        line, if its own title is scrolled out of sight and some of it is
        still in view."""
        if self.verticalScrollBar().value() == 0:
            return None
        viewport = self.viewport()
        line = self.pinned.sizeHint().height()
        found: Card | None = None
        for card in self.cards(str(self.sections.value())):
            if card.mapTo(viewport, QPoint(0, 0)).y() > line:
                break
            found = card
        if found is None or found.title is None:
            return None
        if found.title.mapTo(viewport, QPoint(0, 0)).y() >= 0:
            return None  # its own title shows
        if found.mapTo(viewport, QPoint(0, found.height())).y() <= 0:
            return None
        return found

    def cards(self, key: str) -> list[Card]:
        """Section `key`'s cards, top to bottom, those shown."""
        column = self._section_layout(key)
        items = (column.itemAt(i) for i in range(column.count()))
        widgets = (item.widget() for item in items if item is not None)
        return [
            w
            for w in widgets
            if isinstance(w, Card) and w in self._marks and w.isVisible()
        ]

    def _language_line(
        self, rows: QVBoxLayout, languages: Sequence[tuple[str, str]]
    ) -> None:
        """The app's language under the title, in every section - not only
        at App's foot (the user's live testing, polyglotic-hq 270: "App
        language should also be more obvious rather than hid in 2 layers";
        284) - its one place since App's own card went (470); each
        language by its own name, so it's found whatever language the app is
        in now."""
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
        self.language_restart = _button(_tr("Restart now"), "settings.language_restart")
        self.language_restart.setProperty("kind", "primary")
        self.language_restart.clicked.connect(self.language_restart_wanted)
        self.language_restart.setHidden(True)
        line.addWidget(self.language_restart)
        self.language_defer = _button(_tr("Later"), "settings.language_defer")
        self.language_defer.setProperty("kind", "ghost")
        self.language_defer.clicked.connect(self._defer_language_restart)
        self.language_defer.setHidden(True)
        line.addWidget(self.language_defer)
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

    def show_running_language(self, running: str, system_language: str) -> None:
        """The interface language this copy started in, and the one "Like this
        PC" resolves to (polyglotic-hq 658): picking the same effective
        language needs no restart."""
        self._running_language = running
        self._system_language = system_language

    def _language_picked(self, index: int) -> None:
        code = str(self.language_picker.itemData(index) or "")
        effective = code or self._system_language
        needs_restart = (
            not self._running_language or effective != self._running_language
        )
        self.language_later.setHidden(not needs_restart)
        self.language_restart.setHidden(not needs_restart)
        self.language_defer.setHidden(not needs_restart)
        self.interface_language_chosen.emit(code)

    def _defer_language_restart(self) -> None:
        """Later: keep the chosen language for the next start and hide the
        restart buttons."""
        self.language_restart.setHidden(True)
        self.language_defer.setHidden(True)
        self.language_later.setHidden(False)

    def _section_layout(self, key: str) -> QVBoxLayout:
        column = self.section[key].layout()
        assert isinstance(column, QVBoxLayout)
        return column

    def _make(self, key: str) -> None:
        """Caption section `key`'s cards (`CAPTION_CARDS`) - every caption
        window's settings, in 248's order (section 2.2), each group in the
        section a learner comes to it for (304) - made the first time the
        section is shown or one of its cards is asked for, not with the
        page: the start makes the page unseen, and its six caption sections
        were about 39 ms of it, which took the start at 30,000 words met
        over its budget (polyglotic-hq 544)."""
        if key not in CAPTION_CARDS or key in self._made:
            return
        self._made.add(key)
        look, timing, speech = self._views
        placed: tuple[tuple[QWidget, Glyph], ...]
        if key == "presets":
            self._presets_panel = PresetsPanel(self._presets)
            self._preset_panel = PresetPanel(self._presets)
            placed = (
                (self._presets_panel, Glyph.FILL),
                (self._preset_panel, Glyph.LOOK),
            )
        elif key == "look":
            self._look = LookPanel(look, notes=True, preview=True, languages=speech)
            # a row per language, its faces downloaded on choice (482)
            self._faces = FacesPanel(look, speech, self._downloads, notes=True)
            self._reset = ResetCard(look)  # the look's: Look's last
            # independent caption and translation sizes, every window's (655)
            self._translation_size = TranslationSizeCard(
                self._translation_now, self._caption_now
            )
            self._translation_size.caption_chosen.connect(self.caption_size_chosen)
            self._translation_size.chosen.connect(self.translation_size_chosen)
            if self._language_sizes is not None:
                self._translation_size.show_languages(self._language_sizes)
            placed = (
                (self._look, Glyph.LOOK),
                (self._translation_size, Glyph.TEXT_SIZE),
                (self._faces, Glyph.FONTS),
                (self._reset, Glyph.RESET),
            )
        elif key == "links":
            # Look was 2,557 px with no landmark: links and readings are
            # sections of their own (449's design 4A, 470); the quiet view,
            # word links' other way of showing words (it turns them off),
            # beside them (477)
            self._word_links = WordLinksPanel(look, notes=True, learning=True)
            self._word_links.learning_wanted.connect(self.learning_wanted)
            self._quiet = QuietViewPanel(look, notes=True)
            placed = ((self._word_links, Glyph.LINKS), (self._quiet, Glyph.QUIET))
        elif key == "readings":
            self._reading = ReadingLinesPanel(
                look, notes=True, japanese_readings=self._japanese_readings
            )
            placed = ((self._reading, Glyph.READINGS),)
        elif key == "timing":
            self._timing = TimingPanel(timing, languages=speech, presets=self._presets)
            self._behaviour = BehaviourPanel(look, notes=True, hidden_windows=True)
            placed = ((self._timing, Glyph.TIMING), (self._behaviour, Glyph.BEHAVIOUR))
        elif key == "speech":
            # the speakers and the mic first, as Home's Sound (372): one view
            self._sound_card = (
                SoundCard(self._sound) if self._sound is not None else None
            )
            # Spoken language here sets every window's own, and the second
            # languages are the ones each window's "When they already speak
            # ..." sets (248's F28; polyglotic-hq 263: each caption window
            # has its own)
            self._speech = LanguagesPanel(speech, speech=True)
            placed = ((self._speech, Glyph.SPEECH),)
            if self._sound_card is not None:
                placed = ((self._sound_card, Glyph.SPEAKER), *placed)
        else:  # experimental: a section of its own, last (284)
            self._lab = LabPanel(look, languages=speech)
            self._lab.load_wanted.connect(self.lab_load_wanted)
            placed = ((self._lab, Glyph.LAB),)
        column = self._section_layout(key)
        for card, glyph in placed:
            column.addWidget(self._marked(card, glyph))

    @property
    def presets(self) -> PresetsPanel:
        self._make("presets")
        return self._presets_panel

    @property
    def preset(self) -> PresetPanel:
        self._make("presets")
        return self._preset_panel

    def _show_preset_line(self) -> None:
        """Settings > Presets is where a learner saves a Settings draft."""
        named = bool(self._presets.value.name)
        self.preset_line.setVisible(named and self._current == "presets")

    def _naming(self) -> None:
        """Save as new preset… asked from a section without the line: it
        shows on Presets, where the new one will be listed."""
        if self._presets.naming.value and self._current != "presets":
            self.show_section("presets")

    @property
    def look(self) -> LookPanel:
        self._make("look")
        return self._look

    @property
    def faces(self) -> FacesPanel:
        self._make("look")
        return self._faces

    @property
    def translation_size(self) -> TranslationSizeCard:
        """Look's translation size (593)."""
        self._make("look")
        return self._translation_size

    @property
    def reset(self) -> ResetCard:
        self._make("look")
        return self._reset

    @property
    def word_links(self) -> WordLinksPanel:
        self._make("links")
        return self._word_links

    @property
    def quiet(self) -> QuietViewPanel:
        self._make("links")
        return self._quiet

    @property
    def reading(self) -> ReadingLinesPanel:
        self._make("readings")
        return self._reading

    @property
    def timing(self) -> TimingPanel:
        self._make("timing")
        return self._timing

    @property
    def behaviour(self) -> BehaviourPanel:
        self._make("timing")
        return self._behaviour

    @property
    def speech(self) -> LanguagesPanel:
        self._make("speech")
        return self._speech

    @property
    def sound(self) -> SoundCard | None:
        self._make("speech")
        return self._sound_card

    @property
    def lab(self) -> LabPanel:
        self._make("lab")
        return self._lab

    def offer_dictation(self, offered: bool, *, speakers: bool = False) -> None:
        """The Dictation section, or none on an OS that has no dictation yet
        (Linux, until polyglotic-hq 546's slice 8; 574): its tab, its line in
        the dropdown and its HoldKeys card in Hotkeys hidden, and Look shown
        if it was on."""
        self._dictation_offered = offered
        self._speaker_typing_offered = offered or speakers
        index = SECTIONS.index("dictation")
        self.sections.buttons[index].setVisible(self._speaker_typing_offered)
        view = self.section_picker.view()
        if isinstance(view, QListView):
            view.setRowHidden(index, not self._speaker_typing_offered)
        self.dictation_card.setVisible(offered)
        self.hold_keys.setVisible(offered)
        self.hotkeys_for_others.setVisible(self._speaker_typing_offered)
        for card in self.respeak_cards:
            card.respeak_way.setVisible(offered)
        self._show_keys()
        if not self._speaker_typing_offered and self._current == "dictation":
            self.show_section("look")

    def use_speaker_clipboard(self) -> None:
        for card in self.respeak_cards:
            card.use_speaker_clipboard()

    def show_section(self, key: str) -> None:
        """Section `key` (one of `SECTIONS`, or a former name: `FORMER`),
        at the top."""
        self._show(key)

    def _show(self, key: str, make: bool = True) -> None:
        """`show_section`; `make`: its cards made first, if they aren't."""
        key = FORMER.get(key, key)
        if key not in self.section:
            raise ValueError(key)
        self._current = key
        if make and key in CAPTION_CARDS and key not in self._made:
            # made hidden, so they're shown with it, in this frame: added to
            # a box on show, Qt shows each card only once the event loop turns
            self.section[key].setVisible(False)
            self._make(key)
        self.sections.set_value(key)
        blocked = self.section_picker.blockSignals(True)
        self.section_picker.setCurrentIndex(SECTIONS.index(key))
        self.section_picker.blockSignals(blocked)
        self._styled(self.section[key])  # before it's shown: polished once
        for each, box in self.section.items():
            box.setVisible(each == key)
        self._show_preset_line()
        self.verticalScrollBar().setValue(0)
        self._place_pinned()

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
        self._ink_tabs()  # the marks in the theme and at the text size now
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

    @staticmethod
    def _show_chosen(picker: QComboBox, code: str) -> None:
        index = max(0, picker.findData(code))
        blocked = picker.blockSignals(True)
        picker.setCurrentIndex(index)
        picker.blockSignals(blocked)

    def show_interface_language(self, code: str) -> None:
        """The interface language as the settings have it ("": like Windows)."""
        self._show_chosen(self.language_picker, code)

    def showEvent(self, event: QShowEvent) -> None:
        if self._current in CAPTION_CARDS and self._current not in self._made:
            self.show_section(self._current)  # first shown: its cards made now
        self.show_typing_permission()  # given in System Settings meanwhile (438)
        super().showEvent(event)

    def show_command(self, command: str) -> None:
        """How a desktop shortcut starts this app (`polyglotic` or the AppImage
        path), shown in Hotkeys when global hotkeys aren't available (647)."""
        self.hotkeys_card.set_command(command)

    def show_hotkeys(
        self,
        keys: Mapping[str, str],
        taken: Collection[str],
        *,
        scopes: Mapping[str, str] | None = None,
        shared: Collection[str] = (),
        alternatives: Mapping[str, Sequence[str]] | None = None,
        unavailable: bool = False,
    ) -> None:
        """Each hotkey's key now, by its name, as kept ("" none); `taken`:
        those another program has (not working); `shared`: those shared via
        fallback hook; `alternatives`: tested free keys per conflicting hotkey;
        `scopes`: each hotkey's scope ("app" or "everywhere"); `unavailable`:
        this desktop doesn't allow global hotkeys (GNOME Wayland, `NoHotkeys`)."""
        self._hotkey_keys = dict(keys)
        self._hotkey_scopes = dict(scopes) if scopes else {}
        self._hotkeys_taken = frozenset(taken)
        self._hotkeys_shared = frozenset(shared)
        self._hotkey_alternatives = (
            {n: tuple(alts) for n, alts in alternatives.items() if alts}
            if alternatives
            else {}
        )
        self._hotkeys_unavailable = unavailable
        self._show_keys()

    def _show_keys(self) -> None:
        dictation = (
            self.dictation_key.key
            if self._dictation_offered
            and (
                self.dictation_on.switch.isChecked()
                or self.dictation_for_others.uses_dictation_key
            )
            else None
        )
        respeak = (
            self.dictation_for_others.own_key if self._speaker_typing_offered else None
        )
        self.hotkeys_card.show_keys(
            self._hotkey_keys,
            self._hotkeys_taken,
            dictation,
            respeak,
            scopes=self._hotkey_scopes,
            shared=self._hotkeys_shared,
            alternatives=self._hotkey_alternatives,
            unavailable=self._hotkeys_unavailable,
        )
        keys = self.hotkeys_card.keys
        for card in self.respeak_cards:
            card.hotkeys = {
                n: k for n, k in keys.items() if n not in (DICTATE, RESPEAK)
            }

    def show_respeaking(
        self,
        on: bool,
        key: str,
        taken: bool = False,
        what: str = "original",
        last_own: str | None = None,
    ) -> None:
        """Speaker typing preferences and whether another program has its key."""
        for card in self.respeak_cards:
            card.show_respeaking(on, key, taken, what, last_own)
        self._show_keys()

    def respeak_key_not_taken(self, wanted: str) -> None:
        """Another program has the key pressed for re-speaking: the one
        before is kept."""
        for card in self.respeak_cards:
            if card.isVisible():
                card.not_taken(wanted)

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
        now (Quit now on Linux) or Open folder when the app's folder isn't
        writable (polyglotic-hq 299, 640)."""
        ready = (
            update_ready_linux()
            if on_linux()
            else _tr("Version {version} is ready. Restart to install it.")
        )
        texts = {
            "up_to_date": _tr("Polyglotic is up to date."),
            "ready": ready,
            "no_feed": _tr(
                "Couldn't reach the update server. Polyglotic tries again later."
            ),
            "not_downloaded": _tr(
                "The update couldn't be downloaded. Polyglotic tries again later."
            ),
            "not_writable": not_writable_notice(),
            "metered": _tr(
                "Version {version} is available. Your connection is metered, so it "
                "waits: Home can download it anyway."
            ),
            "not_installed": _tr(
                "This copy wasn't installed by the installer, so it can't update "
                "itself."
            ),
        }
        text = texts.get(found, "").format(version=version or "")
        self.update_found.setText(text)
        self.update_found.setHidden(not text)
        self.restart_now.setText(quit_now_label() if on_linux() else _tr("Restart now"))
        self.restart_now.setHidden(found != "ready" or version is None)
        self.open_app_folder.setHidden(found != "not_writable")

    def set_notices(self, text: str | None) -> None:
        """The third-party notices' text, or None if this copy has none."""
        self._notices = text
        self.notices.setHidden(not text)

    def _show_notices(self) -> None:
        if self._notices:
            dialog = NoticesDialog(self._notices, self)
            self._styled(dialog)  # the page has no stylesheet of its own
            dialog.exec()
