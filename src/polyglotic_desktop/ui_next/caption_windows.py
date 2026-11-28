"""The caption windows: one per app captioned, at most 3 (polyglotic-hq
DECISIONS.md #53; project 109's structure, sections 1.1, 2 and 8).

`CaptionWindows` keeps a `CaptionWindow` for each captioned source `main`
names (`set_captioned`: an app's key - its name - and its source id; or
"system" for everything the PC plays). Only the first `LIMIT` get one: a
4th app gets no window (the app picker that greys it out comes with Home,
109's step 4).

- **Captions:** every caption update goes to each window whose sources
  it's from: its app's, and the mic's while it shows my speech. A
  window's choices (place, text size, Panel or Strip, language or
  Original only, Show my speech here) are saved by its key, as one
  setting beside today's (`views.caption_window`), a moment after they
  change - today's values moved over the first time (`views.migration`).
- **The session:** what the windows can't decide alone they ask for -
  lock or hide all, the caption timing, stop captioning an app, "Looks
  wrong?" - and they follow what `main` hands them back: the look, the
  timing, second languages, labels, paused, the connection's state,
  notices, today's free minutes used, a busy time and the listening mark.
- **Signed out** (109's section 7): each window says so on its notice
  line for a moment, then the windows go - kept, with their captions,
  places and transcripts, and back when the learner signs in.
- **What the server needs:** each source's languages (`targets`: the
  window's language, or none for Original only; the mic's, every
  language of the windows showing my speech), each source's spoken
  language (`spoken_languages`: the window's, or Detect; the mic's, the
  one the windows showing my speech name, or Detect - polyglotic-hq 263)
  and whether any window shows my speech - the mic is captured only then
  (`mic_wanted`). A server that takes one spoken language for every
  window (before 2026-11-09: `set_spoken_per_source`) hears them all as
  the one they name, or as Detect when they differ - and a window naming
  one then says so (`CaptionWindow.spoken_fallback`).
- **A music player is heard on Detect** (polyglotic-hq 568; `music_player`):
  told a language, the speech model turns music into words like "The.",
  while on Detect it wrote nothing for any of 558's 580 pieces. So a music
  player's window starts on Detect whatever new windows start with, Home's
  Spoken language leaves it be, and its Detect isn't what new windows
  copy. The learner can still name a language in its own window.
- **Songs mode, behind the Lyrics switch** (polyglotic-hq 595, DECISIONS.md
  #248; decision 0287): a music player's window on Detect offers a Lyrics
  switch in its settings - the learner's one setting (`set_lyrics`, as
  Settings > Captions > Speech has it); turned on there, `lyrics_wanted`.
  `songs_sources` names the sources heard in songs mode
  (`core.listening.songs.heard_as_songs`): with the switch on, each music
  player's window on Detect - `main` hands them the speech pipeline.
- **Naming the language, suggested** (polyglotic-hq 317, decision 0109):
  a window whose app is heard as Detect and has spoken one language
  steadily (`core.listening.spoken.SteadyLanguage`, its own app's finished
  captions only) asks "Always hear it as ...?" (`spoken_nudge`); Not now is
  remembered by the window's key (`StoredWindows.declined_spoken`).
- **A window sets itself up** (polyglotic-hq 465, 449's 3A; 478): with
  `offer_set_up` (`main`'s), a caption window that opens asks its three
  language choices in it (`caption_set_up`) - every one, until the
  learner chooses Use as my default in one (`StoredWindows.set_up`; a
  window's chip brings it back, "Ask when a window opens"). A learner
  with windows from before it came is never asked. With Use as my
  default its answers are how new windows start: Start new windows like
  this goes on (`StoredWindows.start_like_this`), so a spoken language
  named there carries to the next window; any window's language chip
  turns it off or on again. Without it, a new window hears Detect, as
  before. A new learner's first window shows my speech too, its switch
  in the set-up (478); Home's sample's window - a trial - neither asks
  nor counts as the first.
- **Joined or separate** (109's 2a): "Join windows" puts every window
  into one (`joined_window`), a column each in the apps' order, at the
  place and height of the window it came from, as wide as they are
  together; "Separate windows" puts each back at its own place. Joined is
  remembered (`JoinedChoices`) until separated: a new app adds a column,
  and at one window left it is that app's own window. Windows start
  joined (polyglotic-hq 554): a second app's window joins the first's
  as it opens, until the learner separates them.
- **The lookup:** one card for every window (`lookup_card`), given the
  learning tools. A Learning action on it (Add to deck, Known, Save to,
  Remove) repaints only the captions holding that entry, in every window
  (`entry_changed`); any other Learning change repaints what shows.
- **Above a game that is itself always on top** (polyglotic-hq 141): such
  a game goes above them once it's clicked. While one is in front, the
  windows - then the lookup card - are put back on top (`keep_on_top`),
  never activated: when the foreground window changes (`front_changed`,
  from `platform` by way of `main`) and when a caption comes, at most once
  a second (`ON_TOP_EVERY_SEC`). Windows' band is `platform`'s (`ports.system.OnTop`).
  A lookup card open while a window shows after it goes back above it
  (`_card_on_top`): a window shown comes up at the top of the band.
- **Hidden too long** (polyglotic-hq 335, decision 0128): each window the
  learner hid has its own timer (`core.listening.hidden`); past the
  learner's limit (Settings > Captions > Behaviour: 5, 15 or 60 minutes,
  or never) its app's listening pauses - `paused_sources`, which `main`
  hands the speech pipeline: nothing of it is sent, as while paused, and
  the mic's only once every window showing my speech is paused. Showing
  the windows starts it again. While a hidden window still captions its
  app's speech, Home and the tray say so (`sight`, `sight_changed`); a
  learner who asked for it gets the windows back when speech starts in
  one (`show_wanted`).
- **Out of the way of the app's own dialogs** (polyglotic-hq 579): always
  on top, the windows sat over Save transcript's and the Anki export's
  save dialogs - their Name, Save and Cancel on Linux's KDE - and would
  take clicks meant for them. So while a modal dialog of the app's is
  open (a save or colour dialog, a message box: whatever blocks the
  windows - Qt tells each, `WindowBlocked`, a native dialog included),
  they step aside: hidden, as by the learner's Hide, and shown again as
  they were once it closes (`aside`, looked at every `DIALOG_CHECK_MS`
  until then). Hidden the same way on every OS: Windows, a Mac and X11
  (Linux's) all show a hidden window again where it was, while lowering
  it isn't something every desktop lets an app do. It isn't the
  learner's Hide: no window's timer starts, Home and the tray say
  nothing of it, and captions keep coming to the windows, there when
  they're back. A box over one window only (window-modal: Read it's
  better voice) blocks no caption window, and they stay.

Holds caption text through its windows: never log it.
"""

import html
import logging
import time
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from functools import partial
from time import perf_counter

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.display import ListeningMark
from polyglotic_desktop.core.listening.hidden import HiddenWindows, Sight
from polyglotic_desktop.core.listening.pace import PaceReading
from polyglotic_desktop.core.listening.playout import (
    Ahead,
    Playout,
    PlayoutRules,
    ReadingPath,
    Split,
    each_character,
)
from polyglotic_desktop.core.listening.preset_reading import preset_sizes
from polyglotic_desktop.core.listening.recheck import RecheckResult
from polyglotic_desktop.core.listening.respeaking import (
    recognition_missed,
    respoken_for,
)
from polyglotic_desktop.core.listening.settings import agreed_language
from polyglotic_desktop.core.listening.settling import SETTLE_AFTER_SEC
from polyglotic_desktop.core.listening.songs import heard_as_songs
from polyglotic_desktop.core.listening.sources import SAMPLE, SourceId, SourceLabel
from polyglotic_desktop.core.listening.spoken import SteadyLanguage
from polyglotic_desktop.core.listening.timing import (
    MAX_WAIT_FOR_TEXT_SEC,
    CaptionId,
    CaptionMode,
)
from polyglotic_desktop.core.releases import flags
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.core.shared.open_beta import UsageMeter
from polyglotic_desktop.perf import spans, trace
from polyglotic_desktop.ports.capture import CaptureIssue
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ports.system import OnTop
from polyglotic_desktop.ports.word_breaks import WordBreaks
from polyglotic_desktop.ports.word_classes import ClassEvidenceFor
from polyglotic_desktop.ui_next import capture_status
from polyglotic_desktop.ui_next.caption_window import (
    ACCENT,
    HINTED_LINES,
    READING_HINT_SEC,
    CaptionWindow,
    notice_text,
    reading_hint,
    to_rect,
    word_hint,
    work_areas,
)
from polyglotic_desktop.ui_next.dictation_key import key_words
from polyglotic_desktop.ui_next.joined_window import JoinedWindow
from polyglotic_desktop.ui_next.languages import (
    taken_off,
    target_languages,
)
from polyglotic_desktop.ui_next.lookup_card import Action, LookupCard
from polyglotic_desktop.ui_next.pointer_watch import PointerWatch
from polyglotic_desktop.ui_next.reading_lines import language_of
from polyglotic_desktop.ui_next.resize_handle import PanelResizeCursor
from polyglotic_desktop.ui_next.selection_reading import SelectionReading
from polyglotic_desktop.ui_next.settings_popover import KeyState
from polyglotic_desktop.ui_next.views import placement
from polyglotic_desktop.ui_next.views.app_choices import AppChoice
from polyglotic_desktop.ui_next.views.caption_window import (
    LIMIT,
    NOTICE_SEC,
    ORIGINAL_ONLY,
    STORED_KEY,
    CaptionLook,
    JoinedChoices,
    Notice,
    WindowChoices,
    slowed_now,
    stepped,
)
from polyglotic_desktop.ui_next.views.captions import CAPTION_TEXT_SIZES
from polyglotic_desktop.ui_next.views.lookup import Learner
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.placement import Preset, Rect
from polyglotic_desktop.ui_next.views.preset_menu import PresetMenu
from polyglotic_desktop.ui_next.views.respeaking import HINT_SEC, MIC_LEVEL_MS
from polyglotic_desktop.ui_next.views.sound import level_of

SAVE_AFTER_MS = 400
"""A window's choices are saved this long after the last change (a run of
text size steps is one save)."""
ON_TOP_EVERY_SEC = 1.0
"""A caption puts the windows back on top of a game at most this often."""
HIDDEN_TICK_MS = 1000
"""How often, while a window is hidden, its timer and what Home and the
tray say of it are looked at."""
DIALOG_CHECK_MS = 250
"""While the windows are out of the way of a dialog (`aside`), how often
they look whether it has closed."""


def _tr(text: str) -> str:
    return QApplication.translate("CaptionWindows", text)


def undo_line(text: str) -> str:
    """A notice line's words with Undo after them, a link whose click is
    the step "undo" (polyglotic-hq 587) - the words escaped: a preset's name
    is the learner's."""
    undo = html.escape(_tr("Undo"))
    return (
        f'{html.escape(text)} &nbsp;<a href="undo" style="color: {ACCENT};'
        f' text-decoration: none; font-weight: 600;">{undo}</a>'
    )


SUBTITLES_SAID_SEC = 3.0
"""How long a window says it moved for Video's subtitles, or back (556):
a few seconds, half a brief notice's."""


def subtitle_text_size(share: float, area: Rect, text_px: float) -> float:
    """A caption window's text size for Video's subtitles: their text
    `share` of the screen's height (polyglotic-hq 556), within a caption
    window's sizes, to two places."""
    size = share * area.height / max(1.0, text_px)
    low, high = CAPTION_TEXT_SIZES
    return round(min(high, max(low, size)), 2)


log = logging.getLogger(__name__)
"""Each window shown, hidden or closed, and why - by its place in the list,
never its app's name (polyglotic-hq 272: catching "the caption window
will minimize")."""


class CaptionWindows(QObject):
    look_changed = Signal()
    """The look changed (`set_look`): transcripts follow its reading
    lines (369)."""
    languages_changed = Signal()
    """A window's language changed, or the windows or who shows my speech
    did: the server's settings follow (`targets`)."""
    sizes_changed = Signal()
    """A window's caption size or translation size changed (655): Settings >
    Look follows."""
    mic_wanted = Signal(bool)
    """Whether any window shows my speech: the mic is captured only then."""
    lock_wanted = Signal()
    unlock_wanted = Signal()
    """A locked window's Unlock, where the mouse rested on its lock (398)."""
    unlock_told = Signal()
    """The first lock on Linux said at length how to unlock (570)."""
    hide_wanted = Signal()
    stop_wanted = Signal(str)
    report_wanted = Signal()
    """A caption window's "Report a problem" (an alpha tester's, 275)."""
    """An app's key: stop captioning it (its window's close)."""
    transcript_wanted = Signal(str)
    all_settings_wanted = Signal()
    opacity_wanted = Signal(float)
    links_wanted = Signal(bool, tuple)
    class_colours_wanted = Signal(bool)
    """A window's word links button: on or off, for every window (249, F9),
    with that window's reading lines (446)."""
    quiet_wanted = Signal(bool, tuple)
    """A window's quiet view button: on or off, for every window, with that
    window's reading lines (477)."""
    quiet_word_wanted = Signal(str, bool)
    """A window's popover: one of the quiet view's chosen words ticked or
    not, for every window (477)."""
    fill_wanted = Signal(bool)
    """A window's filled lines button: on or off, for every window (372)."""
    aligned_wanted = Signal(bool)
    """A window's parts lined up button: on or off, for every window (372)."""
    said_colours_wanted = Signal(bool)
    """A window's popover: linked words in what was said in their link's
    colour, on or off, for every window (431)."""
    lyrics_wanted = Signal(bool)
    """A music player's window: the Lyrics switch on or off - songs mode
    for every music player on Detect (595)."""
    translation_colours_wanted = Signal(bool)
    """And in the translation (431)."""
    timing_wanted = Signal(str)
    path_wanted = Signal(str)
    """The translation's timing picked on a timing chip: a `ReadingPath`'s
    value (Learning's after or with, polyglotic-hq 593)."""
    app_wanted = Signal(str, str)
    """A window's key, and an app's name: caption that app there instead
    (its settings' Captioning list, F12, 249)."""
    second_language_wanted = Signal(str, str)
    """A window's "Lines already in ...": a translation language, and the
    language its lines already in it are shown in ("": left as they are) -
    the session's second languages, kept by language (263)."""
    joined_changed = Signal(bool)
    """The windows now show joined as one (True), or each on its own."""
    window_shown = Signal()
    """A caption window or joined column became visible."""
    front_changed = Signal()
    """Another app's window came to the foreground (from any thread): the
    windows go back on top if it's a game that is itself always on top."""
    paused_changed = Signal()
    """The sources whose listening is paused - their windows hidden too
    long - changed (`paused_sources`)."""
    sight_changed = Signal()
    """A window became shown, hidden, captioning while hidden or paused
    (`sight`): Home and the tray say it."""
    show_wanted = Signal()
    """Speech started in a hidden window and the learner asked for the
    windows back then (the look's `show_on_speech`)."""
    set_up_done = Signal()
    """A window's set-up went (465; 478: on every open until Use as my
    default)."""
    # the preset dropdown's (polyglotic-hq 556), passed on from any window
    preset_wanted = Signal(str)
    lines_wanted = Signal(str)
    video_lines_wanted = Signal(int)
    long_lines_wanted = Signal(str)
    readings_wanted = Signal(bool, tuple)
    customise_wanted = Signal()
    preset_step = Signal(str)
    """A step on the chosen preset - save, discard, undo... (587)."""
    subtitles_changed = Signal(float, float)
    """Video's subtitles' text size and width share, changed in a window
    (A- / A+, a resize): saved into the preset (556)."""
    translations_wanted = Signal()
    """A window was given a language to translate into while every window
    showed the original only: translations show again (556)."""

    def __init__(
        self,
        store: SettingsStore | None,
        mic: SourceId | None = None,
        areas: Callable[[], list[Rect]] = work_areas,
        parent: QObject | None = None,
        keys: KeyState | None = None,
        learner: Learner | None = None,
        on_top: OnTop | None = None,
        offer_set_up: bool = False,
        watch_pointer: bool = False,
    ) -> None:
        """`keys`: whether Esc or a mouse button is held anywhere (from
        `platform`, by way of `main`), for closing a settings popover;
        `learner`: the learning tools, for the windows' highlights and the
        lookup; `on_top`: Windows' always-on-top band (`keep_on_top`);
        `offer_set_up`: a window that opens asks its languages, until Use as
        my default (465, 478); `watch_pointer`: the windows told of the
        mouse while the app is in the background, which a Mac doesn't do
        (`pointer_watch`, 515)."""
        super().__init__(parent)
        self.offer_set_up = offer_set_up
        self.keys = keys
        self.on_top = on_top
        self._panel_cursor = (
            getattr(on_top, "refresh_panel_cursor", None) if watch_pointer else None
        )
        self._on_top_at = -ON_TOP_EVERY_SEC
        self.front_changed.connect(self.keep_on_top, Qt.ConnectionType.QueuedConnection)
        self._store = store
        self.learner = learner
        self.class_evidence: ClassEvidenceFor | None = None
        self.card = (
            LookupCard(learner, keys, act=self._learning_action)
            if learner is not None
            else None
        )
        if self.card is not None:
            self.card.opened.connect(self._looked_up)
        self.pointer_watch = (
            PointerWatch(self.under_the_mouse, self) if watch_pointer else None
        )
        if self.pointer_watch is not None:
            self.pointer_watch.start()
        self._acting = False
        self._window_mic_pace: dict[CaptionWindow, PaceReading] = {}
        self._shown_pace: (
            tuple[dict[str, PaceReading], dict[str, PaceReading]] | None
        ) = None
        self._read: dict[str, object] = store.load() if store else {}
        """The settings file as last read, for `save_now`."""
        read = stored_windows(self._read)
        self.taken_off = taken_off(
            c.translate_into for c in [read.last, *read.by_key.values()]
        )
        """Saved languages taken off the list (DECISIONS.md #40), found at
        this start: `main` says so on Home. Saved without them at once, so
        it's said once."""
        self.stored = read.only_offered({str(c) for c in target_languages()})
        self.mic = mic
        self.windows: dict[str, CaptionWindow] = {}
        self.say_it: SelectionReading | None = None
        """Reads a selection aloud from its card (polyglotic-hq 495)."""
        self._reporting = False  # "Report a problem" on the strips (275)
        self._usage: UsageMeter | None = None  # a capped plan's ring (684)
        self.joined_window: JoinedWindow | None = None
        """The windows joined as one, while they are (two or more)."""
        self._order: list[str] = []  # the apps' order: the columns'
        self.look = CaptionLook()
        self.timing = CaptionMode.WHOLE
        self.longest_wait = MAX_WAIT_FOR_TEXT_SEC
        self.settle_after = SETTLE_AFTER_SEC
        self.second_languages: dict[Language, Language] = {}
        self.spoken_per_source: bool | None = None
        """Whether the server uses each window's spoken language (its
        `welcome.source_fields`); None until a server has said."""
        self.labels: dict[SourceId, SourceLabel] = {}
        self.you = "You"
        self.locked = False
        self.tell_how_to_unlock = False
        """The next lock says at length how to unlock (`unlock_told`): the
        first on Linux (polyglotic-hq 570)."""
        self.unlock_keys = "Ctrl+Alt+L"
        self.live_keys = ""
        """Back to live's hotkey as the OS writes it ("" none: 567)."""
        """The hotkey that unlocks, as it is now ("" if another app has it)."""
        self.unlock_spot = False
        """A locked window's corner takes the mouse itself (`set_unlock_spot`)."""
        self.app_choices: Callable[[str], list[AppChoice]] = lambda key: []
        """The apps the window of a key can caption instead (`main`'s)."""
        self.music_player: Callable[[str], bool] = lambda key: False
        """Whether the app of a key is a music player (the known-apps list's,
        `main`'s): its window is heard on Detect unless the learner names a
        language in it - never the one new windows start with or Home names
        for every window (polyglotic-hq 568)."""
        self.lyrics = False
        """The learner's Lyrics setting, as `main` last handed it
        (`set_lyrics`; 595)."""
        self.hidden = False
        self.paused = False
        self.connection: tuple[Notice | None, float | None] = (None, None)
        self.minutes_used = False
        self.failing = False
        self.unstable = False
        self.busy = False
        self.signed_out = False
        """Gone while not signed in - once each window has said so on its
        notice line (`_going`) - and kept for when the learner signs in."""
        self._going = QTimer(self, singleShot=True, interval=round(NOTICE_SEC * 1000))
        self._going.timeout.connect(self._gone)
        self.aside = False
        """Out of the way while one of the app's own modal dialogs is open
        (579): hidden, and back when it closes."""
        self._dialog_open = QTimer(self, interval=DIALOG_CHECK_MS)
        self._dialog_open.timeout.connect(self._step_aside)
        self._areas = areas
        self.reading: Callable[[str], bool] = lambda key: False
        """Whether app `key`'s transcript window is open: a hidden window
        being read there isn't paused (`main` hands it the transcripts')."""
        self.clock: Callable[[], float] = time.monotonic
        """The hidden windows' timers' clock (seconds)."""
        self.word_split: Split = each_character
        """A run of Chinese as words, for the playout: `main` hands it the
        learner's dictionary's word split."""
        self.playout = Playout(split=lambda run: self.word_split(run))
        self.word_breaks: WordBreaks | None = None
        """Steady's and Calm's words, shown at the pace they were said
        (`core.listening.playout`, decision 0245): every window's."""
        self.word_clock: Callable[[], float] = perf_counter
        """The clock the caption updates' speech times are on."""
        self.two_zones = True
        """Whether the paced modes show two zones (`set_two_zones`)."""
        self.cards = True
        """Whether the paced modes show the card stack (`set_cards`;
        decision 0260): it takes the two zones' place."""
        self.path = ReadingPath.BOTH
        self.respeaking: tuple[bool, str, bool] = (False, "", False)
        """Re-speaking on, its key in words, and whether that key is its own
        (`set_respeaking`)."""
        self.preset_my_speech: bool | None = None
        """The active preset's own-speech default for newly opened windows
        (Conversation on, Video off, others None so the first window keeps its
        default)."""
        self.read_mic_peak: Callable[[], float | None] = lambda: None
        """Current mic peak (0..1) while own-speech capture runs; None when idle."""
        self._mic_levels = QTimer(self, interval=MIC_LEVEL_MS.value)
        self._mic_levels.timeout.connect(self._poll_mic_level)
        self._visited: list[SourceId] = []
        self._respeaking_sources: frozenset[SourceId] | None = None
        self._word_due = QTimer(self, singleShot=True)
        self._word_due.setTimerType(Qt.TimerType.PreciseTimer)
        self._word_due.timeout.connect(self.release_words)
        self.show_on_speech = self.look.show_on_speech
        self.sights = HiddenWindows(self.look.pause_hidden_after)
        self._sights_said: dict[str, Sight] = {}
        self._paused_said: frozenset[SourceId] = frozenset()
        self._hidden_tick = QTimer(self, interval=HIDDEN_TICK_MS)
        self._hidden_tick.timeout.connect(self.tick)
        self._marks: dict[str, ListeningMark] = {}
        self._steady: dict[str, SteadyLanguage] = {}
        self.save_preset_language: Callable[[str, str, str], None] | None = None
        self._preset_languages: Mapping[str, Mapping[str, str]] = {}
        self._applying_preset_languages = False
        """Each window's app heard as Detect: the language it speaks
        steadily, for the window's question (317)."""
        self.preset_menu = PresetMenu()
        """The presets as `main` last said: every window's chip (556)."""
        self.subtitles: tuple[float, float] | None = None
        """Video's subtitles' text size and width share while they're on
        (`set_subtitles`, 556); None: each window where the learner put it."""
        self._own: dict[str, WindowChoices] = {}
        """While subtitles are on, each window's own choices - its place and
        text size from before, kept and saved as its own."""
        self.original_only = False
        """Every window shows the original only (a preset's Show, 556)."""
        self._save = QTimer(self, singleShot=True, interval=SAVE_AFTER_MS)
        self._save.timeout.connect(self.save_now)
        if (self.stored.first_use and self.stored.by_key) or self.taken_off:
            self.save_now()  # today's values moved over, or a language taken off: once

    # -- which windows ----------------------------------------------------------------

    def set_captioned(self, captioned: Sequence[tuple[str, SourceId]]) -> None:
        """The sources captioned, in order, each with its key: a window for
        each of the first LIMIT; any other window closes."""
        wanted = list(dict(captioned).items())[:LIMIT]
        self._order = [key for key, _ in wanted]
        keys = {key for key, _ in wanted}
        changed = False
        for key in [k for k in self.windows if k not in keys]:
            self._close(key)
            changed = True
        for index, (key, source) in enumerate(wanted):
            found = self.windows.get(key)
            if found is not None and found.source == source:
                continue
            if found is not None:
                self._close(key)
            self.windows[key] = self._open(key, source, index)
            changed = True
        if not changed:
            return
        self.stored.first_use = False  # windows from now on are new ones
        for window in self.windows.values():
            window.windows = len(self.windows)
            self._original(window)  # a new one: as every window shows (556)
        self._arrange()
        self._place_subtitles()
        self._spoken_fallbacks()
        self.languages_changed.emit()
        self.mic_wanted.emit(self.show_mic_anywhere)
        self._sync_mic_levels()
        self._say_sights()

    def use_say_it(self, reading: SelectionReading) -> None:
        """Say it on each window's selection card reads through `reading`
        (`main`'s: the PC's voices, polyglotic-hq 495)."""
        self.say_it = reading
        for window in self.windows.values():
            window.use_say_it(reading)

    def _open(self, key: str, source: SourceId, index: int) -> CaptionWindow:
        choices = self.stored.by_key.get(key)
        if choices is None:
            choices = self.stored.by_key[key] = self.stored.for_new(
                index,
                key,
                self.offer_set_up,
                self.music_player(key),
                my_speech=self.preset_my_speech,
            )
            self._save.start()
        label = self.labels.get(source) or SourceLabel(key, ACCENT)
        window = CaptionWindow(
            key,
            source,
            choices,
            label,
            replace(self.look, opacity=choices.opacity),
            index,
            self.mic,
            self._areas,
            keys=self.keys,
            learner=self.learner,
            card=self.card,
        )
        window.view.class_evidence = self.class_evidence
        window.view.word_breaks = self.word_breaks
        if self._panel_cursor is not None:
            window.resize_hint = PanelResizeCursor(window, self._panel_cursor)
        window.two_zones = self.two_zones
        window.cards_on = self.cards
        window.card_split = lambda run: self.word_split(run)
        window.path = self.path
        window.faint_ahead = self._faint_ahead()
        window.set_timing(self.timing)
        if self.save_preset_language is not None:
            window.save_preset_language = partial(self.save_preset_language, key)
        window.longest_wait = self.longest_wait
        window.view.set_settle_after(self.settle_after)
        window.set_second_languages(self.second_languages)
        window.set_labels(self.labels, self.you)
        window.set_paused(self.paused)
        window.set_minutes_used(self.minutes_used)
        window.set_failing(self.failing)
        if self._shown_pace is not None:
            self._set_window_pace(window, self._shown_pace)
        window.set_unstable(self.unstable)
        window.set_connection(*self.connection)
        window.set_unlock_keys(self.unlock_keys)
        window.set_live_keys(self.live_keys)
        window.unlock_spot.catch(self.unlock_spot)
        window.set_locked(self.locked)
        window.use_say_it(self.say_it)
        window.music_player = self.music_player(key)
        window.set_lyrics(self.lyrics)
        window.lyrics_wanted.connect(self.lyrics_wanted)
        window.set_start_like_this(self.stored.start_like_this)
        window.start_like_this_wanted.connect(
            lambda on: self._start_like_this(window, on)
        )
        window.set_asks_set_up(self.offer_set_up and not self.stored.set_up)
        window.ask_set_up_wanted.connect(self.set_asks_set_up)
        window.set_up_done.connect(
            lambda as_default: self._set_up_done(window, as_default)
        )
        if self._asks_set_up() and source != SAMPLE:  # the sample is a trial (478)
            window.ask_set_up()
        self._marks[key] = ListeningMark()
        if self.hidden:  # opened hidden: its timer starts now
            self.sights.hide(key, self.clock())
            self._hidden_tick.start()
        window.changed.connect(lambda: self._changed(window))
        window.language_changed.connect(self._spoken_fallbacks)
        window.language_changed.connect(self._keep_subtitle_height)
        window.language_changed.connect(self.languages_changed)
        window.language_size_wanted.connect(
            lambda language, size: self.set_language_size(window, language, size)
        )
        window.size_languages_changed.connect(
            lambda: self._size_languages_changed(window)
        )
        window.set_language_sizes(choices.language_sizes)
        window.second_wanted.connect(self.second_language_wanted)
        window.mic_changed.connect(self._mic_changed)
        window.lock_wanted.connect(self.lock_wanted)
        window.unlock_wanted.connect(self.unlock_wanted)
        window.hide_wanted.connect(self.hide_wanted)
        window.all_settings_wanted.connect(self.all_settings_wanted)
        window.opacity_wanted.connect(
            lambda opacity: self._set_opacity(window, opacity)
        )
        window.links_wanted.connect(self.links_wanted)
        window.class_colours_wanted.connect(self.class_colours_wanted)
        window.quiet_wanted.connect(self.quiet_wanted)
        window.quiet_word_wanted.connect(self.quiet_word_wanted)
        window.fill_wanted.connect(self.fill_wanted)
        window.aligned_wanted.connect(self.aligned_wanted)
        window.said_colours_wanted.connect(self.said_colours_wanted)
        window.translation_colours_wanted.connect(self.translation_colours_wanted)
        window.set_presets(self.preset_menu)
        window.preset_wanted.connect(self.preset_wanted)
        window.preset_step.connect(self.preset_step)
        window.lines_wanted.connect(self.lines_wanted)
        window.video_lines_wanted.connect(self.video_lines_wanted)
        window.long_lines_wanted.connect(self.long_lines_wanted)
        window.readings_wanted.connect(self.readings_wanted)
        window.customise_wanted.connect(self.customise_wanted)
        window.app_choices = lambda: self.app_choices(key)
        window.recent_spoken = self.recent_spoken
        window.spoken_declined.connect(lambda code: self._spoken_declined(window, code))
        window.spoken_unanswered.connect(
            lambda code: self._spoken_unanswered(window, code)
        )
        window.app_wanted.connect(lambda name: self.app_wanted.emit(key, name))
        window.timing_wanted.connect(self.timing_wanted)
        window.path_wanted.connect(self.path_wanted)
        self._follow_respeaking(window)
        window.stop_wanted.connect(lambda: self.stop_wanted.emit(window.key))
        window.report_wanted.connect(self.report_wanted)
        window.set_reporting(self._reporting)
        window.set_usage(self._usage)
        window.transcript_wanted.connect(
            lambda: self.transcript_wanted.emit(window.key)
        )
        window.join_wanted.connect(lambda: self.join(window.key))
        window.installEventFilter(self)  # a dialog blocking it (579)
        return window  # shown by _arrange: on its own, or as a column

    def _close(self, key: str) -> None:
        window = self.windows.pop(key)
        self._window_mic_pace.pop(window, None)
        if window.source in self._visited:
            self._visited.remove(window.source)
        log.info("caption window %d closed: its app no longer captioned", window.index)
        self._marks.pop(key, None)
        self.sights.forget(key)
        if self.joined_window is not None:
            self.joined_window.remove(window)
        window.close()
        window.deleteLater()

    # -- joined or separate ---------------------------------------------------------------

    def join(self, key: str | None = None) -> None:
        """Every window into one, a column each in the apps' order, at the
        place and height of `key`'s window (Home: the first's), as wide as
        they are together - clamped to the screen (109's 2a). Each window's
        own place is kept, for separating."""
        ordered = self._ordered()
        if self.joined_window is not None or len(ordered) < 2:
            return
        with spans.span("caption_windows.join"):
            commanding = self.windows[key] if key in self.windows else ordered[0]
            self.stored.joined = JoinedChoices(
                True,
                commanding.choices.preset,
                self._joined_place(commanding, ordered),
                self.stored.joined.shares,  # the columns' widths, as last dragged
                chosen=True,
            )
            self._arrange()
        self._save.start()

    def separate(self) -> None:
        """Each window back at its own place - and new ones open on their
        own, the learner's choice (554), until they join them again."""
        if not self.stored.joined.on:
            return
        with spans.span("caption_windows.separate"):
            self.stored.joined = replace(self.stored.joined, on=False, chosen=True)
            self._arrange()
        self._save.start()

    def _ordered(self) -> list[CaptionWindow]:
        return [self.windows[key] for key in self._order if key in self.windows]

    def _joined_place(
        self, commanding: CaptionWindow, ordered: list[CaptionWindow]
    ) -> Rect:
        """Where a joined window of `ordered` goes: from `commanding`'s place
        on the screen - a column's own geometry is its place in its joined
        window, so the joined window placed again (`_place_subtitles`, as a
        second app's window joins) went to the screen's top left
        (polyglotic-hq 572). A column already: from its joined window's own
        place, which it keeps - centred on the first column's centre, a
        bottom centre joined window moved half its width left each time
        and sat at the screen's left (586)."""
        host = commanding.host
        if host is not None:
            return to_rect(host.geometry())
        start = to_rect(QRect(commanding.mapToGlobal(QPoint(0, 0)), commanding.size()))
        areas = self._areas()
        area = placement.area_for(start, areas) or (areas[0] if areas else start)
        width = sum(window.width() for window in ordered)
        return placement.joined(start, commanding.choices.preset, width, area)

    def _arrange(self) -> None:
        """Joined - while it's chosen and there are two windows or more - or
        each window on its own; shown unless hidden."""
        ordered = self._ordered()
        was_joined = self.joined_window is not None
        if self.stored.joined.on and len(ordered) >= 2:
            joined = self.joined_window
            if joined is None:
                joined = self.joined_window = self._joined(ordered)
            joined.set_columns(ordered)
            joined.setVisible(not self.out_of_sight)
            log.info(
                "caption windows joined, %d columns: %s",
                len(ordered),
                "hidden" if self.out_of_sight else "shown",
            )
        else:
            if self.joined_window is not None:
                joined, self.joined_window = self.joined_window, None
                joined.set_columns([])  # each a window of its own again
                joined.close()
                joined.deleteLater()
            for window in ordered:
                window.setVisible(not self.out_of_sight)
            log.info(
                "caption windows on their own, %d: %s",
                len(ordered),
                "hidden" if self.out_of_sight else "shown",
            )
        self._card_on_top()
        if was_joined != (self.joined_window is not None):
            self.joined_changed.emit(not was_joined)

    def _joined(self, ordered: list[CaptionWindow]) -> JoinedWindow:
        choices = self.stored.joined
        joined = JoinedWindow(choices, self._areas, self.keys)
        if self._panel_cursor is not None:
            joined.resize_hint = PanelResizeCursor(joined, self._panel_cursor)
        joined.set_locked(self.locked)
        joined.set_unlock_keys(self.unlock_keys)
        joined.place_at(choices.geometry or self._joined_place(ordered[0], ordered))
        joined.changed.connect(lambda: self._joined_moved(joined))
        joined.separate_wanted.connect(self.separate)
        joined.lock_wanted.connect(self.lock_wanted)
        joined.all_settings_wanted.connect(self.all_settings_wanted)
        joined.opacity_wanted.connect(self._set_joined_opacity)
        joined.installEventFilter(self)  # a dialog blocking it (579)
        return joined

    def _joined_moved(self, joined: JoinedWindow) -> None:
        self.stored.joined = joined.choices
        self._save.start()

    # -- their choices ------------------------------------------------------------------

    def _changed(self, window: CaptionWindow) -> None:
        if self._applying_preset_languages:
            return
        before = self.stored.by_key.get(window.key)
        spoken = window.choices.spoken_language
        if before is None or before.spoken_language != spoken:
            self.stored.spoken_named(spoken)  # first in the lists (317)
            steady = self._steady.get(window.key)
            if steady is not None:  # heard afresh from the next caption
                steady.start_again()
        if self.original_only and window.choices.translate_into != ORIGINAL_ONLY:
            self.translations_wanted.emit()  # a language picked: shown again (556)
        choices = self._kept_own(window)
        if before is not None:
            overridden = self._preset_languages.get(window.key, {})
            choices = replace(
                choices,
                **{field: getattr(before, field) for field in overridden},
            )
        self.stored.by_key[window.key] = choices
        last = choices
        if self.music_player(window.key):  # new windows don't start on its Detect
            last = replace(last, spoken_language=self.stored.last.spoken_language)
        self.stored.last = last
        size_moved = before is None or before.language_sizes != choices.language_sizes
        info_changed = (
            before is None or before.show_caption_info != choices.show_caption_info
        )
        self._save.start()
        if size_moved:
            self.sizes_changed.emit()
        if info_changed:
            self._keep_subtitle_height()

    def _set_opacity(self, window: CaptionWindow, opacity: float) -> None:
        """Change and save only this caption column's panel opacity."""
        chosen = round(min(1.0, max(0.0, opacity)), 2)
        if chosen == window.choices.opacity:
            return
        window.choices = replace(window.choices, opacity=chosen)
        window.set_look(replace(self.look, opacity=chosen))
        self._changed(window)

    def _set_joined_opacity(self, opacity: float) -> None:
        """A joined shell represents all of its columns, so its slider sets each."""
        for window in self.windows.values():
            self._set_opacity(window, opacity)

    # -- presets (polyglotic-hq 556) ------------------------------------------------------

    def set_preset_my_speech(self, my_speech: bool | None) -> None:
        """The active preset's own-speech default for newly opened windows."""
        self.preset_my_speech = my_speech

    def set_presets(self, menu: PresetMenu) -> None:
        """The presets as they are now: every window's chip and dropdown."""
        count_changed = self.preset_menu.video_lines_shown != menu.video_lines_shown
        sides_changed = self.preset_menu.show != menu.show
        self.preset_menu = menu
        for window in self.windows.values():
            window.set_presets(menu)
        if count_changed or sides_changed:
            self._keep_subtitle_height(fit=count_changed)

    def set_original_only(self, on: bool) -> None:
        """Every window shows the original only - its translation language
        kept, and given back when it's off (a preset's Show)."""
        if on == self.original_only:
            return
        self.original_only = on
        for window in self.windows.values():
            self._original(window)
        self._save.start()

    def set_preset_languages(self, languages: Mapping[str, Mapping[str, str]]) -> None:
        """Apply the preset's language choices over each window's saved choices."""
        previous = self._preset_languages
        if languages == previous:
            return
        self._preset_languages = languages
        for key in previous.keys() | languages.keys():
            window = self.windows.get(key)
            if window is not None and previous.get(key) != languages.get(key):
                self._apply_preset_languages(window)

    def _apply_preset_languages(self, window: CaptionWindow) -> None:
        key = window.key
        base = self.stored.by_key[key]
        choices = self._preset_languages.get(key, {})
        spoken = choices.get("spoken_language", base.spoken_language)
        target = choices.get(
            "translate_into", self.stored.kept_languages.get(key, base.translate_into)
        )
        spoken = spoken or None
        if spoken != window.choices.spoken_language:
            self.stored.spoken_named(spoken)
            if steady := self._steady.get(key):
                steady.start_again()
            self._save.start()
        self._applying_preset_languages = True
        try:
            window.set_spoken_language(spoken)
            window.set_language(ORIGINAL_ONLY if self.original_only else target)
        finally:
            self._applying_preset_languages = False

    def _original(self, window: CaptionWindow) -> None:
        if window.key in self._preset_languages:
            self._apply_preset_languages(window)
            return
        kept = self.stored.kept_languages
        language = window.choices.translate_into
        if self.original_only and language != ORIGINAL_ONLY:
            kept[window.key] = language
            window.set_language(ORIGINAL_ONLY)
        elif not self.original_only and language == ORIGINAL_ONLY:
            back = kept.pop(window.key, None)
            if back is not None:  # else it showed the original only by its own choice
                window.set_language(back)
        elif not self.original_only:
            kept.pop(window.key, None)

    def current_language_sizes(self) -> tuple[tuple[Language, float], ...]:
        """The first window's current languages and their sizes for Look."""
        ordered = self._ordered()
        if ordered:
            choices = ordered[0].choices
            codes = ordered[0].size_languages()
        else:
            choices = self.stored.last
            codes = tuple(
                dict.fromkeys(code for code in (choices.spoken, choices.target) if code)
            )
        return tuple((code, choices.language_sizes.get(code, 1.0)) for code in codes)

    def set_current_language_size(self, index: int, size: float) -> None:
        pair = self.current_language_sizes()
        if index < len(pair):
            ordered = self._ordered()
            if ordered:
                self.set_language_size(ordered[0], pair[index][0], size)

    def _size_languages_changed(self, window: CaptionWindow) -> None:
        pending = self.stored.pending_spoken_sizes.get(window.key)
        if pending is not None:
            spoken = window.choices.spoken or window.heard_language()
            if spoken is not None and spoken != window.choices.target:
                del self.stored.pending_spoken_sizes[window.key]
                if spoken not in window.choices.language_sizes:
                    self.set_language_size(window, str(spoken), pending)
                self._save.start()
        self.sizes_changed.emit()

    def set_language_size(
        self, window: CaptionWindow, language: str, size: float
    ) -> None:
        code = Language(language)
        low, high = CAPTION_TEXT_SIZES
        chosen = round(min(high, max(low, size)), 2)
        sizes = dict(window.choices.language_sizes)
        if chosen == sizes.get(code, 1.0):
            return
        sizes[code] = chosen
        window.choices = replace(window.choices, language_sizes=sizes)
        window.set_language_sizes(sizes)
        self._changed(window)
        self._keep_subtitle_height(fit=True)
        self._save.start()
        self.sizes_changed.emit()

    def current_size_readout(self) -> tuple[float, float]:
        """The first window's caption and translation sizes for Settings > Look."""
        ordered = self._ordered()
        choices = ordered[0].choices if ordered else self.stored.last
        return choices.text_size, choices.translation_size

    def set_subtitles(self, subtitles: tuple[float, float] | None) -> None:
        """Video's subtitles (556): with their text's size as a share of the
        screen's height and their width as a share of its width, every
        window at the bottom centre of the screen it's on, that wide, with
        room for the selected lines - each one's own place and size kept;
        None: each back where the learner put it, at its own size. At once,
        saying nothing (`say_subtitles` does, on the learner's pick)."""
        if subtitles == self.subtitles:
            return
        self.subtitles = subtitles
        self._place_subtitles()

    def say_subtitles(self, on: bool) -> None:
        """Each window says where it went, for a moment, when the learner
        picks Video or leaves it (556): never at a start or a move, and
        gone after SUBTITLES_SAID_SEC - not left over a film (Claude,
        2026-11-20)."""
        text = (
            _tr("Subtitles: along the bottom of the screen")
            if on
            else _tr("Back where you put it")
        )
        for window in self.windows.values():
            window.show_notice(text, SUBTITLES_SAID_SEC)

    def _place_subtitles(self) -> None:
        ordered = self._ordered()
        v_cap, v_trans = preset_sizes("video")
        ratio = v_trans / v_cap if v_cap > 0 else 1.0
        for index, window in enumerate(ordered):
            own = self._own.get(window.key)
            if self.subtitles is not None:
                if own is None:
                    self._own[window.key] = window.choices
                share, width = self.subtitles
                area = window.area_now()
                size = subtitle_text_size(share, area, window.text_px())
                trans = round(
                    min(
                        CAPTION_TEXT_SIZES[1],
                        max(CAPTION_TEXT_SIZES[0], size * ratio),
                    ),
                    2,
                )
                window.set_video(True)
                height = window.subtitle_height(size, translation_size=trans)
                rect = placement.subtitle_slot(area, width, height, index)
                window.take_place(Preset.BOTTOM_CENTRE, rect, size, trans)
            elif own is not None:
                del self._own[window.key]
                window.set_video(False)
                window.take_place(
                    own.preset, own.geometry, own.text_size, own.translation_size
                )
        joined = self.joined_window
        if joined is None or not ordered:
            return
        if self.subtitles is not None:
            share, width = self.subtitles
            area = ordered[0].area_now()
            size = subtitle_text_size(share, area, ordered[0].text_px())
            trans = round(
                min(
                    CAPTION_TEXT_SIZES[1],
                    max(CAPTION_TEXT_SIZES[0], size * ratio),
                ),
                2,
            )
            height = max(
                w.subtitle_height(size, translation_size=trans) for w in ordered
            )
            joined.place_at(placement.subtitle_slot(area, width, height))
        else:
            joined.place_at(
                self.stored.joined.geometry or self._joined_place(ordered[0], ordered)
            )
        self.sizes_changed.emit()

    def _keep_subtitle_height(self, *, fit: bool = False) -> None:
        """Keep room for added readings, link marks or a second language."""
        if self.subtitles is None:
            return
        windows: Sequence[CaptionWindow | JoinedWindow] = (
            (self.joined_window,)
            if self.joined_window is not None
            else tuple(self.windows.values())
        )
        for window in windows:
            rect = window._place()
            height = window._minimum().height
            if height > rect.height or (fit and height != rect.height):
                resized = replace(rect, y=rect.bottom - height, height=height)
                area = placement.area_for(rect, self._areas())
                window._set_place(placement.clamped(resized, area) if area else resized)

    def _kept_own(self, window: CaptionWindow) -> WindowChoices:
        """`window`'s choices to keep: as they are - or, while it's a
        subtitle, with its own place and sizes from before, and Video's
        size and width as the learner changed them handed on (556, 655)."""
        own = self._own.get(window.key)
        if own is None or self.subtitles is None:
            return window.choices
        share, width = self.subtitles
        area = window.area_now()
        new_share = share
        if window.choices.text_size != subtitle_text_size(
            share, area, window.text_px()
        ):
            new_share = round(
                window.choices.text_size * window.text_px() / area.height, 4
            )
        new_width = round(min(1.0, max(0.3, window.width() / max(1, area.width))), 2)
        given = min(placement.MAX_SUBTITLE_WIDTH, round(area.width * width))
        if abs(window.width() - given) <= 2:
            new_width = width  # not resized: the width it was given
        if (new_share, new_width) != (share, width):
            self.subtitles = (new_share, new_width)
            self.subtitles_changed.emit(new_share, new_width)
        kept = replace(
            window.choices,
            preset=own.preset,
            geometry=own.geometry,
            text_size=own.text_size,
            translation_size=own.translation_size,
        )
        self._own[window.key] = kept
        return kept

    def _asks_set_up(self) -> bool:
        """Whether a window opening now asks its languages: every one, until
        the learner chose Use as my default in one (478; the first on a PC
        alone, 465) - while no other one is asking."""
        return (
            self.offer_set_up
            and not self.stored.set_up
            and not any(w.set_up is not None for w in self.windows.values())
        )

    def _set_up_done(self, window: CaptionWindow, as_default: bool) -> None:
        """A window's set-up went, its answers that window's. With Use as
        my default: never asked again, and new windows start like it - its
        spoken language too (465, 478). Without: the next window that
        opens asks again (the user, 2026-11-18: "selecting as default on
        start up gets rid of the screen for future opens")."""
        if as_default:
            self.stored.last = window.choices
            self._start_like_this(window, True)
            self.set_asks_set_up(False)
        self.set_up_done.emit()

    def set_asks_set_up(self, on: bool) -> None:
        """Whether a window that opens asks its languages - a window's
        "Ask when a window opens", or Use as my default (off) (478)."""
        self.stored.set_up = not on
        for each in self.windows.values():
            each.set_asks_set_up(self.offer_set_up and on)
        self._save.start()

    def _start_like_this(self, window: CaptionWindow, on: bool) -> None:
        """Start new windows like this, on or off from a window's languages:
        on, `window` is the one they start like."""
        self.stored.start_like_this = on
        if on:
            self.stored.last = window.choices
        for each in self.windows.values():
            each.set_start_like_this(on)
        self._save.start()

    def recent_spoken(self) -> tuple[str, ...]:
        """The spoken languages the learner named last, newest first: first
        in every spoken-language list (polyglotic-hq 317)."""
        return self.stored.recent_spoken

    def _mic_changed(self) -> None:
        if self._shown_pace is not None:
            for window in self.windows.values():
                self._set_window_pace(window, self._shown_pace)
        self.languages_changed.emit()  # the mic's languages are the windows'
        self.mic_wanted.emit(self.show_mic_anywhere)
        self._sync_mic_levels()
        self._say_sights()  # the mic paused or not, with the windows showing it

    def _sync_mic_levels(self) -> None:
        if self.show_mic_anywhere and not self.out_of_sight:
            if not self._mic_levels.isActive():
                self._mic_levels.start()
            self._poll_mic_level()
        else:
            self._mic_levels.stop()
            for window in self.windows.values():
                window.set_mic_level(None)

    def _poll_mic_level(self) -> None:
        level = level_of(self.read_mic_peak())
        for window in self.windows.values():
            window.set_mic_level(level if window.choices.show_mic else None)

    def save_now(self) -> None:
        """The windows' choices into the settings, beside today's."""
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

    @property
    def show_mic_anywhere(self) -> bool:
        return any(w.choices.show_mic for w in self.windows.values())

    def show_window(self, key: str) -> None:
        """Home's Captions: `key`'s window shown, unless all are hidden."""
        window = self.windows.get(key)
        if window is not None and not self.out_of_sight:
            log.info("caption window %d shown from Home", window.index)
            window.show()  # always on top; never raised (that activates it)
            self._card_on_top()

    def open_bar_controls(self) -> None:
        """Open an unlocked window's controls, cycling windows on repeat."""
        windows = [w for w in self._ordered() if w.isVisible() and not w.locked]
        if not windows:
            return
        for index, window in enumerate(windows):
            if window.keyboard_bar_open:
                window.close_settings()
                windows[(index + 1) % len(windows)].open_bar_controls()
                return
        next((w for w in windows if w.hovered), windows[0]).open_bar_controls()

    def set_language(self, key: str, code: str) -> None:
        """Home's language chip: `key`'s window's language (or Original only)."""
        window = self.windows.get(key)
        if window is not None:
            window.set_language(code)

    def set_show_mic(self, key: str, on: bool) -> None:
        """Home's mic mark: my speech in `key`'s window, or not."""
        window = self.windows.get(key)
        if window is not None:
            window.set_show_mic(on)

    def reset_places(self, text_size: bool = False) -> None:
        """Every window back at its default place - the joined window too,
        while joined - and, with the look's Reset to defaults, its caption and
        translation sizes (109's section 4, 655)."""
        cap, trans = WindowChoices().text_size, WindowChoices().translation_size
        for window in self.windows.values():
            window.reset_position()
            if text_size:
                window.set_text_size(cap)
                window.set_translation_size(trans)
        if text_size:
            self.stored.pending_spoken_sizes.clear()
            for window in self.windows.values():
                window.choices = replace(window.choices, language_sizes={})
                window.set_language_sizes({})
            self._save.start()
            self.sizes_changed.emit()
        if self.joined_window is not None:
            self.joined_window.reset_position()

    def set_reporting(self, on: bool) -> None:
        """Every caption window's strip offers "Report a problem", or none
        does - the windows opened later too (polyglotic-hq 275)."""
        self._reporting = on
        for window in self.windows.values():
            window.set_reporting(on)

    def show_usage(self, meter: UsageMeter | None) -> None:
        """A capped plan's allowance left, on every caption window's bar and
        the windows opened later; None on an unlimited plan (684)."""
        self._usage = meter
        for window in self.windows.values():
            window.set_usage(meter)

    def set_show_mic_everywhere(self, on: bool) -> None:
        """The tray's "Caption my own speech": my speech in every window, or
        in none."""
        for window in self.windows.values():
            window.set_show_mic(on)

    def targets(self) -> dict[SourceId, tuple[Language, ...]]:
        """Each source's languages: a window's own (none: Original only);
        the mic's, every language of the windows showing my speech."""
        found: dict[SourceId, tuple[Language, ...]] = {}
        mic: list[Language] = []
        shown = False
        for window in self.windows.values():
            target = window.choices.target
            own = (target,) if target is not None else ()
            found[window.source] = own
            if window.choices.show_mic:
                shown = True
                mic += own
        if shown and self.mic is not None:
            found[self.mic] = tuple(dict.fromkeys(mic))
        return found

    def spoken_languages(self) -> dict[SourceId, Language | None]:
        """Each source's spoken language (None: Detect): a window's own; the
        mic's, the one the windows showing my speech name - my speech goes
        with what they hear, as a call's does - or Detect when they
        differ."""
        found: dict[SourceId, Language | None] = {}
        mic: list[Language | None] = []
        for window in self.windows.values():
            found[window.source] = window.choices.spoken
            if window.choices.show_mic:
                mic.append(window.choices.spoken)
        if mic and self.mic is not None:
            found[self.mic] = agreed_language(mic)
        return found

    def window_reading(self) -> dict[SourceId, tuple[CaptionMode, ReadingPath]]:
        """Each window's effective timing and translation path."""
        return {
            window.source: (window.timing, window.path)
            for window in self.windows.values()
        }

    def songs_sources(self) -> frozenset[SourceId]:
        """The sources heard in songs mode (decision 0287): with the Lyrics
        setting on, each music player's window that hears Detect."""
        return frozenset(
            window.source
            for window in self.windows.values()
            if heard_as_songs(
                self.lyrics, self.music_player(window.key), window.choices.spoken
            )
        )

    def set_lyrics(self, on: bool) -> None:
        """The learner's Lyrics setting: every window's switch shows it."""
        self.lyrics = on
        for window in self.windows.values():
            window.set_lyrics(on)

    def set_spoken_per_source(self, used: bool) -> None:
        """Whether the server uses each window's spoken language - a server
        from before 2026-11-09 takes one for every window."""
        self.spoken_per_source = used
        self._spoken_fallbacks()

    def set_spoken_everywhere(self, code: str | None) -> None:
        """Home's Spoken language, for every window: every window's (None:
        Detect) - but a music player's, which stays as its own window has it
        (568)."""
        for window in self.windows.values():
            if not self.music_player(window.key):
                base = self.stored.by_key[window.key]
                self.stored.by_key[window.key] = replace(base, spoken_language=code)
                window.set_spoken_language(code)
        self._save.start()

    def _spoken_fallbacks(self) -> None:
        """Each window says whether its app is heard as Detect rather than
        as the language it names: on a server that takes one spoken
        language for every window, when another window names a different
        one (the honest fallback, polyglotic-hq 248's Q6 A)."""
        agreed = agreed_language(w.choices.spoken for w in self.windows.values())
        for window in self.windows.values():
            own = window.choices.spoken
            window.set_spoken_fallback(
                self.spoken_per_source is False and own is not None and own != agreed
            )

    # -- captions -------------------------------------------------------------------------

    def apply(self, update: CaptionUpdate) -> None:
        """A caption update (on the interface thread): to each window it's
        for - in a paced caption mode through the playout, so word by word
        as each word's time comes (`release_words`)."""
        if not self.timing.paced:
            self._show(update)
            return
        for window in self.windows.values():  # the cards are sized a word ahead
            window.hear(update)
        self._let_out(self.playout.heard(update, self.word_clock()))
        self._wake_for_words()

    def release_words(self) -> None:
        """The words whose time has come, shown; woken again for the next."""
        self._let_out(self.playout.release(self.word_clock()))
        self._wake_for_words()

    def _let_out(self, updates: Iterable[CaptionUpdate]) -> None:
        """What the playout let out, shown now - each marked in the caption
        timelines as kept until then by the mode's pace, not by a window
        (perf.trace's `released`; polyglotic-hq 551)."""
        pace = self.playout.rules.delay
        for update in updates:
            if update.times is not None:
                trace.tracer().released(update.times.seq, pace)
            self._show(update)

    def _wake_for_words(self) -> None:
        due = self.playout.due()
        if due is None:
            self._word_due.stop()
        else:
            self._word_due.start(max(0, round((due - self.word_clock()) * 1000)))

    def _show(self, update: CaptionUpdate) -> None:
        """A caption update to each window it's for, now."""
        with spans.span("caption_windows.apply"):
            changed = False
            if self.sights.any_hidden:
                self._heard_hidden(update)
            for window in self.windows.values():
                shown = window.receive(update)
                changed = shown or changed
                if shown and update.kind is CaptionKind.FINISHED:
                    self._hint(window, update)
                    self._reading_hint(window, update)
                if update.kind is CaptionKind.FINISHED:
                    self._steady_language(window, update)
            now = time.monotonic()
            if changed and now - self._on_top_at >= ON_TOP_EVERY_SEC:
                self._on_top_at = now
                self.keep_on_top()

    def _heard_hidden(self, update: CaptionUpdate) -> None:
        """A caption of a hidden window's own app: it's captioning while
        hidden - and, if the learner asked, the windows come back when
        speech starts in it (335)."""
        now = self.clock()
        started = False
        for key, window in self.windows.items():
            if update.source_id == window.source:
                started = self.sights.captioned(key, now) or started
        if started and self.show_on_speech and self.hidden:
            log.info("caption windows shown: speech started in a hidden one")
            self.show_wanted.emit()
        self._say_sights()

    def _steady_language(self, window: CaptionWindow, update: CaptionUpdate) -> None:
        """A finished caption of a window's own app (not my speech) heard as
        Detect: once its app has spoken one language steadily, the window
        asks whether to always hear it as that (317) - unless the learner
        said Not now to that language for this window before. Not while its
        flag is off: nothing pushes the learner away from Detect (555)."""
        if not flags.on(flags.SPOKEN_NUDGE):
            return
        if update.source_id != window.source or window.choices.spoken is not None:
            return
        steady = self._steady.get(window.key)
        if steady is None:
            steady = self._steady[window.key] = SteadyLanguage()
            steady.declined = set(self.stored.declined_spoken.get(window.key, ()))
        found = steady.heard(update.language, update.languages_heard)
        if found is not None:
            window.suggest_spoken(found)

    def _spoken_declined(self, window: CaptionWindow, code: str) -> None:
        """Not now: that language isn't asked about again for this window."""
        self.stored.spoken_declined(window.key, code)
        steady = self._steady.get(window.key)
        if steady is not None:
            steady.declined.add(code)
        self._save.start()

    def _spoken_unanswered(self, window: CaptionWindow, code: str) -> None:
        """The question went by itself: not asked again about that language
        for this window until the app starts again (350) - not stored."""
        steady = self._steady.get(window.key)
        if steady is not None:
            steady.unanswered.add(code)

    def _hint(self, window: CaptionWindow, update: CaptionUpdate) -> None:
        """A finished caption shown: "Click any word" until the first
        lookup - only when its words can be looked up here: a dictionary
        for a language heard in it is open (polyglotic-hq 368: a German
        interface's first Chinese caption said so with none open)."""
        if self.card is None or self.learner is None or self.stored.looked_up:
            return
        heard = (update.language, *update.languages_heard)
        if any(self.learner.has_dictionary(code) for code in heard):
            window.set_hint(word_hint())

    def _reading_hint(self, window: CaptionWindow, update: CaptionUpdate) -> None:
        """Once on this PC, after the first lookup: a finished caption with
        Chinese or Japanese in it - said or its translation - where its
        dictionary is on this PC and its reading line is off says that
        pinyin or furigana can go above it (369, 511)."""
        if self.stored.reading_hinted or (
            self.card is not None and not self.stored.looked_up
        ):
            return
        for language in (update.language, window.choices.target):
            code = language_of(language)
            if (
                code in HINTED_LINES
                and code not in self.look.reading_lines
                and window.reads(language)
            ):
                self.stored.reading_hinted = True
                window.show_notice(reading_hint(code), READING_HINT_SEC)
                self._save.start()
                return

    def _looked_up(self) -> None:
        """The first lookup on this PC: the hint goes, for good."""
        if self.stored.looked_up:
            return
        self.stored.looked_up = True
        for window in self.windows.values():
            window.set_hint(None)
        self._save.start()

    def use_checked(self, caption_id: CaptionId, result: RecheckResult) -> None:
        """The best model's version of a line, which the learner said is right."""
        for window in self.windows.values():
            if window.view.use_checked(
                caption_id, result.clauses, result.language, result.languages_heard
            ):
                window.apply_changed(new_caption=False)

    def show_capture_status(
        self, status: Mapping[SourceId, CaptureIssue | None], crostini: bool
    ) -> None:
        for window in self.windows.values():
            source = window.source
            issue = status.get(source)
            if (
                issue is None
                and window.mic is not None
                and window.mic in window.view.sources
            ):
                issue = status.get(window.mic)
                if issue:
                    source = window.mic
            if issue:
                message = capture_status.explanation(issue, mic=source == window.mic)
            elif window.source != SAMPLE and any(
                s in status for s in window.view.sources
            ):
                message = capture_status.listening_for_speech()
            elif crostini and window.source != SAMPLE:
                message = capture_status.chromebook_help()
            else:
                message = ""
            window.set_capture_message(message)

    def heard(self, under_way: Collection[SourceId]) -> None:
        """Whose speech is under way now: the listening mark, in every
        timing - the mic's speech and the apps' alike (polyglotic-hq 260,
        the user's F33)."""
        now = time.monotonic()
        for key, window in self.windows.items():
            mark = self._marks[key]
            mark.heard([s for s in under_way if s in window.view.sources], now)
            window.set_listening(self._listening(mark, now))
            window.speaking = mark.speaking()

    def captioned(self, source_id: str) -> None:
        """A finished or withdrawn caption from `source_id` arrived."""
        now = time.monotonic()
        for key, window in self.windows.items():
            if source_id in window.view.sources:
                mark = self._marks[key]
                mark.captioned(SourceId(source_id), now)
                window.set_listening(self._listening(mark, now))

    def _listening(self, mark: ListeningMark, now: float) -> bool:
        return mark.showing(now)

    # -- the mouse while the app is in the background (a Mac) ---------------------------

    def under_the_mouse(self) -> list[QWidget]:
        """What `pointer_watch` tells of the mouse, top-most first: the
        windows' open popovers, the lookup card, the joined window, then the
        windows of their own."""
        found: list[QWidget] = []
        for window in self.windows.values():
            found += [p for p in (window.popover, window.languages) if p is not None]
        joined = self.joined_window
        if joined is not None and joined.popover is not None:
            found.append(joined.popover)
        if self.card is not None:
            found.append(self.card)
        if joined is not None:
            found.append(joined)
        found += [w for w in reversed(self.windows.values()) if w.isWindow()]
        return found

    # -- above a game that is itself always on top ---------------------------------------

    def keep_on_top(self) -> None:
        """While a game that is itself always on top is in front: the windows
        shown, then the lookup card, back on top of it - none activated, so
        the game keeps the keyboard (polyglotic-hq 141)."""
        if self.on_top is None or not self.on_top.game_in_front():
            return
        with spans.span("caption_windows.keep_on_top"):
            shown: list[QWidget] = [
                window
                for window in (self.joined_window, *self.windows.values())
                if window is not None and window.isWindow() and window.isVisible()
            ]
            if self.card is not None and self.card.isVisible():
                shown.append(self.card)  # last: above the windows it came from
            if shown:
                self.on_top.put_on_top([int(window.winId()) for window in shown])

    def _card_on_top(self) -> None:
        """A lookup card open while a caption window shows after it - which
        comes up at the top of the band - back above it (polyglotic-hq 141):
        the card is never raised, which would activate it."""
        card = self.card
        if self.on_top is not None and card is not None and card.isVisible():
            self.on_top.put_on_top([int(card.winId())])

    # -- the session's, for every window --------------------------------------------------

    def _learning_action(self, action: Action) -> None:
        """A Learning action from the lookup card: run it, then repaint only
        the captions holding the entry it changed (`learning_changed`, which
        it sets off on the way, is left to this)."""
        self._acting = True
        try:
            with spans.span("caption_windows.learning_action"):
                entry = action()
        finally:
            self._acting = False
        if entry is not None:
            self.entry_changed(entry)

    def entry_changed(self, entry: DictionaryEntry) -> None:
        """One entry's status or saved word changed: the captions holding it
        repaint, in every window - nothing is laid out."""
        texts = tuple(t for t in (entry.headword, entry.traditional) if t)
        for window in self.windows.values():
            window.entry_changed(entry.entry_id, texts)

    def dictionary_ready(self) -> None:
        """The dictionary's word-split data is read (`CaptionFeed`): the
        captions shown before it are marked now."""
        for window in self.windows.values():
            window.dictionary_ready()

    def refresh_link_classes(self) -> None:
        for window in self.windows.values():
            window.view.class_evidence = self.class_evidence
            window.refresh_link_classes()

    def load_changed(self, entries: frozenset[EntryId] | None) -> None:
        """The learning load changed (`LearningTools.load_changed`): the
        captions holding a word whose stage changed repaint, in every
        window - every caption if any word's may have (None). A lookup
        card's own action too: a word checked from the card is replaced by
        another, which other captions may hold."""
        for window in self.windows.values():
            window.load_changed(entries)

    def learning_changed(self, what: str) -> None:
        """Learning changed (`LearningTools.changed`): marks drawn again - a
        lookup card's own action repaints only its entry's captions."""
        if self._acting:
            return
        for window in self.windows.values():
            window.learning_changed(what)
        if self.card is not None:
            self.card.refresh()

    def restyle(self) -> None:
        """Windows' text size changed while they were open: their chrome
        at it (the captions keep each window's own size)."""
        for window in self.windows.values():
            window.restyle()
        if self.joined_window is not None:
            self.joined_window.restyle()

    @contextmanager
    def batch_settings(self) -> Iterator[None]:
        """Rebuild each existing window's lines once after its settings change."""
        with ExitStack() as stack:
            for window in self.windows.values():
                stack.enter_context(window.batch_settings())
            yield

    def set_look(self, look: CaptionLook) -> None:
        recolour = look.background != self.look.background
        apply_opacity = (
            recolour
            or look.original != self.look.original
            or look.translation != self.look.translation
            or look.opacity != self.look.opacity
        )
        self.look = look
        if self.card is not None:
            self.card.model.japanese_reading = look.japanese_reading
        self.show_on_speech = look.show_on_speech
        if look.pause_hidden_after != self.sights.limit:
            self.sights.limit = look.pause_hidden_after
            self.tick()  # a shorter limit may be past already
        for window in self.windows.values():
            if apply_opacity and window.choices.opacity != look.opacity:
                window.choices = replace(window.choices, opacity=look.opacity)
                window.set_look(look)
                self._changed(window)
            else:
                window.set_look(replace(look, opacity=window.choices.opacity))
        self._keep_subtitle_height()
        self.look_changed.emit()
        if self.joined_window is not None:
            self.joined_window.refresh_settings()
            if recolour:
                self.joined_window.restyle()  # its controls on the new panel

    def set_timing(self, mode: CaptionMode) -> None:
        if self.timing.paced and not mode.paced:
            self._word_due.stop()
            self._let_out(self.playout.clear())  # what was waiting shows now
        self.timing = mode
        for window in self.windows.values():
            window.set_timing(mode)
            window.set_faint_ahead(self._faint_ahead())

    def set_playout(self, rules: PlayoutRules) -> None:
        """How the paced modes' words are played out (the settings')."""
        if rules != self.playout.rules:
            self.playout.change(rules)
            self._wake_for_words()
        for window in self.windows.values():
            window.set_faint_ahead(self._faint_ahead())

    def _faint_ahead(self) -> bool:
        """Karaoke: the paced modes' waiting words show, faint."""
        return self.timing.paced and self.playout.rules.ahead is not Ahead.NONE

    def set_cards(self, on: bool) -> None:
        """Steady's card stack, on or off, in every window."""
        self.cards = on
        for window in self.windows.values():
            window.set_cards(on)

    def set_two_zones(self, on: bool) -> None:
        """Whether the paced modes show two zones (`views.zones`; the
        learner's choice in Settings > Timing)."""
        self.two_zones = on
        for window in self.windows.values():
            window.set_two_zones(on)

    def set_caption_sizes(self, size: float) -> None:
        """Every window's caption size at `size` (independent of translation
        size), and every new one's: Settings > Look's (polyglotic-hq 655)."""
        low, high = CAPTION_TEXT_SIZES
        size = round(min(high, max(low, size)), 2)
        for window in self.windows.values():
            window.set_text_size(size)
        if self.stored.last.text_size != size:
            self.stored.last = replace(self.stored.last, text_size=size)
            self._save.start()
        self.sizes_changed.emit()

    def set_translation_sizes(self, size: float) -> None:
        """Every window's translation at `size` (independent of caption size),
        and every new one's: Settings > Look's (polyglotic-hq 593, 655)."""
        low, high = CAPTION_TEXT_SIZES
        size = round(min(high, max(low, size)), 2)
        for window in self.windows.values():
            window.set_translation_size(size)
        if self.stored.last.translation_size != size:
            self.stored.last = replace(self.stored.last, translation_size=size)
            self._save.start()
        self.sizes_changed.emit()

    def _visited_source(self, source: SourceId) -> None:
        if source in self._visited:
            self._visited.remove(source)
        self._visited.insert(0, source)

    def respeaking_window(
        self, point: QPoint | None = None, *, for_speakers: bool = False
    ) -> CaptionWindow | None:
        """At key-down, choose a visible caption column, even when locked."""
        point = QCursor.pos() if point is None else point
        eligible = {
            w.source: w
            for w in self.windows.values()
            if w.isVisible() and (for_speakers or w.respeak_offered())
        }
        # Follow Qt's stacking order when windows overlap. A click-through
        # window can be invisible to widgetAt, so also check its global bounds.
        widget = QApplication.widgetAt(point)
        while widget is not None:
            if isinstance(widget, CaptionWindow) and widget.source in eligible:
                self._visited_source(widget.source)
                return widget
            widget = widget.parentWidget()
        ordered = dict.fromkeys((*self._visited, *eligible))
        pointed = [
            s
            for s in ordered
            if s in eligible
            and eligible[s].rect().contains(eligible[s].mapFromGlobal(point))
        ]
        source = respoken_for(eligible, (*pointed, *self._visited))
        if source is None:
            return None
        self._visited_source(source)
        return eligible[source]

    def show_respeaking_level(
        self, source: SourceId | None, state: str, level: float
    ) -> CaptionWindow | None:
        for window in self.windows.values():
            if window.source == source and window.isVisible():
                return window
        return None

    def set_pace(
        self,
        pace: tuple[dict[str, PaceReading], dict[str, PaceReading]],
    ) -> None:
        """Show each source's measured pace only in its caption window."""
        if self._shown_pace == pace:
            return
        self._shown_pace = pace
        for window in self.windows.values():
            self._set_window_pace(window, pace)

    def _set_window_pace(
        self,
        window: CaptionWindow,
        pace: tuple[dict[str, PaceReading], dict[str, PaceReading]],
    ) -> None:
        them, you = pace
        empty = PaceReading(0, 0, 0.0, 0.0, 0, 0.0)
        their_reading = them.get(str(window.source), empty)
        # Ordinary microphone speech is visible wherever this window's My
        # speech choice is on. Re-speaking is addressed to its source window.
        own_reading = you.get(str(window.source), empty)
        mic = you.get(str(self.mic)) if self.mic is not None else None
        if mic is None:
            self._window_mic_pace.pop(window, None)
        elif window.choices.show_mic:
            self._window_mic_pace[window] = mic
            own_reading = own_reading.combined(mic)
        elif previous := self._window_mic_pace.get(window):
            # Keep the session average this window saw before its mic was hidden.
            own_reading = own_reading.combined(
                replace(previous, now=0, recent_words=0, recent_seconds=0, fade=0)
            )
        window.set_pace(
            their_reading.now,
            their_reading.mean,
            own_reading.now,
            own_reading.mean,
        )

    def offer_respeaking(self, update: CaptionUpdate) -> None:
        """A recognition miss, before the history groups or discards the answer."""
        if self.stored.respeaking_hinted or update.respoken:
            return
        on, key, hold_only = self.respeaking
        if not (on and key and recognition_missed(update)):
            return
        for window in self.windows.values():
            if (
                window.source == update.source_id
                and window.isVisible()
                and window.respeak_offered()
            ):
                tip = (
                    _tr("Didn't catch that? Hold {key} and say it.")
                    if hold_only
                    else _tr("Didn't catch that? Tap {key}, then hold it and say it.")
                )
                # In a joined window the first column owns the shared notice line.
                owner = window.host.columns[0] if window.host is not None else window
                owner.show_notice(tip.format(key=key_words(key)), HINT_SEC.value)
                self.stored.respeaking_hinted = True
                self.save_now()
                return

    def set_respeaking(self, on: bool, key: str = "", hold_only: bool = False) -> None:
        """Follow the setting and the shortcut that the system registered."""
        self.respeaking = (on, key, hold_only)
        for window in self.windows.values():
            self._follow_respeaking(window)

    def set_respeaking_sources(self, captured: Collection[SourceId]) -> None:
        """Only windows whose source is being captured can re-speak."""
        self._respeaking_sources = frozenset(captured)
        for window in self.windows.values():
            self._follow_respeaking(window)

    def _follow_respeaking(self, window: CaptionWindow) -> None:
        on, key, hold_only = self.respeaking
        eligible = self._respeaking_sources
        window.set_respeaking(
            on and (eligible is None or window.source in eligible), key, hold_only
        )

    def set_path(self, path: ReadingPath) -> None:
        """What is read first in the paced modes (decision 0253)."""
        self.path = path
        for window in self.windows.values():
            window.set_path(path)

    def set_longest_wait(self, seconds: float) -> None:
        """The longest wait for text (decision 0068): no caption waits
        longer than this for the Lab's gap between new captions (284)."""
        self.longest_wait = seconds
        for window in self.windows.values():
            window.longest_wait = seconds

    def set_settle_after(self, seconds: float) -> None:
        """How long shown text may still change (decision 0099): every
        window's captions settle after this from now on."""
        self.settle_after = seconds
        for window in self.windows.values():
            window.view.set_settle_after(seconds)

    def set_second_languages(self, seconds: Mapping[Language, Language]) -> None:
        if dict(seconds) == self.second_languages:
            return
        self.second_languages = dict(seconds)
        for window in self.windows.values():
            window.set_second_languages(self.second_languages)

    def set_labels(self, labels: Mapping[SourceId, SourceLabel], you: str) -> None:
        """Each source's name and colour (on this PC only)."""
        if dict(labels) == self.labels and you == self.you:
            return
        self.labels, self.you = dict(labels), you
        for window in self.windows.values():
            window.set_labels(self.labels, you)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        for window in self.windows.values():
            window.set_paused(paused)

    def set_connection(self, notice: Notice | None, retry_in: float | None) -> None:
        self.connection = (notice, retry_in)
        for window in self.windows.values():
            window.set_connection(notice, retry_in)
        if notice is Notice.NOT_SIGNED_IN:
            if not (self.signed_out or self._going.isActive()):
                self._going.start()  # each says so on its notice line, then they go
            return
        self._going.stop()
        if self.signed_out:
            self.signed_out = False
            self._show_or_hide()
            for window in self.windows.values():
                window.introduce()  # back, and shown where they are

    def _gone(self) -> None:
        self.signed_out = True
        self._show_or_hide()

    def set_minutes_used(self, used: bool) -> None:
        """Today's free minutes are used (or there are more again)."""
        self.minutes_used = used
        for window in self.windows.values():
            window.set_minutes_used(used)

    def set_failing(self, failing: bool) -> None:
        """Captions are failing on the server (or that's over)."""
        self.failing = failing
        for window in self.windows.values():
            window.set_failing(failing)

    def set_unstable(self, unstable: bool) -> None:
        """The connection keeps dropping (or it has held again)."""
        self.unstable = unstable
        for window in self.windows.values():
            window.set_unstable(unstable)

    def set_busy(self, busy: bool) -> None:
        """The server's pace hint: a busy time, said briefly when it begins
        slowing the live updates the windows show (`slowed_now`)."""
        if slowed_now(self.busy, busy, self.timing):
            self.show_notice(notice_text(Notice.BUSY, None))
        self.busy = busy

    def show_notice(self, text: str) -> None:
        for window in self.windows.values():
            window.show_notice(text)

    def offer_undo(self, text: str, seconds: float) -> None:
        """`text`, what a preset step lost, with Undo after it on every
        window's notice line for `seconds` (polyglotic-hq 587): a click on
        Undo in any of them is the step "undo"."""
        line = undo_line(text)
        for window in self.windows.values():
            window.show_notice(line, seconds)

    def set_live_keys(self, keys: str) -> None:
        """Back to live's hotkey as it is now ("" none), on every window's
        Back to live (polyglotic-hq 567)."""
        self.live_keys = keys
        for window in self.windows.values():
            window.set_live_keys(keys)

    def go_live(self) -> None:
        """Every window back to its newest caption, as its Back to live does
        (the hotkey's: polyglotic-hq 567)."""
        for window in self.windows.values():
            window.go_live()

    def step_text(self, steps: int) -> None:
        """Every window's text `steps` sizes bigger (or smaller), as its
        own A+ and A- do (the hotkeys': polyglotic-hq 567)."""
        for window in self.windows.values():
            codes = window.size_languages()
            if codes:
                code = codes[0]
                size = window.choices.language_sizes.get(code, 1.0)
                self.set_language_size(
                    window, str(code), stepped(size, steps, CAPTION_TEXT_SIZES)
                )

    def set_locked(self, locked: bool) -> None:
        at_length = locked and not self.locked and self.tell_how_to_unlock
        self.locked = locked
        if locked and self.card is not None:
            self.card.close_card()
        for window in self.windows.values():
            window.set_locked(locked, at_length)
        if at_length:
            self.tell_how_to_unlock = False
            self.unlock_told.emit()
        if self.joined_window is not None:
            self.joined_window.set_locked(locked)

    def set_unlock_spot(self, on: bool) -> None:
        """Whether a locked window's corner keeps taking the mouse, so resting
        on its lock offers Unlock where the OS can't say where the mouse is
        over another app (Linux on a Wayland desktop: `UnlockSpot.catch`,
        polyglotic-hq 570)."""
        self.unlock_spot = on
        for window in self.windows.values():
            window.unlock_spot.catch(on)

    def set_unlock_keys(self, keys: str) -> None:
        """The lock's hotkey as it is now ("" if it doesn't work here): what a
        locked window says unlocks it (F10, 249), and the lock button's tip
        (398)."""
        self.unlock_keys = keys
        for window in self.windows.values():
            window.set_unlock_keys(keys)
        if self.joined_window is not None:
            self.joined_window.set_unlock_keys(keys)

    def carry(self, old: str, new: str) -> None:
        """App `new` is about to be captioned in the window of `old`: it
        opens with that window's choices - its place, size, language - as
        the window it replaces (F12)."""
        found = self.stored.by_key.get(old)
        if found is not None:
            self.stored.by_key[new] = found
            self._save.start()

    def set_hidden(self, hidden: bool) -> None:
        """Hidden: nothing drawn (Ctrl+Alt+H). Each window's timer starts
        (335); shown, any listening paused starts again."""
        self.hidden = hidden
        now = self.clock()
        for key, window in self.windows.items():
            if hidden:
                self.sights.hide(key, now)
            elif self.sights.show(key):
                log.info("caption window %d shown: listening again", window.index)
        if hidden and self.windows:
            self._hidden_tick.start()
        self._show_or_hide()
        self._say_sights()

    # -- hidden too long (335) ------------------------------------------------------------

    def tick(self) -> None:
        """Windows hidden past the limit pause; what Home and the tray say
        follows. The tick stops once nothing is hidden."""
        now = self.clock()
        for key, read in self.windows.items():
            if self.reading(key) and self.sights.read(key, now):
                log.info(
                    "caption window %d listening again: its transcript is open",
                    read.index,
                )
        for key in self.sights.tick(now):
            window = self.windows.get(key)
            index = window.index if window is not None else -1
            log.info(
                "caption window %d paused: hidden %s min", index, self.sights.limit
            )
        if not self.sights.any_hidden:
            self._hidden_tick.stop()
        self._say_sights()

    def _say_sights(self) -> None:
        """`paused_changed` and `sight_changed`, when either changed."""
        paused = self.paused_sources()
        if paused != self._paused_said:
            self._paused_said = paused
            self.paused_changed.emit()
        now = self.clock()
        sights = {key: self.sights.sight(key, now) for key in self.windows}
        if sights != self._sights_said:
            self._sights_said = sights
            self.sight_changed.emit()

    def paused_sources(self) -> frozenset[SourceId]:
        """The sources nothing is sent for: each paused window's app, and
        the mic once every window that shows my speech is paused."""
        paused = self.sights.paused()
        found = {w.source for key, w in self.windows.items() if key in paused}
        showing = [key for key, w in self.windows.items() if w.choices.show_mic]
        if self.mic is not None and showing and all(k in paused for k in showing):
            found.add(self.mic)
        return frozenset(found)

    def sight(self, key: str) -> tuple[Sight, int | None]:
        """`key`'s window as the learner would find it - and, paused, the
        minutes it was hidden before it paused."""
        return (
            self.sights.sight(key, self.clock()),
            self.sights.paused().get(key),
        )

    @property
    def out_of_sight(self) -> bool:
        """Hidden by the learner, gone while signed out, or out of the way
        of a dialog."""
        return self.hidden or self.signed_out or self.aside

    # -- out of the way of the app's own dialogs (579) ------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """A window's events, untouched: one blocked by a modal dialog -
        which Qt says as the dialog opens - has the windows step aside."""
        if isinstance(watched, CaptionWindow) and event.type() in (
            QEvent.Type.Enter,
            QEvent.Type.WindowActivate,
        ):
            self._visited_source(watched.source)
        if event.type() is QEvent.Type.Show:
            self.window_shown.emit()
        elif event.type() is QEvent.Type.WindowBlocked:
            QTimer.singleShot(0, self, self._step_aside)  # once Qt's done with it
        return False

    def _step_aside(self) -> None:
        """Out of the way while a modal dialog of the app's is open - the
        windows hidden, without the learner's Hide - and, once none is,
        shown again as they were."""
        aside = QGuiApplication.modalWindow() is not None
        if aside:
            self._dialog_open.start()
        else:
            self._dialog_open.stop()
        if aside == self.aside:
            return
        before = self.out_of_sight
        self.aside = aside
        if self.out_of_sight != before:
            self._show_or_hide()

    def _show_or_hide(self) -> None:
        gone = self.out_of_sight
        why = (
            "hidden (Ctrl+Alt+H)"
            if self.hidden
            else "signed out"
            if self.signed_out
            else "out of the way of a dialog"
        )
        log.info("caption windows %s", why if gone else "shown again")
        if gone and self.card is not None:
            self.card.close_card()
        for window in self.windows.values():
            if window.host is None:  # a column shows with its joined window
                window.setVisible(not gone)
        if self.joined_window is not None:
            self.joined_window.setVisible(not gone)
        self._sync_mic_levels()
        self._card_on_top()

    def close(self) -> None:
        self._dialog_open.stop()
        self._mic_levels.stop()
        if self.card is not None:
            self.card.close_card()
        if self._save.isActive():
            self.save_now()
        for key in list(self.windows):
            self._close(key)
        if self.joined_window is not None:
            joined, self.joined_window = self.joined_window, None
            joined.close()
            joined.deleteLater()
