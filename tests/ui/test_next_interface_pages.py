"""`main`'s developer switch hands the new main window the new interface's
Words, Account, Settings and Help (project 109's build step 6), wired to
today's commands: the theme to the settings, Help's report to the
feedback form, the session's sign-in state to the new Account page, Words
to the learning tools and the caption windows' lookup card. Made-up apps
and learning; offscreen."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from tests.lexicon.sample import chinese_sample
from tests.ui.fakes import FakeAppList, MemorySettingsStore, tools_for

from polyglotic_desktop.connection.session import SessionState, Status
from polyglotic_desktop.core.lexicon.chinese import ChineseDictionary
from polyglotic_desktop.core.listening.sources import MIC
from polyglotic_desktop.core.shared import Level
from polyglotic_desktop.main import Hub, Panels, QtListener
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.settings import TRANSCRIPT_LENGTHS
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.account_page import AccountPage
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.help_page import HelpPage
from polyglotic_desktop.ui_next.learning_page import LearningPage
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.transcript import TranscriptLength
from polyglotic_desktop.ui_next.words_page import WordsPage


@pytest.fixture
def hub(qapp: QApplication) -> Iterator[tuple[DesktopApp, Hub]]:
    tools = tools_for(ChineseDictionary(chinese_sample()), "hsk-2025")
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, tools, FakeAppList())
    windows = CaptionWindows(
        store, MIC, lambda: [Rect(0, 0, 1920, 1040)], learner=tools
    )
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    yield desktop, built
    built.window.keep_in_tray = False
    built.window.close()
    built.window.deleteLater()  # not left to outlive the application
    windows.close()
    desktop.close()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_the_new_pages_stand_in_for_todays(hub: tuple[DesktopApp, Hub]) -> None:
    _desktop, built = hub
    pages = built.window.pages
    assert isinstance(pages["words"], WordsPage)
    assert isinstance(pages["learning"], LearningPage)
    assert isinstance(pages["account"], AccountPage)
    assert isinstance(pages["settings"], SettingsPage)
    assert isinstance(pages["help"], HelpPage)
    assert "transcript" not in pages  # the transcripts are windows of their own
    assert [
        k for k, b in built.window.nav_buttons.items() if b.objectName() == "NavButton"
    ] == ["home", "words", "learning", "account"]  # Learning: polyglotic-hq 262
    assert (
        built.words is not None and built.words.first.card is not None
    )  # the windows' card


def test_the_theme_is_todays_setting_both_ways(hub: tuple[DesktopApp, Hub]) -> None:
    desktop, built = hub
    built.settings.theme.choose("glaze")
    built.settings.window_theme.choose("light")
    value = desktop.settings.value
    assert (value.theme, value.window_theme) == ("glaze", "light")
    desktop.settings.update(theme="signal")
    assert built.settings.theme.value() == "signal"


def test_help_reports_with_the_checks_result(hub: tuple[DesktopApp, Hub]) -> None:
    desktop, built = hub
    reports: list[str] = []
    desktop.check_report_wanted.connect(reports.append)
    built.help.report.click()
    assert len(reports) == 1


def test_the_sessions_sign_in_state_reaches_the_new_account_page(
    hub: tuple[DesktopApp, Hub],
) -> None:
    desktop, built = hub
    listener = QtListener(desktop, None, None, built.account)
    built.account.set_signed_in(True)
    listener.status_changed(
        Status(SessionState.LISTENING, account_id="3f9c2a7e-made-up")
    )
    QApplication.processEvents()
    assert "3f9c2a7e" in built.account.account_id.text()


def test_words_follows_learning(hub: tuple[DesktopApp, Hub]) -> None:
    desktop, built = hub
    assert desktop.tools is not None and built.words is not None
    built.window.show()
    built.window.go_to("words")
    QApplication.processEvents()
    assert not built.words.first.hearing.words.items
    tools = desktop.tools
    tools.vocabulary.set_level(Level("hsk-2025", 6))
    for n in range(3):
        tools.vocabulary.caption_finished(f"c{n}", tools.words_in("我的电脑"), False)
    QApplication.processEvents()
    assert built.words.first.hearing.words.items


def test_the_app_text_size_is_the_settings_both_ways_and_applies_at_once(
    hub: tuple[DesktopApp, Hub],
) -> None:
    """Settings > App > Text size (polyglotic-hq 292): chosen, it's saved
    and every window is at it at once - the main window restyled, and
    `text_size_changed` for the others; changed elsewhere, the page shows
    it. Any other change leaves it as `main` applied it at start: the hub
    follows a change of it, nothing else (the UI lab found the hub's
    first settings change putting a Largest run back to Normal)."""
    desktop, built = hub
    sizes: list[float] = []
    built.window.text_size_changed.connect(lambda: sizes.append(style.text_scale()))
    try:
        style.use_app_text_size("larger")  # as `main` applies it at start
        desktop.settings.update(theme="signal")  # another setting changed
        assert style.app_text_size() == 1.45 and sizes == []
        built.settings.text_size.choose("largest")
        assert desktop.settings.value.interface_text_size == "largest"
        assert sizes == [1.75]
        assert "font-size: 23px" in built.window.sidebar.styleSheet()  # 13 px text
        desktop.settings.update(interface_text_size="normal")  # e.g. a settings reset
        assert built.settings.text_size.value() == "normal"
        assert sizes == [1.75, 1.3]
    finally:
        style.use_app_text_size("normal")


def test_how_far_back_transcripts_go_is_the_settings_both_ways(
    hub: tuple[DesktopApp, Hub],
) -> None:
    """Settings > App > Transcripts (polyglotic-hq 334): the newest 1,000
    lines until chosen; chosen, it's saved; changed elsewhere, shown."""
    desktop, built = hub
    choice = built.settings.transcript_length
    assert choice.value() == "newest"
    choice.choose("three_hours")
    assert desktop.settings.value.transcript_length == "three_hours"
    desktop.settings.update(transcript_length="session")
    assert choice.value() == "session"
    ask = built.settings.transcript_ask.switch
    assert ask.isChecked()  # Quit asks, until "Don't ask again"
    ask.click()
    assert desktop.settings.value.transcript_ask_at_quit is False
    desktop.settings.update(transcript_ask_at_quit=True)
    assert ask.isChecked()
    assert tuple(length.value for length in TranscriptLength) == TRANSCRIPT_LENGTHS


def test_words_says_whose_words_until_the_chosen_language_starts(
    hub: tuple[DesktopApp, Hub],
) -> None:
    """polyglotic-hq 299 ("word frequency and saved words don't work for
    English"): a learner who chose English on Learning, with Chinese's
    dictionary in use until the next start, saw Chinese words on Words with
    nothing to say whose - and English captions counted nothing meanwhile.
    Words now says so; back on Chinese, nothing is said."""
    desktop, built = hub
    assert built.words is not None
    assert built.words.in_use.isHidden()
    desktop.settings.update(learning="en")
    assert not built.words.in_use.isHidden()
    assert built.words.in_use.text() == (
        "These are your Chinese words. English is used from the next time "
        "Polyglotic starts, and keeps its own words."
    )
    desktop.settings.update(learning="zh")
    assert built.words.in_use.isHidden()
