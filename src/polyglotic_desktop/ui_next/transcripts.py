"""The transcripts: one per app captioned, each with its window on demand
(polyglotic-hq project 109's structure, sections 3 and 8).

`Transcripts` keeps a `Transcript` (`views.transcript`) for every app its
caption windows caption - from the moment the app is captioned, whether
its transcript window is open or not - and opens that app's
`TranscriptWindow` when asked: from the caption window's "Open
transcript", the tray's Transcript menu (`menu`) and, with the new main
window, Home's app row.

- **It follows the caption windows** (`follow`, on their
  `languages_changed` and whenever `main` changes the session's
  settings): each transcript in its window's language (or Original
  only), with my speech while its window shows it, its label and the
  session's timing. A transcript's own controls - its strip's language,
  and its rail's "This window" rows (a `WindowLanguageView` per app) -
  change its caption window's language and Show my speech here through
  that window, so the two never disagree.
- **The rail's panels** are the session's (`panels`: the views every
  Languages, Timing and Look panel binds to - Home's, the Look window's),
  so a change in one shows in all.
- **An app no longer captioned:** its transcript window closes; its lines
  are kept for this session, and show again if the app is captioned again
  (section 8).
- **Remembered per app:** each transcript's text size and whether its
  rail is open (`views.transcript.TranscriptChoices`), saved a moment
  after they change as one setting, `transcripts`, beside today's.
- **How far back every transcript's list goes** (`set_length`: Settings >
  App, polyglotic-hq 334): the newest 1,000 lines, the last three hours,
  or the whole session - Copy all and Save have the whole session
  whichever it is.
- **Asked once at Quit** (`may_quit`, polyglotic-hq 334): with three hours
  or the whole session kept, each transcript of more than 300 lines that
  isn't saved - its app's caption window open or closed - is offered
  Save..., Quit without saving or Cancel, with "Don't ask again"
  (`asking_changed`; Settings > App turns it back on). Closing a caption
  window asks nothing: its transcript stays for the session. Nothing is
  ever written unless the learner saves it.

Holds caption text through its transcripts: never log it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import partial
from typing import Protocol

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QCheckBox, QMenu, QMessageBox, QWidget

from polyglotic_desktop.core.learning.vocabulary import Changed
from polyglotic_desktop.core.listening.captions import CaptionUpdate
from polyglotic_desktop.core.listening.recheck import RecheckResult
from polyglotic_desktop.core.listening.sources import SourceLabel
from polyglotic_desktop.core.listening.timing import CaptionId
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_marks import Learner
from polyglotic_desktop.ui_next.caption_window import work_areas
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import LanguagesPanel, LookPanel, TimingPanel
from polyglotic_desktop.ui_next.save_folder import SaveFolder
from polyglotic_desktop.ui_next.selection_reading import SelectionReading
from polyglotic_desktop.ui_next.transcript_window import YOU, TranscriptWindow
from polyglotic_desktop.ui_next.views.caption_window import Notice
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    TimingView,
    WindowLanguage,
    WindowLanguageView,
)
from polyglotic_desktop.ui_next.views.placement import Rect, Size, area_for
from polyglotic_desktop.ui_next.views.transcript import (
    DEFAULT_SIZE,
    STORED_KEY,
    StoredTranscripts,
    Transcript,
    TranscriptChoices,
    TranscriptLength,
    beside,
    clear_of,
)

SAVE_AFTER_MS = 400
"""A transcript's choices are saved this long after the last change."""


class SessionPanels(Protocol):
    """The views the session's panels bind to (`main.Panels`)."""

    @property
    def languages(self) -> LanguagesView: ...

    @property
    def timing(self) -> TimingView: ...

    @property
    def look(self) -> LookView: ...


def _tr(text: str) -> str:
    return QApplication.translate("Transcripts", text)


def _trn(text: str, n: int) -> str:
    """A count's text in the language's form for `n` (decision 0034)."""
    return QApplication.translate("Transcripts", text, None, n)


class QuitChoice(Enum):
    """What the learner chose when Quit asked about a transcript."""

    SAVE = "save"
    QUIT = "quit"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class QuitAnswer:
    """The choice, and whether "Don't ask again" was ticked."""

    choice: QuitChoice
    never_again: bool = False


def ask_to_save(name: str, lines: int) -> QuitAnswer:
    """Quit's question about app `name`'s transcript of `lines` lines:
    Save... (the default), Quit without saving or Cancel (Esc), and "Don't
    ask again". A window of its own: Quit comes from the tray as often as
    from a window."""
    box = question(name, lines)
    box.exec()
    clicked = box.clickedButton()
    roles = {QMessageBox.ButtonRole.AcceptRole: QuitChoice.SAVE}
    roles[QMessageBox.ButtonRole.DestructiveRole] = QuitChoice.QUIT
    role = box.buttonRole(clicked) if clicked is not None else None
    choice = (
        roles.get(role, QuitChoice.CANCEL) if role is not None else QuitChoice.CANCEL
    )
    check = box.checkBox()
    answer = QuitAnswer(choice, check is not None and check.isChecked())
    box.deleteLater()
    return answer


def question(name: str, lines: int) -> QMessageBox:
    """Quit's question, made - not shown (`ask_to_save` shows it)."""
    box = QMessageBox(
        QMessageBox.Icon.Question,
        _tr("Save the transcript?"),
        _tr("Save the transcript of {app} before quitting?").format(app=name),
    )
    box.setObjectName("transcripts.ask_to_save")
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.setInformativeText(
        _trn("It has %Ln line(s), and it's gone when Polyglotic quits.", lines)
    )
    save = box.addButton(_tr("Save…"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(_tr("Quit without saving"), QMessageBox.ButtonRole.DestructiveRole)
    cancel = box.addButton(_tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(save)
    box.setEscapeButton(cancel)
    box.setCheckBox(QCheckBox(_tr("Don't ask again"), box))
    return box


class Transcripts(QObject):
    timing_wanted = Signal(str)
    """The session's caption timing, chosen on a transcript's strip."""
    opened = Signal()
    """A transcript window was opened or brought forward (the listening
    session's usage statistics count it; polyglotic-hq project 134)."""
    asking_changed = Signal(bool)
    """"Don't ask again" at Quit's question: False (`main` saves it)."""

    def __init__(
        self,
        windows: CaptionWindows,
        store: SettingsStore | None,
        learner: Learner | None = None,
        areas: Callable[[], list[Rect]] = work_areas,
        parent: QObject | None = None,
        clock: Callable[[], datetime] | None = None,
        save_folder: SaveFolder | None = None,
    ) -> None:
        """`windows`: the caption windows each app's transcript follows;
        `learner`: the learning tools, for saved words' colours; `clock`:
        when captions arrive (default: now - the lab's are made up);
        `save_folder`: where Save transcript as... opens (Words' exports
        share it: `main`)."""
        self._clock = clock
        super().__init__(parent)
        self.windows = windows
        self.learner = learner
        self.save_folder = save_folder or SaveFolder(store)
        self.theme = style.current()
        self.panels: SessionPanels | None = None
        self._own: dict[str, WindowLanguageView] = {}
        """Each app's "This window" rows' view, while its transcript has a rail."""
        self.paused = False
        self.notice: Notice | None = None
        self.transcripts: dict[str, Transcript] = {}
        """Every app captioned this session, by its key."""
        self.length = TranscriptLength.NEWEST
        """How far back every transcript's list goes (`set_length`)."""
        self.ask_at_quit = True
        """Quit asks about a long transcript not saved (Settings > App)."""
        self.ask: Callable[[str, int], QuitAnswer] = ask_to_save
        """Asks Quit's question (an app's name, its transcript's lines)."""
        self._quit_answered = False
        self._labels: dict[str, SourceLabel] = {}
        """Each app's label as its caption window last had it, by key - a
        transcript outlives its window (Quit's question names it)."""
        self.shown: dict[str, TranscriptWindow] = {}
        """The transcript windows opened, by app (closed ones kept, hidden)."""
        self.say_it: SelectionReading | None = None
        """Reads a selection aloud from its menu (polyglotic-hq 495)."""
        self._store = store
        self._areas = areas
        self._read: dict[str, object] = store.load() if store else {}
        """The settings file as last read, for `save_now`."""
        self.stored = StoredTranscripts.from_stored(self._read)
        self.menu = QMenu(_tr("Transcript"))
        self.menu.setObjectName("transcripts.menu")
        self._menu_names: list[tuple[str, str]] | None = None
        self._save = QTimer(self, singleShot=True, interval=SAVE_AFTER_MS)
        self._save.timeout.connect(self.save_now)
        windows.languages_changed.connect(self.follow)
        windows.look_changed.connect(self._follow_look)
        self.follow()

    # -- in step with the caption windows ---------------------------------------------

    def _you(self) -> SourceLabel:
        mic = self.windows.mic
        found = self.windows.labels.get(mic) if mic else None
        return found or SourceLabel(self.windows.you, YOU)

    def follow(self) -> None:
        """Each captioned app's transcript as its caption window is now; the
        windows of apps no longer captioned close."""
        windows = self.windows
        for key, window in windows.windows.items():
            self._labels[key] = window.label
            choices = window.choices
            target = choices.target
            second = windows.second_languages.get(target) if target else None
            found = self.transcripts.get(key)
            if found is None or found.source != window.source:
                found = self.transcripts[key] = Transcript(
                    window.source,
                    target,
                    second=second,
                    mic=windows.mic,
                    show_mic=choices.show_mic,
                    text_size=self._choices(key).text_size,
                    clock=self._clock,
                    length=self.length,
                )
            found.set_language(target, second)
            found.set_settle_after(windows.settle_after)
            found.set_show_mic(choices.show_mic)
            own = self._own.get(key)
            if own is not None:
                own.follow(self._window_language(key))
            shown = self.shown.get(key)
            if shown is not None:
                shown.follow(
                    window.label,
                    choices.translate_into,
                    choices.show_mic,
                    windows.timing,
                    self._you(),
                )
        for key in [k for k in self.shown if k not in windows.windows]:
            self._close(key)
        self._fill_menu()

    def _fill_menu(self) -> None:
        """The tray's Transcript menu: an entry per app captioned."""
        names = [(k, w.label.name) for k, w in self.windows.windows.items()]
        if names == self._menu_names:
            return
        self._menu_names = names
        self.menu.clear()
        for key, name in names:
            self.menu.addAction(name, partial(self.show, key))
        self.menu.setEnabled(bool(names))

    def _choices(self, key: str) -> TranscriptChoices:
        return self.stored.by_key.get(key) or TranscriptChoices()

    # -- captions ---------------------------------------------------------------------

    def apply(self, update: CaptionUpdate) -> None:
        """A caption update (on the interface thread): to each captioned
        app's transcript it's for; its window repaints if open."""
        with spans.span("transcripts.apply"):
            for key in self.windows.windows:
                found = self.transcripts.get(key)
                if found is not None and found.apply(update):
                    shown = self.shown.get(key)
                    if shown is not None and shown.isVisible():
                        shown.refresh()

    def use_checked(self, caption_id: CaptionId, result: RecheckResult) -> None:
        """The best model's version of a line, which the learner said is right."""
        for key, found in self.transcripts.items():
            if found.use_checked(
                caption_id, result.clauses, result.language, result.languages_heard
            ):
                shown = self.shown.get(key)
                if shown is not None and shown.isVisible():
                    shown.refresh()

    # -- the session's ----------------------------------------------------------------

    def is_open(self, key: str) -> bool:
        """Whether app `key`'s transcript window is open and not minimised:
        its captions are being read there (a hidden caption window isn't
        paused meanwhile, polyglotic-hq 335)."""
        shown = self.shown.get(key)
        return shown is not None and shown.isVisible() and not shown.isMinimized()

    def set_length(self, length: TranscriptLength) -> None:
        """How far back every transcript's list goes (Settings > App): now,
        in each - an open one shows it at once."""
        if length is self.length:
            return
        self.length = length
        for key, found in self.transcripts.items():
            found.set_length(length)
            shown = self.shown.get(key)
            if shown is not None and shown.isVisible():
                shown.refresh()

    def _follow_look(self) -> None:
        """The caption windows' look changed: each transcript's reading
        lines follow it - pinyin above Chinese there too (369) - and its
        contrast and vibrance (481)."""
        for shown in self.shown.values():
            shown.list.set_reading(self.windows.look)
            shown.list.set_tone(self.windows.look)

    def dictionary_ready(self) -> None:
        """The dictionary's word-split data is read (`CaptionFeed`): saved
        words are found in the lines shown before it, and pinyin comes."""
        for shown in self.shown.values():
            shown.list.dictionary_ready()
        self.learning_changed(Changed.SAVED_WORDS.value)

    def learning_changed(self, what: str) -> None:
        """Learning changed: saved words' colours drawn again."""
        for shown in self.shown.values():
            shown.list.learning_changed(what)

    def set_theme(self, theme: style.Theme) -> None:
        """The window theme (today's, from `main`)."""
        self.theme = theme
        for shown in self.shown.values():
            shown.set_theme(theme)

    def restyle(self) -> None:
        """Windows' text size changed while they were open."""
        for shown in self.shown.values():
            shown.restyle()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self._show_notice()

    def set_connection(self, notice: Notice | None) -> None:
        self.notice = notice
        self._show_notice()

    def _notice(self) -> Notice | None:
        """What the transcripts say over their lists: Paused before anything
        about the connection (as the caption windows)."""
        return Notice.PAUSED if self.paused else self.notice

    def _show_notice(self) -> None:
        for shown in self.shown.values():
            shown.set_notice(self._notice())

    # -- the windows -------------------------------------------------------------------

    def show(self, key: str) -> None:
        """App `key`'s transcript window, opened beside its caption window -
        or brought forward."""
        found = self.transcripts.get(key)
        window = self.windows.windows.get(key)
        if found is None or window is None:
            return
        with spans.span("transcripts.show"):
            shown = self.shown.get(key)
            if shown is None:
                shown = self.shown[key] = self._open(key, found)
            shown.follow(
                window.label,
                window.choices.translate_into,
                window.choices.show_mic,
                self.windows.timing,
                self._you(),
            )
            shown.show()
            shown.raise_()
            shown.activateWindow()
        self.opened.emit()

    def _open(self, key: str, found: Transcript) -> TranscriptWindow:
        """App `key`'s transcript window, made (not shown) - with no caption
        window left for it (Quit's Save... for an app no longer captioned),
        named as its window last was, without the rail's panels."""
        window = self.windows.windows.get(key)
        shown = TranscriptWindow(
            key,
            found,
            self._label(key),
            self._choices(key),
            self.theme,
            self.learner,
            self._you(),
            self.windows.card,
            self._panels(key) if window is not None else [],
            self.save_folder,
        )
        # beside its caption window - or, joined, the joined window it's a column of
        joined = self.windows.joined_window
        anchor: QWidget | None = joined if joined is not None else window
        near = None
        if anchor is not None:
            corner = anchor.mapToGlobal(QPoint(0, 0))
            near = Rect(corner.x(), corner.y(), anchor.width(), anchor.height())
        areas = self._areas()
        found_area = area_for(near, areas) if near is not None else None
        area = found_area or (areas[0] if areas else Rect(0, 0, 1920, 1040))
        size = Size(style.px(DEFAULT_SIZE.width), style.px(DEFAULT_SIZE.height))
        showing = anchor is not None and anchor.isVisible()
        place = beside(near if showing else None, size, area)
        others = [w.geometry() for w in self.shown.values() if w.isVisible()]
        taken = [Rect(g.x(), g.y(), g.width(), g.height()) for g in others]
        place = clear_of(place, taken, area)
        shown.setGeometry(place.x, place.y, place.width, place.height)
        shown.changed.connect(lambda: self._changed(shown))
        shown.language_wanted.connect(lambda code: self._language(key, code))
        shown.timing_wanted.connect(self.timing_wanted)
        shown.set_notice(self._notice())
        shown.list.set_reading(self.windows.look)
        shown.list.set_tone(self.windows.look)
        shown.list.use_say_it(self.say_it)
        return shown

    def use_say_it(self, reading: SelectionReading) -> None:
        """Each transcript's selection menu says it aloud through `reading`
        (`main`'s: the PC's voices, polyglotic-hq 495)."""
        self.say_it = reading
        for shown in self.shown.values():
            shown.list.use_say_it(reading)

    def _language(self, key: str, code: str) -> None:
        """A transcript's language is its caption window's: set there."""
        window = self.windows.windows.get(key)
        if window is not None:
            window.set_language(code)  # its window says so: `follow`

    def _panels(self, key: str) -> list[Callable[[], QWidget]]:
        """What makes the rail's panels for app `key`'s transcript: the
        session's Languages (with its window's rows), Timing and Look."""
        views = self.panels
        if views is None:
            return []
        own = self._own.get(key)
        if own is None:
            own = self._own[key] = WindowLanguageView(
                self._window_language(key), partial(self._own_changed, key)
            )
        return [
            partial(LanguagesPanel, views.languages, own),
            partial(TimingPanel, views.timing),
            partial(LookPanel, views.look),
        ]

    def _window_language(self, key: str) -> WindowLanguage:
        window = self.windows.windows.get(key)
        if window is None:
            return self._own[key].value
        choices = window.choices
        return WindowLanguage(
            window.label.name, choices.translate_into, choices.show_mic
        )

    def _own_changed(self, key: str, value: WindowLanguage) -> None:
        """A transcript's "This window" rows changed: its caption window's
        choices, set there (it says so: `follow`)."""
        window = self.windows.windows.get(key)
        if window is not None:
            window.set_language(value.translate_into)
            window.set_show_mic(value.show_mic)

    def _changed(self, shown: TranscriptWindow) -> None:
        self.stored.by_key[shown.key] = shown.choices
        self._save.start()

    def _close(self, key: str) -> None:
        self._own.pop(key, None)
        shown = self.shown.pop(key)
        shown.close()
        shown.deleteLater()

    def _label(self, key: str) -> SourceLabel:
        """App `key`'s label: its caption window's, or as it last was."""
        window = self.windows.windows.get(key)
        if window is not None:
            return window.label
        return self._labels.get(key) or SourceLabel(key, YOU)

    # -- Quit (polyglotic-hq 334) -------------------------------------------------------

    def may_quit(self) -> bool:
        """Whether Quit (or Restart now) may go on: with three hours or the
        whole session kept, each transcript that needs saving is asked
        about - Save... saves it (its window made if it never was); Cancel,
        or a save not made, stays. Asked once: after a yes, True at once."""
        if self._quit_answered:
            return True
        if self.ask_at_quit and self.length is not TranscriptLength.NEWEST:
            for key, found in list(self.transcripts.items()):
                if not self.ask_at_quit:
                    break  # "Don't ask again" ticked for one: not for the rest
                if not found.needs_saving():
                    continue
                answer = self.ask(self._label(key).name, found.kept)
                if answer.choice is QuitChoice.CANCEL:
                    return False
                if answer.never_again:
                    self.ask_at_quit = False
                    self.asking_changed.emit(False)
                if answer.choice is QuitChoice.SAVE and not self._save_one(key, found):
                    return False
        self._quit_answered = True
        return True

    def _save_one(self, key: str, found: Transcript) -> bool:
        """Save transcript as... for app `key`'s transcript, from Quit."""
        shown = self.shown.get(key)
        if shown is None:
            shown = self.shown[key] = self._open(key, found)
        return shown.save_as()

    def save_now(self) -> None:
        """The transcripts' choices into the settings, beside today's."""
        self._save.stop()
        if self._store is None:
            return
        read = self._store.load()
        if read:
            self._read = read
        # nothing read - the file gone or unreadable for a moment - keeps
        # today's settings as last read rather than losing them (the rule
        # `Settings.update` follows; polyglotic-hq 121, 127)
        self._store.save({**self._read, STORED_KEY: self.stored.to_stored()})

    def close(self) -> None:
        if self._save.isActive():
            self.save_now()
        for key in list(self.shown):
            self._close(key)
