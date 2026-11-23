"""Home, in the new main window (polyglotic-hq project 109's structure,
sections 5 and 7; wireframes 3 and 6).

Top to bottom, in one column:
1. **The state line** (today's hero card): the banner - the notice the
   caption windows show on their notice line, in the same words (a server
   notice, a busy time, today's free minutes used; 087 section 5.5), or
   the learner's dictionary being out, with how to fix it, or their
   learning data set aside at the start (polyglotic-hq 206) - then
   the dot and the state, its details, this month's minutes, and Pause
   captions / Resume, or Sign in while signed out; "Listening moved to
   another device" with Listen here; the "ran into an error last time"
   offer; until the learner sets their level or says Not now, one
   quiet line asking for it - the first run doesn't (polyglotic-hq 293);
   and, once an update has downloaded, a quiet card saying so - "Version X
   is ready", what's new in two lines, Restart now and Later
   (`show_update`; polyglotic-hq 299) - on a metered connection, "Version
   X is available", its size and Download anyway instead (345): never a
   window over what the learner is doing; after an update, what's new in
   this version, in a few lines, with All the changes (Help's) and Close -
   once per version (`show_whats_new`; polyglotic-hq 345).
2. **Caption** - the app picker (`PickerCard`): a row per captioned app
   (at most 3) with its colour and name (click either to change it), what
   it's doing, its window's language (or Original only), the my-speech
   mark, Captions, Transcript and x; once an app is added, "Also caption
   everything else the PC plays" (a row of its own when on; off, saying
   why, with 2 or 3 apps - DECISIONS.md #59); the apps with sound that
   could be added - greyed at 3 of 3, or beside everything else, with the
   reason; Everything the PC plays instead; and the "My speech" line.
   **Sound** under it (`sound_card`, polyglotic-hq 372): which speakers
   everything the PC plays comes from, Caption what I say, the mic and
   its level - the same card as Settings > Speech's.
3. **Caption windows**: Lock all, Hide all, Join windows / Separate
   windows (with 2 apps or more), Reset positions.
4. The feedback line.

The Languages and Timing panels moved to Settings > Captions (248's
section 2.1; 261): Timing keeps its one-line shortcut on each caption
window. What it shows comes from its views (`views.home`); what the
learner does goes back to them. Apps' names stay on this PC.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import (
    QDate,
    QDateTime,
    QEvent,
    QLocale,
    QObject,
    QPoint,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAccessible,
    QAccessibleAnnouncementEvent,
    QAction,
    QColor,
    QCursor,
    QGuiApplication,
    QHideEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from polyglotic_desktop.core.listening.hidden import Sight
from polyglotic_desktop.core.listening.hotkeys import OWN_MODIFIERS
from polyglotic_desktop.core.listening.maintenance import Maintenance
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.shared.papers import STATUS_PAGE
from polyglotic_desktop.perf import spans
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ports.learning import SetAsideLearningData
from polyglotic_desktop.ui_next import maintenance, style, wheel
from polyglotic_desktop.ui_next.caption_window import notice_text, reduced_motion
from polyglotic_desktop.ui_next.controls import (
    Card,
    Flow,
    GlyphButton,
    StatusDot,
    SwitchRow,
    WrapButton,
    WrapRadioButton,
    label,
    page_button,
    swatch,
)
from polyglotic_desktop.ui_next.glyphs import Glyph, paint
from polyglotic_desktop.ui_next.languages import (
    in_sentence,
    language_name,
    name_list,
    not_offered_note,
    shown_name,
    target_languages,
)
from polyglotic_desktop.ui_next.lookup_card import dictionary_out
from polyglotic_desktop.ui_next.os_words import (
    hotkeys_here,
    on_linux,
    pc_mac_or_linux,
    pc_or_mac,
    platform,
)
from polyglotic_desktop.ui_next.pack_row import megabytes
from polyglotic_desktop.ui_next.plan import get_plus_text
from polyglotic_desktop.ui_next.sound_card import SoundCard
from polyglotic_desktop.ui_next.views.caption_window import (
    ORIGINAL_ONLY,
    Notice,
    minutes_used_up,
)
from polyglotic_desktop.ui_next.views.home import (
    Action,
    AddableApp,
    AppRow,
    AppStatus,
    Detail,
    HomeState,
    ListeningState,
    Picker,
    PickerView,
    Sample,
    Title,
    state_line,
    unreachable_line,
)
from polyglotic_desktop.ui_next.views.sound import SoundView

COLUMN = 720
"""The content column's width at most (109's 10.5)."""
MARGIN = 24
"""Around a page's column."""
REFRESH_MS = 3000
"""The apps with sound are looked for again this often while Home shows
(off the interface thread)."""
NOTICE_ON_HOME_MS = 120_000
"""A brief notice (a server's, a busy time) stays on Home this long (today's)."""
TICK_MS = 1000
"""While reconnecting, the seconds to the next try count down this often."""
MAINTENANCE_CHECK_MS = 30_000
"""While a planned maintenance window is held, its line is looked at again
this often: it comes a day ahead, changes at the start, and goes at the end."""
MAX_LABEL = 40
"""Characters in an app's label (today's `MAX_SOURCE_NAME`)."""
NAME_LEAST = 96
"""An app's name on its row is never narrower (at 100 % text size): its
buttons go under it first (polyglotic-hq 354)."""
WHATS_NEW_ON_HOME = 3
"""What's new after an update: its notes' first lines on Home (345)."""


def _tr(text: str) -> str:
    return QApplication.translate("Home", text)


def not_writable_notice() -> str:
    """Home's and Settings > Updates' notice when an AppImage sits in a folder
    the learner can't change: one string, so both say the same (polyglotic-hq 640)."""
    return _tr(
        "Polyglotic can't update itself in this folder. Move it to your "
        "Applications folder (~/Applications) and start it from there."
    )


def open_folder_label() -> str:
    """Button beside the not-writable notice on Home and in Settings > Updates."""
    return _tr("Open folder")


def update_ready_linux() -> str:
    """Home's and Settings > Updates' "update ready" line on Linux, where an
    AppImage update applies when the app quits (polyglotic-hq 640)."""
    return _tr(
        "Version {version} is ready. Quit and start Polyglotic again to finish updating."
    )


def quit_now_label() -> str:
    """Button beside the update-ready line on Linux (polyglotic-hq 640)."""
    return _tr("Quit now")


def learning_set_aside_notice(aside: SetAsideLearningData) -> str:
    """Home's words for learning data set aside at the start
    (polyglotic-hq 206): what happened, the file's name - for a report -
    and that the words come back."""
    return pc_or_mac(
        _tr(
            "Your learning data on this PC was damaged, so it's been set aside as"
            " {name}. Your saved words are coming back from your account."
        ),
        _tr(
            "Your learning data on this Mac was damaged, so it's been set aside as "
            "{name}. Your saved words are coming back from your account."
        ),
    ).format(name=aside.path.name)


def learning_unsaved_notice() -> str:
    """Home's words for learning data found damaged since the start
    (polyglotic-hq 206): nothing more is kept until a restart, which brings
    the words back."""
    return pc_or_mac(
        _tr(
            "Your learning data on this PC was damaged, so changes aren't kept on"
            " this PC until you restart Polyglotic. Your saved words then come back"
            " from your account."
        ),
        _tr(
            "Your learning data on this Mac was damaged, so changes aren't kept on "
            "this Mac until you restart Polyglotic. Your saved words then come back "
            "from your account."
        ),
    )


KEYS_THAT_CLICK = frozenset(
    {Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Select}
)
"""Keys that press a focused button."""


class OneClick(QObject):
    """The picker's + (or its x): the second click of a double-click is let
    go - one within the double-click time and distance of the last. Adding
    or stopping an app moves the rows, and a double-click's second click
    landed on the next app's - two captioned, or two stopped (polyglotic-hq
    133). A quick click somewhere else is the learner's next choice, and
    counts (141: a second app's + clicked half a second after the first did
    nothing). A press by the keyboard always counts: a keyboard has no
    double-click, and the mouse hasn't moved between two presses (158) -
    for the buttons it `watch`es."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        where: Callable[[], QPoint] = QCursor.pos,
    ) -> None:
        super().__init__()
        self.clock = clock
        self.where = where
        self._last: tuple[float, QPoint] | None = None
        self._by_keyboard = False

    def watch(self, button: QWidget) -> None:
        """`button`'s presses by the keyboard are told from the mouse's."""
        button.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(event, QKeyEvent) and event.key() in KEYS_THAT_CLICK:
            self._by_keyboard = True
        elif event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        ):
            self._by_keyboard = False
        return False

    def __call__(self, then: Callable[[], None]) -> None:
        by_keyboard, self._by_keyboard = self._by_keyboard, False
        if by_keyboard:
            self._last = None  # nor is a click after it a double-click's second
            then()
            return
        now, at = self.clock(), self.where()
        hints = QGuiApplication.styleHints()
        if self._last is not None:
            then_, there = self._last
            soon = now - then_ < hints.mouseDoubleClickInterval() / 1000
            near = (at - there).manhattanLength() <= hints.mouseDoubleClickDistance()
            if soon and near:
                return
        self._last = (now, at)
        then()


class Page(QScrollArea):
    """A page of the main window: a scrolling column of cards, at most
    `width` px wide and centred - the extra width is margin, not stretched
    cards. `content` is the column's layout."""

    def __init__(self, title: str, width: int = COLUMN) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("Page")
        row = QHBoxLayout(inner)
        row.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        self._row = row
        row.addStretch(1)
        column = QWidget()
        column.setMaximumWidth(style.px(width))  # grows with the text size
        self._column, self._width = column, width
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(column, 1000)
        row.addStretch(1)
        self.content = QVBoxLayout(column)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(16)
        self.content.addWidget(label(title, "PageTitle"))
        self.setWidget(inner)
        # the wheel scrolls the page, never a list or slider it passes over
        # (polyglotic-hq 304, decision 0092)
        wheel.guard(self)
        self.verticalScrollBar().rangeChanged.connect(self._keep_gutter)
        self._keep_gutter()

    def _keep_gutter(self) -> None:
        """The scroll bar's room kept at the right while there's no bar: a
        page short enough to need none had its column 5 px further right
        than a long one's, so the title and Settings' sections stepped
        sideways under the mouse from one section to the next (polyglotic-hq
        376; 109's "nothing moves")."""
        bar = self.verticalScrollBar()
        spare = 0 if bar.maximum() > bar.minimum() else bar.sizeHint().width()
        margins = self._row.contentsMargins()
        if margins.right() != MARGIN + spare:
            margins.setRight(MARGIN + spare)
            self._row.setContentsMargins(margins)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:  # perhaps another text size
            self.fit_column()
            self._keep_gutter()

    def fit_column(self) -> None:
        """The column's width at the text size now."""
        self._column.setMaximumWidth(style.px(self._width))


def _button(text: str, kind: str | None = None, tip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        button.setProperty("kind", kind)
    if tip:
        button.setToolTip(tip)
    return button


def hotkey_works(action: QAction) -> bool:
    """`action`'s hotkey (Ctrl+Alt+ a letter) works on this PC: one another
    app has, or that was never registered, is cleared from it
    (`DesktopApp.hotkeys_not_working`, polyglotic-hq 398) - and then
    nothing on Home or Help names it (400)."""
    return not action.shortcut().isEmpty()


def own_hotkey(action: QAction, letter: str) -> bool:
    """`action`'s hotkey works and is still the app's own Ctrl+Alt+`letter`
    (the platform's: ⌃⌘ on a Mac): the words that name it say that one, so a key the
    learner chose instead leaves them unsaid (polyglotic-hq 567)."""
    qt = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Meta"}
    held = [qt[m.value] for m in OWN_MODIFIERS[platform()]]
    own = QKeySequence("+".join([*held, letter]))  # Qt reads them in any order
    return hotkey_works(action) and action.shortcut() == own


def _bound(text: str, action: QAction) -> QPushButton:
    """A checkable button showing a checkable action - either changes it."""
    button = _button(text)
    button.setCheckable(True)
    button.setChecked(action.isChecked())
    button.toggled.connect(action.setChecked)
    action.toggled.connect(button.setChecked)
    return button


# -- the state line --------------------------------------------------------------------


class StateCard(Card):
    """Home's first card: the banner, what's happening, and Pause captions /
    Resume - or Sign in; and Server status while the server can't be
    reached and the problem may be ours."""

    def __init__(
        self,
        pause: QAction,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """`clock`: what the countdown to the next try reads (the
        connection's `retry_at` is on it); `wall_clock`: this PC's time, a
        planned maintenance window is placed against (319)."""
        super().__init__()
        self.setObjectName("Card")
        self._clock = clock
        self._wall_clock = wall_clock
        self._state = HomeState()
        self.notice = label("", "Banner", wrap=True)
        """The banner: captions failing on the server, else the newest
        brief notice for a while, else today's free minutes used, else an
        unstable connection - in the caption windows' words - else the
        learner's dictionary being out, else their learning data set aside
        (`_show_banner`)."""
        self.notice.hide()
        self.add(self.notice)
        self.capture_problem = label("", "Banner", wrap=True)
        self.capture_settings = page_button(
            QApplication.translate("Settings", "Open System Settings"),
            "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            "home.system_audio_settings",
        )
        self.capture_settings.setToolTip(
            QApplication.translate("Settings", "Open System Settings")
        )
        self.add(self.capture_problem)
        self.add(self.capture_settings)
        self.capture_problem.hide()
        self.capture_settings.hide()
        self._brief: str | None = None
        self._minutes_used = False
        self._failing = False
        self._unstable = False
        self._clock_off: str | None = None
        """This PC's clock looks wrong (313): on the banner, captions working."""
        self._email_sign_in = True
        self._pause_key = True
        """Ctrl+Alt+P works here (`show_pause_key`)."""
        self._dictionary: str | None = None
        self._learning: str | None = None
        self._maintenance: Maintenance | None = None
        self._maintenance_check = QTimer(self, interval=MAINTENANCE_CHECK_MS)
        self._maintenance_check.timeout.connect(self._show_banner)
        # its button under its words where they don't fit beside (354)
        row = Flow(spacing=14)
        self.dot = StatusDot(size=14)
        row.addWidget(self.dot)
        words = QVBoxLayout()
        words.setSpacing(2)
        self.title_label = label("", "StateTitle", wrap=True)  # never wider (354)
        self.title_label.setObjectName("StateTitle")
        self.detail = label("", "Dim", wrap=True)
        self.minutes = label("", "Faint", wrap=True)
        self.minutes.hide()
        self.plan = label("", "Faint", wrap=True)
        """The account's plan in one line (`views.plan`; polyglotic-hq 185)."""
        self.plan.setObjectName("home.plan")
        self.plan.hide()
        self._plus_ended = False  # the title says it: the plan line would repeat it
        for each in (self.title_label, self.detail, self.minutes, self.plan):
            words.addWidget(each)
        self.status_page = page_button(
            server_status_text(), STATUS_PAGE, "home.status_page"
        )
        """While the server can't be reached and the problem may be ours:
        the site's status page (polyglotic-hq 540, 563)."""
        self.status_page.setProperty("kind", "ghost")
        self.status_page.hide()
        row.add_layout(words, 1)
        self.pause = QToolButton()
        self.pause.setDefaultAction(pause)
        self.pause.setProperty("kind", "primary")
        self.pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause.setMinimumWidth(style.px(110))
        self.pause.hide()
        row.addWidget(self.pause)
        self.sign_in = _button(_tr("Sign in"), "primary")
        self.sign_in.setObjectName("home.sign_in")
        self.sign_in.setMinimumWidth(style.px(110))
        self.sign_in.hide()
        row.addWidget(self.sign_in)
        self.get_plus = _button(get_plus_text(), "primary")
        """Plus ended: the site's Plus page (Account's "Get Plus" - one address)."""
        self.get_plus.setObjectName("home.get_plus")
        self.get_plus.setMinimumWidth(style.px(110))
        self.get_plus.hide()
        row.addWidget(self.get_plus)
        self.upgrade = _button(_tr("Upgrade"), "primary")
        self.upgrade.setObjectName("home.upgrade")
        self.upgrade.hide()
        row.addWidget(self.upgrade)
        self.review_consent = _button(_tr("Review consent"), "primary")
        self.review_consent.hide()
        row.addWidget(self.review_consent)
        # after the state's own button: where they don't fit, it goes under
        row.addWidget(self.status_page)
        self.add(row)
        self._notice_timer = QTimer(self, singleShot=True, interval=NOTICE_ON_HOME_MS)
        self._notice_timer.timeout.connect(lambda: self.set_notice(None))
        self._tick = QTimer(self, interval=TICK_MS)
        """While reconnecting: the seconds to the next try, counting down."""
        self._tick.timeout.connect(self.tick)

    def show_state(self, state: HomeState) -> None:
        said = self._state.unreachable
        self._state = state
        self.tick()
        if state.unreachable != said:  # the unstable connection's notice
            self._show_banner()

    def show_pause_key(self, works: bool) -> None:
        """Ctrl+Alt+P works here: the paused line names it; else it says
        to resume here or from the tray (polyglotic-hq 400)."""
        if works != self._pause_key:
            self._pause_key = works
            self.tick()

    def use_email_sign_in(self, available: bool) -> None:
        self._email_sign_in = available
        self.tick()

    def tick(self) -> None:
        """The line as it is now - the countdown a second on."""
        line = state_line(replace(self._state, failing=self._failing), self._clock())
        self.dot.set_token(line.tone.value)
        self.dot.set_pulsing(line.pulse)
        if line.title is Title.MAINTENANCE:  # until when (319)
            title = maintenance.state_title(self._maintenance, self._wall_clock())
        else:
            title = _TITLES[line.title]()
        self.title_label.setText(title)
        self.detail.setText(
            " · ".join(
                _detail(d, arg, self._pause_key, email_sign_in=self._email_sign_in)
                for d, arg in line.details
            )
        )
        self.sign_in.setVisible(line.action is Action.SIGN_IN)
        self.get_plus.setVisible(line.action is Action.GET_PLUS)
        self.upgrade.setVisible(line.action is Action.UPGRADE)
        self.review_consent.setVisible(line.action is Action.REVIEW_CONSENT)
        self.status_page.setVisible(line.status_page)
        self.pause.setVisible(line.action is Action.PAUSE)
        self._plus_ended = line.title is Title.PLUS_ENDED
        self.plan.setVisible(bool(self.plan.text()) and not self._plus_ended)
        counting = any(detail is Detail.RETRY_IN for detail, _ in line.details)
        if counting and not self._tick.isActive():
            self._tick.start()
        elif not counting:
            self._tick.stop()

    def show_capture_problem(self, text: str) -> None:
        """Keep the recovery action visible while the selected source is unavailable."""
        self.capture_problem.setText(text)
        self.capture_problem.setVisible(bool(text))
        self.capture_settings.setVisible(bool(text))

    def set_notice(self, text: str | None) -> None:
        """A brief notice on the banner for a while (None: gone)."""
        self._brief = text or None
        if text:
            self._notice_timer.start()
        self._show_banner()

    def _show_banner(self) -> None:
        """Captions failing first - it's what is happening now, and a brief
        notice lasts two minutes here: the server's warm-up said "starting"
        while every window said failing (184's QA, 176) - then a brief
        notice, then today's minutes used, then an unstable connection, then
        this PC's clock looking wrong (313: captions work - set it), then
        the learner's dictionary being out: it's for lookups only, and it
        stays until it's repaired (polyglotic-hq 199) - then the learning
        data set aside at the start: nothing to do, so last; it stays while
        the app runs (polyglotic-hq 206). The unstable connection isn't said
        while the state line says why the server can't be reached: "Connection
        unstable" beside "the problem is ours" left it unclear whose it was
        (polyglotic-hq 251) - the caption windows don't say it beside a state
        either. A planned maintenance window comes after the unstable
        connection: a day ahead, and during it while the state line doesn't
        say it (polyglotic-hq 319)."""
        text = notice_text(Notice.FAILING, None) if self._failing else self._brief
        if text is None and self._minutes_used:
            text = notice_text(Notice.MINUTES_USED, None)
        if text is None and self._unstable and self._state.unreachable is None:
            text = notice_text(Notice.UNSTABLE, None)
        if text is None and self._state.unreachable is not Unreachable.MAINTENANCE:
            text = maintenance.banner(self._maintenance, self._wall_clock())
        if text is None:
            text = self._clock_off
        if text is None:
            text = self._dictionary
        if text is None:
            text = self._learning
        self.notice.setText(text or "")
        self.notice.setVisible(text is not None)

    def set_maintenance(self, window: Maintenance | None) -> None:
        """The planned maintenance window the app holds (None: none): a
        quiet line on the banner from a day before, and until when while
        it's on - unless the state line says it (polyglotic-hq 319)."""
        self._maintenance = window
        if window is None:
            self._maintenance_check.stop()
        elif not self._maintenance_check.isActive():
            self._maintenance_check.start()
        self._show_banner()
        self.tick()

    def set_failing(self, failing: bool) -> None:
        """Captions failing on the server: on the banner until a caption
        arrives again, in the caption windows' words."""
        self._failing = failing
        self._show_banner()
        self.tick()  # the state's colour with it

    def set_unstable(self, unstable: bool) -> None:
        """The connection keeps dropping: on the banner until it has held
        again, in the caption windows' words."""
        self._unstable = unstable
        self._show_banner()

    def set_plan(self, text: str | None) -> None:
        """The plan line (`ui_next.plan.plan_text`); None: none heard."""
        self.plan.setText(text or "")
        self.plan.setVisible(bool(text) and not self._plus_ended)

    def set_minutes(self, used: float, left: float | None) -> None:
        if left is None:
            text = _tr("Minutes captioned this month: {used}").format(used=int(used))
        else:
            text = _tr("Minutes this month: {used} of {total}").format(
                used=int(used), total=int(used + left)
            )
        self.minutes.setText(text)
        self.minutes.show()
        used_up = minutes_used_up(left)
        if used_up != self._minutes_used:
            self._minutes_used = used_up
            self._show_banner()

    def set_dictionary_out(
        self, problem: DictionaryProblem | None, chinese: bool
    ) -> None:
        """The learner's dictionary is out (None: it isn't): what's wrong
        and how to fix it, in the lookup card's words, on the banner until
        it's repaired (polyglotic-hq 199)."""
        if problem is None:
            self._dictionary = None
        else:
            what, fix = dictionary_out(problem, chinese)
            #: a problem, then how to fix it: two sentences of their own
            self._dictionary = _tr("{problem}. {fix}").format(problem=what, fix=fix)
        self._show_banner()

    def set_clock_looks_wrong(self, wrong: bool) -> None:
        """A session opened with its certificate let through on this PC's
        clock (connection.tls; 313): on the banner while it stays so, with
        what the clock said then - captions work, nothing stops."""
        self._clock_off = clock_looks_wrong_notice() if wrong else None
        self._show_banner()

    def set_learning_set_aside(
        self, aside: SetAsideLearningData | None, unsaved: bool = False
    ) -> None:
        """The learner's learning data was set aside at the start (None: it
        wasn't), or `unsaved` - found damaged since, so nothing is kept until
        a restart: on the banner, last, while the app runs (polyglotic-hq
        206)."""
        if unsaved:
            self._learning = learning_unsaved_notice()
        else:
            self._learning = learning_set_aside_notice(aside) if aside else None
        self._show_banner()


_TITLES: dict[Title, Callable[[], str]] = {
    Title.PAUSED: lambda: _tr("Paused"),
    Title.PICK: lambda: _tr("Pick what to caption"),
    Title.NOT_CONNECTED: lambda: _tr("Not connected"),
    Title.CONNECTING: lambda: _tr("Connecting"),
    Title.LISTENING: lambda: _tr("Listening"),
    Title.RECONNECTING: lambda: _tr("Reconnecting"),
    # full, not the learner's connection (208): "trying again in 24 s" after it
    Title.SERVER_BUSY: lambda: _tr("Polyglotic is busy — try again in a few minutes"),
    Title.NOT_SIGNED_IN: lambda: _tr("Not signed in"),
    Title.UPDATE_NEEDED: lambda: _tr("Update needed"),
    Title.MOVED: lambda: _tr("Listening moved"),
    Title.PLUS_ENDED: lambda: _tr("Plus has ended"),
    Title.ALLOWANCE_EXHAUSTED: lambda: _tr("You’ve used your listening allowance"),
    Title.CROSS_BORDER_CONSENT_REQUIRED: lambda: _tr(
        "Consent is needed to start listening"
    ),
    Title.STOPPED: lambda: _tr("Stopped"),
    # waiting to try again: why the server can't be reached (251)
    Title.CANT_REACH: lambda: _tr("Can't reach Polyglotic's server"),
    Title.SERVER_RESTARTING: lambda: _tr("Polyglotic's server is restarting"),
    Title.SERVER_PROBLEM: lambda: _tr("Polyglotic's server has a problem"),
    Title.BLOCKED: lambda: _tr("This network is blocking Polyglotic"),
    Title.NOT_SECURE: lambda: _tr("Can't connect securely"),
    Title.CLOCK: lambda: pc_or_mac(
        _tr("Check this PC's date and time"), _tr("Check this Mac's date and time")
    ),
    Title.TOO_MANY_SESSIONS: lambda: pc_or_mac(
        _tr("Polyglotic is open on too many of your PCs"),
        _tr("Polyglotic is open on too many of your computers"),
    ),
    Title.TOO_MANY_TRIES: lambda: _tr("Too many sign-in tries"),
    # with the window held, "until 15:30" (`ui_next.maintenance.state_title`)
    Title.MAINTENANCE: lambda: maintenance.state_title(None, datetime.now(UTC)),
}


def server_status_text() -> str:
    """The site's status page, as Home and Help name it: one string."""
    return _tr("Server status")


def unreachable_words(why: Unreachable) -> tuple[str, str]:
    """What's wrong and what to do when the server can't be reached, in
    Home's words, as Help's check says them: the title, and the detail as
    a sentence (polyglotic-hq 251)."""
    title, detail = unreachable_line(why)
    text = _UNREACHABLE_DETAILS[detail]()
    #: Home's line on why the server can't be reached, as a sentence in Help
    return _TITLES[title](), _tr("{line}.").format(line=text[:1].upper() + text[1:])


def this_pcs_date() -> str:
    """The date this PC's clock says, as its regional format writes it."""
    return QLocale().toString(QDate.currentDate(), QLocale.FormatType.LongFormat)


def clock_looks_wrong_notice() -> str:
    """Home's banner while the connection was let through with this PC's
    time outside its certificate's dates (connection.tls, decision 0104;
    polyglotic-hq 313): captions work; what the clock says, and where to
    set it."""
    now = QDateTime.currentDateTime()
    return pc_mac_or_linux(
        #: {date}, {time}: what this PC's clock says, in its regional format
        _tr(
            "This PC's date or time looks wrong: it says {date}, {time}. Captions "
            "work; to set it, turn on Set time automatically in Windows' Settings, "
            "Time & language, Date & time, then choose Sync now."
        ),
        #: {date}, {time}: what this Mac's clock says, in its regional format
        _tr(
            "This Mac's date or time looks wrong: it says {date}, {time}. Captions "
            "work; to set it, turn on Set time and date automatically in System "
            "Settings, General, Date & Time."
        ),
        #: {date}, {time}: what this PC's clock says, in its regional format.
        #: Linux: GNOME's, KDE's and Xfce's settings each have a Date & Time page
        _tr(
            "This PC's date or time looks wrong: it says {date}, {time}. Captions "
            "work; to set it, turn on automatic date and time in your desktop's "
            "settings, under Date & Time."
        ),
    ).format(
        date=QLocale().toString(now.date(), QLocale.FormatType.LongFormat),
        time=QLocale().toString(now.time(), QLocale.FormatType.ShortFormat),
    )


def sign_in_needed(email: bool = True) -> str:
    """What signing in needs - Home's line after "Not signed in", and
    Account's: one string, so the two say the same (polyglotic-hq 228)."""
    return (
        _tr("sign in with your email to listen")
        if email
        else _tr("you need a code from us: an invite, or the one in your Plus email")
    )


def _detail(
    detail: Detail, arg: object, pause_key: bool = True, *, email_sign_in: bool = True
) -> str:
    """`pause_key`: Ctrl+Alt+P works here, so the paused line names it."""
    if detail is Detail.RESUME:
        if not pause_key:
            return pc_mac_or_linux(
                _tr("resume here or from the tray"),
                _tr("resume here or from the menu bar"),
                _tr("resume here"),  # Linux: GNOME has no tray of its own (571)
            )
        return hotkeys_here(
            pc_mac_or_linux(
                _tr("resume with Ctrl+Alt+P, or from the tray"),
                _tr("resume with Ctrl+Alt+P, or from the menu bar"),
                _tr("resume with Ctrl+Alt+P, or here"),
            )
        )
    if detail is Detail.WINDOWS_PAUSED:  # after "Paused": why, and what to do
        return _trn(
            "every caption window hidden over %n minute(s) - show them to carry on",
            int(arg),  # type: ignore[call-overload]
        )
    if detail is Detail.SIGN_IN:
        return sign_in_needed(email_sign_in)
    if detail is Detail.NOTHING_CHOSEN:
        # the Caption card under it says how (once: 109's rule 3)
        return _tr("nothing is captioned yet")
    if detail is Detail.HELP_CHECKS:
        return _tr("Help can check what's wrong")
    if detail is Detail.START_AGAIN:  # Help's check says the same (228)
        return pc_mac_or_linux(
            _tr(
                "quit from the tray and start Polyglotic again - if it keeps "
                "stopping, Help can check what's wrong"
            ),
            _tr(
                "quit from the menu bar and start Polyglotic again - if it keeps "
                "stopping, Help can check what's wrong"
            ),
            _tr(
                "quit Polyglotic and start it again - if it keeps stopping, Help can "
                "check what's wrong"
            ),
        )
    if detail is Detail.RETRY_IN:
        # the caption windows' words: "Reconnecting - trying again in 8 s"
        return _tr("trying again in {seconds} s").format(seconds=arg)
    if detail is Detail.CAPTIONS_IN:
        names = [shown_name(str(code)) for code in arg]  # type: ignore[attr-defined]
        return in_sentence(_tr("captions in {languages}"), languages=names)
    if detail is Detail.ORIGINAL_ONLY:
        return _tr("captions without translation")
    if detail in _UPDATE_DETAILS:
        return _UPDATE_DETAILS[detail]()
    if detail in _UNREACHABLE_DETAILS:
        return _UNREACHABLE_DETAILS[detail]()
    if detail is Detail.WORDS_STAY:  # a transcript is this session's only (235)
        return _tr(
            "captions have stopped. Your words and lookups stay; a transcript is "
            "gone when you quit, unless you save it - get Plus to listen again"
        )
    return _tr("your speech not captioned")


_UPDATE_DETAILS: dict[Detail, Callable[[], str]] = {
    Detail.UPDATING: lambda: _tr(
        "getting the update - Polyglotic restarts by itself when it's ready"
    ),
    Detail.RESTART_TO_INSTALL: lambda: pc_mac_or_linux(
        _tr(
            "the update is downloaded - quit from the tray and start Polyglotic "
            "again to install it"
        ),
        _tr(
            "the update is downloaded - quit from the menu bar and start Polyglotic "
            "again to install it"
        ),
        _tr(
            "the update is downloaded - quit Polyglotic and start it again to "
            "install it"
        ),
    ),
    Detail.NO_UPDATE_YET: lambda: _tr(
        "no update is ready yet - Polyglotic looks again every few minutes, "
        "or ask us for the newest installer"
    ),
    Detail.INSTALL_BY_HAND: lambda: _tr(
        "this copy can't update itself - install the newest Polyglotic (ask us for it)"
    ),
    #: "Library" and "Get updates" are the Microsoft Store app's own words
    Detail.UPDATE_FROM_STORE: lambda: _tr(
        "the Microsoft Store updates this copy - open the Store, go to Library "
        "and choose Get updates"
    ),
}
"""Update needed: what to do (polyglotic-hq 137)."""


_UNREACHABLE_DETAILS: dict[Detail, Callable[[], str]] = {
    Detail.CHECK_INTERNET: lambda: pc_or_mac(
        _tr(
            "this PC seems to be offline. Check its internet connection; if it's "
            "working, the problem is ours"
        ),
        _tr(
            "this Mac seems to be offline. Check its internet connection; if it's "
            "working, the problem is ours"
        ),
    ),
    Detail.INTERNET_OR_US: lambda: _tr(
        "check your internet; if it's working, we're probably down"
    ),
    Detail.OURS: lambda: _tr(
        "not your internet - the problem is ours. Captions come back by themselves"
    ),
    Detail.BACK_IN_A_MOMENT: lambda: _tr(
        "captions come back by themselves in a moment"
    ),
    Detail.NETWORK_BLOCKS: lambda: _tr(
        "a firewall or proxy on this network won't let it reach its server. "
        "Try another network, or ask whoever runs this one"
    ),
    Detail.NETWORK_IN_THE_WAY: lambda: _tr(
        "something on this network is in the way - a Wi-Fi sign-in page, a "
        "firewall or an antivirus. Sign in to the Wi-Fi, or try another network"
    ),
    # only when the clock is certainly wrong - before this copy of the app
    # was built (connection.tls, decision 0104; polyglotic-hq 313)
    Detail.SET_THE_CLOCK: lambda: pc_mac_or_linux(
        #: {date}: the date this PC's clock says, in its regional format
        _tr(
            "this PC says it's {date}, which can't be right. Turn on Set time "
            "automatically in Windows' Settings, Time & language, Date & time, "
            "then choose Sync now"
        ),
        #: {date}: the date this Mac's clock says, in its regional format
        _tr(
            "this Mac says it's {date}, which can't be right. Turn on Set time and "
            "date automatically in System Settings, General, Date & Time"
        ),
        #: {date}: the date this PC's clock says, in its regional format
        _tr(
            "this PC says it's {date}, which can't be right. Turn on automatic date "
            "and time in your desktop's settings, under Date & Time"
        ),
    ).format(date=this_pcs_date()),
    #: a certificate out of date, and this PC's clock looks right (313)
    Detail.CERT_IN_THE_WAY: lambda: _tr(
        "something on this network is in the way with an out-of-date "
        "certificate - most often an antivirus's HTTPS scanning, or a VPN. "
        "Turn it off for Polyglotic, or try another network"
    ),
    Detail.QUIT_ON_ANOTHER_PC: lambda: _tr(
        "your account has as many open as it can. Quit it on one of them, and "
        "captions start here by themselves"
    ),
    Detail.TRIES_SOON: lambda: pc_or_mac(
        _tr(
            "too many failed sign-ins came from this network, so the server waits "
            "before it lets this PC in"
        ),
        _tr(
            "too many failed sign-ins came from this network, so the server waits "
            "before it lets this Mac in"
        ),
    ),
    Detail.MAINTENANCE: maintenance.state_detail,
}
"""Waiting to try again: whose side it's on and what to do (polyglotic-hq 251)."""


# -- the app picker --------------------------------------------------------------------


def _status(status: AppStatus) -> str:
    return {
        AppStatus.PLAYING: _tr("playing"),
        AppStatus.QUIET: _tr("quiet"),
        AppStatus.NOT_OPEN: _tr("not open - captioned when it opens"),
        # its name says "Everything the PC plays" since 484 (it was "This PC")
        AppStatus.EVERYTHING: _tr("every app's sound"),
        AppStatus.EVERYTHING_ELSE: pc_or_mac(
            _tr("everything else the PC plays"), _tr("everything else the Mac plays")
        ),
    }[status]


def _trn(text: str, n: int) -> str:
    return QApplication.translate("Home", text, None, n)


def row_status(row: AppRow) -> str:
    """A captioned app's line under its name: its window captioning while
    hidden, or paused after a time hidden (polyglotic-hq 335) - else
    whether it's playing."""
    if row.sight is Sight.CAPTIONING:
        return _tr("captioning while hidden")
    if row.sight is Sight.PAUSED and row.paused_after is not None:
        return _trn(
            "paused after %n minute(s) hidden - show it to carry on", row.paused_after
        )
    return _status(row.status)


def _chip_text(code: str) -> str:
    return (_tr("Original only") if code == ORIGINAL_ONLY else code.upper()) + " ▾"


def _fit_note(menu: QMenu, note: QWidgetAction) -> None:
    """The note at the end of a menu wrapped to the menu's width as its
    items make it, in the font it has now, rather than widening it."""
    words = note.defaultWidget()
    note.setVisible(False)
    metric = menu.style().pixelMetric
    frame = metric(QStyle.PixelMetric.PM_MenuPanelWidth, None, menu)
    margin = metric(QStyle.PixelMetric.PM_MenuHMargin, None, menu)
    width = menu.sizeHint().width() - 2 * (frame + margin)
    note.setVisible(True)
    words.setFixedWidth(width)
    words.setFixedHeight(words.heightForWidth(width))


class AppRowWidget(QFrame):
    """One captioned app: colour, name, status, language chip, my-speech
    mark, Captions, Transcript, x."""

    def __init__(
        self,
        index: int | str,
        view: PickerView,
        colours: Sequence[str],
        stopping: OneClick | None = None,
    ) -> None:
        """The `index`-th row (made once; `show_row` gives it its app);
        `stopping`: what its x goes through (one for every row)."""
        super().__init__()
        self.setObjectName("AppRow")
        self.key = ""
        self.view = view
        # its buttons under its name where the room runs out (354): a long
        # language or a large text size at the main window's narrowest
        line = Flow(self, spacing=6)
        line.setContentsMargins(0, 6, 0, 6)

        self.colour = QToolButton()
        self.colour.setObjectName(f"picker.colour.{index}")
        self.colour.setToolTip(_tr("Colour"))
        self.colour.setProperty("kind", "ghost")
        self.colour.setProperty("chip", True)
        self.colour.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.colour.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self.colour)
        for colour in colours:
            action = menu.addAction(swatch(colour), "")
            action.triggered.connect(
                lambda _=False, c=colour: view.recolour(self.key, c)
            )
        self.colour.setMenu(menu)
        line.addWidget(self.colour)

        words = QVBoxLayout()
        words.setSpacing(0)
        self.name = _button("", "name", _tr("Rename"))
        self.name.setObjectName(f"picker.name.{index}")
        self.name.clicked.connect(self._rename)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.name.setMinimumWidth(style.px(NAME_LEAST))
        self.edit = QLineEdit()
        self.edit.setObjectName(f"picker.rename.{index}")
        self.edit.setMaxLength(MAX_LABEL)
        self.edit.hide()
        self.edit.editingFinished.connect(self._renamed)
        # wrapped, not cut: a hidden window's line ("paused after 15 minutes
        # hidden - show it to carry on", 335) runs under the row's buttons
        # in German at the usual 1,000 px, and in English at the smallest
        # (polyglotic-hq 336); a short status still takes one line
        self.status = label("", "Faint", wrap=True)
        self.status.setContentsMargins(5, 0, 0, 0)
        status_size = QSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        status_size.setHeightForWidth(True)
        self.status.setSizePolicy(status_size)
        words.addWidget(self.name)
        words.addWidget(self.edit)
        words.addWidget(self.status)
        line.add_layout(words, 1)

        self.chip = QToolButton()
        self.chip.setObjectName(f"picker.language.{index}")
        self.chip.setToolTip(_tr("This window's language"))
        self.chip.setProperty("chip", True)
        self.chip.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.chip.setCursor(Qt.CursorShape.PointingHandCursor)
        languages = QMenu(self.chip)
        choices = [(ORIGINAL_ONLY, _tr("Original only (no translation)"))]
        choices += [(str(c), language_name(str(c))) for c in target_languages()]
        for code, name in choices:
            action = languages.addAction(name)
            action.triggered.connect(
                lambda _=False, c=code: view.set_translate_into(self.key, c)
            )
        # at the list's end, as the rail says it (DECISIONS.md #40)
        languages.addSeparator()
        note = QWidgetAction(languages)
        why = label(not_offered_note(), "Faint", wrap=True)
        why.setParent(languages)  # before it's ever shown
        why.setContentsMargins(12, 4, 12, 4)  # in line with the items' words
        note.setDefaultWidget(why)
        languages.addAction(note)
        languages.aboutToShow.connect(lambda: _fit_note(languages, note))
        self.chip.setMenu(languages)
        line.addWidget(self.chip)

        self.mic = GlyphButton(Glyph.MIC)
        self.mic.setObjectName(f"picker.mic.{index}")
        self.mic.setProperty("mark", True)
        self.mic.setCheckable(True)
        self.mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic.clicked.connect(lambda on: view.set_show_mic(self.key, on))
        line.addWidget(self.mic)

        self.captions = _button(_tr("Captions"), "small")
        self.captions.setObjectName(f"picker.captions.{index}")
        self.captions.clicked.connect(lambda: view.show_window(self.key))
        line.addWidget(self.captions)
        self.transcript = _button(_tr("Transcript"), "small")
        self.transcript.setObjectName(f"picker.transcript.{index}")
        self.transcript.clicked.connect(lambda: view.open_transcript(self.key))
        line.addWidget(self.transcript)
        self.stop = _button(_tr("Stop"), "small")
        self.stop.setObjectName(f"picker.stop.{index}")
        once = stopping or OneClick()
        once.watch(self.stop)
        self.stop.clicked.connect(lambda: once(lambda: view.remove(self.key)))
        line.addWidget(self.stop)

    def show_row(self, row: AppRow, hidden: bool, hide_key: bool = True) -> None:
        """This row shows `row`'s app (a row is reused for another app);
        `hide_key`: Ctrl+Alt+H works here, so a hidden window's tip names
        it (polyglotic-hq 400)."""
        if row.key != self.key:
            self.key = row.key
            self.edit.hide()
            self.name.show()
        self.row = row
        self.colour.setIcon(swatch(row.colour, 14))
        self.name.setText(style.button_text(row.label))
        self.status.setText(row_status(row))
        self.chip.setText(_chip_text(row.translate_into))
        self.mic.setChecked(row.show_mic)
        self.mic.setToolTip(
            _tr("Your speech shows in this window - click to stop")
            if row.show_mic
            else _tr("Show my speech in this window")
        )
        if not hidden:
            self.captions.setToolTip(_tr("Show its caption window"))
        elif hide_key:
            self.captions.setToolTip(hotkeys_here(_tr("Hidden - Ctrl+Alt+H")))
        else:
            self.captions.setToolTip(_tr("Hidden - turn off Hide all to show it"))
        stop = _tr("Stop captioning {app}").format(app=row.label)
        self.stop.setToolTip(stop)
        self.stop.setAccessibleName(stop)
        self.colour.setAccessibleName(
            _tr("Colour of {app}'s label").format(app=row.label)
        )
        self.name.setAccessibleName(_tr("Rename {app}").format(app=row.label))
        self.edit.setAccessibleName(_tr("New name for {app}").format(app=row.label))
        self.chip.setAccessibleName(
            _tr("{app}'s window's language").format(app=row.label)
        )
        self.mic.setAccessibleName(
            _tr("Show my speech in {app}'s window").format(app=row.label)
        )
        self.captions.setAccessibleName(
            _tr("Show {app}'s caption window").format(app=row.label)
        )
        self.transcript.setAccessibleName(
            _tr("Open {app}'s transcript").format(app=row.label)
        )

    def _rename(self) -> None:
        self.edit.setText(self.row.label)
        self.name.hide()
        self.edit.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def _renamed(self) -> None:
        if self.edit.isHidden():
            return
        self.edit.hide()
        self.name.show()
        if self.edit.text().strip() != self.row.label:
            self.view.rename(self.key, self.edit.text())


WAVE_SIDE = 16
"""Logical pixels at base text size (12–24). Match the small status glyphs."""
WAVE_FRAME_MS = 450
"""Milliseconds per sound-wave frame (250–750). Slow enough to read beside text."""
START_HEIGHT = 40
"""Minimum primary button height in logical pixels at base size (32–48)."""


class PlayingWave(QWidget):
    """A playing source. Use the static speaker when reduced motion is on."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(style.px(WAVE_SIDE), style.px(WAVE_SIDE))
        self.frame = Glyph.SPEAKER
        self.timer = QTimer(self, interval=WAVE_FRAME_MS)
        self.timer.timeout.connect(self.advance)

    def advance(self) -> None:
        self.frame = Glyph.SPEAKING if self.frame is Glyph.SPEAKER else Glyph.SPEAKER
        self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not reduced_motion():
            self.timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        paint(
            painter, self.frame, QRectF(self.rect()), QColor(style.current()["ACCENT"])
        )
        painter.end()


class AddRow(QFrame):
    """An app with sound that could be added: its name, then playing or
    quiet in the same dim place for both (the captioned rows say their
    status the same way), and a "Caption" chip. The whole row is the
    target - a click anywhere on it captions the app (151's W5, 176: a new
    learner's first click was a 24 px "+")."""

    def __init__(
        self, app: AddableApp, view: PickerView, adding: OneClick | None = None
    ) -> None:
        super().__init__()
        self.setObjectName("AddRow")
        self.name = app.name
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 2, 0, 2)
        # a click anywhere on the row captions the app: its words don't take it
        self.title = label(app.title, copyable=False)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        line.addWidget(self.title, 1)
        playing = _tr("playing") if app.playing else _tr("quiet")
        self.status = label(playing, "Faint", copyable=False)
        if app.playing:
            line.addWidget(PlayingWave(self))
        line.addWidget(self.status)
        self.suggestion = label(_tr("Suggested"), "RowTitle", copyable=False)
        line.addWidget(self.suggestion)
        caption = _tr("Caption {app}").format(app=app.title)
        self.add = _button(
            _tr("Caption"), "primary" if app.playing else "small", caption
        )
        self.add.setAccessibleName(caption)
        self.add.setObjectName(f"picker.add.{app.name}")
        once = adding or OneClick()
        once.watch(self.add)
        self._add = lambda: once(lambda: view.add(self.name))
        self.add.clicked.connect(self._add)
        line.addWidget(self.add)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(caption)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """A click anywhere on the row: the app captioned, as its chip."""
        if (
            event.button() is Qt.MouseButton.LeftButton
            and self.isEnabled()
            and self.rect().contains(event.position().toPoint())
        ):
            self._add()
        super().mouseReleaseEvent(event)


class PickerCard(Card):
    """Home's "Caption" card: the app picker (109's section 5)."""

    def __init__(self, view: PickerView, colours: Sequence[str]) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.view = view
        self.colours = tuple(colours)
        self._hide_key = True
        """Ctrl+Alt+H works here (`show_hide_key`)."""
        self.add_once = OneClick()
        """The + buttons' (a double-click captions one app)."""
        self.stop_once = OneClick()
        """The rows' x (a double-click stops one app)."""
        head = QHBoxLayout()
        head.addWidget(label(_tr("Caption"), "CardTitle"))
        self.nothing = label(_tr("Not captioning yet"), "CaptionIdle")
        head.addWidget(self.nothing)
        self.active = label("", "CaptionActive", wrap=True)
        head.addWidget(self.active)
        self._state_text = ""
        head.addStretch(1)
        self.count = label("", "Dim")
        self.count.setObjectName("picker.count")
        head.addWidget(self.count)
        self.add(head)
        self.start = WrapButton(parent=self)
        self.start.setProperty("kind", "primary")
        self.start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start.setObjectName("picker.start")
        self.start.setMinimumHeight(style.px(START_HEIGHT))
        self.add_once.watch(self.start)
        self.start.clicked.connect(lambda: self.add_once(view.start))
        self.add(self.start)
        # everything the PC plays - a new learner's from the first launch: what
        # that takes in, said plainly once, and the one click to an app instead
        # (polyglotic-hq 484)
        self.everything_said = label("", "Dim", wrap=True)
        self.everything_said.setObjectName("picker.everything_said")
        self.add(self.everything_said)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(0)
        self.add(self.rows_box)
        self.pool = [
            AppRowWidget(n, view, self.colours, self.stop_once)
            for n in range(view.value.limit)
        ]
        for widget in self.pool:
            widget.hide()
            self.rows_box.addWidget(widget)
        self.rows: dict[str, AppRowWidget] = {}
        """The rows showing now, by their app's key."""
        self.everything_else = SwitchRow(
            pc_or_mac(
                _tr("Also caption everything else the PC plays (in its own window)"),
                _tr("Also caption everything else the Mac plays (in its own window)"),
            ),
            _tr("With one app only"),  # `refresh` says what applies
            "picker.everything_else",
        )
        self.everything_else.switch.clicked.connect(
            lambda on: view.set_everything_else(bool(on))
        )
        self.add(self.everything_else)

        self.adding = QWidget()
        adding = QVBoxLayout(self.adding)
        adding.setContentsMargins(0, 4, 0, 0)
        adding.setSpacing(4)
        add_head = QHBoxLayout()
        # the list's order on hover, not beside it (151's P2, 176)
        self.add_title = label(_tr("Add an app"), "RowTitle")
        self.add_title.setToolTip(_tr("apps with sound open, playing first"))
        add_head.addWidget(self.add_title)
        add_head.addStretch(1)
        refresh = _button(_tr("Refresh"), "ghost")
        refresh.setObjectName("picker.refresh")
        refresh.clicked.connect(view.refresh)
        add_head.addWidget(refresh)
        adding.addLayout(add_head)
        self.full = label("", "Warning", wrap=True)
        self.full.setObjectName("picker.full")
        adding.addWidget(self.full)
        self.add_box = QVBoxLayout()
        self.add_box.setSpacing(0)
        adding.addLayout(self.add_box)
        self.none_found = label(
            _tr("No app has sound open. Play something, then Refresh."),
            "Faint",
            wrap=True,
        )
        adding.addWidget(self.none_found)
        # nothing playing: a sample of the language learned, played and
        # captioned by the app (polyglotic-hq 176)
        self.sample = QWidget()
        self.sample.setObjectName("picker.sample")
        sample = QHBoxLayout(self.sample)
        sample.setContentsMargins(0, 2, 0, 0)
        self.sample_button = _button(_tr("Try it on a sample"), "small")
        self.sample_button.setObjectName("picker.sample_button")
        self.sample_button.clicked.connect(
            lambda: view.try_sample(view.value.sample is not Sample.PLAYING)
        )
        sample.addWidget(self.sample_button)
        self.sample_note = label(
            _tr(
                "a short recording, played and captioned like any app (FLEURS, CC BY "
                "4.0)"
            ),
            "Faint",
            wrap=True,
        )
        sample.addWidget(self.sample_note, 1)
        # played to its end: the next step (208, 203's option B)
        self.sample_next = label(_tr("Pick an app to caption yours"), wrap=True)
        self.sample_next.setObjectName("picker.sample_next")
        self.sample_next.setContentsMargins(0, 6, 0, 0)  # apart from the apps
        adding.addWidget(self.sample_next)
        adding.addWidget(self.sample)
        self.add(self.adding)
        self.add_rows: dict[str, AddRow] = {}
        self._available: tuple[AddableApp, ...] | None = None

        choices = QHBoxLayout()
        self.pick_apps = WrapRadioButton(_tr("Pick apps"), self)
        self.all_audio = WrapRadioButton(
            pc_or_mac(_tr("Everything the PC plays"), _tr("Everything the Mac plays")),
            self,
        )
        for button, detail in (
            (self.pick_apps, _tr("Only caption the apps you choose.")),
            (self.all_audio, _tr("Caption sound from all apps together.")),
        ):
            column = QVBoxLayout()
            column.addWidget(button)
            column.addWidget(label(detail, "Faint", wrap=True))
            choices.addLayout(column, 1)
            button.setAccessibleDescription(detail)
        self.pick_apps.clicked.connect(lambda: view.set_whole_system(False))
        self.all_audio.clicked.connect(lambda: view.set_whole_system(True))
        self.add(choices)
        everything = QHBoxLayout()
        self.everything_note = label("", "Faint", wrap=True)
        everything.addWidget(self.everything_note, 1)
        # capturing apps one by one failed here: tried again (decision 0076)
        self.apps_again = _button(_tr("Try apps again"), "small")
        self.apps_again.setObjectName("picker.apps_again")
        self.apps_again.clicked.connect(view.try_apps_again)
        everything.addWidget(self.apps_again)
        self.add(everything)

        you = QHBoxLayout()
        you.setSpacing(6)
        self.you_label = label(_tr("Your speech is labelled"), "Dim", wrap=True)
        you.addWidget(self.you_label)
        self.you = AppRowWidget("you", view, self.colours)  # its colour and name
        parts: tuple[QWidget, ...] = (
            self.you.status,
            self.you.chip,
            self.you.mic,
            self.you.captions,
            self.you.transcript,
            self.you.stop,
        )
        for part in parts:  # only its colour and name
            part.hide()
        self.you.setObjectName("AddRow")  # no line under it
        you.addWidget(self.you, 1)
        self.add(you)
        self.speech = label("", "Dim", wrap=True)
        self.speech.setObjectName("picker.my_speech")
        self.add(self.speech)
        stop = view.subscribe(self._changed)
        self.destroyed.connect(lambda *_: stop())
        self.refresh()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._state_text:
            QAccessible.updateAccessibility(
                QAccessibleAnnouncementEvent(self, self._state_text)
            )

    def _changed(self) -> None:
        with spans.span("home.picker"):
            self.refresh()

    def refresh(self) -> None:
        value = self.view.value
        self._rows(value)
        self.all_audio.setChecked(value.whole_system)
        self.pick_apps.setChecked(not value.whole_system)
        self.pick_apps.setEnabled(value.per_app)
        self._note(value)
        if value.whole_system:  # its row says it: no count of apps
            self.count.setText("")
        elif value.everything_else:
            self.count.setText(_tr("1 app + everything else"))
        else:
            self.count.setText(
                _tr("{n} of {limit}").format(n=len(value.apps), limit=value.limit)
            )
        self._everything_else(value)
        self._show_caption_state(value)
        self._everything_said(value)
        # with everything the PC plays too: one click captions an app instead
        self.adding.setVisible(value.per_app)
        self.add_title.setText(
            _tr("Caption one app instead") if value.whole_system else _tr("Add an app")
        )
        self._addable(value)
        if value.you is not None:
            self.you.show_row(value.you, hidden=False)
            self.you.stop.hide()
        self.you.setVisible(bool(value.captioned) and value.you is not None)
        self.you_label.setVisible(bool(value.captioned) and value.you is not None)
        self.speech.setVisible(bool(value.captioned))
        shown = value.speech_shown_in
        if shown:
            self.speech.setText(
                _tr(
                    "My speech: shown in {windows} - sent for your captions only "
                    "while it's shown"
                ).format(windows=name_list(shown))
            )
        elif value.captioned:
            self.speech.setText(
                _tr(
                    "My speech: not shown in any window - turn it on with a row's "
                    "microphone, or a window's settings"
                )
            )

    def _show_caption_state(self, value: Picker) -> None:
        sample = value.sample is Sample.PLAYING
        idle = not value.captioned and not sample
        if self.property("captionIdle") != idle:
            self.setProperty("captionIdle", idle)
            self.style().unpolish(self)
            self.style().polish(self)
        self.nothing.setVisible(idle)
        self.start.setVisible(idle)
        suggested = self.view.suggested
        if idle:
            target = (
                _tr("Caption {app}").format(app=suggested.title)
                if suggested
                else pc_or_mac(
                    _tr("Caption everything the PC plays"),
                    _tr("Caption everything the Mac plays"),
                )
            )
            self.start.setText("▶ " + style.button_text(target))
            self.start.setAccessibleName(target)
        listening_to = [
            row.label
            for row in value.captioned
            if row.sight is not Sight.PAUSED and row.status is not AppStatus.NOT_OPEN
        ]
        live = value.listening and (sample or bool(listening_to))
        self.active.setVisible(live)
        words = ""
        if idle:
            words = self.nothing.text()
            self.nothing.setAccessibleName(words)
        elif live:
            names = _tr("Sample") if sample else name_list(listening_to)
            words = _tr("Captioning {app}").format(app=names)
            self.active.setText("● " + words)
            self.active.setAccessibleName(words)
        if words != self._state_text:
            self._state_text = words
            if words and self.isVisible():
                QAccessible.updateAccessibility(
                    QAccessibleAnnouncementEvent(self, words)
                )

    def _everything_said(self, value: Picker) -> None:
        """While everything the PC plays is captioned: that a call's voices
        are in it too - said plainly once, where it's chosen (polyglotic-hq
        484: a new learner's first launch captions it) - and, where apps
        can be captioned one by one, that one click on an app below
        captions it instead."""
        self.everything_said.setVisible(value.whole_system)
        if not value.whole_system:
            return
        if value.per_app:
            said = pc_or_mac(
                _tr(
                    "Everything the PC plays is captioned - a call's voices too. "
                    "To caption one app instead, choose it below."
                ),
                _tr(
                    "Everything the Mac plays is captioned - a call's voices too. "
                    "To caption one app instead, choose it below."
                ),
            )
        else:
            said = pc_or_mac(
                _tr("Everything the PC plays is captioned - a call's voices too."),
                _tr("Everything the Mac plays is captioned - a call's voices too."),
            )
        self.everything_said.setText(said)

    def _note(self, value: Picker) -> None:
        """What "Everything the PC plays" is: on hover where apps can be
        captioned one by one (151's P2, 176); said under it where it's why
        Apps is off - an older Windows 10, or trying apps failed here, with
        "Try apps again" (decision 0076)."""
        if value.fell_back:
            note = pc_mac_or_linux(
                _tr(
                    "instead of apps: Windows on this PC couldn't caption one app alone"
                ),
                _tr("instead of apps: this Mac couldn't caption one app alone"),
                _tr("instead of apps: this PC couldn't caption one app alone"),
            )
        elif not value.per_app and on_linux():  # one app alone: slice 2 (550)
            note = _tr("instead of apps (the only choice on Linux for now)")
        elif not value.per_app:
            note = pc_or_mac(
                _tr("instead of apps (the only choice on this version of Windows)"),
                _tr("instead of apps (the only choice on this version of macOS)"),
            )
        else:
            note = _tr("instead of apps")
        self.pick_apps.setToolTip(note if not value.per_app else "")
        self.everything_note.setText(note)
        self.everything_note.setVisible(not value.per_app)
        self.apps_again.setVisible(value.fell_back)

    def show_hide_key(self, works: bool) -> None:
        """Ctrl+Alt+H works here: a hidden window's tip names it
        (polyglotic-hq 400)."""
        if works != self._hide_key:
            self._hide_key = works
            self._rows(self.view.value)

    def _rows(self, value: Picker) -> None:
        """A row per captioned app. The rows (at most LIMIT) are made once
        and reused - a row is a dozen widgets to style, too slow to make
        on a click."""
        shown = value.captioned[: len(self.pool)]
        self.rows = {}
        for widget, row in zip(self.pool, shown, strict=False):
            widget.show_row(row, value.hidden, self._hide_key)
            self.rows[row.key] = widget
        for index, widget in enumerate(self.pool):
            widget.setVisible(index < len(shown))

    def _everything_else(self, value: Picker) -> None:
        """The switch: there once an app is added (not with everything the
        PC plays, nor where apps can't be captioned one by one); on with one
        app only - off with 2 or 3, saying why."""
        row = self.everything_else
        row.setVisible(value.per_app and not value.whole_system and bool(value.apps))
        row.switch.set_quietly(value.everything_else)
        row.switch.setEnabled(value.everything_else or value.everything_else_allowed)
        if value.everything_else or value.everything_else_allowed:
            app = value.apps[0].label if value.apps else ""
            detail = pc_or_mac(
                _tr("Everything the PC plays except {app}, in a window of its own"),
                _tr("Everything the Mac plays except {app}, in a window of its own"),
            ).format(app=app)
        else:
            detail = pc_mac_or_linux(
                _tr("With one app only - Windows can leave just one app out"),
                _tr("With one app only"),
                _tr("With one app only"),
            )
        row.detail.setText(detail)
        row.switch.setAccessibleDescription(detail)

    def _addable(self, value: Picker) -> None:
        self.full.setText(
            _tr("One app beside everything else - turn that off to add another")
            if value.everything_else
            else _tr("{used} of {limit} - stop one to add another").format(
                used=QLocale().toString(len(value.apps)),
                limit=QLocale().toString(value.limit),
            )
        )
        self.full.setVisible(value.full)
        self.none_found.setVisible(not value.available)
        self.sample.setVisible(value.sample is not Sample.NONE)
        self.sample_next.setVisible(value.sample is Sample.ENDED)
        self.sample_button.setText(
            _tr("Stop the sample")
            if value.sample is Sample.PLAYING
            else _tr("Try it on a sample")
        )
        if value.available != self._available:
            self._available = value.available
            for widget in self.add_rows.values():
                widget.hide()
                widget.deleteLater()
            self.add_rows = {}
            for app in value.available:
                widget = AddRow(app, self.view, self.add_once)
                self.add_box.addWidget(widget)
                self.add_rows[app.name] = widget
        suggested = self.view.suggested
        for widget in self.add_rows.values():
            widget.suggestion.setVisible(
                not value.captioned
                and suggested is not None
                and widget.name == suggested.name
            )
            widget.setEnabled(not value.full)


# -- Home ------------------------------------------------------------------------------


class HomePage(Page):
    """Home: the state, what's captioned, the caption windows' commands,
    and feedback."""

    listen_here_wanted = Signal()
    crash_report_wanted = Signal()
    start_with_windows_answered = Signal(bool)
    """The learner's answer to "Start Polyglotic with Windows?"."""
    sign_in_wanted = Signal()
    get_plus_wanted = Signal()
    upgrade_wanted = Signal()
    review_consent_wanted = Signal()
    """Plus ended: "Get Plus" (`main` opens Account's address)."""
    reset_positions_wanted = Signal()
    level_wanted = Signal()
    """The level line's Set your level."""
    level_dismissed = Signal()
    """The level line's Not now: never shown again."""
    join_wanted = Signal()
    """Join windows, or Separate windows while they're joined."""
    restart_wanted = Signal()
    """The update card's Restart now: `main` quits and installs it (299)."""
    update_later = Signal()
    """The update card's Later: not asked again until the next start."""
    download_anyway_wanted = Signal()
    """The update card's Download anyway, on a metered connection (345)."""
    open_app_folder_wanted = Signal()
    """The not-writable card's Open folder: `main` opens the folder holding
    this copy so the learner can move it to ~/Applications (640)."""
    whats_new_wanted = Signal()
    """What's new's All the changes: `main` opens Help's What's new (345)."""
    whats_new_closed = Signal()
    """What's new's Close: this version's notes are seen, not shown again."""

    def __init__(
        self,
        picker: PickerView,
        pause: QAction,
        lock: QAction,
        hide: QAction,
        colours: Sequence[str],
        sound: SoundView | None = None,
    ) -> None:
        """`pause`, `lock` and `hide`: today's commands (the tray's and the
        hotkeys' too); `colours`: the colours an app's label can have."""
        super().__init__(_tr("Home"))
        self.picker = picker
        self.state = StateCard(pause)
        self.state.sign_in.clicked.connect(self.sign_in_wanted)
        self.state.get_plus.clicked.connect(self.get_plus_wanted)
        self.state.upgrade.clicked.connect(self.upgrade_wanted)
        self.state.review_consent.clicked.connect(self.review_consent_wanted)
        self.content.addWidget(self.state)

        # the level, which the first run doesn't ask (polyglotic-hq 293):
        # one quiet line under the state until it's set or put off
        self.level_line = QWidget()
        self.level_line.setObjectName("home.level")
        level = QHBoxLayout(self.level_line)
        level.setContentsMargins(4, 0, 0, 0)
        level.setSpacing(8)
        level.addWidget(
            label(
                _tr("Set your level so we know which words to explain"),
                "Dim",
                wrap=True,
            ),
            1,
        )
        set_level = _button(_tr("Set your level"))
        set_level.setObjectName("home.level.set")
        set_level.clicked.connect(self.level_wanted)
        not_now = _button(_tr("Not now"), "ghost")
        not_now.setObjectName("home.level.not_now")
        not_now.clicked.connect(self.level_line.hide)
        not_now.clicked.connect(self.level_dismissed)
        level.addWidget(set_level)
        level.addWidget(not_now)
        self.level_line.hide()
        self.content.addWidget(self.level_line)

        # an update downloaded (polyglotic-hq 299): a quiet card under the
        # state, never a window of its own over a game or a call - framed as
        # a card: the stylesheet draws one by its object name, `Card`, so
        # it keeps it (361: named "home.update" it lost its frame beside
        # What's new's)
        self.update_card = Card()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.update_title = label("", "RowTitle", wrap=True)
        row.addWidget(self.update_title, 1)
        restart = _button(_tr("Restart now"))
        restart.setObjectName("home.update.restart")
        restart.clicked.connect(self.restart_wanted)
        self.update_restart = restart
        # on a metered connection, nothing downloads by itself (345)
        self.download_anyway = _button(_tr("Download anyway"))
        self.download_anyway.setObjectName("home.update.download_anyway")
        self.download_anyway.clicked.connect(self._downloading)
        self.download_anyway.clicked.connect(self.download_anyway_wanted)
        later = _button(_tr("Later"), "ghost")
        later.setObjectName("home.update.later")
        later.clicked.connect(self.update_card.hide)
        later.clicked.connect(self.update_later)
        row.addWidget(restart)
        row.addWidget(self.download_anyway)
        row.addWidget(later)
        self.update_card.add(row)
        self.whats_new: list[QLabel] = []
        for _ in range(2):  # what's new: the release notes' first two lines
            line = label("", "Dim", wrap=True)
            self.update_card.add(line)
            self.whats_new.append(line)
        self.update_then = label("", "Faint", wrap=True)
        self.update_card.add(self.update_then)
        self.update_card.hide()
        self.content.addWidget(self.update_card)

        # an AppImage in a folder the learner can't change (polyglotic-hq 640):
        # shown instead of failing silently in the log, with Open folder
        self.not_writable_card = Card()
        self.not_writable_card.setObjectName("Card")
        not_writable_row = QHBoxLayout()
        not_writable_row.setSpacing(8)
        self.not_writable_notice = label(not_writable_notice(), wrap=True)
        self.not_writable_notice.setObjectName("home.update.not_writable_notice")
        not_writable_row.addWidget(self.not_writable_notice, 1)
        self.open_app_folder = _button(open_folder_label())
        self.open_app_folder.setObjectName("home.update.open_folder")
        self.open_app_folder.clicked.connect(self.open_app_folder_wanted)
        not_writable_row.addWidget(self.open_app_folder)
        self.not_writable_card.add(not_writable_row)
        self.not_writable_card.hide()
        self.content.addWidget(self.not_writable_card)

        # what's new, after an update (polyglotic-hq 345): this version's
        # notes in a few lines, once - until Close; Help keeps them all
        self.whats_new_card = Card()
        row = QHBoxLayout()
        row.setSpacing(8)
        self.whats_new_title = label("", "RowTitle", wrap=True)
        row.addWidget(self.whats_new_title, 1)
        everything = _button(_tr("All the changes"))
        everything.setObjectName("home.whats_new.all")
        everything.clicked.connect(self.whats_new_wanted)
        closing = _button(_tr("Close"), "ghost")
        closing.setObjectName("home.whats_new.close")
        closing.clicked.connect(self.whats_new_card.hide)
        closing.clicked.connect(self.whats_new_closed)
        row.addWidget(everything)
        row.addWidget(closing)
        self.whats_new_card.add(row)
        self.whats_new_lines: list[QLabel] = []
        for _ in range(WHATS_NEW_ON_HOME):
            line = label("", "Dim", wrap=True)
            self.whats_new_card.add(line)
            self.whats_new_lines.append(line)
        self.whats_new_more = label("", "Faint", wrap=True)
        self.whats_new_card.add(self.whats_new_more)
        self.whats_new_card.hide()
        self.content.addWidget(self.whats_new_card)

        self.moved = Card()
        self.moved.setObjectName("Card")
        moved = QHBoxLayout()
        moved.addWidget(label(_tr("Listening moved to another device."), wrap=True), 1)
        listen_here = _button(_tr("Listen here"))
        listen_here.setObjectName("home.listen_here")
        listen_here.clicked.connect(self.listen_here_wanted)
        moved.addWidget(listen_here)
        self.moved.add(moved)
        self.moved.hide()
        self.content.addWidget(self.moved)

        self.picker_card = PickerCard(picker, colours)
        self.content.addWidget(self.picker_card)
        # which speakers and mic, and what I say (polyglotic-hq 372)
        self.sound = SoundCard(sound) if sound is not None else None
        if self.sound is not None:
            self.content.addWidget(self.sound)

        windows = Card(_tr("Caption windows"))
        windows.setObjectName("Card")
        buttons = Flow()  # onto two lines where the room runs out (354)
        self.lock = _bound(_tr("Lock all"), lock)
        self.lock.setObjectName("home.lock_all")
        self.hide_all = _bound(_tr("Hide all"), hide)
        self.hide_all.setObjectName("home.hide_all")
        self._hotkeys = (pause, lock, hide)
        for action in self._hotkeys:  # one that doesn't work goes unnamed (400)
            action.changed.connect(self._show_hotkeys)
        self._show_hotkeys()
        self.join = _button(_tr("Join windows"))
        self.join.setObjectName("home.join")
        self.join.clicked.connect(self.join_wanted)
        self.show_joined(False, 0)
        reset = _button(_tr("Reset positions"))
        reset.setObjectName("home.reset_positions")
        reset.clicked.connect(self.reset_positions_wanted)
        for each in (self.lock, self.hide_all, self.join, reset):
            buttons.addWidget(each)
        windows.add(buttons)
        self.content.addWidget(windows)
        self.feedback = Flow(spacing=4)
        self.content.addLayout(self.feedback)
        self.content.addStretch(1)

        self._state = HomeState()
        self._looking = QTimer(self, interval=REFRESH_MS)
        self._looking.timeout.connect(picker.refresh)
        self.show_state(self._state)

    def _show_hotkeys(self) -> None:
        """Lock all's and Hide all's tips, the paused line and a hidden
        window's tip name a hotkey only while it works (polyglotic-hq 400:
        398's preview build registers none, and they said "Ctrl+Alt+L")."""
        pause, lock, hide = (
            own_hotkey(action, letter)
            for action, letter in zip(self._hotkeys, "PLH", strict=True)
        )
        self.lock.setToolTip(hotkeys_here(_tr("Ctrl+Alt+L")) if lock else "")
        self.hide_all.setToolTip(hotkeys_here(_tr("Ctrl+Alt+H")) if hide else "")
        self.state.show_pause_key(pause)
        self.picker_card.show_hide_key(hide)

    def show_joined(self, joined: bool, windows: int) -> None:
        """Join windows - with 2 caption windows or more - or, while
        they're joined, Separate windows (109's 2a)."""
        self.join.setText(_tr("Separate windows") if joined else _tr("Join windows"))
        self.join.setEnabled(joined or windows >= 2)
        self.join.setToolTip(
            _tr("Each caption window back at its own place")
            if joined
            else _tr("The caption windows as one, a column each")
            if windows >= 2
            else _tr("With two apps or more")
        )

    def show_level_line(self, shown: bool) -> None:
        """The quiet line asking for the learner's level - words are
        estimated at a middle one until it's set (polyglotic-hq 293)."""
        self.level_line.setVisible(shown)

    def show_update(
        self,
        version: str | None,
        whats_new: Sequence[str] = (),
        metered_size: int | None = None,
    ) -> None:
        """The update card: `version` downloaded and ready to restart into,
        with what's new in its notes' words (up to two lines; English, as
        the notes are) - or, None, no card (polyglotic-hq 299). With
        `metered_size` (its bytes, 0 if not known), it's found but not
        downloaded, the connection being metered: how big it is, and
        Download anyway instead of Restart now (polyglotic-hq 345)."""
        self.update_card.setVisible(version is not None)
        if version is None:
            return
        held = metered_size is not None
        if not held:
            if on_linux():
                title = update_ready_linux()
                then = _tr("Or later: it applies when you quit Polyglotic.")
                self.update_restart.setText(quit_now_label())
            else:
                title = _tr("Version {version} is ready. Restart to install it.")
                then = _tr("Or later: it installs the next time Polyglotic starts.")
                self.update_restart.setText(_tr("Restart now"))
        else:
            title = (
                _tr("Version {version} is available: {size} MB to download.")
                if metered_size
                else _tr("Version {version} is available.")
            )
            then = _tr(
                "Your connection is metered, so it isn't downloaded by itself. "
                "It is once you're on a connection that isn't."
            )
        self.update_title.setText(
            title.format(version=version, size=megabytes(metered_size or 0))
        )
        self.update_then.setText(then)
        self.update_restart.setVisible(not held)
        self.download_anyway.setVisible(held)
        self.download_anyway.setEnabled(True)
        for line, text in zip(
            self.whats_new, [*whats_new, "", ""][: len(self.whats_new)], strict=True
        ):
            line.setText(f"• {text}" if text else "")
            line.setVisible(bool(text))

    def show_update_not_writable(self, shown: bool) -> None:
        """Home's quiet card when the app's folder can't be written to
        (e.g. a Linux AppImage in /opt): tells the learner to move it to
        ~/Applications and offers Open folder (polyglotic-hq 640)."""
        self.not_writable_card.setVisible(shown)

    def _downloading(self) -> None:
        """Download anyway, clicked: it says so until the download ends -
        the card then offers Restart now, or Download anyway again."""
        self.download_anyway.setEnabled(False)
        self.update_then.setText(_tr("Downloading. This can take a few minutes."))

    def show_whats_new(
        self,
        version: str | None,
        lines: Sequence[str] = (),
        earlier: Sequence[str] = (),
        in_english: bool = False,
    ) -> None:
        """What's new after an update (polyglotic-hq 345): `version`'s notes
        in a few `lines`, the `earlier` versions also new since the last
        update named under them (their notes are in Help), and - the
        interface not in English - that the notes are (`in_english`). None:
        no card."""
        self.whats_new_card.setVisible(version is not None)
        if version is None:
            return
        self.whats_new_title.setText(
            _tr("What's new in Polyglotic {version}").format(version=version)
        )
        shown = [*lines][: len(self.whats_new_lines)]
        for at, line in enumerate(self.whats_new_lines):
            text = shown[at] if at < len(shown) else ""
            line.setText(f"• {text}" if text else "")
            line.setVisible(bool(text))
        more = []
        if earlier:
            more.append(
                _tr("Also new since your last update: {versions}.").format(
                    versions=", ".join(earlier)
                )
            )
        if in_english:
            more.append(_tr("The release notes are in English."))
        self.whats_new_more.setText(" ".join(more))
        self.whats_new_more.setVisible(bool(more))

    def show_state(self, state: HomeState) -> None:
        self._state = state
        self.state.show_state(state)
        self.moved.setVisible(state.connection is ListeningState.MOVED)

    def offer_crash_report(self, at_start: bool) -> None:
        """Polyglotic hit an error nothing caught last time: a quiet card
        under the state, offering once to send a report (today's)."""
        card = Card()
        card.setObjectName("Card")
        text = label(
            _tr("Polyglotic couldn't start last time.")
            if at_start
            else _tr("Polyglotic ran into an error last time."),
            wrap=True,
        )
        row = QHBoxLayout()
        row.addWidget(text, 1)
        send = _button(_tr("Send a report…"))
        send.setObjectName("home.crash.send")
        no = _button(_tr("No thanks"), "ghost")
        no.setObjectName("home.crash.dismiss")
        row.addWidget(send)
        row.addWidget(no)
        card.add(row)
        card.add(
            label(
                _tr(
                    "The report can include the app's log, which records what went "
                    "wrong - never what you heard or said. You see it before it's sent."
                ),
                "Faint",
                wrap=True,
            )
        )
        send.clicked.connect(card.hide)
        send.clicked.connect(self.crash_report_wanted)
        no.clicked.connect(card.hide)
        self.content.insertWidget(2, card)  # under the state

    def offer_start_with_windows(self) -> None:
        """After a good session, once: a quiet card under the state asking
        whether to start with Windows - off unless they say yes
        (polyglotic-hq 176). On a Mac, whether to open at login (428)."""
        card = Card()
        card.setObjectName("Card")
        row = QHBoxLayout()
        row.addWidget(
            label(
                pc_mac_or_linux(
                    _tr("Start Polyglotic with Windows?"),
                    _tr("Open Polyglotic when you log in?"),
                    _tr("Start Polyglotic when you sign in?"),  # Linux (571)
                ),
                "RowTitle",
                wrap=True,
            ),
            1,
        )
        yes = _button(
            pc_mac_or_linux(
                _tr("Start with Windows"), _tr("Open at login"), _tr("Start at sign-in")
            )
        )
        yes.setObjectName("home.startup.yes")
        no = _button(_tr("Not now"), "ghost")
        no.setObjectName("home.startup.no")
        row.addWidget(yes)
        row.addWidget(no)
        card.add(row)
        card.add(
            label(
                pc_mac_or_linux(
                    _tr(
                        "It waits in the tray, so captions are a click away when "
                        "you play or watch. Windows' Startup apps can turn it off."
                    ),
                    # a Mac opens a login item with its window: not "waits" (428)
                    _tr(
                        "It opens when you log in, so captions are a click away "
                        "when you play or watch. Login Items in System Settings "
                        "can turn it off."
                    ),
                    # Linux: an autostart entry; not every desktop lists them
                    # (GNOME needs Tweaks), so Polyglotic's own Settings (571)
                    _tr(
                        "It starts when you sign in, so captions are a click away "
                        "when you play or watch. You can turn it off in Settings."
                    ),
                ),
                "Faint",
                wrap=True,
            )
        )
        for button, answer in ((yes, True), (no, False)):
            button.clicked.connect(card.hide)
            button.clicked.connect(
                lambda _=False, a=answer: self.start_with_windows_answered.emit(a)
            )
        self.content.insertWidget(2, card)  # under the state
        self.startup_card = card

    def add_feedback(self, *actions: QAction) -> None:
        """The quiet line at the bottom: something wrong, or an idea?"""
        self.feedback.addWidget(label(_tr("Something wrong, or an idea?"), "Faint"))
        for action in actions:
            button = QToolButton()
            button.setDefaultAction(action)
            button.setProperty("kind", "ghost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.feedback.addWidget(button)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.picker.refresh()
        self._looking.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self._looking.stop()
        super().hideEvent(event)
