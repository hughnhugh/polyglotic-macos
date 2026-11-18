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
  and at one window left it is that app's own window.
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

Holds caption text through its windows: never log it.
"""

import logging
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import replace

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget

from polyglotic_desktop.core.lexicon.entries import DictionaryEntry
from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Language,
)
from polyglotic_desktop.core.listening.display import ListeningMark
from polyglotic_desktop.core.listening.hidden import HiddenWindows, Sight
from polyglotic_desktop.core.listening.recheck import RecheckResult
from polyglotic_desktop.core.listening.settings import agreed_language
from polyglotic_desktop.core.listening.settling import SETTLE_AFTER_SEC
from polyglotic_desktop.core.listening.sources import SAMPLE, SourceId, SourceLabel
from polyglotic_desktop.core.listening.spoken import SteadyLanguage
from polyglotic_desktop.core.listening.timing import (
    MAX_WAIT_FOR_TEXT_SEC,
    CaptionId,
    CaptionMode,
)
from polyglotic_desktop.core.shared import EntryId
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ports.system import OnTop
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
from polyglotic_desktop.ui_next.joined_window import JoinedWindow
from polyglotic_desktop.ui_next.languages import taken_off, target_languages
from polyglotic_desktop.ui_next.lookup_card import Action, LookupCard
from polyglotic_desktop.ui_next.pointer_watch import PointerWatch
from polyglotic_desktop.ui_next.reading_lines import language_of
from polyglotic_desktop.ui_next.selection_reading import SelectionReading
from polyglotic_desktop.ui_next.settings_popover import KeyState
from polyglotic_desktop.ui_next.views import placement
from polyglotic_desktop.ui_next.views.app_choices import AppChoice
from polyglotic_desktop.ui_next.views.caption_window import (
    LIMIT,
    NOTICE_SEC,
    STORED_KEY,
    CaptionLook,
    JoinedChoices,
    Notice,
    WindowChoices,
    slowed_now,
)
from polyglotic_desktop.ui_next.views.lookup import Learner
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.placement import Rect

SAVE_AFTER_MS = 400
"""A window's choices are saved this long after the last change (a run of
text size steps is one save)."""
ON_TOP_EVERY_SEC = 1.0
"""A caption puts the windows back on top of a game at most this often."""
HIDDEN_TICK_MS = 1000
"""How often, while a window is hidden, its timer and what Home and the
tray say of it are looked at."""

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
    mic_wanted = Signal(bool)
    """Whether any window shows my speech: the mic is captured only then."""
    lock_wanted = Signal()
    unlock_wanted = Signal()
    """A locked window's Unlock, where the mouse rested on its lock (398)."""
    hide_wanted = Signal()
    stop_wanted = Signal(str)
    report_wanted = Signal()
    """A caption window's "Report a problem" (an alpha tester's, 275)."""
    """An app's key: stop captioning it (its window's close)."""
    transcript_wanted = Signal(str)
    all_settings_wanted = Signal()
    links_wanted = Signal(bool, tuple)
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
    translation_colours_wanted = Signal(bool)
    """And in the translation (431)."""
    timing_wanted = Signal(str)
    app_wanted = Signal(str, str)
    """A window's key, and an app's name: caption that app there instead
    (its settings' Captioning list, F12, 249)."""
    second_language_wanted = Signal(str, str)
    """A window's "Lines already in ...": a translation language, and the
    language its lines already in it are shown in ("": left as they are) -
    the session's second languages, kept by language (263)."""
    joined_changed = Signal(bool)
    """The windows now show joined as one (True), or each on its own."""
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
        self._on_top_at = -ON_TOP_EVERY_SEC
        self.front_changed.connect(self.keep_on_top, Qt.ConnectionType.QueuedConnection)
        self._store = store
        self.learner = learner
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
        self.joined_window: JoinedWindow | None = None
        """The windows joined as one, while they are (two or more)."""
        self._order: list[str] = []  # the apps' order: the columns'
        self.look = CaptionLook()
        self.timing = CaptionMode.STEADY
        self.longest_wait = MAX_WAIT_FOR_TEXT_SEC
        self.settle_after = SETTLE_AFTER_SEC
        self.second_languages: dict[Language, Language] = {}
        self.spoken_per_source: bool | None = None
        """Whether the server uses each window's spoken language (its
        `welcome.source_fields`); None until a server has said."""
        self.labels: dict[SourceId, SourceLabel] = {}
        self.you = "You"
        self.locked = False
        self.unlock_keys = "Ctrl+Alt+L"
        """The hotkey that unlocks, as it is now ("" if another app has it)."""
        self.app_choices: Callable[[str], list[AppChoice]] = lambda key: []
        """The apps the window of a key can caption instead (`main`'s)."""
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
        self._areas = areas
        self.reading: Callable[[str], bool] = lambda key: False
        """Whether app `key`'s transcript window is open: a hidden window
        being read there isn't paused (`main` hands it the transcripts')."""
        self.clock: Callable[[], float] = time.monotonic
        """The hidden windows' timers' clock (seconds)."""
        self.show_on_speech = self.look.show_on_speech
        self.sights = HiddenWindows(self.look.pause_hidden_after)
        self._sights_said: dict[str, Sight] = {}
        self._paused_said: frozenset[SourceId] = frozenset()
        self._hidden_tick = QTimer(self, interval=HIDDEN_TICK_MS)
        self._hidden_tick.timeout.connect(self.tick)
        self._marks: dict[str, ListeningMark] = {}
        self._steady: dict[str, SteadyLanguage] = {}
        """Each window's app heard as Detect: the language it speaks
        steadily, for the window's question (317)."""
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
        self._arrange()
        self._spoken_fallbacks()
        self.languages_changed.emit()
        self.mic_wanted.emit(self.show_mic_anywhere)
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
                index, key, self.offer_set_up
            )
            self._save.start()
        label = self.labels.get(source) or SourceLabel(key, ACCENT)
        window = CaptionWindow(
            key,
            source,
            choices,
            label,
            self.look,
            index,
            self.mic,
            self._areas,
            keys=self.keys,
            learner=self.learner,
            card=self.card,
        )
        window.set_timing(self.timing)
        window.longest_wait = self.longest_wait
        window.view.set_settle_after(self.settle_after)
        window.set_second_languages(self.second_languages)
        window.set_labels(self.labels, self.you)
        window.set_paused(self.paused)
        window.set_minutes_used(self.minutes_used)
        window.set_failing(self.failing)
        window.set_unstable(self.unstable)
        window.set_connection(*self.connection)
        window.set_unlock_keys(self.unlock_keys)
        window.set_locked(self.locked)
        window.use_say_it(self.say_it)
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
        window.language_changed.connect(self.languages_changed)
        window.second_wanted.connect(self.second_language_wanted)
        window.mic_changed.connect(self._mic_changed)
        window.lock_wanted.connect(self.lock_wanted)
        window.unlock_wanted.connect(self.unlock_wanted)
        window.hide_wanted.connect(self.hide_wanted)
        window.all_settings_wanted.connect(self.all_settings_wanted)
        window.links_wanted.connect(self.links_wanted)
        window.quiet_wanted.connect(self.quiet_wanted)
        window.quiet_word_wanted.connect(self.quiet_word_wanted)
        window.fill_wanted.connect(self.fill_wanted)
        window.aligned_wanted.connect(self.aligned_wanted)
        window.said_colours_wanted.connect(self.said_colours_wanted)
        window.translation_colours_wanted.connect(self.translation_colours_wanted)
        window.app_choices = lambda: self.app_choices(key)
        window.recent_spoken = self.recent_spoken
        window.spoken_declined.connect(lambda code: self._spoken_declined(window, code))
        window.spoken_unanswered.connect(
            lambda code: self._spoken_unanswered(window, code)
        )
        window.app_wanted.connect(lambda name: self.app_wanted.emit(key, name))
        window.timing_wanted.connect(self.timing_wanted)
        window.stop_wanted.connect(lambda: self.stop_wanted.emit(window.key))
        window.report_wanted.connect(self.report_wanted)
        window.set_reporting(self._reporting)
        window.transcript_wanted.connect(
            lambda: self.transcript_wanted.emit(window.key)
        )
        window.join_wanted.connect(lambda: self.join(window.key))
        return window  # shown by _arrange: on its own, or as a column

    def _close(self, key: str) -> None:
        window = self.windows.pop(key)
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
            )
            self._arrange()
        self._save.start()

    def separate(self) -> None:
        """Each window back at its own place."""
        if not self.stored.joined.on:
            return
        with spans.span("caption_windows.separate"):
            self.stored.joined = replace(self.stored.joined, on=False)
            self._arrange()
        self._save.start()

    def _ordered(self) -> list[CaptionWindow]:
        return [self.windows[key] for key in self._order if key in self.windows]

    def _joined_place(
        self, commanding: CaptionWindow, ordered: list[CaptionWindow]
    ) -> Rect:
        start = to_rect(commanding.geometry())
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
        joined.set_locked(self.locked)
        joined.set_unlock_keys(self.unlock_keys)
        joined.place_at(choices.geometry or self._joined_place(ordered[0], ordered))
        joined.changed.connect(lambda: self._joined_moved(joined))
        joined.separate_wanted.connect(self.separate)
        joined.lock_wanted.connect(self.lock_wanted)
        joined.all_settings_wanted.connect(self.all_settings_wanted)
        return joined

    def _joined_moved(self, joined: JoinedWindow) -> None:
        self.stored.joined = joined.choices
        self._save.start()

    # -- their choices ------------------------------------------------------------------

    def _changed(self, window: CaptionWindow) -> None:
        before = self.stored.by_key.get(window.key)
        spoken = window.choices.spoken_language
        if before is None or before.spoken_language != spoken:
            self.stored.spoken_named(spoken)  # first in the lists (317)
            steady = self._steady.get(window.key)
            if steady is not None:  # heard afresh from the next caption
                steady.start_again()
        self.stored.by_key[window.key] = window.choices
        self.stored.last = window.choices
        self._save.start()

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
        self.languages_changed.emit()  # the mic's languages are the windows'
        self.mic_wanted.emit(self.show_mic_anywhere)
        self._say_sights()  # the mic paused or not, with the windows showing it

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
        while joined - and, with the look's Reset to defaults, its text
        size (109's section 4)."""
        for window in self.windows.values():
            window.reset_position()
            if text_size:
                window.set_text_size(WindowChoices().text_size)
        if self.joined_window is not None:
            self.joined_window.reset_position()

    def set_reporting(self, on: bool) -> None:
        """Every caption window's strip offers "Report a problem", or none
        does - the windows opened later too (polyglotic-hq 275)."""
        self._reporting = on
        for window in self.windows.values():
            window.set_reporting(on)

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

    def set_spoken_per_source(self, used: bool) -> None:
        """Whether the server uses each window's spoken language - a server
        from before 2026-11-09 takes one for every window."""
        self.spoken_per_source = used
        self._spoken_fallbacks()

    def set_spoken_everywhere(self, code: str | None) -> None:
        """Home's Spoken language, for every window: every window's (None:
        Detect)."""
        for window in self.windows.values():
            window.set_spoken_language(code)

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
        """A caption update (on the interface thread): to each window it's for."""
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
        said Not now to that language for this window before."""
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

    def set_look(self, look: CaptionLook) -> None:
        recolour = look.background != self.look.background
        self.look = look
        self.show_on_speech = look.show_on_speech
        if look.pause_hidden_after != self.sights.limit:
            self.sights.limit = look.pause_hidden_after
            self.tick()  # a shorter limit may be past already
        for window in self.windows.values():
            window.set_look(look)
        self.look_changed.emit()
        if recolour and self.joined_window is not None:
            self.joined_window.restyle()  # its controls on the new panel

    def set_timing(self, mode: CaptionMode) -> None:
        self.timing = mode
        for window in self.windows.values():
            window.set_timing(mode)

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

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        if locked and self.card is not None:
            self.card.close_card()
        for window in self.windows.values():
            window.set_locked(locked)
        if self.joined_window is not None:
            self.joined_window.set_locked(locked)

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
        """Hidden by the learner, or gone while signed out."""
        return self.hidden or self.signed_out

    def _show_or_hide(self) -> None:
        gone = self.out_of_sight
        why = "hidden (Ctrl+Alt+H)" if self.hidden else "signed out"
        log.info("caption windows %s", why if gone else "shown again")
        if gone and self.card is not None:
            self.card.close_card()
        for window in self.windows.values():
            if window.host is None:  # a column shows with its joined window
                window.setVisible(not gone)
        if self.joined_window is not None:
            self.joined_window.setVisible(not gone)
        self._card_on_top()

    def close(self) -> None:
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
