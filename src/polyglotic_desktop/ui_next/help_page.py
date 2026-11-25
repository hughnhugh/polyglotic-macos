"""Help, in the new main window (polyglotic-hq project 109's structure,
section 7; today's page, project 096 and 087's wireframe 5.2), in the
new interface's words: caption windows, not overlays; Home, not Audio,
Languages or Captions; Words, not Vocabulary.

- **No captions?** - the live check (`core.listening.check`): signed in
  and connected, an app added, sound from it, speech heard, captions
  drawn - stopping at the first broken link, with its likely fix. It
  looks only at what the app already knows, and runs again every few
  seconds while the page shows, and on Check again. Under it, while the
  learner's dictionary is out, what's wrong with it and how to fix it, in
  the lookup card's words (polyglotic-hq 199); and when their learning
  data was set aside at the start, that, where the old file is, and that
  their words come back (polyglotic-hq 206). Beside Check again, Server
  status opens the site's status page (polyglotic-hq 540, 563).
- **Set up** and **Questions** - 040's HELP.md, shortened; each opens
  with a click. "What we keep" says what the privacy notice v2 says, and
  under the questions the notice and the tester agreement open in the
  browser (polyglotic-hq 185).
- **What's new** - each version's release notes, newest first: the
  newest open, the others a click away (polyglotic-hq 345). Home's card
  after an update opens it.
- **Still stuck?** - Report a problem, with the check's result attached:
  ticks and crosses and the kind of problem, never an app's name, a path
  or anything heard (`report_wanted`).
"""

from collections.abc import Callable, Collection, Sequence

from PySide6.QtCore import QLocale, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from polyglotic_desktop.core.listening.check import (
    SOUND_WINDOW,
    Facts,
    Link,
    Problem,
    Status,
    Step,
    run_check,
    summary,
)
from polyglotic_desktop.core.listening.dictation_keys import DEFAULT_KEY
from polyglotic_desktop.core.listening.recent_speech import HOLD_MINUTES
from polyglotic_desktop.core.listening.respeaking import DEFAULT_RESPEAK_KEY
from polyglotic_desktop.core.listening.timing import MAX_WAIT_FOR_TEXT_SEC
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.core.shared.papers import (
    PRIVACY_NOTICE,
    STATUS_PAGE,
    TESTER_AGREEMENT,
)
from polyglotic_desktop.ports.dictionary import DictionaryProblem
from polyglotic_desktop.ports.learning import SetAsideLearningData
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import live_tip
from polyglotic_desktop.ui_next.controls import (
    Card,
    Flow,
    WrapButton,
    label,
    page_button,
)
from polyglotic_desktop.ui_next.dictation_key import key_words
from polyglotic_desktop.ui_next.home import (
    Page,
    server_status_text,
    unreachable_words,
)
from polyglotic_desktop.ui_next.lookup_card import dictionary_out
from polyglotic_desktop.ui_next.os_words import (
    hotkeys_here,
    on_linux,
    pc_mac_or_linux,
    pc_or_mac,
)
from polyglotic_desktop.ui_next.views.caption_window import LIMIT

CHECK_EVERY_MS = 2000
KEEP_WHATS_NEW_MS = 500
"""How long All the changes keeps What's new at the top of Help while
the page settles (361)."""
MARKS = {Status.OK: "✓", Status.BROKEN: "✗", Status.WAITING: "–"}
MARK_INDENT = 18
"""The column a line's mark sits in (at 100 % text size: it grows with the
mark, `style.px`); the line's words, its fix and a topic's text all start
after it. The mark was the first characters of the line's own text, and
✓ ✗ and – are each a different width, so the words started 2 to 4 px
apart from row to row (polyglotic-hq 376, 403)."""
CLOSED, OPEN = "▸", "▾"
HOTKEYS = frozenset("LHP")
"""Ctrl+Alt+ these: Lock all, Hide all, Pause captions (`DesktopApp.hotkeys`)
- those that work are named (`HelpPage.show_hotkeys`)."""


def _tr(text: str) -> str:
    return QApplication.translate("Help", text)


def _trn(text: str, n: int) -> str:
    return QApplication.translate("Help", text, None, n)


class Topic(QWidget):
    """A help topic: its title, and its text when opened."""

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.name = title
        # a long title wraps rather than widening the page (354)
        self.title = WrapButton(f"{CLOSED}  {title}")
        self.title.setObjectName("help.topic")
        self.title.setAccessibleName(title)
        self.title.setCheckable(True)
        self.title.setProperty("kind", "name")
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        column.addWidget(self.title)
        self.text = label(text, "Dim", wrap=True)
        self.text.setContentsMargins(MARK_INDENT, 0, 0, 6)
        column.addWidget(self.text)
        self.text.setHidden(True)
        self.title.toggled.connect(self._open)

    def _open(self, on: bool) -> None:
        self.title.setText(f"{OPEN if on else CLOSED}  {self.name}")
        self.text.setHidden(not on)


class HelpPage(Page):
    """No captions?, set up, questions, still stuck."""

    report_wanted = Signal(str)
    """"Report a problem": the check's result, as `check.summary` words it."""
    suggestion_wanted = Signal()
    """"Suggest a feature": open feedback without attaching the check."""

    def __init__(
        self,
        facts: Callable[[], Facts],
        dictionary_problem: Callable[[], DictionaryProblem | None] = lambda: None,
        chinese: bool = True,
        learning_set_aside: Callable[[], SetAsideLearningData | None] = lambda: None,
        learning_unsaved: Callable[[], bool] = lambda: False,
    ) -> None:
        """`dictionary_problem`: why the learner's dictionary is out, if it
        is; `chinese`: it's a Chinese learner's (else an English one's);
        `learning_set_aside`: their learning data file set aside at the
        start, if it was, or since; `learning_unsaved`: since, so nothing is
        kept until a restart (polyglotic-hq 206)."""
        super().__init__(_tr("Help"))
        self._facts = facts
        self._dictionary_problem = dictionary_problem
        self._chinese = chinese
        self._learning_set_aside = learning_set_aside
        self._learning_unsaved = learning_unsaved
        self._whats_new_kept = False
        self.links: tuple[Link, ...] = ()
        self.problem: DictionaryProblem | None = None
        self.set_aside: SetAsideLearningData | None = None
        self.unsaved = False

        check = Card(
            _tr("No captions?"),
            _tr("Checks each step now and stops at the first problem."),
        )
        self._mark_columns: list[tuple[QGridLayout, QLabel]] = []
        self.marks: dict[Step, QLabel] = {}
        self.rows: dict[Step, QLabel] = {}
        self.fixes: dict[Step, QLabel] = {}
        for step in Step:
            row, mark, line, fix = self._checked(f"help.{step.value}")
            check.add(row)
            self.marks[step], self.rows[step], self.fixes[step] = mark, line, fix
        row, self.dictionary_mark, self.dictionary, self.dictionary_fix = self._checked(
            "help.dictionary"
        )
        check.add(row)
        row, self.learning_mark, self.learning, self.learning_then = self._checked(
            "help.learning_data"
        )
        check.add(row)
        for each in (
            self.dictionary_mark,
            self.dictionary,
            self.dictionary_fix,
            self.learning_mark,
            self.learning,
            self.learning_then,
        ):
            each.hide()
        buttons = QHBoxLayout()
        self.check_again = QPushButton(_tr("Check again"))
        self.check_again.setObjectName("help.check_again")
        self.check_again.clicked.connect(self.refresh)
        buttons.addWidget(self.check_again)
        # whether the server is up, from outside the app (polyglotic-hq 540, 563)
        self.status_page = page_button(
            server_status_text(), STATUS_PAGE, "help.status_page"
        )
        self.status_page.setProperty("kind", "ghost")
        buttons.addWidget(self.status_page)
        buttons.addStretch(1)
        check.add(buttons)
        self.content.addWidget(check)

        self._live_key = ""
        self._hotkeys: frozenset[str] = HOTKEYS
        """Those that work here (`show_hotkeys`)."""
        self._command = "polyglotic"
        """How the desktop's own shortcuts start this app (`show_command`)."""
        self._set_up: list[Topic] = []
        self._speaker_only = False
        self._speaker_clipboard = False
        setting_up = self._topics(_tr("Set up"), set_up(), self._set_up)
        self.dictation = Topic(*dictation_topic(key_words(DEFAULT_KEY)))
        setting_up.add(self.dictation)
        self.respeaking = Topic(
            *respeak_topic(key_words(DEFAULT_KEY), own=key_words(DEFAULT_RESPEAK_KEY))
        )
        setting_up.add(self.respeaking)
        self.content.addWidget(setting_up)
        asked = self._topics(_tr("Questions"), questions())
        papers = Flow()
        papers.addWidget(
            page_button(_tr("Privacy notice"), PRIVACY_NOTICE, "help.privacy_notice")
        )
        papers.addWidget(
            page_button(
                _tr("Tester agreement"), TESTER_AGREEMENT, "help.tester_agreement"
            )
        )
        asked.add(papers)
        self.content.addWidget(asked)

        # each version's release notes, newest first and open: what Home's
        # What's new card shows after an update, kept (polyglotic-hq 345)
        self.whats_new = Card(_tr("What's new"))
        self.whats_new.column.setSpacing(2)
        self.whats_new_language = label(
            _tr("The release notes are in English."), "Faint", wrap=True
        )
        self.whats_new.add(self.whats_new_language)
        self._versions: list[Topic] = []
        self._versions_given: list[tuple[str, str]] = []
        self._versions_built = True
        self.whats_new.hide()
        self.content.addWidget(self.whats_new)

        still = Card(_tr("Still stuck?"))
        # Stack the explanation above wrapping actions.  Keeping all three in
        # one horizontal row made long translations widen Help past its
        # supported minimum viewport.
        stuck = QVBoxLayout()
        stuck.setSpacing(12)
        stuck.addWidget(
            label(
                _tr(
                    "Your report includes these results, but nothing you heard or read."
                ),
                "Faint",
                wrap=True,
            ),
        )
        actions = Flow()
        self.report = QPushButton(_tr("Report a problem"))
        self.report.setObjectName("help.report")
        self.report.clicked.connect(self._report)
        actions.addWidget(self.report)
        self.suggest = QPushButton(_tr("Suggest a feature"))
        self.suggest.setObjectName("help.suggest")
        self.suggest.clicked.connect(self.suggestion_wanted)
        actions.addWidget(self.suggest)
        stuck.addLayout(actions)
        still.add(stuck)
        self.content.addWidget(still)
        self.content.addStretch(1)

        self._timer = QTimer(self, interval=CHECK_EVERY_MS)
        self._timer.timeout.connect(self.refresh)  # started when shown

    def _checked(self, name: str) -> tuple[QGridLayout, QLabel, QLabel, QLabel]:
        """One line of the check: its mark in a column of its own
        (`MARK_INDENT`), its words (named `name`), and under the words
        what to do about it."""
        row = QGridLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setHorizontalSpacing(0)
        row.setVerticalSpacing(1)
        row.setColumnStretch(1, 1)
        mark = label("")
        self._mark_columns.append((row, mark))
        mark.setObjectName(f"{name}.mark")
        line = label("", wrap=True)
        line.setObjectName(name)
        fix = label("", "Faint", wrap=True)  # its name is its look
        row.addWidget(mark, 0, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(line, 0, 1)
        row.addWidget(fix, 1, 1)
        return row, mark, line, fix

    @staticmethod
    def _say(mark: QLabel, line: QLabel, status: Status, words: str) -> None:
        """A line's mark and words; read out as they were written, the mark
        first."""
        mark.setText(MARKS[status])
        line.setText(words)
        line.setAccessibleName(f"{MARKS[status]}  {words}")

    def _topics(
        self,
        title: str,
        topics: list[tuple[str, str]],
        made: list[Topic] | None = None,
    ) -> Card:
        """A card of `topics`, each one also put in `made` if given."""
        card = Card(title)
        card.column.setSpacing(2)
        for name, text in topics:
            topic = Topic(name, text)
            card.add(topic)
            if made is not None:
                made.append(topic)
        return card

    def show_whats_new(
        self, versions: Sequence[tuple[str, str]], in_english: bool = False
    ) -> None:
        """What's new: each version's notes as (version, plain text), newest
        first - the newest open, the others a click away; `in_english`: the
        interface isn't, and the notes are. None given: no card."""
        for topic in self._versions:
            topic.deleteLater()
        self._versions = []
        self._versions_given = list(versions)
        self._versions_built = False
        self.whats_new_language.setVisible(in_english)
        self.whats_new.setVisible(bool(self._versions_given))
        if self.isVisible():
            self._build_versions()

    @property
    def versions(self) -> list[Topic]:
        """What's new's versions, built now if they weren't: they're built
        when Help is first shown, not at the start - every version's notes
        laid out on the interface thread took about 100 ms of each start,
        right after the first paint (361)."""
        self._build_versions()
        return self._versions

    def _build_versions(self) -> None:
        if self._versions_built:
            return
        self._versions_built = True
        for version, text in self._versions_given:
            topic = Topic(_tr("Version {version}").format(version=version), text)
            topic.setObjectName("help.version")
            self.whats_new.add(topic)
            self._versions.append(topic)
        if self._versions:
            self._versions[0].title.setChecked(True)

    def open_whats_new(self) -> None:
        """Home's All the changes: What's new in view from its heading, the
        newest open. Not `ensureWidgetVisible`: once a version is open the
        section is taller than the view, and Qt then centres it - the
        learner landed in the middle of the newest version's notes (361).
        Kept at the heading while the page settles (its text wraps again
        once the scroll bar shows), not after."""
        if self.versions:
            self.versions[0].title.setChecked(True)
        if not self._whats_new_kept:
            self.verticalScrollBar().rangeChanged.connect(self._keep_whats_new)
        self._whats_new_kept = True
        self._whats_new_to_top()
        QTimer.singleShot(KEEP_WHATS_NEW_MS, self, self._let_whats_new_go)

    def _keep_whats_new(self) -> None:
        if self._whats_new_kept:
            self._whats_new_to_top()

    def _let_whats_new_go(self) -> None:
        if self._whats_new_kept:  # a second All the changes' timer: gone already
            self._whats_new_kept = False
            self.verticalScrollBar().rangeChanged.disconnect(self._keep_whats_new)

    def _whats_new_to_top(self) -> None:
        inner = self.widget()
        if inner is None:
            return
        if (layout := inner.layout()) is not None:
            layout.activate()  # the scroll bar's range takes the open version
        self.verticalScrollBar().setValue(self.whats_new.mapTo(inner, QPoint(0, 0)).y())

    def show_hotkeys(self, working: Collection[str], live_key: str = "") -> None:
        """Only `working` hotkeys are named - the others another app has, or
        weren't registered (`DesktopApp.hotkeys_not_working`; polyglotic-hq
        398's preview build has none, and Help said "Ctrl+Alt+L": 400)."""
        self._hotkeys = frozenset(working)
        self._live_key = live_key
        self._show_set_up()

    def show_command(self, command: str) -> None:
        """How a shortcut of the desktop's own starts this app - the
        AppImage's path - for Linux's topic on them (polyglotic-hq 570)."""
        self._command = command
        self._show_set_up()

    def _show_set_up(self) -> None:
        topics = set_up(self._hotkeys, self._command)
        for topic, (title, text) in zip(self._set_up, topics, strict=True):
            if self._live_key and title == _tr("Move, lock and resize caption windows"):
                text += "\n\n" + live_tip(self._live_key)
            topic.text.setText(text)
        if self.isVisible():
            self.refresh()

    def offer_dictation(
        self, offered: bool, *, speakers: bool = False, clipboard: bool = False
    ) -> None:
        """Dictation's topic, or none on an OS that has no dictation yet
        (Linux, until polyglotic-hq 546's slice 8; 574)."""
        self.dictation.setVisible(offered)
        self.respeaking.setVisible(offered or speakers)
        self._speaker_only = speakers and not offered
        self._speaker_clipboard = clipboard

    def show_dictation_key(self, key: str, on: bool = True) -> None:
        """Dictation's key, in words ("Right Ctrl"), as its topic names it,
        and whether dictation is on (576)."""
        self.dictation.text.setText(dictation_topic(key, on)[1])

    def show_respeaking(self, key: str, on: bool, dictating: bool, own: str) -> None:
        """Re-speaking's topic as the settings have it: `key`, dictation's
        key in words, `own` its own key's ("" for one key for both)."""
        if self._speaker_only:
            own = own or key_words(DEFAULT_RESPEAK_KEY)
        self.respeaking.text.setText(
            respeak_topic(key, on, dictating, own, clipboard=self._speaker_clipboard)[1]
        )

    def showEvent(self, event: QShowEvent) -> None:
        self._build_versions()
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def refresh(self) -> None:
        """Runs the check on the facts as they are now."""
        self.links = run_check(self._facts())
        for row, mark in self._mark_columns:  # at the text size now
            widest = max(
                mark.fontMetrics().horizontalAdvance(each) for each in MARKS.values()
            )
            row.setColumnMinimumWidth(0, max(style.px(MARK_INDENT), widest + 6))
        broken_before = False
        for link in self.links:
            title, fix = words(link, broken_before, self._hotkeys)
            self._say(self.marks[link.step], self.rows[link.step], link.status, title)
            self.fixes[link.step].setText(fix)
            self.fixes[link.step].setHidden(not fix)
            broken_before = broken_before or link.status is not Status.OK
        self.problem = self._dictionary_problem()
        if self.problem is not None:
            what, fix = dictionary_out(self.problem, self._chinese)
            self._say(self.dictionary_mark, self.dictionary, Status.BROKEN, what)
            self.dictionary_fix.setText(fix)
        for each in (self.dictionary_mark, self.dictionary, self.dictionary_fix):
            each.setVisible(self.problem is not None)
        self.set_aside = self._learning_set_aside()
        self.unsaved = self._learning_unsaved()
        if self.set_aside is not None:
            what, then = learning_set_aside(self.set_aside, self.unsaved)
            self._say(self.learning_mark, self.learning, Status.BROKEN, what)
            self.learning_then.setText(then)
        for each in (self.learning_mark, self.learning, self.learning_then):
            each.setVisible(self.set_aside is not None)

    def _report(self) -> None:
        self.refresh()
        found = summary(self.links)
        if self.problem is not None:  # its kind only, as the log has it
            found += f"\ndictionary: {self.problem.value}"
        if self.set_aside is not None:  # its kind only: a path holds the user's name
            found += f"\nlearning data: set aside ({self.set_aside.problem.value})"
            if self.unsaved:
                found += ", after the start"
        self.report_wanted.emit(found)


def learning_set_aside(
    aside: SetAsideLearningData, unsaved: bool = False
) -> tuple[str, str]:
    """Help's words for learning data set aside: what happened, then that
    the words come back - now, or after a restart if it was found damaged
    since the start (`unsaved`) - and where the old file is (polyglotic-hq
    206)."""
    if unsaved:
        then = pc_or_mac(
            _tr(
                "Changes aren't kept on this PC until you restart Polyglotic; your"
                " saved words then come back from your account. The old file is kept"
                " as {path}, in case we ask for it in a report."
            ),
            _tr(
                "Changes aren't kept on this Mac until you restart Polyglotic; your "
                "saved words then come back from your account. The old file is kept as "
                "{path}, in case we ask for it in a report."
            ),
        )
    else:
        then = _tr(
            "Your saved words are coming back from your account. The old file"
            " is kept as {path}, in case we ask for it in a report."
        )
    return (
        pc_or_mac(
            _tr("Your learning data on this PC was damaged and has been set aside"),
            _tr("Your learning data on this Mac was damaged and has been set aside"),
        ),
        then.format(path=aside.path),
    )


# -- the words ------------------------------------------------------------------------


def words(
    link: Link, after_trouble: bool, hotkeys: Collection[str] = HOTKEYS
) -> tuple[str, str]:
    """A link's line and, under it, its fix (if broken) or what it's
    waiting for (if it's the one being waited on). `hotkeys`: those that
    work here, the only ones named."""
    name = link.source or ""
    if link.status is Status.BROKEN and link.cause is not None:
        return unreachable_words(link.cause)  # Home's words (251)
    if link.status is Status.BROKEN and link.problem is not None:
        return problem(link.problem, name, hotkeys)
    if link.status is Status.OK:
        return {
            Step.CONNECTED: _tr("Signed in and connected to the server"),
            Step.TICKED: _tr("{name} is added on Home").format(name=name),
            Step.SOUND: _trn(
                "Sound from {name} in the last %Ln second(s)", SOUND_WINDOW
            ).format(name=name),
            Step.SPEECH: _tr("Speech heard"),
            Step.CAPTIONS: _tr("Captions shown"),
        }[link.step], ""
    titles = {
        Step.CONNECTED: _tr("Signed in and connected to the server"),
        Step.TICKED: _tr("Something is added on Home"),
        Step.SOUND: _trn("Sound from it in the last %Ln second(s)", SOUND_WINDOW),
        Step.SPEECH: _tr("Speech heard"),
        Step.CAPTIONS: _tr("Captions shown"),
    }
    waits = {
        Step.CONNECTED: _tr("Connecting to the server…"),
        Step.SOUND: _tr("Listening for sound…"),
        Step.SPEECH: _tr("Listening for speech…"),
        Step.CAPTIONS: _tr("Waiting for the first caption…"),
    }
    return titles[link.step], "" if after_trouble else waits.get(link.step, "")


def problem(
    found: Problem, name: str, hotkeys: Collection[str] = HOTKEYS
) -> tuple[str, str]:
    """A broken link's line and its likely fix. The server unreachable is
    said by its cause (`words`); without one, as nothing answering.
    `hotkeys`: those that work here, the only ones named."""
    if found is Problem.SERVER_UNREACHABLE:
        return unreachable_words(Unreachable.NO_ANSWER)
    line, fix = {
        Problem.SIGN_IN_NEEDED: (
            _tr("Not signed in"),
            _tr("Sign in with your email to continue."),
        ),
        Problem.PLUS_ENDED: (
            _tr("Plus has ended"),
            _tr(
                "Get Plus on Account, and captions start again by themselves. "
                "Your words and lookups stay; a transcript is gone when you quit, "
                "unless you save it."
            ),
        ),
        Problem.UPDATE_NEEDED: (
            _tr("Polyglotic needs an update"),
            pc_mac_or_linux(
                _tr(
                    "It downloads the update and restarts by itself. If it doesn't, "
                    "quit from the tray and start it again."
                ),
                _tr(
                    "It downloads the update and restarts by itself. If it doesn't, "
                    "quit from the menu bar and start it again."
                ),
                # Linux: GNOME has no tray without an extension (571)
                _tr(
                    "It downloads the update and restarts by itself. If it doesn't, "
                    "quit Polyglotic and start it again."
                ),
            ),
        ),
        Problem.SERVER_BUSY: (
            _tr("The server is busy"),
            _tr("The server is at capacity. Polyglotic will keep trying."),
        ),
        Problem.NOT_CONNECTED: (
            _tr("Not connected to the server"),
            pc_mac_or_linux(
                _tr(
                    "Quit from the tray and start Polyglotic again. If it keeps "
                    "happening, report a problem."
                ),
                _tr(
                    "Quit from the menu bar and start Polyglotic again. If it keeps "
                    "happening, report a problem."
                ),
                _tr(
                    "Quit Polyglotic and start it again. If it keeps happening, "
                    "report a problem."
                ),
            ),
        ),
        Problem.NOTHING_TICKED: (
            _tr("Nothing to caption"),
            pc_or_mac(
                _tr(
                    "On Home, add an app (up to {limit}), or choose Everything the PC "
                    "plays."
                ),
                _tr(
                    "On Home, add an app (up to {limit}), or choose Everything the Mac "
                    "plays."
                ),
            ).format(limit=QLocale().toString(LIMIT)),
        ),
        Problem.APP_NOT_OPEN: (
            _tr("{name} isn't open").format(name=name),
            _tr("Open it to start captions."),
        ),
        Problem.CAPTURE_STOPPED: (  # 557: it was "quiet" while its capture was dead
            _tr(
                "Polyglotic stopped hearing {name} - it's starting again by itself"
            ).format(name=name),
            pc_mac_or_linux(
                _tr(
                    "Quit from the tray and start Polyglotic again. If it keeps "
                    "happening, report a problem."
                ),
                _tr(
                    "Quit from the menu bar and start Polyglotic again. If it keeps "
                    "happening, report a problem."
                ),
                _tr(
                    "Quit Polyglotic and start it again. If it keeps happening, "
                    "report a problem."
                ),
            ),
        ),
        Problem.MIC_STOPPED: (
            _tr(
                "Polyglotic stopped hearing your microphone - it's starting again "
                "by itself"
            ),
            pc_mac_or_linux(
                _tr(
                    "Quit from the tray and start Polyglotic again. If it keeps "
                    "happening, report a problem."
                ),
                _tr(
                    "Quit from the menu bar and start Polyglotic again. If it keeps "
                    "happening, report a problem."
                ),
                _tr(
                    "Quit Polyglotic and start it again. If it keeps happening, "
                    "report a problem."
                ),
            ),
        ),
        Problem.APP_QUIET: (
            _trn(
                "{name} is quiet: no sound from it in the last %Ln second(s)",
                SOUND_WINDOW,
            ).format(name=name),
            pc_or_mac(
                _tr(
                    "Play something, then check that it uses this PC's speakers or "
                    "headset and isn't muted."
                ),
                _tr(
                    "Play something, then check that it uses this Mac's speakers or "
                    "headset and isn't muted."
                ),
            ),
        ),
        Problem.SYSTEM_QUIET: (
            pc_or_mac(
                _trn(
                    "The PC is quiet: nothing it plays has made sound in %Ln second(s)",
                    SOUND_WINDOW,
                ),
                _trn(
                    "The Mac is quiet: nothing it plays has made sound in %Ln second(s)",
                    SOUND_WINDOW,
                ),
            ),
            pc_or_mac(
                _tr(
                    "Play something. If you hear it on a headset that isn't "
                    "the PC's default device, make that the default, or add the "
                    "app instead."
                ),
                _tr(
                    "Play something. If you hear it on a headset that isn't the Mac's "
                    "default device, make that the default, or add the app instead."
                ),
            ),
        ),
        Problem.MIC_QUIET: (
            _trn(
                "Your microphone is quiet: no sound from it in %Ln second(s)",
                SOUND_WINDOW,
            ),
            pc_or_mac(
                _tr(
                    "Check that it isn't muted and is selected in this PC's sound "
                    "settings."
                ),
                _tr(
                    "Check that it isn't muted and is selected in this Mac's sound "
                    "settings."
                ),
            ),
        ),
        Problem.SOUND_NOT_ALLOWED: (
            _tr("Polyglotic isn't allowed to hear what the Mac plays"),
            #: macOS System Settings' own names (macOS 15 and later): keep them
            #: as the Mac shows them in the language
            _tr(
                "In System Settings, open Privacy & Security, then Screen & "
                "System Audio Recording, and turn on Polyglotic under System "
                "Audio Recording Only. Then quit Polyglotic and open it again."
            ),
        ),
        Problem.MIC_NOT_ALLOWED: (
            _tr("Polyglotic isn't allowed to use the microphone"),
            #: macOS System Settings' own names: keep them as the Mac shows them
            _tr(
                "In System Settings, open Privacy & Security, then Microphone, "
                "and turn on Polyglotic. Then quit Polyglotic and open it again."
            ),
        ),
        Problem.NO_SPEECH: (
            _tr("Sound heard, but no speech"),
            _tr(
                "Music and sound effects aren't captioned. Play clear speech louder "
                "than any background sound."
            ),
        ),
        Problem.PAUSED: (
            _tr("Captions are paused"),
            pc_mac_or_linux(
                _tr("Choose Resume on Home or in the tray menu, or press Ctrl+Alt+P."),
                _tr(
                    "Choose Resume on Home or in the menu bar's menu, or press "
                    "Ctrl+Alt+P."
                ),
                _tr("Choose Resume on Home, or press Ctrl+Alt+P."),
            )
            if "P" in hotkeys
            else pc_mac_or_linux(
                _tr("Choose Resume on Home or in the tray menu."),
                _tr("Choose Resume on Home or in the menu bar's menu."),
                _tr("Choose Resume on Home."),
            ),
        ),
        Problem.OVERLAYS_HIDDEN: (
            _tr("The caption windows are hidden"),
            pc_mac_or_linux(
                _tr(
                    "Press Ctrl+Alt+H, or use Hide all on Home or the tray menu. An "
                    "app's transcript shows whether captions are arriving."
                ),
                _tr(
                    "Press Ctrl+Alt+H, or use Hide all on Home or the menu bar's menu. "
                    "An app's transcript shows whether captions are arriving."
                ),
                _tr(
                    "Press Ctrl+Alt+H, or use Hide all on Home. An app's transcript "
                    "shows whether captions are arriving."
                ),
            )
            if "H" in hotkeys
            else pc_mac_or_linux(
                _tr(
                    "Use Hide all on Home or the tray menu. An app's transcript "
                    "shows whether captions are arriving."
                ),
                _tr(
                    "Use Hide all on Home or the menu bar's menu. An app's transcript "
                    "shows whether captions are arriving."
                ),
                _tr(
                    "Use Hide all on Home. An app's transcript shows whether captions "
                    "are arriving."
                ),
            ),
        ),
        Problem.SERVER_FAILING: (
            _tr("Captions are failing on the server"),
            pc_or_mac(
                _tr(
                    "It keeps trying by itself - nothing on this PC needs changing. "
                    "If it goes on for more than a few minutes, report a problem."
                ),
                _tr(
                    "It keeps trying by itself - nothing on this Mac needs changing. "
                    "If it goes on for more than a few minutes, report a problem."
                ),
            ),
        ),
        Problem.NO_CAPTIONS: (
            _tr("Speech heard, but no captions shown"),
            _tr(
                "If the app's transcript shows captions, its caption window may "
                "be off-screen: Reset positions on Home puts every window back."
            ),
        ),
    }[found]
    return line, hotkeys_here(fix)  # "⌃⌘P" on a Mac (428)


def set_up(
    hotkeys: Collection[str] = HOTKEYS, command: str = "polyglotic"
) -> list[tuple[str, str]]:
    """`hotkeys`: those that work here. A topic names its hotkeys only
    while they all work; else it says where else the commands are
    (polyglotic-hq 400). On Linux, a topic on the desktop's own shortcuts,
    which start the app (`command`) with --lock and the like (570)."""
    topics = [
        (
            pc_mac_or_linux(
                _tr("Caption apps you add (Windows 11)"),
                _tr("Caption apps you add (macOS 14.2 or later)"),
                _tr("Caption apps you add"),  # Linux: PipeWire or PulseAudio (561)
            ),
            pc_mac_or_linux(
                _trn(
                    "On Home, add up to %Ln app(s) with sound open; each gets a caption "
                    "window of its own, labelled with its name. An app you added that "
                    "isn't open is captioned when it opens. Windows 10 can't tell apps "
                    "apart, so there everything the PC plays is captioned.",
                    LIMIT,
                ),
                _trn(
                    "On Home, add up to %Ln app(s) with sound open; each gets a caption "
                    "window of its own, labelled with its name. An app you added that "
                    "isn't open is captioned when it opens. Before macOS 14.2 a Mac "
                    "can't tell apps apart, so there everything the Mac plays is "
                    "captioned.",
                    LIMIT,
                ),
                _trn(
                    "On Home, add up to %Ln app(s) with sound open; each gets a caption "
                    "window of its own, labelled with its name. An app you added that "
                    "isn't open is captioned when it opens.",
                    LIMIT,
                ),
            ),
        ),
        (
            _tr("Caption one app separately"),
            pc_mac_or_linux(
                _tr(
                    "With one app added on Home, turn on Also caption everything else "
                    "the PC plays: everything except that app gets a caption window of "
                    "its own, labelled Everything else - a call in one window, the "
                    "game "
                    "or video in the other, nothing in both. Windows can leave out "
                    "only "
                    "one app, so it's there with one app at a time (Windows 11)."
                ),
                _tr(
                    "With one app added on Home, turn on Also caption everything else "
                    "the Mac plays: everything except that app gets a caption window "
                    "of its own, labelled Everything else - a call in one window, the "
                    "game or video in the other, nothing in both. It's there with one "
                    "app at a time."
                ),
                _tr(
                    "With one app added on Home, turn on Also caption everything else "
                    "the PC plays: everything except that app gets a caption window of "
                    "its own, labelled Everything else - a call in one window, the "
                    "game or video in the other, nothing in both. It's there with one "
                    "app at a time."
                ),
            ),
        ),
        (
            pc_or_mac(
                _tr("Caption everything the PC plays"),
                _tr("Caption everything the Mac plays"),
            ),
            pc_or_mac(
                _tr(
                    "On Home, choose Everything the PC plays: all it plays through "
                    "its default speakers or headset, labelled This PC. If "
                    "your headset isn't the default device, make it the default."
                ),
                _tr(
                    "On Home, choose Everything the Mac plays: all it plays through "
                    "its default speakers or headset, labelled This Mac. If your "
                    "headset isn't the default device, make it the default."
                ),
            ),
        ),
        (_tr("Caption your own microphone"), microphone_help()),
        (
            _tr("Move, lock and resize caption windows"),
            (
                _tr(
                    "Drag a caption window to move it, or drag its edges to resize "
                    "it. Lock all (Ctrl+Alt+L) lets clicks pass through; Hide all is "
                    "Ctrl+Alt+H; Pause captions is Ctrl+Alt+P. Lost one? Reset "
                    "positions on Home puts every window back."
                )
                if {"L", "H", "P"} <= set(hotkeys)
                else pc_mac_or_linux(
                    _tr(
                        "Drag a caption window to move it, or drag its edges to resize "
                        "it. Lock all, on Home or in the tray menu, lets clicks pass "
                        "through. Lost one? Reset positions on Home puts every window "
                        "back."
                    ),
                    _tr(
                        "Drag a caption window to move it, or drag its edges to resize it. "
                        "Lock all, on Home or in the menu bar's menu, lets clicks pass "
                        "through. Lost one? Reset positions on Home puts every window back."
                    ),
                    _tr(
                        "Drag a caption window to move it, or drag its edges to resize it. "
                        "Lock all, on Home, lets clicks pass through. Lost one? Reset "
                        "positions on Home puts every window back."
                    ),
                )
            )
            + "\n\n"
            + hotkeys_here(  # Command's on a Mac (451)
                _tr(
                    "In a caption window, press Home or Ctrl+Home to jump to the "
                    "first caption, and End or Ctrl+End to return to live."
                )
            ),
        ),
        (
            _tr("Over a game"),
            _tr(
                "A caption window never takes the game's keyboard or mouse: "
                "it is never the active window. Put it where it doesn't cover "
                "what you need to see, then Lock all (Ctrl+Alt+L) so clicks go "
                "through to the game; Hide all (Ctrl+Alt+H) in a fight. The "
                "hotkeys work while the game has focus; Settings > Hotkeys "
                "changes them. A game in exclusive full screen covers every "
                "other window: choose its borderless or windowed full screen "
                "instead."
            )
            if {"L", "H"} <= set(hotkeys)
            else pc_mac_or_linux(
                _tr(
                    "A caption window never takes the game's keyboard or mouse: "
                    "it is never the active window. Put it where it doesn't cover "
                    "what you need to see, then Lock all on Home or in the tray "
                    "menu so clicks go through to the game. A game in exclusive "
                    "full screen covers every other window: choose its borderless "
                    "or windowed full screen instead."
                ),
                _tr(
                    "A caption window never takes the game's keyboard or mouse: it is "
                    "never the active window. Put it where it doesn't cover what you "
                    "need to see, then Lock all on Home or in the menu bar's menu so "
                    "clicks go through to the game. A game in exclusive full screen "
                    "covers every other window: choose its borderless or windowed full "
                    "screen instead."
                ),
                _tr(
                    "A caption window never takes the game's keyboard or mouse: it is "
                    "never the active window. Put it where it doesn't cover what you "
                    "need to see, then Lock all on Home so clicks go through to the "
                    "game. A game in exclusive full screen covers every other window: "
                    "choose its borderless or windowed full screen instead."
                ),
            ),
        ),
    ]
    if on_linux():  # GNOME's Wayland session gives the app no hotkey (570)
        topics.append(desktop_shortcuts(command))
    return [(title, hotkeys_here(text)) for title, text in topics]  # "⌃⌘L" (428)


def desktop_shortcuts(command: str) -> tuple[str, str]:
    """Linux's topic on shortcuts the desktop keeps (polyglotic-hq 546, 570):
    where the app gets no hotkeys of its own (GNOME's Wayland session), a
    custom shortcut in the desktop's keyboard settings runs the app again
    with `--lock`, `--pause` or `--hide`, and the copy that runs does it."""
    return (
        _tr("Desktop shortcuts"),
        _tr(
            "Where Polyglotic's hotkeys don't work (GNOME on Wayland), add a custom "
            "shortcut in your desktop's keyboard settings (GNOME: Settings > "
            "Keyboard > Custom Shortcuts) with the command {command} --lock, or "
            "--pause, or --hide. It does what the hotkey would."
        ).format(command=command),
    )


def dictation_topic(key: str, on: bool = True) -> tuple[str, str]:
    """Dictation's topic, naming its key in words ("Right Ctrl";
    polyglotic-hq 283, 289): `on`, dictation is - on from the start
    (decision 0220), so it says where to turn it off; else where to turn
    it on (polyglotic-hq 576)."""
    if on:
        text = pc_or_mac(
            _tr(
                "Hold {key} and speak; let go, and your words are typed where your "
                "cursor is. Esc cancels before they're typed. Dictation is on from "
                "the start: turn it off in Settings > Dictation, or in the tray "
                "menu. To use another key or combination, click the key in "
                "Settings > Dictation and press the one you want."
            ),
            _tr(
                "Hold {key} and speak; let go, and your words are typed where your "
                "cursor is. Esc cancels before they're typed. Dictation is on from "
                "the start: turn it off in Settings > Dictation, or in the menu "
                "bar's menu. To use another key or combination, click the key in "
                "Settings > Dictation and press the one you want."
            ),
        )
    else:
        text = pc_or_mac(
            _tr(
                "Turn on Dictation in Settings > Dictation, or in the tray menu. Hold"
                " {key} and speak; let go, and your words are typed where your cursor"
                " is. Esc cancels before they're typed. To use another key or"
                " combination, click the key in Settings > Dictation and press the"
                " one you want."
            ),
            _tr(
                "Turn on Dictation in Settings > Dictation, or in the menu bar's menu. "
                "Hold {key} and speak; let go, and your words are typed where your "
                "cursor is. Esc cancels before they're typed. To use another key or "
                "combination, click the key in Settings > Dictation and press the one "
                "you want."
            ),
        )
    return _tr("Dictate into any app (preview)"), text.format(key=key)


def respeak_topic(
    key: str,
    on: bool = True,
    dictating: bool = True,
    own: str = "",
    *,
    clipboard: bool = False,
) -> tuple[str, str]:
    """Speaker typing and its current key, including the shared gesture."""
    if not on:
        text = _tr("Turn on Type what they said in Settings > Dictation.")
    else:
        gesture = (
            _tr("Tap {key}, then hold it while they speak.")
            if dictating and not own
            else _tr("Hold {key} while they speak.")
        ).format(key=own or key)
        text = " ".join(
            (
                gesture,
                _tr(
                    "Use the words or translation from the caption window you’re watching."
                    " Without captions, listen to the speakers selected in Settings > Speech."
                ),
                (
                    _tr(
                        "Release to copy the speech to the clipboard, then paste it where you want."
                    )
                    if clipboard
                    else _tr("Focus a text field in another app before you let go.")
                ),
                _tr(
                    "Choose the key and whether to type the original or its translation in Settings > Dictation."
                ),
            )
        )
    return _tr("Type what they said"), text


def microphone_help() -> str:
    text = _tr(
        "Your first caption window and Conversation windows show your speech as You "
        "by default. Use the microphone button on a window's bar to turn it on or off there."
    )
    return text + pc_mac_or_linux(
        " " + _tr("Dictation also uses the microphone while you hold its key."),
        " "
        + _tr("Dictation also uses the microphone while you hold its key.")
        + " "
        + _tr("macOS asks for microphone access."),
        "",
    )


def _default_wait() -> str:
    wait = MAX_WAIT_FOR_TEXT_SEC
    if wait == int(wait):
        return _trn("%Ln second(s)", int(wait))
    return _tr("{seconds} s").format(seconds=QLocale().toString(wait))


def questions() -> list[tuple[str, str]]:
    return [
        (
            _tr("What we keep"),
            pc_or_mac(
                _trn(
                    "Only speech leaves this PC: our server turns it into captions and "
                    "translations, and never stores the audio, the captions or the "
                    "translations. This PC holds the last %Ln minute(s) of each app's "
                    "finished speech in memory, and sends it again only when you ask. "
                    "Your transcript never leaves this PC, and it's gone when you quit "
                    "Polyglotic unless you save it. We keep your account, your minutes, "
                    "a record of each session (never what was said or the app's name) "
                    "and the dictionary words you look up, save or mark - never the "
                    "sentence around them. Usage statistics and word counts are shared "
                    "only if you turn them on (Account > Choose what to share), and you "
                    "can delete your learning data on Account. The privacy notice, "
                    "below, says it all.",
                    HOLD_MINUTES,
                ),
                _trn(
                    "Only speech leaves this Mac: our server turns it into captions and "
                    "translations, and never stores the audio, the captions or the "
                    "translations. This Mac holds the last %Ln minute(s) of each app's "
                    "finished speech in memory, and sends it again only when you ask. "
                    "Your transcript never leaves this Mac, and it's gone when you quit "
                    "Polyglotic unless you save it. We keep your account, your minutes, "
                    "a record of each session (never what was said or the app's name) "
                    "and the dictionary words you look up, save or mark - never the "
                    "sentence around them. Usage statistics and word counts are shared "
                    "only if you turn them on (Account > Choose what to share), and you "
                    "can delete your learning data on Account. The privacy notice, "
                    "below, says it all.",
                    HOLD_MINUTES,
                ),
            ),
        ),
        (
            _tr("Captioning a call"),
            _tr(
                "In some places everyone on a call has to agree before it's captioned. "
                "Tell the people you're talking with."
            ),
        ),
        (
            _tr("Why is a line wrong?"),
            _tr(
                "Captions and translations are made by machine and can be wrong, "
                "most of all with names, slang, music behind a voice and several "
                "people talking at once. Add slang, memes and names you hear often "
                "- rizz, yyds, a streamer's name - in Names and slang, under "
                "Settings > Speech, so they're spelled your way."
            ),
        ),
        (
            # songs are heard in part (polyglotic-hq 536, measured after #943:
            # on Detect 12-52 % of each song heard, most lines shown right; a
            # Mandarin song under fixed English came back as English)
            _tr("Are songs captioned?"),
            _tr(
                "In part. Polyglotic is made for speech: in a song it catches "
                "some of the lines sung, and a few come out wrong. Songs work best "
                "with Spoken language on Detect: with a language chosen there, a song "
                "in another language comes out as a translation into it. Music "
                "without words isn't captioned."
            ),
        ),
        (
            # The default first (626), in the order of Settings > Timing.
            _tr("When do captions appear?"),
            _tr(
                "Instant, the default: words appear as they're said and may change "
                "until the sentence ends. Whole captions shows each finished sentence "
                "at once. Steady follows the speaker's pace with a short delay. "
                "Calm waits for words the speech model is sure of. Choose a mode in "
                "Settings > Timing or from the caption bar. The longest wait for text "
                "is {wait} by default.",
            ).format(wait=_default_wait()),
        ),
        (
            _tr("Look up a word, and keep it"),
            _tr(
                "Point at a word in a caption window or a transcript (the window "
                "unlocked): its reading and first meaning appear. Click it for "
                "the whole entry, or drag across a phrase. Add to deck keeps it "
                "with the line it was in; Known stops it being marked; Save to "
                "puts it in a category of yours. Esc closes the card."
            ),
        ),
        (
            _tr("Where are my words?"),
            pc_or_mac(
                _tr(
                    "Words you look up and save are on Words. They are kept on this "
                    "PC and, with your account, on our server, so they follow you to "
                    "another PC."
                ),
                _tr(
                    "Words you look up and save are on Words. They are kept on this "
                    "Mac and, with your account, on our server, so they follow you to "
                    "another computer."
                ),
            ),
        ),
        (
            _tr("Put your words into Anki"),
            _tr(
                "Words > Export for Anki. The deck file (.apkg) is the easy way: "
                "double-click it and Anki adds a Polyglotic deck with its own "
                "note type - word, reading, meaning, the sentence with the word "
                "in bold, its translation - and Anki's own text-to-speech for "
                "sound. The CSV imports as it is into Anki's Basic (front and "
                "back), whatever Anki's language. For a note type of your own, "
                "pick it in Anki's import dialog and match its fields to the "
                "columns by number: 1 word, 4 reading, 5 meaning, 6 sentence, "
                "7 translation. Keep to one of the two: a word stays the kind of note "
                "it "
                "first came as. Exporting again updates the same cards rather "
                "than doubling them, and leaves your own notes and tags on words "
                "that haven't changed here; tick Only words not exported yet to "
                "keep the file short. Anki may call 行 (háng) and 行 (xíng) "
                "duplicates - it compares the first field only. They are two "
                "words: keep both."
            ),
        ),
    ]
