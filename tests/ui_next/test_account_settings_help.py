"""Account, Settings and Help in the new main window (project 109's
structure, section 7; build step 6): today's pages' commands and states,
in the new interface's words - caption windows, Home, Words. Made-up
names only; offscreen."""

import time
from collections.abc import Iterator
from dataclasses import replace

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFocusEvent,
    QKeyEvent,
    QKeySequence,
)
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from tests.ui_next.test_lock_says_how_to_unlock import LOCK_KEYS

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.languages import LearningLanguages, Tier
from polyglotic_desktop.core.listening.check import (
    Facts,
    Problem,
    SourceActivity,
    Step,
    Ticked,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.shared.papers import PRIVACY_NOTICE, TESTER_AGREEMENT
from polyglotic_desktop.ui_next import help_page, os_words
from polyglotic_desktop.ui_next.account_page import AccountPage
from polyglotic_desktop.ui_next.dictation_key import key_words
from polyglotic_desktop.ui_next.help_page import HelpPage, Topic
from polyglotic_desktop.ui_next.learning_page import LearningPage
from polyglotic_desktop.ui_next.os_words import hotkeys_here as keys
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.learning import LanguageCard
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.words import LevelLine

APP = SourceId("app-1")


@pytest.fixture(autouse=True)
def windows_deleted(qapp: QApplication) -> Iterator[None]:
    """Every window a test makes is deleted after it. A page kept alive to
    the end of the run (its signals' lambdas hold it) is destroyed after the
    application, and the process can end with an error once every test has
    passed (CI, 2026-11-07)."""
    before = set(QApplication.topLevelWidgets())
    yield
    for widget in QApplication.topLevelWidgets():
        if widget not in before:
            widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def settle() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QApplication.processEvents()


def texts(page: QWidget) -> list[str]:
    """Every label's and button's words on a page - and each help topic's."""
    found = [w.text() for w in page.findChildren(QLabel)]
    found += [w.text() for w in page.findChildren(QPushButton)]
    return found


# -- Account ---------------------------------------------------------------------------


def test_account_signed_out_offers_sign_in_and_no_deletion(qapp: QApplication) -> None:
    page = AccountPage()
    page.show()
    settle()
    assert page.sign_in_button.isVisible() and not page.sign_out_button.isVisible()
    assert not page.delete_learning.isEnabled()
    assert "an invite, or the one in your Plus email" in page.state.text()
    assert not page.account_id.isVisible()
    page.close()


def test_home_and_account_say_the_same_when_signed_out(qapp: QApplication) -> None:
    """polyglotic-hq 228 (224's finding 4): Home's line trailed off on a
    possessive ("... or your Plus email's") while Account's read well. One
    string now says what signing in needs, in both."""
    from polyglotic_desktop.ui_next.home import StateCard
    from polyglotic_desktop.ui_next.views.home import HomeState, ListeningState

    card = StateCard(QAction("Pause captions"))
    card.show_state(HomeState(ListeningState.SIGN_IN_NEEDED, chosen=True))
    needed = "you need a code from us: an invite, or the one in your Plus email"
    assert card.title_label.text() == "Not signed in"
    assert card.detail.text() == needed
    page = AccountPage()
    assert page.state.text() == f"Not signed in - {needed}."


def test_account_signed_in_shows_the_start_of_the_account_id(
    qapp: QApplication,
) -> None:
    page = AccountPage()
    page.show()
    page.set_signed_in(True)
    page.show_account("3f9c2a7e-0000-made-up")
    settle()
    assert page.sign_out_button.isVisible() and not page.sign_in_button.isVisible()
    assert page.delete_learning.isEnabled()
    assert "3f9c2a7e." in page.account_id.text()
    assert "0000" not in page.account_id.text()
    page.set_signed_in(False)  # signing out forgets it
    assert not page.account_id.isVisible()
    page.close()


def test_signed_in_account_offers_i_have_a_code(qapp: QApplication) -> None:
    """polyglotic-hq 185: the code from a Plus email goes onto this account."""
    page = AccountPage()
    assert page.have_code_button.isHidden()  # signed out: Sign in takes any code
    page.set_signed_in(True)
    assert not page.have_code_button.isHidden()
    assert page.have_code_button.text() == "I have a code"


def test_accounts_buttons_run_the_commands_main_connects(qapp: QApplication) -> None:
    page = AccountPage()
    ran: list[str] = []
    for action in (page.sign_in, page.your_data, page.delete_learning):
        action.triggered.connect(lambda _=False, a=action: ran.append(a.objectName()))
    page.set_signed_in(True)
    report = QAction("Report a problem…")
    report.setObjectName("feedback.problem")
    report.triggered.connect(lambda: ran.append("report"))
    page.add_feedback(report)
    for name in ("account.your_data", "account.delete_learning", "feedback.problem"):
        button = page.findChild(QPushButton, name)
        assert button is not None, name
        button.click()
    assert ran == ["account.your_data", "account.delete_learning", "report"]


def test_accounts_items_that_open_a_dialog_end_in_one_ellipsis(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 228 (224's finding 8): "Delete learning data..." used
    three dots where the app's other items ("Report a problem…", "Save
    transcript as…") use the one character."""
    page = AccountPage()
    page.set_signed_in(True)
    texts = [button.text() for button in page.findChildren(QPushButton)]
    assert "Delete learning data…" in texts
    assert not [text for text in texts if text.endswith("...")]


def opened_by(
    page: QWidget, names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """The addresses `page`'s buttons named `names` open, in order."""
    opened: list[str] = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    for name in names:
        button = page.findChild(QPushButton, name)
        assert button is not None, name
        button.click()
    return opened


def test_account_opens_the_privacy_notice_and_the_tester_agreement(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 185: in the browser, never inside the app."""
    names = ("account.privacy_notice", "account.tester_agreement")
    assert opened_by(AccountPage(), names, monkeypatch) == [
        PRIVACY_NOTICE,
        TESTER_AGREEMENT,
    ]


# -- Settings --------------------------------------------------------------------------


PAGES: list[SettingsPage] = []
"""Settings pages made, deleted after their test (`settings_deleted`)."""


@pytest.fixture(autouse=True)
def settings_deleted() -> Iterator[None]:
    """A Settings page deleted at the end of its test, its caption panels
    with it - not left to the interpreter's exit, where panels still bound to
    their views crashed Linux's run now and then (261)."""
    yield
    while PAGES:
        page = PAGES.pop()
        if shiboken6.isValid(page):
            page.close()
            shiboken6.delete(page)


def settings_page() -> tuple[SettingsPage, dict[str, QAction]]:
    hotkeys = {"L": QAction("Lock overlays"), "P": QAction("Pause captions")}
    hotkeys["L"].setShortcut(QKeySequence("Ctrl+Alt+L"))
    page = SettingsPage(
        [("margin", "Margin"), ("glaze", "Glaze"), ("signal", "Signal")],
        hotkeys,
        QAction("Tell us"),
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
    )
    PAGES.append(page)
    return page, hotkeys


def test_settings_say_the_theme_and_ask_for_a_change(qapp: QApplication) -> None:
    page, _keys = settings_page()
    page.show_theme("glaze", "light")
    assert page.theme.value() == "glaze" and page.window_theme.value() == "light"
    chosen: list[str] = []
    page.theme_chosen.connect(chosen.append)
    page.window_theme_chosen.connect(chosen.append)
    page.theme.choose("signal")
    page.window_theme.choose("system")
    assert chosen == ["signal", "system"]


def test_settings_show_the_hotkeys_the_version_and_the_notices(
    qapp: QApplication,
) -> None:
    page, _keys = settings_page()
    page.show_section("app")
    page.show()
    settle()
    assert page.hotkey_values["L"].text() == LOCK_KEYS
    assert page.hotkey_values["P"].text() == "another program has it"
    assert not page.version.isVisible() and not page.notices.isVisible()
    page.set_version("0.4.0", "win-x64-alpha")
    page.set_notices("notices")
    assert page.version.isVisible() and "win-x64-alpha" in page.version.text()
    assert page.notices.isVisible()
    asked: list[str] = []
    page.check_for_updates.connect(lambda: asked.append("updates"))
    page.update_now.click()
    assert asked == ["updates"]
    page.close()


def test_the_hotkeys_are_written_in_the_apps_language(qapp: QApplication) -> None:
    """In German, Settings > App says "Strg+Alt+L", as Home's Lock all and
    the dictation card do - not Qt's portable "Ctrl+Alt+L" (polyglotic-hq
    300: the German walk showed both on one page)."""
    from PySide6.QtCore import QTranslator

    from polyglotic_desktop.ui import interface_language

    german = QTranslator()
    if not german.load(str(interface_language._qts_own("de"))):
        pytest.skip("no Qt translation of its own words for German here")
    qapp.installTranslator(german)
    try:
        native = QKeySequence("Ctrl+Alt+L").toString(
            QKeySequence.SequenceFormat.NativeText
        )
        if "Strg" not in native:
            pytest.skip("Qt's German doesn't name Ctrl here")
        page, _keys = settings_page()
        page.show_section("app")
        page.show()
        settle()
        assert page.hotkey_values["L"].text() == native
        assert "Strg" in page.hotkey_values["L"].text()
        page.close()
    finally:
        qapp.removeTranslator(german)


def test_the_store_copy_says_the_store_keeps_it_up_to_date(qapp: QApplication) -> None:
    """The Microsoft Store's copy (decision 0056): the Store updates it, so
    the version says so, and there's no Check now."""
    page, _keys = settings_page()
    page.show_section("app")  # where the version is (261)
    page.show()
    settle()
    page.set_version("0.4.0", "win-x64-alpha", store=True)
    assert "0.4.0" in page.version.text()
    assert "Microsoft Store" in page.version.text()
    assert "win-x64-alpha" not in page.version.text()
    assert not page.update_now.isVisible()
    page.set_version("0.4.0", "win-x64-alpha")  # our installer's copy
    assert page.update_now.isVisible()
    page.close()


def test_the_first_run_questions_again_are_split_where_each_belongs(
    qapp: QApplication,
) -> None:
    """Settings' "Ask me the first-run questions again" asked the level and
    what's shared, one after the other (polyglotic-hq 248's 1.4, 262): the
    level is Learning's, on the language in use's card; what's shared is
    Account's. Settings asks neither."""
    page, _keys = settings_page()
    assert not hasattr(page, "ask_again") and not hasattr(page, "first_run_again")
    texts = [b.text() for b in page.findChildren(QPushButton)]
    assert "Ask me the first-run questions again" not in texts
    page.close()
    learning = LearningPage()
    languages = LearningLanguages("zh")
    card = LanguageCard(
        "zh", Tier.FULL, main=True, running=True, level=LevelLine(False)
    )
    learning.show_learning(languages, (card,), WordIntroductions.A_FEW, "zh")
    wanted: list[str] = []
    learning.change_level_wanted.connect(lambda: wanted.append("level"))
    (shown,) = learning.cards
    assert shown.change_level is not None
    shown.change_level.click()
    account = AccountPage()
    account.your_data.triggered.connect(lambda: wanted.append("share"))
    account.set_signed_in(True)
    account.your_data.trigger()
    assert wanted == ["level", "share"]
    for made in (learning, account):  # not left to the interpreter's exit
        shiboken6.delete(made)


def test_settings_speak_of_the_caption_windows(qapp: QApplication) -> None:
    page, _keys = settings_page()
    words = " ".join(texts(page))
    assert "caption windows stay as they are" in words
    assert "Lock all caption windows" in words  # not today's "Lock overlays"
    assert "Pause captions" in words
    assert "overlay" not in words.lower()


# -- Help ------------------------------------------------------------------------------


def facts_with(quiet: bool) -> Facts:
    now = time.monotonic()
    last = now - 60 if quiet else now - 1
    return Facts(
        now=now,
        connection="listening",
        paused=False,
        overlays_hidden=False,
        ticked=[Ticked(APP, "Video Player", "app")],
        activity={APP: SourceActivity(now - 300, now - 200, last, last)},
        last_caption=last,
    )


def test_help_runs_the_check_and_says_the_fix(qapp: QApplication) -> None:
    quiet = True
    page = HelpPage(lambda: facts_with(quiet))
    page.show()
    settle()
    assert page.rows[Step.TICKED].text().endswith("Video Player is added on Home")
    assert "quiet" in page.rows[Step.SOUND].text()
    assert page.fixes[Step.SOUND].isVisible()
    quiet = False
    page.check_again.click()
    assert page.marks[Step.SOUND].text() == "✓"
    assert not page.fixes[Step.SOUND].isVisible()
    reports: list[str] = []
    page.report_wanted.connect(reports.append)
    page.report.click()
    assert reports and "Video Player" not in reports[0]  # ticks and crosses only
    page.close()


def test_help_speaks_of_caption_windows_home_and_words(qapp: QApplication) -> None:
    """The glossary's words (DOMAIN.md): no overlays, no Audio, Languages,
    Captions or Vocabulary pages - they're Home, the caption windows' own
    settings and Words now."""
    page = HelpPage(lambda: facts_with(True))
    every = [
        text for pair in help_page.set_up() + help_page.questions() for text in pair
    ]
    every += [t for p in Problem for t in help_page.problem(p, "Video Player")]
    every += texts(page)
    joined = " ".join(every)
    # Home has no tick boxes: an app is added with "+" (135, 2026-11-07);
    # "Captions >" was the old page, Settings > Captions is today's (261)
    without = joined.replace("Settings > Captions >", "")
    for old in ("overlay", "on Audio", "Vocabulary", "Captions >", "on Languages"):
        assert old not in without, old
    for old in ("ticked", "tick an app", "tick up to", "you tick", "tick the app"):
        assert old not in joined, old
    assert "Home" in joined and "Words" in joined and "caption window" in joined
    # the gamer, the Anki user and anyone's first lookup have a topic (135)
    titles = [title for title, _ in help_page.set_up() + help_page.questions()]
    assert "Over a game" in titles
    assert "Look up a word, and keep it" in titles
    assert "Put your words into Anki" in titles
    assert "Caption one app, and everything else apart" in titles  # 139


def test_help_points_to_where_each_setting_is_now(qapp: QApplication) -> None:
    """Names and slang and the timing moved from Home's panels to Settings >
    Captions (261), then to sections of their own, Speech and Timing (304),
    and dictation to Dictation; a caption window has no Position since 249:
    Help sends the learner there, and those places are where Help says
    (262's finding: it still said "in Languages on Home")."""
    every = dict(help_page.set_up() + help_page.questions())
    joined = " ".join(every.values())
    gone = ("Languages on Home", "Timing on Home", "Position in its settings")
    for each in (*gone, "Settings > Captions", "Settings > App"):
        assert each not in joined, each
    assert "Settings > Speech" in every["Why is a line wrong?"]
    assert "Names and slang" in every["Why is a line wrong?"]
    assert "Settings > Timing" in every["When do captions appear?"]
    _, dictation = help_page.dictation_topic("Right Ctrl")
    assert dictation.count("Settings > Dictation") == 2
    page, _keys = settings_page()
    assert page.speech.title is not None and page.speech.title.text() == "Speech"
    assert "Names and slang" in texts(page.speech)
    assert page.section["speech"].isAncestorOf(page.speech)
    assert page.timing.title is not None and page.timing.title.text() == "Timing"
    assert page.section["timing"].isAncestorOf(page.timing)
    assert page.section["dictation"].isAncestorOf(page.dictation_key)


def test_help_says_what_the_privacy_notice_v2_says_and_links_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 185: "What we keep" as the notice v2 has it - only
    speech leaves the PC; 2 minutes of finished speech held in memory (not
    30 s), sent again only when asked ("Looks wrong?", which did, went in
    339) - and the notice and the tester agreement a click away."""
    [kept] = [text for title, text in help_page.questions() if title == "What we keep"]
    for words in (
        pc_or_mac("Only speech leaves this PC", "Only speech leaves this Mac"),
        "never stores the audio",
        "last 2 minutes",
        "sends it again only when you ask",
        "never the sentence around them",
    ):
        assert words in kept, words
    assert "Looks wrong" not in kept
    assert "crash reports" not in kept  # the notice v2: none are sent yet
    # a transcript lasts only this session: not "stays ... unless" (228)
    assert "it's gone when you quit Polyglotic unless you save it" in kept
    assert "transcript stays on this" not in kept
    names = ("help.privacy_notice", "help.tester_agreement")
    page = HelpPage(lambda: facts_with(True))
    assert opened_by(page, names, monkeypatch) == [PRIVACY_NOTICE, TESTER_AGREEMENT]


def test_a_help_topic_opens_and_closes(qapp: QApplication) -> None:
    topic = Topic("What we keep", "Speech is sent to our server.")
    topic.show()
    assert topic.text.isHidden() and topic.title.text().startswith("▸")
    topic.title.click()
    assert not topic.text.isHidden() and topic.title.text().startswith("▾")
    topic.title.click()
    assert topic.text.isHidden()
    topic.close()


def test_help_says_how_to_dictate_with_the_key_chosen(
    qapp: QApplication, pc: None
) -> None:
    """polyglotic-hq 289: Help's dictation topic names the key - in a PC's
    words, whatever this machine is (a Mac names it "Right ⌘": 429; 443)."""
    page = HelpPage(lambda: facts_with(True))
    try:
        assert page.dictation.name == "Dictate into any program (preview)"
        assert "Hold Right Ctrl and speak" in page.dictation.text.text()
        page.show_dictation_key("Ctrl + Alt + D")
        assert "Hold Ctrl + Alt + D and speak" in page.dictation.text.text()
    finally:
        shiboken6.delete(page)


@pytest.fixture
def pc(monkeypatch: pytest.MonkeyPatch) -> None:
    """The key's words and the box as on a PC, whatever this machine is
    (a Mac's: `test_dictation_key_on_a_mac`)."""
    monkeypatch.setattr(os_words, "on_a_mac", lambda: False)


def test_settings_turn_dictation_on_choose_its_key_and_language(
    qapp: QApplication, pc: None
) -> None:
    """Dictation's card (polyglotic-hq 283): off until turned on; each change
    asked for as the settings name it; a key another program has said."""
    page, _keys = settings_page()
    page.show_section("dictation")
    page.show()
    settle()
    assert not page.dictation_on.switch.isChecked()
    assert page.dictation_key.text() == "Right Ctrl"  # polyglotic-hq 289
    assert page.dictation_on.detail.text().startswith("Hold Right Ctrl and speak")
    assert page.dictation_language.currentData() == ""  # Detect
    assert page.dictation_key_note.isHidden()
    asked: list[dict[str, object]] = []
    page.dictation_changes.connect(asked.append)
    page.dictation_on.switch.click()
    page.dictation_language.setCurrentIndex(page.dictation_language.findData("zh"))
    page.dictation_language.activated.emit(page.dictation_language.currentIndex())
    page.dictation_australian.switch.click()
    assert asked == [
        {"dictation": True},
        {"dictation_language": "zh"},
        {"dictation_australian": True},
    ]
    page.show_dictation(True, "pause", None, False, taken=True)
    assert page.dictation_key.text() == "Pause"
    assert page.dictation_on.detail.text().startswith("Hold Pause and speak")
    assert page.dictation_language.currentData() == ""
    assert not page.dictation_australian.switch.isChecked()
    assert (
        page.dictation_key_note.text() == "Another program has Pause: choose another."
    )
    assert len(asked) == 3  # shown quietly: nothing asked again
    page.show_dictation(True, "pause", None, False, taken=False)
    assert page.dictation_key_note.isHidden()
    page.close()


def press(box: QWidget, key: Qt.Key, scan: int = 0, vk: int = 0) -> None:
    """A key going down and up in the box, as Qt would hand it over: no
    key is pressed on the PC."""
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(
            box, QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier, scan, vk, 0)
        )


def key_event(kind: QEvent.Type, key: Qt.Key, scan: int = 0, vk: int = 0) -> QKeyEvent:
    return QKeyEvent(kind, key, Qt.KeyboardModifier.NoModifier, scan, vk, 0)


def test_settings_say_when_the_os_doesnt_let_dictation_type(
    qapp: QApplication,
) -> None:
    """polyglotic-hq 438: a Mac without the Accessibility permission -
    Settings > Dictation says why nothing is typed and where to allow it,
    with a way to System Settings; asked again each time it shows, so it
    goes once the learner has given it. Windows asks nothing: never shown."""
    page, _keys = settings_page()
    page.show_section("dictation")
    page.show()
    settle()
    assert not page.typing_not_allowed.isVisible()  # no permission asked here
    allowed = [False]
    page.typing_allowed = lambda: allowed[0]
    page.hide()
    page.show()
    settle()
    assert page.typing_not_allowed.isVisible()
    words = " ".join(texts(page.typing_not_allowed))
    assert "Privacy & Security" in words and "Accessibility" in words
    opened: list[bool] = []
    page.typing_settings_wanted.connect(lambda: opened.append(True))
    page.typing_settings.click()
    assert opened == [True]
    allowed[0] = True  # given in System Settings meanwhile
    page.hide()
    page.show()
    settle()
    assert not page.typing_not_allowed.isVisible()
    allowed[0] = False  # taken away: dictation's sign says so, then Settings
    page.show_typing_permission()
    assert page.typing_not_allowed.isVisible()


def test_settings_dictation_key_is_pressed_in_a_box(
    qapp: QApplication, pc: None
) -> None:
    """polyglotic-hq 289: click the key, press the one you want - taken if
    nothing refuses it, refused with why if something does, Reset back to
    Right Ctrl; the dictation key let go meanwhile."""
    page, _keys = settings_page()
    page.show_section("dictation")
    page.show()
    settle()
    wanted: list[str] = []
    listening: list[bool] = []
    page.dictation_key_wanted.connect(wanted.append)
    page.dictation_key_listening.connect(listening.append)
    box = page.dictation_key

    def down(key: Qt.Key, scan: int = 0, vk: int = 0) -> None:
        QApplication.sendEvent(box, key_event(QEvent.Type.KeyPress, key, scan, vk))

    def up(key: Qt.Key, scan: int = 0, vk: int = 0) -> None:
        QApplication.sendEvent(box, key_event(QEvent.Type.KeyRelease, key, scan, vk))

    # Ctrl + Alt + D
    box.click()
    assert box.listening and listening == [True]
    assert box.text().startswith("Press a key or combination")
    down(Qt.Key.Key_Control, 0x1D)
    down(Qt.Key.Key_Alt, 0x38)
    down(Qt.Key.Key_D, 0x20, 0x44)
    assert not box.listening and listening == [True, False]
    assert wanted == ["ctrl+alt+d"]
    up(Qt.Key.Key_D)  # what's let go after isn't another key
    up(Qt.Key.Key_Alt)
    up(Qt.Key.Key_Control)
    assert wanted == ["ctrl+alt+d"]

    # Right Ctrl alone, by its side: down and up with nothing between
    page.show_dictation(True, "ctrl+alt+d", None, False)
    assert box.text() == "Ctrl + Alt + D"
    box.click()
    down(Qt.Key.Key_Control, 0x11D)
    up(Qt.Key.Key_Control, 0x11D)
    assert wanted[-1] == "right_ctrl"

    # a key that types: refused, said why, nothing asked
    box.click()
    press(box, Qt.Key.Key_A, 0x1E, 0x41)
    assert wanted == ["ctrl+alt+d", "right_ctrl"]
    assert page.dictation_key_note.text() == (
        "That key types. Hold it with Ctrl, Alt or Win, or choose another."
    )
    # one of the app's own hotkeys (Settings > App lists them)
    box.click()
    down(Qt.Key.Key_Control, 0x1D)
    down(Qt.Key.Key_Alt, 0x38)
    down(Qt.Key.Key_L, 0x26, 0x4C)
    assert page.dictation_key_note.text() == (
        "That's one of Polyglotic's own hotkeys: choose another."
    )
    up(Qt.Key.Key_Alt)
    up(Qt.Key.Key_Control)
    # Left Shift alone
    box.click()
    down(Qt.Key.Key_Shift, 0x2A)
    up(Qt.Key.Key_Shift, 0x2A)
    assert "only Right Ctrl or Ctrl + Win work" in page.dictation_key_note.text()
    # a key dictation can't be held on
    box.click()
    press(box, Qt.Key.Key_Semicolon, 0x27, 0xBA)
    assert page.dictation_key_note.text() == (
        "Polyglotic can't use that key: choose another."
    )
    # Esc stops listening; nothing asked, the note left as it was
    box.click()
    press(box, Qt.Key.Key_Escape, 0x01, 0x1B)
    assert not box.listening and box.text() == "Ctrl + Alt + D"
    assert wanted == ["ctrl+alt+d", "right_ctrl"]
    # F9, a key on its own, clears the note
    box.click()
    press(box, Qt.Key.Key_F9, 0x43, 0x78)
    assert wanted[-1] == "f9" and page.dictation_key_note.isHidden()

    # another program has it: the one before kept, and said so
    page.dictation_key_not_taken("f9")
    assert page.dictation_key_note.text() == (
        "Another program has F9: kept Ctrl + Alt + D."
    )
    # Reset: back to Right Ctrl
    assert page.dictation_key_reset.isEnabled()
    page.dictation_key_reset.click()
    assert wanted[-1] == "right_ctrl"
    page.show_dictation(True, "right_ctrl", None, False)
    assert not page.dictation_key_reset.isEnabled()  # it's Right Ctrl already
    page.close()


def test_the_dictation_key_box_takes_tab_and_stops_when_left(
    qapp: QApplication,
) -> None:
    page, _keys = settings_page()
    page.show_section("dictation")
    page.show()
    settle()
    wanted: list[str] = []
    page.dictation_key_wanted.connect(wanted.append)
    box = page.dictation_key
    box.click()
    QApplication.sendEvent(
        box,
        QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier
        ),
    )
    # caught by the box, not moving the focus; no Ctrl went down in it: Tab
    assert not box.listening and wanted == []
    assert page.dictation_key_note.text().startswith("That key types")
    box.click()
    QApplication.sendEvent(box, QFocusEvent(QEvent.Type.FocusOut))
    assert not box.listening
    listening: list[bool] = []
    page.dictation_key_listening.connect(listening.append)
    box.click()
    page.show_section("look")  # its section hidden: it stops listening
    assert not box.listening and listening == [True, False]
    page.close()


def test_the_check_lines_words_start_in_one_column(qapp: QApplication) -> None:
    """✓ ✗ and – are each a different width: as the first characters of a
    line's own text they started its words 2 to 4 px apart from row to row
    (polyglotic-hq 376, 403). The mark has a column of its own."""
    page = HelpPage(lambda: facts_with(True))
    page.resize(760, 600)
    page.show()
    settle()
    marks = {page.marks[step].text() for step in Step}
    assert len(marks) >= 2  # more than one mark on show
    starts = {page.rows[step].mapTo(page, QPoint(0, 0)).x() for step in Step}
    assert len(starts) == 1
    (start,) = starts
    for step in Step:
        assert page.marks[step].geometry().right() < page.rows[step].geometry().left()
        if not page.fixes[step].isHidden():  # under the words, not the mark
            assert page.fixes[step].mapTo(page, QPoint(0, 0)).x() == start
        assert page.rows[step].accessibleName().startswith(page.marks[step].text())
    # (the autouse fixture deletes the page)


def test_help_names_only_the_hotkeys_that_work(qapp: QApplication) -> None:
    """polyglotic-hq 400 (found by 398): Help's Set up and its check said
    "Lock all (Ctrl+Alt+L)", "press Ctrl+Alt+P" and "Press Ctrl+Alt+H" in a
    build whose hotkeys did nothing (398's preview build registers none);
    now only the hotkeys that work are named - all or none in a passage."""
    now = time.monotonic()
    speech = {APP: SourceActivity(now - 300, now - 200, now - 1, now - 20)}
    no_captions = replace(facts_with(False), activity=speech, last_caption=None)
    paused = replace(no_captions, paused=True)
    hidden = replace(no_captions, overlays_hidden=True)
    facts = [paused]
    page = HelpPage(lambda: facts[0])
    page.show()
    settle()

    def said() -> str:
        topics = " ".join(t.text.text() for t in page.findChildren(Topic))
        return topics + " " + " ".join(f.text() for f in page.fixes.values())

    assert keys("Ctrl+Alt+L") in said() and keys("Ctrl+Alt+P") in said()
    page.show_hotkeys([])  # none works
    assert keys("Ctrl+Alt+L")[:-1] not in said(), said()
    assert "Lock all, on Home or in the tray menu, lets clicks pass" in said()
    assert "Choose Resume on Home or in the tray menu." in said()
    facts[0] = hidden
    page.check_again.click()
    assert keys("Ctrl+Alt+L")[:-1] not in said(), said()
    assert "Use Hide all on Home or the tray menu." in said()

    page.show_hotkeys(["L", "H"])  # Pause captions' is another app's
    assert keys("Ctrl+Alt+P") not in said()
    assert keys("Lock all (Ctrl+Alt+L) so clicks go") in said()  # Over a game
    assert keys("Press Ctrl+Alt+H") in said()
    every = {t for p in Problem for t in help_page.problem(p, "Video Player", ())}
    every |= {t for pair in help_page.set_up(()) for t in pair}
    assert not any(keys("Ctrl+Alt+L")[:-1] in text for text in every)
    page.close()
    page.deleteLater()


def test_dictation_key_on_a_mac(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """polyglotic-hq 429: on a Mac the key is named as its menus write it
    (Qt's Ctrl is Command, its Meta Control: "right_ctrl" is Right ⌘), the
    box reads a Mac's key codes (Tab is 0x30, which is "0" on Windows), and
    a refusal names a Mac's keys."""
    monkeypatch.setattr(os_words, "on_a_mac", lambda: True)
    assert key_words("right_ctrl") == "Right ⌘"
    assert key_words("ctrl+win+d") == "⌃⌘D"
    assert key_words("ctrl+alt+shift+f9") == "⌥⇧⌘F9"
    page, _keys = settings_page()
    page.show_section("dictation")
    page.show()
    settle()
    assert page.dictation_key.text() == "Right ⌘"
    page.show_dictation(True, "f9", None, False)  # so Right ⌘ is a change
    wanted: list[str] = []
    page.dictation_key_wanted.connect(wanted.append)
    box = page.dictation_key

    def down(key: Qt.Key, vk: int) -> None:
        QApplication.sendEvent(box, key_event(QEvent.Type.KeyPress, key, 0, vk))

    def up(key: Qt.Key, vk: int) -> None:
        QApplication.sendEvent(box, key_event(QEvent.Type.KeyRelease, key, 0, vk))

    box.click()  # Right Command alone
    down(Qt.Key.Key_Control, 0x36)
    up(Qt.Key.Key_Control, 0x36)
    assert wanted == ["right_ctrl"]
    box.click()  # Control + Command + D
    down(Qt.Key.Key_Meta, 0x3B)
    down(Qt.Key.Key_Control, 0x37)
    down(Qt.Key.Key_D, 0x02)
    assert wanted[-1] == "ctrl+win+d"
    up(Qt.Key.Key_D, 0x02)
    up(Qt.Key.Key_Control, 0x37)
    up(Qt.Key.Key_Meta, 0x3B)
    box.click()  # Left Command alone: refused, said with a Mac's keys
    down(Qt.Key.Key_Control, 0x37)
    up(Qt.Key.Key_Control, 0x37)
    assert page.dictation_key_note.text() == (
        "On their own, only Right ⌘ or ⌃⌘ work: hold ⌘, ⌥ or ⇧ with a key."
    )
    box.click()  # Tab: a key that types, not the digit 0
    press(box, Qt.Key.Key_Tab, 0, 0x30)
    assert page.dictation_key_note.text() == (
        "That key types. Hold it with ⌘ or ⌃, or choose another."
    )
    assert wanted == ["right_ctrl", "ctrl+win+d"]
    # ⌃⌘L, the Mac's Lock hotkey (polyglotic-hq 428, 438): one of the app's
    # own - not "another program has it" once the OS refuses it
    box.click()
    down(Qt.Key.Key_Meta, 0x3B)
    down(Qt.Key.Key_Control, 0x37)
    down(Qt.Key.Key_L, 0x25)
    assert page.dictation_key_note.text() == (
        "That's one of Polyglotic's own hotkeys: choose another."
    )
    assert wanted == ["right_ctrl", "ctrl+win+d"]
    up(Qt.Key.Key_L, 0x25)
    up(Qt.Key.Key_Control, 0x37)
    up(Qt.Key.Key_Meta, 0x3B)
    # ⌥⌘L is Windows' combination, not the Mac's hotkey: free to take
    box.click()
    down(Qt.Key.Key_Alt, 0x3A)
    down(Qt.Key.Key_Control, 0x37)
    down(Qt.Key.Key_L, 0x25)
    assert wanted[-1] == "ctrl+alt+l"
    up(Qt.Key.Key_L, 0x25)
    up(Qt.Key.Key_Control, 0x37)
    up(Qt.Key.Key_Alt, 0x3A)
    page.close()
