"""The app as one piece behind its windows: settings, the caption feed, the
session's state, the commands and the tray, kept in step.

`DesktopApp` is what `main` builds and talks to; the new interface's
windows (`ui_next`, wired by `main`'s `Hub`) follow it:
- `feed.receive(update)` - caption updates, from any thread;
- `caption_failed()` - a finished caption failed on the server: several
  in a row, and `captions_failing` tells Home and the caption windows,
  until a caption arrives again or the session's state changes;
- `set_connection(state, retry_in, unreachable)` - the listening
  session's state, kept here (`connection`, `retry_in`, and while it
  waits to try again, why the server can't be reached - `unreachable`,
  polyglotic-hq 251) and announced (`connection_changed`) for Home, the
  caption windows, the transcripts and the tray;
  `set_minutes(used, left)` and `show_notice(code)` - the server's
  `minutes` and `notice`, announced for Home and the caption windows;
- `settings` - the user's choices, saved through the `SettingsStore` port
  as they change; `main` turns them into the connection's settings and
  the capture's sources, and follows `settings.changed`;
- `set_app_sources(apps)` - which app each source id is (`main`'s
  `Sources`), so captions are labelled with its name and colour (the
  learner's own, if they set one) - on this PC only (`source_labels`);
- the named commands the tray, Home, the caption windows and the hotkeys
  share: `open_window` (`window_wanted`), `pause` (checkable - `main`
  pauses the timing rules), `caption_mic` (checkable, saved),
  `dictation` (checkable, saved: dictation on or off - polyglotic-hq 283)
  and its language's menu (Detect, English, Mandarin, Cantonese, the one
  chosen, "More languages…" - `set_dictation_languages`),
  `lock_windows` (checkable, saved) and `hide_windows` (checkable) for
  every caption window, `quit`; `report_problem` and `suggest` (in the
  tray, on Home and on Account), which ask for the feedback form:
  `feedback_wanted.emit(kind)`, opened by `main` (project 053);
  `work_with_us`, a quiet line in Settings' About card - the same form,
  to say you'd like to work on Polyglotic; Help's "Report a problem" asks
  for it with the "no captions?" check's result attached:
  `check_report_wanted.emit(summary)` (project 096);
- `set_activity(provider)` - what each source being captured has done
  (sound and speech heard), for that check (`caption_facts`);
- `hotkeys` - the commands with a system-wide hotkey, by its name
  (`core.listening.hotkeys.Hotkey`): lock, pause and hide (Ctrl+Alt+ the
  letter, as in the proof of concept; ⌃⌘ the letter on a Mac), back to
  live, and copy the newest caption, the next preset and the captions'
  text size (polyglotic-hq 567) - each key the learner's own
  (`set_hotkeys`), shown in the tray menu;
  `hotkey_pressed.emit(name)` from any thread runs one on the Qt thread
  (`main` registers them with the OS); `hotkeys_not_working` stops showing
  the ones that don't work here - another app already has them, or they
  weren't registered (a preview build has none: polyglotic-hq 398) - so
  nothing names a hotkey that does nothing;
- the window theme (`theme`), applied at start, when the learner changes
  it and when Windows turns light or dark (`themed`);
- the tray icon, its state following the app's: listening (captioning),
  idle, or paused - drawn for the taskbar's own light or dark
  (`light_taskbar`, from `main`: Windows' taskbar can differ from its apps)
  - and its tooltip, the state Home shows (`show_state_title`) and a
  hidden caption window's (`show_hidden`: captioning while hidden, or
  paused after a time hidden - polyglotic-hq 335); the first
  time the main window is closed rather than quit, a message from the tray
  saying the app is still running there (`note_in_tray`, once per PC);
  its menu opens wholly on the work area, above the taskbar, as Windows'
  own tray menus do (`tray_menu_place`) - on Linux the desktop's tray
  shows it itself (`DESKTOP_SHOWS_TRAY_MENU`, polyglotic-hq 571).

It holds no rules: what to show is core's, what to do with the user's
choices is `main`'s.
"""

import logging
import sys
import time
from collections.abc import Callable, Collection, Mapping
from enum import StrEnum

from PySide6.QtCore import (
    QLocale,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QIcon, QKeySequence
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from polyglotic_desktop.core.learning.curriculum import chosen_from
from polyglotic_desktop.core.listening.captions import CaptionUpdate
from polyglotic_desktop.core.listening.check import Facts, SourceActivity, Ticked
from polyglotic_desktop.core.listening.dictation_keys import DictationKey
from polyglotic_desktop.core.listening.failing import FailingCaptions
from polyglotic_desktop.core.listening.held_back import LIVE_UPDATES_HELD_BACK
from polyglotic_desktop.core.listening.history import CaptionHistory
from polyglotic_desktop.core.listening.hotkeys import CONFLICT_NOTIFY_MS, Hotkey
from polyglotic_desktop.core.listening.hotkeys import keys as hotkey_keys
from polyglotic_desktop.core.listening.sources import (
    EVERYTHING_ELSE,
    MIC,
    SAMPLE,
    WHOLE_SYSTEM,
    SourceId,
    SourceLabel,
)
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.listening.unstable import UnstableConnection
from polyglotic_desktop.core.listening.warm_up import (
    MODELS_WARMING_UP,
    SERVER_RESTARTING,
    TRANSLATOR_WARMING_UP,
    warm_up_over,
)
from polyglotic_desktop.ports.capture import AppList
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ui import theme
from polyglotic_desktop.ui.apps_with_sound import AppsWithSound
from polyglotic_desktop.ui.captions import CaptionFeed
from polyglotic_desktop.ui.icons import (
    TrayState,
    menu_bar_icon,
    tray_icon,
    with_idle_dot,
)
from polyglotic_desktop.ui.learning import LearningTools
from polyglotic_desktop.ui.os_words import (
    on_a_mac,
    on_linux,
    pc_mac_or_linux,
    pc_or_mac,
    platform,
)
from polyglotic_desktop.ui.settings import (
    SOURCE_KEY_EVERYTHING_ELSE,
    SOURCE_KEY_MIC,
    SOURCE_KEY_SAMPLE,
    SOURCE_KEY_SYSTEM,
    Settings,
    load_rules_changes,
)

log = logging.getLogger(__name__)

DARK_TRAY_MENU = """

QMenu { background: #2c2c2c; color: #ffffff; border: 1px solid #454545; padding: 3px 0; }
QMenu::item { padding: 4px 16px 4px 28px; margin: 0 4px; border-radius: 4px; }
QMenu::item:selected { background: #3d3d3d; }
QMenu::item:disabled { color: #787878; }
QMenu::separator { height: 1px; background: #454545; margin: 3px 0; }
"""
"""The tray menu on a dark taskbar: Windows 11's dark menu colours (on a
light one, Qt's Windows 11 style draws Windows' light menu as it is)."""


class ConnectionState(StrEnum):
    """The listening session's state, as Home shows it (`main` maps the
    connection's own states onto these)."""

    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    LISTENING = "listening"
    WAITING = "waiting"  # to reconnect
    SERVER_BUSY = "server_busy"  # to reconnect: the server is full (208)
    SIGN_IN_NEEDED = "sign_in_needed"  # no device token, or it was refused
    UPDATE_NEEDED = "update_needed"  # the server needs a newer app
    MOVED = "moved"  # the account listens on another device (project 095)
    PLUS_ENDED = "plus_ended"  # the server closed listening: Plus ended (4009, 185)
    ALLOWANCE_EXHAUSTED = "allowance_exhausted"
    CROSS_BORDER_CONSENT_REQUIRED = "cross_border_consent_required"
    STOPPED = "stopped"  # for another reason, until the user acts


def tray_menu_place(at: QPoint, size: QSize, area: QRect) -> QPoint:
    """Where the tray's menu opens (its top left): upwards from `at` (the
    mouse on the tray icon), kept wholly on the work area `area` - so above
    a taskbar at the bottom, below one at the top, beside one at a side, as
    Windows' own tray menus open. Qt placed it against the whole screen:
    its last entries (Quit) sat over the taskbar, where a mouse jumping
    straight onto Quit missed it (polyglotic-hq 141)."""
    x = min(at.x(), area.x() + area.width() - size.width())
    y = min(at.y() - size.height(), area.y() + area.height() - size.height())
    return QPoint(max(x, area.x()), max(y, area.y()))


DESKTOP_SHOWS_TRAY_MENU = sys.platform.startswith("linux")
"""Linux's trays show the tray's menu themselves (polyglotic-hq 571): KDE's
and GNOME's AppIndicator draw it from what Qt hands them over D-Bus (the
StatusNotifierItem's menu) and never ask the app to open one, and an X11
tray's (XFCE's older one) is Qt's own at the click. The app opens it itself
only on Windows and a Mac (`show_tray_menu`), where Qt would place it badly."""

TIP_MAX = 127
"""The most a tray icon's tooltip can hold, in UTF-16 units: Windows keeps
it in NOTIFYICONDATA's 128-unit `szTip` with its end, and Qt cuts anything
longer there - mid-word (polyglotic-hq 336)."""


def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def fitted_tip(lines: list[str], limit: int = TIP_MAX) -> str:
    """The tray's tooltip from its lines - the state first, the hidden
    windows' after it (335) - within `limit`: the lines between the first
    and the last go first (Home's rows say "captioning while hidden" too;
    the last, what to do, stays), then the last is cut at a word with "…".
    Never cut mid-word by Windows (polyglotic-hq 336: "Captioning VLC media
    player while hidden" with a window paused ran to "show the windows to
    c" in English, and far shorter in German)."""
    kept = [line for line in lines if line]
    while len(kept) > 2 and _units("\n".join(kept)) > limit:
        del kept[1]
    text = "\n".join(kept)
    if _units(text) <= limit:
        return text
    head = "\n".join(kept[:-1])
    room = limit - _units(head) - (1 if head else 0) - 1  # the line break, the "…"
    words = kept[-1].split(" ")
    last = ""
    for word in words:
        longer = f"{last} {word}" if last else word
        if _units(longer) > room:
            break
        last = longer
    if not last:  # one word longer than the room: cut it
        last = kept[-1][: max(0, room)]
    fitted = f"{head}\n{last}…" if head else f"{last}…"
    return fitted if _units(fitted) <= limit else text[: limit - 1] + "…"


QT_KEYS = {
    "minus": "-",
    "equal": "=",
    "bracket_left": "[",
    "bracket_right": "]",
    "backslash": "\\",
    "semicolon": ";",
    "apostrophe": "'",
    "grave": "`",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "space": "Space",
    "enter": "Return",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Del",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "home": "Home",
    "end": "End",
    "page_up": "PgUp",
    "page_down": "PgDown",
    "insert": "Ins",
    "escape": "Esc",
    "pause": "Pause",
    "scroll_lock": "ScrollLock",
    "print_screen": "Print",
    "menu": "Menu",
    "media_play": "Media Toggle Play/Pause",
    "media_stop": "Media Stop",
    "media_next": "Media Next",
    "media_prev": "Media Previous",
    "volume_up": "Volume Up",
    "volume_down": "Volume Down",
    "volume_mute": "Volume Mute",
}
"""`dictation_keys.KEYS` that Qt names otherwise; letters, digits and F1-F24
are its own names, upper case."""
QT_MODIFIERS = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Meta"}
"""As kept, Qt's names: on a Mac Qt's Ctrl is Command and Meta Control."""


def key_sequence(key: DictationKey | None) -> QKeySequence:
    """A hotkey's key as Qt's shortcut, for menus and the OS's own words
    ("Ctrl+Alt+L"; on a Mac "⌃⌘L"); an empty one for none."""
    if key is None or key.held_alone:
        return QKeySequence()
    held = [QT_MODIFIERS[part] for part in key.parts[:-1]]
    name = key.parts[-1]
    return QKeySequence("+".join([*held, QT_KEYS.get(name) or name.upper()]))


class DesktopApp(QObject):
    hotkey_pressed = Signal(str)
    """A hotkey's name (`Hotkey`), from any thread (queued to the Qt
    thread)."""
    feedback_wanted = Signal(str)
    """The feedback form, opened on a kind (`problem`, `suggestion`, ...)."""
    check_report_wanted = Signal(str)
    """The feedback form for a problem, with Help's check result (ticks and
    crosses, no content) to attach."""
    window_wanted = Signal(bool)
    """The main window, in front: True from the tray - on the page where
    the learner picks what to caption while nothing is (DECISIONS.md
    #25; a new learner's first run captions everything, 484); False: on whatever page it shows
    (nothing asks for that since "Looks wrong?" went, polyglotic-hq 339)."""
    caption_notice = Signal(str)
    """A notice the caption windows show briefly (a server notice;
    listening moved)."""
    connection_changed = Signal(object, object)
    """The listening session's state (a ConnectionState) and the seconds
    until it tries again (or None)."""
    minutes_changed = Signal(float, object)
    connection_unstable = Signal(bool)
    """The listening session's connection keeps dropping or has stalled
    (True), or it has held again (False): said on Home and the caption
    windows (core.listening.unstable)."""
    captions_failing = Signal(bool)
    """Captions are failing on the server (True), or that's over (False):
    said on Home and the caption windows (core.listening.failing)."""
    """This month's minutes (used, left or None)."""
    home_notice = Signal(str)
    """A line Home shows for a while (a server notice, what became of a
    report); empty: the one it shows is over (a warm-up, once captions
    show it is)."""
    themed = Signal()
    """The window's theme changed (the `theme` module has the new colours)."""
    labels_changed = Signal()
    """Which app a source is changed (`set_app_sources`): its captions'
    label (`source_labels`) may be another."""
    dictation_settings_wanted = Signal()
    """The tray's "More languages…" for dictation: Settings > App."""
    hotkeys_settings_wanted = Signal()
    """The tray's hotkey conflict item: opens Settings > Hotkeys (966)."""

    def __init__(
        self,
        store: SettingsStore | None,
        tools: LearningTools | None,
        apps: AppList | None,
        your_sources: tuple[SourceId, ...] = (MIC,),
        history: CaptionHistory | None = None,
        light_taskbar: Callable[[], bool] | None = None,
        activate_from_tray: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.settings = Settings(store, self)
        # the window's theme first: what's built next takes its colours
        self._look = (self.settings.value.theme, self.settings.value.window_theme)
        theme.apply(self._look[1], self._look[0])
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._system_theme)
        self.tools = tools
        if tools is not None:  # the learner's choices for its language (323)
            self._follow_language_choices()
            self.settings.changed.connect(self._follow_language_choices)
            # and its learning load's rules, while the Lab's mode is on (324)
            self._follow_load_rules()
            self.settings.changed.connect(self._follow_load_rules)
            # and the quiet view's chosen words, our curriculum's set (477) -
            # the set filled once the window is up (`fill_curriculum`, 509)
            self._follow_chosen_words(fill=False)
            self.settings.changed.connect(self._follow_chosen_words)
            tools.load_rules_raised.connect(self._keep_load_rules)
        self.history = history or CaptionHistory(your_sources=your_sources)
        self.feed = CaptionFeed(self.history, tools, self)
        self.feed.captioned.connect(self._captioned)
        self.feed.applied.connect(self._applied)
        self._warming_up: str | None = None
        """The warm-up notice on Home's banner, if one is: it comes off once
        the captions show the warm-up is over (`warm_up_over`)."""
        self._restarting = False
        """The server's restart notice is on Home's banner: it comes off once
        the session listens again (`set_connection`)."""
        self.connection = ConnectionState.NOT_CONNECTED
        """The listening session's state now (`set_connection`)."""
        self.retry_in: float | None = None
        self.unreachable: Unreachable | None = None
        """Why the server can't be reached, while the session waits to try
        again (`set_connection`; None: not known, or not waiting)."""
        value = self.settings.value

        self.open_window = self._action("app.open", self.tr("Open Polyglotic"))
        self.pause = self._action(
            "app.pause", self.tr("Pause captions"), checkable=True
        )
        self.caption_mic = self._action(
            "app.caption_mic", self.tr("Caption my own speech"), checkable=True
        )
        self.caption_mic.setChecked(value.caption_mic)
        self.dictation = self._action(
            "app.dictation", self.tr("Dictation (preview)"), checkable=True
        )
        self.dictation.setChecked(value.dictation)
        # dictation's language at the tray, as modes: Detect, English,
        # Mandarin... (`set_dictation_languages`; polyglotic-hq 283)
        self.dictation_language_menu = QMenu(self.tr("Dictation language"))
        self.dictation_language_menu.setObjectName("app.dictation_language")
        self.dictation_language_menu.menuAction().setObjectName(
            "app.dictation_language"
        )
        self._dictation_languages: list[tuple[str, str]] = []
        self._dictation_shown = 0
        self._dictation_shown_as = value.dictation_language
        self.more_dictation_languages = self._action(
            "app.dictation_more", self.tr("More languages…")
        )
        self.more_dictation_languages.triggered.connect(self.dictation_settings_wanted)
        self._show_dictation_languages()  # Detect only, until `main` names them
        self.lock_windows = self._action(
            "windows.lock", self.tr("Lock all caption windows"), checkable=True
        )
        self.lock_windows.setToolTip(
            self.tr("Clicks pass through to the windows underneath")
        )
        self.lock_windows.setChecked(value.locked)
        self.hide_windows = self._action(
            "windows.hide", self.tr("Hide all caption windows"), checkable=True
        )
        self.show_delay = self._action(
            "captions.delay", self.tr("Show each caption's delay"), checkable=True
        )
        self.show_delay.setToolTip(
            self.tr(
                "Above each caption: how long after the speech started and"
                " ended it showed, and the server's share"
            )
        )
        self.show_delay.setChecked(value.show_delay)
        self.quit = self._action("app.quit", self.tr("Quit"))
        self.install_update = self._action("app.install_update", "")
        """The tray's "Restart to install version X", while an update is
        downloaded (polyglotic-hq 299): `main` quits and installs it."""
        self.install_update.setVisible(False)
        self.usage = self._action("account.usage", "")
        """The tray's usage line on a capped plan, "62% of today's free
        captions left" (`show_usage`; polyglotic-hq 684): `main` opens
        Upgrade from it."""
        self.usage.setVisible(False)
        self.hotkey_conflict = self._action("app.hotkey_conflict", "")
        """The tray's conflict item when another program holds a hotkey (966):
        opens Settings > Hotkeys to switch to a free key."""
        self.hotkey_conflict.setVisible(False)
        self.hotkey_conflict.triggered.connect(self.hotkeys_settings_wanted)
        self.quit_check: Callable[[], bool] | None = None
        """Asked before Quit goes on (`may_quit`): `main` hands it the
        transcripts' question (polyglotic-hq 334)."""
        self.report_problem = self._action(
            "feedback.problem", self.tr("Report a problem…")
        )
        self.suggest = self._action(
            "feedback.suggestion", self.tr("Suggest something…")
        )
        self.report_problem.triggered.connect(
            lambda: self.feedback_wanted.emit("problem")
        )
        self.suggest.triggered.connect(lambda: self.feedback_wanted.emit("suggestion"))
        self.work_with_us = self._action(
            "feedback.work_with_us", self.tr("Help build Polyglotic…")
        )
        self.work_with_us.triggered.connect(
            lambda: self.feedback_wanted.emit("work_with_us")
        )
        self.quit.setToolTip(
            pc_mac_or_linux(
                self.tr("Quit Polyglotic - closing the window keeps it in the tray"),
                self.tr(
                    "Quit Polyglotic - closing the window keeps it in the menu bar"
                ),
                # Linux: true with a tray or without one (GNOME's own: 571)
                self.tr("Quit Polyglotic - closing the window keeps it running"),
            )
        )
        self.pause.toggled.connect(
            lambda on: self.pause.setText(
                self.tr("Resume") if on else self.tr("Pause captions")
            )
        )

        # what only a hotkey does: `main` connects each (polyglotic-hq 567),
        # named as Settings > Hotkeys names them
        self.go_live = self._action(
            "captions.live", QApplication.translate("Hotkeys", "Back to live")
        )
        self.copy_caption = self._action(
            "captions.copy",
            QApplication.translate("Hotkeys", "Copy the newest caption"),
        )
        self.next_preset = self._action(
            "captions.preset", QApplication.translate("Hotkeys", "Next preset")
        )
        self.text_bigger = self._action(
            "captions.bigger", QApplication.translate("Hotkeys", "Caption text bigger")
        )
        self.text_smaller = self._action(
            "captions.smaller",
            QApplication.translate("Hotkeys", "Caption text smaller"),
        )
        self.caption_controls = self._action(
            "captions.bar",
            QApplication.translate("Hotkeys", "Open a caption window's controls"),
        )
        self.hotkeys = {
            Hotkey.LOCK.value: self.lock_windows,
            Hotkey.PAUSE.value: self.pause,
            Hotkey.HIDE.value: self.hide_windows,
            Hotkey.LIVE.value: self.go_live,
            Hotkey.COPY.value: self.copy_caption,
            Hotkey.PRESET.value: self.next_preset,
            Hotkey.BIGGER.value: self.text_bigger,
            Hotkey.SMALLER.value: self.text_smaller,
            Hotkey.BAR.value: self.caption_controls,
        }
        """Each hotkey's command, by its name, system-wide (`Hotkey`). (W,
        the newest line checked with the best model, went with "Looks
        wrong?": polyglotic-hq 339.)"""
        self._activity: Callable[[], dict[SourceId, SourceActivity]] = dict
        self._last_caption: float | None = None
        self._drops = UnstableConnection()
        """The listening session's drops (`set_connection`)."""
        self._stalled = False  # the connection stalled (`connection_stalled`)
        self._unstable = False  # as last said (`connection_unstable`)
        self._held = QTimer(self, singleShot=True)
        self._held.timeout.connect(self._held_again)
        self._failures = FailingCaptions()
        """Finished captions failed on the server in a row (`caption_failed`)."""
        self.feed.captioned.connect(self._captions_back)
        # found off the interface thread; main's sources read the same one
        self.apps = AppsWithSound(apps, self) if apps is not None else None
        self.open_window.triggered.connect(self.show_window)
        self.quit.triggered.connect(self._quit)
        self.caption_mic.toggled.connect(
            lambda on: self.settings.update(caption_mic=on)
        )
        self.dictation.toggled.connect(lambda on: self.settings.update(dictation=on))
        self.lock_windows.toggled.connect(lambda on: self.settings.update(locked=on))
        self.show_delay.toggled.connect(lambda on: self.settings.update(show_delay=on))
        self.settings.changed.connect(self._settings_changed)
        for action in self.hotkeys.values():
            # shown in menus; the OS's hotkey does the work, from anywhere
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
            action.setShortcutVisibleInContextMenu(True)
        self.set_hotkeys(hotkey_keys(value.hotkeys, platform()))
        self.hotkey_pressed.connect(self._hotkey, Qt.ConnectionType.QueuedConnection)
        self.tray: QSystemTrayIcon | None = None
        self.tray_icons: Callable[[TrayState, bool], QIcon] = (
            menu_bar_icon if on_a_mac() else tray_icon
        )
        """The tray's icon for a state and a light taskbar: on a Mac the menu
        bar's template, which macOS draws light or dark itself (428)."""
        self.tray_menu = self._tray_menu()
        self.tray_menu.aboutToShow.connect(self._style_tray_menu)
        self.sample_playing = False
        self.state_title = ""
        """The state Home shows, for the tray's tooltip (`show_state_title`)."""
        self.hidden_line = ""
        """Hidden caption windows' line in the tray's tooltip (`show_hidden`)."""
        self.usage_line = ""
        """A capped plan's allowance left, in the tray's tooltip (`show_usage`)."""
        self.hotkey_conflict_line = ""
        """Hotkey conflict line in the tray's tooltip (`show_hotkey_conflicts`)."""
        self._last_hotkey_conflicts: tuple[tuple[str, str, bool], ...] = ()
        self.banner_in_view: Callable[[], bool] = lambda: False
        """Whether Home's banner is in front of the learner now (`main`'s
        main window sets it): a report's outcome is then said there only,
        not in the tray too (`show_feedback`; polyglotic-hq 279)."""
        # Windows doesn't say when only the taskbar turns light or dark
        self._activate_from_tray = activate_from_tray
        self._light_taskbar = light_taskbar or (lambda: theme.system_theme() == "light")
        self._taskbar_check = QTimer(self)
        self._taskbar_check.setInterval(10_000)
        self._taskbar_check.timeout.connect(self._show_tray_state)
        self.pause.toggled.connect(self._show_tray_state)
        # where the OS's light or dark is read by the app, not Qt (Linux's
        # portal: `theme.os_mode`), nothing tells Qt it changed: asked again
        # every 10 s, and followed as Qt's change is (571)
        self._os_mode = theme.system_theme()
        self._os_mode_check = QTimer(self)
        self._os_mode_check.setInterval(10_000)
        self._os_mode_check.timeout.connect(self._follow_os_mode)
        if theme.os_mode is not None:
            self._os_mode_check.start()
        self._apps: dict[SourceId, tuple[str, str]] = {}

    # -- source labels ----------------------------------------------------------------

    def set_app_sources(self, apps: dict[SourceId, tuple[str, str]]) -> None:
        """Each app captured: its source id -> (its name, what it's called
        on screen). From `main`'s `Sources`, on the Qt thread."""
        if dict(apps) != self._apps:
            self._apps = dict(apps)
            self.labels_changed.emit()

    def source_labels(self) -> dict[SourceId, SourceLabel]:
        """How each source's captions are labelled: the learner's name for
        it, or its own ("You" for the mic, "Everything the PC plays" for
        everything it plays - "This PC" until polyglotic-hq 484 -,
        "Everything else" beside one app, an app's on-screen name); and its
        colour."""
        value = self.settings.value
        names = {
            SOURCE_KEY_MIC: self.tr("You"),
            SOURCE_KEY_SYSTEM: pc_or_mac(
                self.tr("Everything the PC plays"), self.tr("Everything the Mac plays")
            ),
        }
        ids = {SOURCE_KEY_MIC: MIC, SOURCE_KEY_SYSTEM: WHOLE_SYSTEM}
        for source_id, (name, title) in self._apps.items():
            names[name], ids[name] = title, source_id
        # last: the colours the others had before it existed stay theirs
        names[SOURCE_KEY_EVERYTHING_ELSE] = self.tr("Everything else")
        ids[SOURCE_KEY_EVERYTHING_ELSE] = EVERYTHING_ELSE
        names[SOURCE_KEY_SAMPLE] = self.tr("Sample")  # Home's (polyglotic-hq 176)
        ids[SOURCE_KEY_SAMPLE] = SAMPLE
        colors = value.source_colors_for(names)
        return {
            ids[key]: SourceLabel(value.source_names.get(key) or own, colors[key])
            for key, own in names.items()
        }

    def set_activity(
        self, provider: Callable[[], dict[SourceId, SourceActivity]]
    ) -> None:
        """What each source being captured has done (`main`'s pipeline), for
        Help's check."""
        self._activity = provider

    def caption_facts(self) -> Facts:
        """What Help's "no captions?" check looks at, as it is now."""
        value = self.settings.value
        labels = self.source_labels()
        activity = self._activity()
        by_name = {name: sid for sid, (name, _) in self._apps.items()}
        ticked: list[Ticked] = []
        for name in value.apps:
            found = by_name.get(name)
            if found is not None:
                ticked.append(Ticked(found, labels[found].name, "app"))
            elif WHOLE_SYSTEM in activity:  # no per-app capture here (Windows 10)
                ticked.append(Ticked(WHOLE_SYSTEM, labels[WHOLE_SYSTEM].name, "system"))
            else:
                shown = value.source_names.get(name) or name
                ticked.append(Ticked(SourceId(f"app:{name}"), shown, "app"))
        if value.whole_system and all(t.id != WHOLE_SYSTEM for t in ticked):
            ticked.append(Ticked(WHOLE_SYSTEM, labels[WHOLE_SYSTEM].name, "system"))
        if value.captions_everything_else and WHOLE_SYSTEM not in activity:
            label = labels[EVERYTHING_ELSE].name
            ticked.append(Ticked(EVERYTHING_ELSE, label, "system"))
        if value.caption_mic:
            ticked.append(Ticked(MIC, labels[MIC].name, "mic"))
        return Facts(
            now=time.monotonic(),
            connection=str(self.connection),
            paused=self.pause.isChecked(),
            overlays_hidden=self.hide_windows.isChecked(),
            ticked=ticked,
            activity=activity,
            last_caption=self._last_caption,
            failing=self.captions_are_failing,
            unreachable=self.unreachable,
        )

    def _action(self, name: str, text: str, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        action.setObjectName(name)
        action.setCheckable(checkable)
        return action

    def set_dictation_languages(
        self, choices: list[tuple[str, str]], shown: int = 3
    ) -> None:
        """The languages dictation can be set to, as (code, name), the
        first `shown` of them in the tray's "Dictation language" menu with
        "Detect automatically" - and the one chosen, if it's another; the
        rest are in Settings ("More languages…")."""
        self._dictation_languages, self._dictation_shown = list(choices), shown
        self._show_dictation_languages()

    def _show_dictation_languages(self, now: bool = True) -> None:
        """The menu as the setting is: the tick moved at once; the
        languages listed again (`now`, or else once the event loop runs
        again - never under the action just triggered, which a rebuild
        deletes)."""
        menu = self.dictation_language_menu
        chosen = self.settings.value.dictation_language or ""
        shown = self._dictation_languages[: self._dictation_shown]
        named = dict(self._dictation_languages)
        if chosen and chosen not in dict(shown) and chosen in named:
            shown.append((chosen, named[chosen]))
        wanted = [("", self.tr("Detect automatically")), *shown]
        there = [a for a in menu.actions() if a.isCheckable()]
        for action in there:
            action.setChecked(action.data() == chosen)
        if [a.data() for a in there] == [code for code, _ in wanted]:
            return
        if not now:
            QTimer.singleShot(0, self._show_dictation_languages)
            return
        menu.clear()
        for code, name in wanted:
            action = menu.addAction(name)
            action.setObjectName(f"app.dictation_language.{code or 'detect'}")
            action.setData(code)
            action.setCheckable(True)
            action.setChecked(code == chosen)
            action.triggered.connect(
                lambda _on, code=code: self.settings.update(
                    dictation_language=code or None
                )
            )
        menu.addSeparator()
        menu.addAction(self.more_dictation_languages)

    def _tray_menu(self) -> QMenu:
        menu = QMenu()
        menu.addAction(self.open_window)
        menu.setDefaultAction(self.open_window)
        menu.addAction(self.install_update)  # hidden until one is ready
        menu.addAction(self.usage)  # hidden on an unlimited plan
        menu.addAction(self.hotkey_conflict)  # hidden unless another app holds a hotkey
        menu.addSeparator()
        for action in (
            self.pause,
            self.lock_windows,
            self.hide_windows,
            self.caption_mic,
            self.dictation,
        ):
            menu.addAction(action)
        menu.addMenu(self.dictation_language_menu)
        for action in (self.show_delay,):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.report_problem)
        menu.addAction(self.suggest)
        menu.addSeparator()
        menu.addAction(self.quit)
        return menu

    def show_update_ready(self, version: str | None) -> None:
        """An update downloaded (`version`), or none: the tray's menu offers
        to restart into it (on Linux: quit to finish updating, since the
        AppImage applies as the app quits - polyglotic-hq 640), under Open -
        quietly, never a notification over a game or a call (polyglotic-hq
        299). Kept after Home's Later."""
        self.install_update.setVisible(version is not None)
        if version is not None:
            text = (
                self.tr("Quit to finish updating to {version}")
                if on_linux()
                else self.tr("Restart to install version {version}")
            )
            self.install_update.setText(text.format(version=version))

    def show_usage(self, line: str | None) -> None:
        """A capped plan's allowance left, as one line in the tray's menu
        and its tooltip - or none, on an unlimited plan (polyglotic-hq 684;
        the words are `ui_next.usage`'s, handed over by `main`)."""
        self.usage_line = line or ""
        self.usage.setText(self.usage_line)
        self.usage.setVisible(bool(line))
        if self.tray is not None:
            self.tray.setToolTip(self._tooltip())

    def offer_dictation(self, offered: bool) -> None:
        """Dictation in the tray's menu, with its languages - or neither, on
        an OS that has no dictation yet (Linux, until polyglotic-hq 546's
        slice 8: its key would be said to be another program's; 574)."""
        self.dictation.setVisible(offered)
        self.dictation_language_menu.menuAction().setVisible(offered)

    def show_dictation_key(self, key: str) -> None:
        """Dictation's key, in words ("Right Ctrl"), at the right of its
        line in the tray menu, as a hotkey is (polyglotic-hq 289)."""
        self.dictation.setText(f"{self.tr('Dictation (preview)')}\t{key}")
        self.dictation.setToolTip(
            self.tr(
                "Hold {key} and speak: your words are typed where your cursor is"
            ).format(key=key)
        )

    def set_hotkeys(self, keys: Mapping[Hotkey, DictationKey | None]) -> None:
        """Each hotkey's key now, shown on its command: Ctrl+Alt+L; on a Mac
        Control+Command, which Qt writes Meta+Ctrl there: "⌃⌘L"
        (polyglotic-hq 428, DECISIONS #193). None: no key."""
        for hotkey, key in keys.items():
            self.hotkeys[hotkey.value].setShortcut(key_sequence(key))

    def hotkeys_not_working(self, keys: Collection[str]) -> None:
        """These hotkeys don't work here - another app already has them, or
        they weren't registered: stop showing them, so a locked caption
        window says where else to unlock it (polyglotic-hq 398), and say so
        in the log."""
        named = [
            self.hotkeys[key].shortcut().toString()
            for key in keys
            if key in self.hotkeys and not self.hotkeys[key].shortcut().isEmpty()
        ]
        if named:
            log.warning("hotkey(s) not working, not shown: %s", ", ".join(named))
        for key in keys:
            if key in self.hotkeys:
                self.hotkeys[key].setShortcut(QKeySequence())

    def show_hotkey_conflicts(
        self, conflicts: Mapping[str, tuple[str, str, bool]]
    ) -> None:
        """Report hotkeys held by another program in the tray menu, tooltip,
        and tray notification (no silent failure, polyglotic-hq 966).

        `conflicts`: hotkey name -> `(label, key_text, shared)` where `shared`
        is True if a fallback hook is sharing the chord so it still works."""
        ordered = tuple(
            (name, key_text, shared)
            for name, (_label, key_text, shared) in sorted(conflicts.items())
        )
        if not conflicts:
            self.hotkey_conflict.setVisible(False)
            self.hotkey_conflict.setText("")
            self.hotkey_conflict_line = ""
            self._last_hotkey_conflicts = ()
            if self.tray is not None:
                self.tray.setToolTip(self._tooltip())
            return
        items = list(conflicts.values())
        keys_joined = QLocale().createSeparatedList(
            [key_text for _, key_text, _ in items]
        )
        self.hotkey_conflict.setText(
            self.tr("Hotkey conflict: {keys}").format(keys=keys_joined)
        )
        self.hotkey_conflict.setVisible(True)
        self.hotkey_conflict_line = self.tr("Another program uses {keys}").format(
            keys=keys_joined
        )
        if self.tray is not None:
            self.tray.setToolTip(self._tooltip())
        if ordered == self._last_hotkey_conflicts:
            return
        self._last_hotkey_conflicts = ordered
        if len(items) == 1:
            label_text, key_text, shared = items[0]
            if shared:
                title = self.tr("Hotkey shared with another program")
                body = self.tr(
                    "Another program also uses {key} ({name}). Polyglotic shares it"
                    " so it still works; open Settings > Hotkeys to switch."
                ).format(key=key_text, name=label_text)
            else:
                title = self.tr("Hotkey conflict")
                body = self.tr(
                    "{name} ({key}) is used by another program. Open Settings >"
                    " Hotkeys to choose a free key."
                ).format(name=label_text, key=key_text)
        else:
            title = self.tr("Hotkey conflicts")
            body = self.tr(
                "Another program uses {keys}. Open Settings > Hotkeys to choose"
                " free keys."
            ).format(keys=keys_joined)
        if self.tray is not None:
            self.tray.showMessage(
                title, body, self.tray.icon(), CONFLICT_NOTIFY_MS.value
            )

    @Slot(str)
    def _hotkey(self, key: str) -> None:
        action = self.hotkeys.get(key)
        if action is not None:
            action.trigger()

    def show_tray(self) -> None:
        """The tray icon, where Windows has a tray: closing the main window
        then keeps the app running there (`tray` is set)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self)
        tray.setToolTip(self._tooltip())
        if DESKTOP_SHOWS_TRAY_MENU:  # Linux: the tray shows it (571)
            tray.setContextMenu(self.tray_menu)
        # elsewhere no setContextMenu: Qt would open it against the whole
        # screen, over the taskbar (`show_tray_menu` opens it above)
        tray.activated.connect(self._tray_activated)
        self.tray = tray
        self._show_tray_state()
        tray.show()
        self._taskbar_check.start()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if self._activate_from_tray is not None and reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Context,
        ):
            self._activate_from_tray()
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()
        elif (
            reason is QSystemTrayIcon.ActivationReason.Context
            and not DESKTOP_SHOWS_TRAY_MENU  # there, it's open already (571)
        ):
            if self._activate_from_tray:
                # Cocoa finishes making the accessory active after the
                # status-item callback. A popup opened during that change
                # closes as soon as its temporary window loses focus.
                QTimer.singleShot(150, self, self.show_tray_menu)
            else:
                self.show_tray_menu()

    def show_tray_menu(self) -> None:
        """The tray's menu, from the mouse on the icon - or the icon, opened
        from the keyboard - wholly on the work area of its screen
        (`tray_menu_place`), measured as styled for the taskbar now
        (polyglotic-hq 146: the taskbar may have turned since the icon's
        last check)."""
        at = QCursor.pos()
        icon = self.tray.geometry() if self.tray is not None else QRect()
        if icon.isValid() and not icon.contains(at):
            at = icon.center()
        screen = QGuiApplication.screenAt(at) or QGuiApplication.primaryScreen()
        menu = self.tray_menu
        self._style_tray_menu()  # before measuring: dark and light differ in size
        menu.popup(tray_menu_place(at, menu.sizeHint(), screen.availableGeometry()))

    def show_state_title(self, title: str, sample_playing: bool = False) -> None:
        """The state Home shows ("Listening", "Paused", ...): the tray's
        tooltip says it too."""
        if self.sample_playing != sample_playing:
            self.sample_playing = sample_playing
            self._show_tray_state()
        self.state_title = title
        if self.tray is not None:
            self.tray.setToolTip(self._tooltip())

    def show_hidden(self, captioning: list[str], paused_after: int | None) -> None:
        """Hidden caption windows, in the tray's tooltip (polyglotic-hq
        335): the apps whose speech they still caption, unseen, and - any
        paused - the minutes they were hidden before their listening
        paused."""
        lines = []
        if captioning:
            names = QLocale().createSeparatedList(captioning)
            lines.append(self.tr("Hidden windows captioning {apps}").format(apps=names))
        if paused_after is not None:
            lines.append(
                self.tr(
                    "Hidden windows paused after %n minutes - show them to resume",
                    "",
                    paused_after,
                )
            )
        self.hidden_line = "\n".join(lines)
        if self.tray is not None:
            self.tray.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        title = f"Polyglotic - {self.state_title}" if self.state_title else "Polyglotic"
        idle = self.tr("Nothing selected to caption") if self._needs_source else ""
        # the usage line sits in the middle: the first to go when it's too long
        return fitted_tip(
            [
                title,
                idle,
                self.usage_line,
                self.hotkey_conflict_line,
                *self.hidden_line.split("\n"),
            ]
        )

    @property
    def _needs_source(self) -> bool:
        return not self.settings.value.source_chosen and not self.sample_playing

    @property
    def tray_state(self) -> TrayState:
        """As Home says it: paused if the learner paused captions;
        listening while the listening session is live and something is
        picked to caption; idle otherwise."""
        if self.pause.isChecked():
            return TrayState.PAUSED
        live = self.connection is ConnectionState.LISTENING
        if live and not self._needs_source:
            return TrayState.LISTENING
        return TrayState.IDLE

    def _show_tray_state(self) -> None:
        if self.tray is not None:
            light = self._light_taskbar()
            icon = self.tray_icons(self.tray_state, light)
            self.tray.setIcon(
                with_idle_dot(icon, theme.WARNING) if self._needs_source else icon
            )
            self.tray.setToolTip(self._tooltip())
            self._style_tray_menu(light)

    def _style_tray_menu(self, light: bool | None = None) -> None:
        """The tray's menu - and its submenus (Transcript) - for the
        taskbar as it is: Windows' own tray menus follow the taskbar's light
        or dark, which can differ from the apps' (Qt follows the apps':
        polyglotic-hq 141 saw a light menu on a dark taskbar). Kept in step
        with the icon, and again just before the menu shows."""
        if light is None:
            light = self._light_taskbar()
        sheet = "" if light else DARK_TRAY_MENU
        submenus = [a.menu() for a in self.tray_menu.actions()]
        for menu in [self.tray_menu, *(m for m in submenus if isinstance(m, QMenu))]:
            if menu.styleSheet() != sheet:
                menu.setStyleSheet(sheet)

    def note_in_tray(self) -> None:
        """The main window was closed, not quit: the first time on this PC
        the tray says the app is still running there and how to quit.
        Closing it used to hide it without a word, and learners thought
        they had quit (polyglotic-hq 135, finding 10)."""
        if self.tray is None or self.settings.value.tray_note_shown:
            return
        title, text = self.tray_note()
        self.tray.showMessage(title, text, self.tray.icon(), 10_000)
        self.settings.update(tray_note_shown=True)

    def tray_note(self) -> tuple[str, str]:
        """The tray's one-time message (title, text), for the state the
        tray shows: captioning, paused, or neither."""
        state = self.tray_state
        if state is TrayState.LISTENING:
            title = self.tr("Polyglotic is still captioning")
        elif state is TrayState.PAUSED:
            title = self.tr("Captions are paused")
            return title, pc_mac_or_linux(
                self.tr("Use the tray icon to resume or quit."),
                self.tr("Use the menu bar icon to resume or quit."),
                # Linux: the tray is the panel's - GNOME's top bar, KDE's, Xfce's
                self.tr("Use the panel icon to resume or quit."),
            )
        else:
            title = self.tr("Polyglotic is still running")
        return title, pc_mac_or_linux(
            self.tr("Use the tray icon to quit."),
            self.tr("Use the menu bar icon to quit."),
            self.tr("Use the panel icon to quit."),
        )

    def show_window(self) -> None:
        """The main window, in front - on the page where the learner picks
        what to caption while nothing is chosen (polyglotic-hq DECISIONS.md
        #25). A new learner's first run captions everything the PC plays
        (484), so it opens on Home, which says so."""
        self.window_wanted.emit(True)

    def set_minutes(self, used: float, left: float | None) -> None:
        """This month's minutes, as the server counts them."""
        self.minutes_changed.emit(used, left)

    def show_notice(self, code: str) -> None:
        """A server notice (protocol.md, `notice`): on Home for a while and
        briefly on the caption windows. A code this app doesn't know isn't
        shown."""
        text = self._notice_text(code)
        if text is None:
            return
        self._warming_up = (
            code if code in (MODELS_WARMING_UP, TRANSLATOR_WARMING_UP) else None
        )
        self._restarting = code == SERVER_RESTARTING
        self.home_notice.emit(text)
        self.caption_notice.emit(text)

    def show_feedback(self, outcome: str, just_sent: bool) -> None:
        """What became of a report, on Home: `sent`, `refused`, `waiting`
        (kept to send later), or `sign_in` (kept until the user signs in).
        A report sent again later says so only once it's through.

        The tray says it too, unless Home's banner is in front of the
        learner (`banner_in_view`): someone in a game or a call never sees
        Home (polyglotic-hq 279). It's Windows' own notification, so focus
        assist (Do not disturb) holds it as it holds any app's; the app adds
        no sound of its own."""
        if outcome in ("waiting", "sign_in") and not just_sent:
            return
        text = {
            "sent": self.tr("Thanks - we have your report.")
            if just_sent
            else self.tr("Thanks - your earlier report reached us."),
            "refused": self.tr(
                "The server couldn't take your report. Please write to us instead."
            ),
            "waiting": self.tr(
                "Your report is saved, and will be sent when the server can be reached."
            ),
            "sign_in": self.tr(
                "Your report is saved, and will be sent once you're signed in."
            ),
        }.get(outcome)
        if text is not None:
            self._warming_up = None  # Home's banner says this instead
            self._restarting = False
            self.home_notice.emit(text)
            if self.tray is not None and not self.banner_in_view():
                self.tray.showMessage("Polyglotic", text, self.tray.icon(), 10_000)

    def _notice_text(self, code: str) -> str | None:
        return {
            MODELS_WARMING_UP: self.tr(
                "Captioning is starting - the first captions may be slow."
            ),
            TRANSLATOR_WARMING_UP: self.tr(
                "Translation is starting - captions appear first."
            ),
            SERVER_RESTARTING: self.tr(
                "Polyglotic's server is restarting - captions resume shortly."
            ),
            # the app's own notice, not the server's: several apps talking
            # at once in Live updates (decision 0097)
            LIVE_UPDATES_HELD_BACK: self.tr(
                "Lots of speech at once - captions update less often"
            ),
        }.get(code)

    def set_connection(
        self,
        state: ConnectionState,
        retry_in: float | None = None,
        unreachable: Unreachable | None = None,
    ) -> None:
        """The listening session's state: kept, announced, and in the tray.
        `unreachable`: why the server can't be reached, if it's known - a
        restart's said by the state line from then on, so the banner's
        notice of it goes (it said the same)."""
        moved_now = (
            state is ConnectionState.MOVED
            and self.connection is not ConnectionState.MOVED
        )
        self._note_drop(state)
        if state is not self.connection and self._failures.captioned():
            self.captions_failing.emit(False)  # the state line says what's next
        if (
            state is ConnectionState.LISTENING
            and state is not self.connection
            and self._restarting
        ):  # the restart is over: Home said so for two minutes (polyglotic-hq 203)
            self._restarting = False
            self.home_notice.emit("")
        if unreachable is Unreachable.RESTARTING and self._restarting:
            self._restarting = False
            self.home_notice.emit("")
        self.connection, self.retry_in = state, retry_in
        self.unreachable = unreachable
        if moved_now:  # one line on the caption windows, once (Home keeps the banner)
            self.caption_notice.emit(self.tr("Listening continues on another device"))
        self.connection_changed.emit(state, retry_in)
        self._show_tray_state()

    def _note_drop(self, state: ConnectionState) -> None:
        """Listening, then reconnecting, is a drop; listening over (any state
        but those) forgets them (core.listening.unstable)."""
        now = time.monotonic()
        reconnecting = (ConnectionState.WAITING, ConnectionState.CONNECTING)
        if self.connection is ConnectionState.LISTENING and state in reconnecting:
            self._drops.dropped(now)
            clears_at = self._drops.clears_at()
            if clears_at is not None:
                self._held.start(max(0, round((clears_at - now) * 1000)))
        elif state not in (ConnectionState.LISTENING, *reconnecting):
            self._held.stop()
            self._drops.stopped(now)
            self._stalled = False
        self._say_unstable(now)

    def _held_again(self) -> None:
        """The connection has held since its last drop: the notice comes off."""
        self._say_unstable(time.monotonic())

    @Slot(bool)
    def connection_stalled(self, stalled: bool) -> None:
        """The connection stalled, or answers flow again
        (core.listening.unstable.stalled)."""
        self._stalled = stalled
        self._say_unstable(time.monotonic())

    def _say_unstable(self, now: float) -> None:
        """`connection_unstable` when it changes: drops that add up, or a
        stall now."""
        dropping = self._drops.unstable(now)
        unstable = dropping or self._stalled
        if unstable != self._unstable:
            self._unstable = unstable
            # the notice and its cause, for the log (polyglotic-hq 271: "Why
            # am I seeing connection unstable ... Why doesn't this ever go away")
            log.info(
                'the "Connection unstable" notice %s (drops that add up: %s; stalled: %s)',
                "is on" if unstable else "is off",
                "yes" if dropping else "no",
                "yes" if self._stalled else "no",
            )
            self.connection_unstable.emit(unstable)

    @property
    def captions_are_failing(self) -> bool:
        return self._failures.failing

    @Slot()
    def caption_failed(self) -> None:
        """A finished caption failed on the server (`processing_failed`)."""
        if self._failures.failed():
            self.captions_failing.emit(True)

    def _captions_back(self, _source_id: str) -> None:
        """A caption arrived: captions failing on the server are over."""
        if self._failures.captioned():
            self.captions_failing.emit(False)

    def _follow_language_choices(self) -> None:
        """The learning tools have what the settings keep for their language
        (the learning window's size, which words are linked) and for each
        other language learned; captions follow a change at once."""
        if self.tools is not None:
            value = self.settings.value
            self.tools.set_choices(
                value.choices_for(self.tools.language),
                {c: value.choices_for(c) for c in value.learning_languages.all},
            )

    def _follow_load_rules(self) -> None:
        """The learner's vocabulary has the learning load's rules the
        settings keep for its language - or none, while the Lab's mode is
        off (polyglotic-hq 324)."""
        if self.tools is not None:
            self.tools.set_load_rules(
                self.settings.value.load_rules_for(self.tools.language)
            )

    def _follow_chosen_words(self, fill: bool = True) -> None:
        """The learner's vocabulary keeps up the quiet view's chosen words
        - our curriculum's set while it's chosen, at its size - as the
        settings keep them (polyglotic-hq 477). `fill` False at the start:
        the set fills at `fill_curriculum`."""
        if self.tools is not None:
            value = self.settings.value
            self.tools.vocabulary.set_chosen(
                chosen_from(value.quiet_words), value.curriculum_size, fill
            )

    def fill_curriculum(self) -> None:
        """Our curriculum's set filled, after the start (`main`): it looks
        through every word heard - 31 ms at 30,000 words met on the main
        PC, which the start's budget had no room for (polyglotic-hq 509)."""
        if self.tools is not None:
            self.tools.vocabulary.fill_curriculum()

    def _keep_load_rules(self) -> None:
        """Words added to the load by hand raised its size: the settings
        keep the size it has now."""
        tools = self.tools
        rules = tools.vocabulary.load.rules if tools is not None else None
        if tools is not None and rules is not None:
            value = self.settings.value
            if rules != value.load_rules_for(tools.language):
                self.settings.update(**load_rules_changes(value, tools.language, rules))

    def _captioned(self, _source_id: str) -> None:
        self._last_caption = time.monotonic()

    @Slot(object)
    def _applied(self, update: CaptionUpdate) -> None:
        """A caption update shown: a warm-up notice on Home that it shows
        is over comes off (the caption windows' went after a few seconds)."""
        if self._warming_up is not None and warm_up_over(self._warming_up, update):
            self._warming_up = None
            self.home_notice.emit("")

    # -- keeping things in step -------------------------------------------------------

    def _settings_changed(self) -> None:
        value = self.settings.value
        if (value.theme, value.window_theme) != self._look:
            self._look = (value.theme, value.window_theme)
            self._retheme()
        if self.caption_mic.isChecked() != value.caption_mic:
            self.caption_mic.setChecked(value.caption_mic)
        if self.lock_windows.isChecked() != value.locked:
            self.lock_windows.setChecked(value.locked)
        if self.show_delay.isChecked() != value.show_delay:
            self.show_delay.setChecked(value.show_delay)
        if self.dictation.isChecked() != value.dictation:
            self.dictation.setChecked(value.dictation)
        if value.dictation_language != self._dictation_shown_as:
            self._dictation_shown_as = value.dictation_language
            self._show_dictation_languages(now=False)

        self._show_tray_state()

    def _follow_os_mode(self) -> None:
        """The OS's light or dark as `theme.os_mode` reads it, followed when
        it changes (571)."""
        mode = theme.system_theme()
        if mode != self._os_mode:
            self._os_mode = mode
            self._system_theme()

    def _system_theme(self) -> None:
        """Windows switched between light and dark: followed if the
        learner chose "system"; the tray's icon follows the taskbar."""
        if self._look[1] == "system":
            self._retheme()
        self._show_tray_state()

    def _retheme(self) -> None:
        theme.apply(self._look[1], self._look[0])
        self.themed.emit()

    def may_quit(self) -> bool:
        """Whether Quit may go on: `quit_check`'s answer (the transcripts'
        question, polyglotic-hq 334), or yes."""
        return self.quit_check() if self.quit_check is not None else True

    def _quit(self) -> None:
        """The learner's Quit: the app ends, whatever its windows say - once
        `may_quit` says yes (a transcript not saved, 334).

        `exit()`, not `quit()`: Qt 6's `quit()` first asks every window to
        close and gives up if one refuses while another still shows - the
        main window, kept in the tray, refuses; and depending on Qt's own
        order of windows the caption windows were still up. On a real
        screen the app then ran on, its tray icon already gone and nothing
        left to quit it with (polyglotic-hq 141). `main`'s `aboutToQuit`
        closes and saves every window as before."""
        if not self.may_quit():
            return
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.exit(0)

    def close(self) -> None:
        self._taskbar_check.stop()
        self._os_mode_check.stop()
        if self.tray is not None:
            self.tray.hide()
        if self.apps is not None:
            self.apps.stop()  # its thread ends; no look starts after this


__all__ = ["ConnectionState", "DesktopApp"]
