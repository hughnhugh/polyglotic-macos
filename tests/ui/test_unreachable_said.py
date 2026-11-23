"""Home, the caption windows and the tray say why the server can't be reached (polyglotic-hq 251).

The user, 2026-11-08: "if you cannot connect to server for whatever reason
... it should notify the user". Every cause read "Reconnecting - trying
again in 8 s". Now each says what's wrong, whose side it's on and what to
do - from the session's status through `main`'s wiring to Home's state
line, the caption windows' notice line and the tray's tooltip - and keeps
saying it through each try. Made-up apps only, offscreen.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication
from tests.stopped_clock import AFTER_MIDNIGHT_IN_MELBOURNE, qt_stopped_at
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.connection.session import SessionState, Status
from polyglotic_desktop.core.listening.check import Problem, Step
from polyglotic_desktop.core.listening.sources import MIC, SourceId
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.main import (
    Hub,
    Panels,
    QtListener,
    unreachable_shown,
    window_notice,
    wire_caption_windows,
)
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui_next import home as home_page
from polyglotic_desktop.ui_next.caption_window import notice_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.help_page import HelpPage
from polyglotic_desktop.ui_next.os_words import pc_mac_or_linux, pc_or_mac
from polyglotic_desktop.ui_next.views.caption_window import Notice, Notices
from polyglotic_desktop.ui_next.views.home import (
    HomeState,
    ListeningState,
    Title,
    Tone,
    state_line,
)
from polyglotic_desktop.ui_next.views.placement import Rect

APP_1 = SourceId("app-1")


@pytest.fixture
def hub(qapp: QApplication) -> Iterator[tuple[DesktopApp, CaptionWindows, Hub]]:
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    wire_caption_windows(windows, desktop, lambda: None)
    windows.set_captioned([("Web Browser", APP_1)])
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    yield desktop, windows, built
    built.window.keep_in_tray = False
    built.window.close()
    windows.close()
    desktop.close()


def waiting(why: Unreachable | None, retry_in: float = 6.0) -> Status:
    return Status(SessionState.WAITING, retry_in=retry_in, unreachable=why)


def test_the_server_down_said_on_home_the_windows_and_the_tray(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    listener = QtListener(desktop, None)
    listener._show_status(waiting(Unreachable.DOWN))
    home = built.home.state
    # what it knows (368): can't reach it, not the learner's internet
    assert home.title_label.text() == "Can't reach Polyglotic's server"
    assert home.detail.text() == (
        "not your internet - the problem is ours. Captions come back by "
        "themselves · trying again in 6 s"
    )
    window = windows.windows["Web Browser"]
    window._tick()
    assert window.notice.text() == (
        "Can't reach Polyglotic's server - trying again in 6 s"
    )
    assert desktop.state_title == "Can't reach Polyglotic's server"  # the tray's
    assert home.notice.isHidden()  # the banner's order is untouched (208)
    # the site's status page, from outside the app (540, 563)
    assert home.status_page.isVisibleTo(built.home)
    assert home.status_page.text() == "Server status"
    assert home.status_page.property("url") == "https://polyglotic.io/status/"
    # each try keeps the reason, as "Reconnecting" was kept (133)
    listener._show_status(Status(SessionState.CONNECTING))
    assert home.title_label.text() == "Can't reach Polyglotic's server"
    assert desktop.unreachable is Unreachable.DOWN
    # back: listening, and nothing more about it
    listener._show_status(Status(SessionState.LISTENING))
    assert home.title_label.text() == "Listening"
    assert desktop.unreachable is None
    assert not home.status_page.isVisibleTo(built.home)
    window._tick()
    assert window.notice.isHidden()  # nothing to say


def test_no_internet_says_to_check_it_and_that_it_may_be_us(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """The brief's words: whose side, and what to do."""
    desktop, _, built = hub
    QtListener(desktop, None)._show_status(waiting(Unreachable.NO_ANSWER, 20.0))
    home = built.home.state
    assert home.title_label.text() == "Can't reach Polyglotic's server"
    assert home.detail.text() == (
        "check your internet; if it's working, we're probably down · "
        "trying again in 20 s"
    )


def test_what_the_learner_can_fix_says_see_home_on_the_windows(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    QtListener(desktop, None)._show_status(waiting(Unreachable.CLOCK))
    assert built.home.state.title_label.text() == pc_or_mac(
        "Check this PC's date and time", "Check this Mac's date and time"
    )
    assert pc_mac_or_linux("Time & language", "Date & Time", "Date & Time") in (
        built.home.state.detail.text()
    )
    window = windows.windows["Web Browser"]
    window._tick()
    assert window.notice.text() == pc_or_mac(
        "Check this PC's date and time - see Home",
        "Check this Mac's date and time - see Home",
    )


def test_a_certificate_out_of_date_on_a_right_clock_names_an_antivirus_or_a_vpn(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """313: refused after the try without the dates, and this PC's clock
    isn't before the build - something in the way, not the clock."""
    desktop, windows, built = hub
    QtListener(desktop, None)._show_status(waiting(Unreachable.OUT_OF_DATE))
    assert built.home.state.title_label.text() == "Can't connect securely"
    assert built.home.state.detail.text().startswith(
        "something on this network is in the way with an out-of-date certificate"
        " - most often an antivirus's HTTPS scanning, or a VPN"
    )
    window = windows.windows["Web Browser"]
    window._tick()
    assert window.notice.text() == notice_text(Notice.NOT_SECURE, None)


def test_the_date_a_wrong_clock_says_is_on_home(
    hub: tuple[DesktopApp, CaptionWindows, Hub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """313: refused with the clock wrong for certain - Home says the date
    it says, and where to set it."""
    desktop, _, built = hub
    stopped_date, _ = qt_stopped_at(AFTER_MIDNIGHT_IN_MELBOURNE)
    # the app's date and the test's one: read twice, they named two days when
    # the PC's midnight fell between (polyglotic-hq 344)
    monkeypatch.setattr(home_page, "QDate", stopped_date)
    QtListener(desktop, None)._show_status(waiting(Unreachable.CLOCK))
    today = QLocale().toString(
        stopped_date.currentDate(), QLocale.FormatType.LongFormat
    )
    assert built.home.state.detail.text().startswith(
        pc_mac_or_linux(
            f"this PC says it's {today}, which can't be right. Turn on Set time"
            " automatically",
            f"this Mac says it's {today}, which can't be right. Turn on Set time"
            " and date automatically",
            f"this PC says it's {today}, which can't be right. Turn on automatic"
            " date and time",  # 571
        )
    )


def test_a_clock_that_looks_wrong_is_on_homes_banner_while_captions_work(
    hub: tuple[DesktopApp, CaptionWindows, Hub], monkeypatch: pytest.MonkeyPatch
) -> None:
    """313: let through on this PC's clock - listening, and one quiet line
    on Home's banner with what the clock says; gone once a session opens
    without it."""
    desktop, _, built = hub
    listener = QtListener(desktop, None)
    doubted: list[bool] = []
    listener.clock_doubted.connect(doubted.append)
    listener._show_status(Status(SessionState.LISTENING, clock_looks_wrong=True))
    listener._show_status(Status(SessionState.WAITING, retry_in=5.0))
    listener._show_status(Status(SessionState.LISTENING))
    assert doubted == [True, False]  # said by each session's `welcome`
    home = built.home.state
    stopped_date, stopped_time = qt_stopped_at(AFTER_MIDNIGHT_IN_MELBOURNE)
    monkeypatch.setattr(home_page, "QDateTime", stopped_time)  # read once (344)
    home.set_clock_looks_wrong(True)
    today = QLocale().toString(
        stopped_date.currentDate(), QLocale.FormatType.LongFormat
    )
    assert home.notice.text().startswith(
        pc_or_mac("This PC's", "This Mac's")
        + f" date or time looks wrong: it says {today}, "
    )
    assert "Captions work" in home.notice.text()
    assert not home.notice.isHidden()
    home.set_clock_looks_wrong(False)
    assert home.notice.isHidden()


def test_a_restart_on_the_state_line_takes_the_banners_place(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """The banner said "The server is restarting" for two minutes while the
    state line said "Reconnecting"; now the state line says it, once."""
    desktop, _, built = hub
    desktop.show_notice("server_restarting")
    assert built.home.state.notice.text().startswith("The server is restarting")
    QtListener(desktop, None)._show_status(waiting(Unreachable.RESTARTING))
    assert built.home.state.title_label.text() == "Polyglotic's server is restarting"
    assert built.home.state.notice.isHidden()


def test_a_full_server_and_a_plain_drop_say_what_they_said() -> None:
    busy = Status(SessionState.WAITING, retry_in=30.0, server_busy=True)
    assert unreachable_shown(busy) is None
    dropped = waiting(None)
    assert unreachable_shown(dropped) is None
    assert window_notice(ConnectionState.WAITING, None) is Notice.RECONNECTING
    trying = Status(SessionState.CONNECTING)
    assert (
        unreachable_shown(trying, ConnectionState.WAITING, Unreachable.OFFLINE)
        is Unreachable.OFFLINE
    )
    assert unreachable_shown(trying, ConnectionState.NOT_CONNECTED) is None


@pytest.mark.parametrize(
    ("why", "title", "tone"),
    [
        (Unreachable.OFFLINE, Title.CANT_REACH, Tone.BAD),
        (Unreachable.NO_ANSWER, Title.CANT_REACH, Tone.WAIT),
        (Unreachable.DOWN, Title.CANT_REACH, Tone.WAIT),
        (Unreachable.RESTARTING, Title.SERVER_RESTARTING, Tone.WAIT),
        (Unreachable.SERVER_ERROR, Title.SERVER_PROBLEM, Tone.WAIT),
        (Unreachable.BLOCKED, Title.BLOCKED, Tone.BAD),
        (Unreachable.NOT_SECURE, Title.NOT_SECURE, Tone.BAD),
        (Unreachable.CLOCK, Title.CLOCK, Tone.BAD),
        (Unreachable.OUT_OF_DATE, Title.NOT_SECURE, Tone.BAD),
        (Unreachable.TOO_MANY_SESSIONS, Title.TOO_MANY_SESSIONS, Tone.BAD),
        (Unreachable.TOO_MANY_TRIES, Title.TOO_MANY_TRIES, Tone.WAIT),
    ],
)
def test_every_reason_has_its_title_tone_and_countdown(
    qapp: QApplication, why: Unreachable, title: Title, tone: Tone
) -> None:
    """The learner's side is a problem to fix (red); ours, or no telling, a
    wait (amber). It still counts down to the next try, and breathes."""
    state = HomeState(
        ListeningState.WAITING, retry_at=108.0, chosen=True, unreachable=why
    )
    line = state_line(state, 100.0)
    assert (line.title, line.tone) == (title, tone)
    assert line.details[-1][1] == 8 and line.pulse
    assert len(line.details) == 2  # what to do, then the countdown: nothing else
    # every caption window says it in its own words
    notice = window_notice(ConnectionState.WAITING, why)
    assert notice is not None and notice_text(notice, 8)
    assert notice_text(notice, None)


def test_too_many_sessions_says_what_to_do_not_reconnecting(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """It read "Reconnecting - trying again in 60 s"."""
    desktop, windows, built = hub
    QtListener(desktop, None)._show_status(waiting(Unreachable.TOO_MANY_SESSIONS, 60.0))
    home = built.home.state
    assert home.title_label.text() == (
        "Polyglotic is open on too many of your " + pc_or_mac("PCs", "computers")
    )
    assert home.detail.text().startswith("your account has as many open as it can")
    assert home.detail.text().endswith("trying again in 60 s")
    window = windows.windows["Web Browser"]
    window._tick()
    assert window.notice.text() == (
        f"Open on too many of your {pc_or_mac('PCs', 'computers')} - see Home"
    )


def test_the_windows_count_down_only_where_waiting_is_the_answer() -> None:
    notices = Notices()
    notices.retry_at = 108.0
    for counted in (
        Notice.OFFLINE,
        Notice.CANT_REACH,
        Notice.SERVER_RESTARTING,
        Notice.TOO_MANY_TRIES,
    ):
        notices.state = counted
        assert notices.retry_in(100.0) == 8
    for see_home in (
        Notice.BLOCKED,
        Notice.NOT_SECURE,
        Notice.CLOCK,
        Notice.TOO_MANY_SESSIONS,
    ):
        notices.state = see_home
        assert notices.retry_in(100.0) is None


def test_helps_check_says_why_in_homes_words(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """Help's check said "Connecting to the server..." for every cause."""
    desktop = hub[0]
    QtListener(desktop, None)._show_status(waiting(Unreachable.NO_ANSWER))
    facts = desktop.caption_facts()
    assert facts.unreachable is Unreachable.NO_ANSWER
    page = HelpPage(desktop.caption_facts)
    page.refresh()
    assert page.marks[Step.CONNECTED].text() == "✗"
    assert page.rows[Step.CONNECTED].text() == "Can't reach Polyglotic's server"
    assert page.fixes[Step.CONNECTED].text() == (
        "Check your internet; if it's working, we're probably down."
    )
    assert page.links[0].problem is Problem.SERVER_UNREACHABLE
    page.close()


def test_an_unstable_connection_isnt_said_beside_why_the_server_cant_be_reached(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """Two drops in 5 minutes put "Connection unstable - captions may come
    late" on the banner, beside "Polyglotic's server is down - not your
    internet": whose was it? It comes back once listening again, if the
    connection still hasn't held."""
    desktop, _, built = hub
    listener = QtListener(desktop, None)
    for _ in range(2):  # dropped twice: unstable
        listener._show_status(Status(SessionState.LISTENING))
        listener._show_status(waiting(None))
    banner = built.home.state.notice
    assert banner.text() == "Connection unstable - captions may come late"
    listener._show_status(waiting(Unreachable.DOWN))
    assert banner.isHidden()
    listener._show_status(Status(SessionState.LISTENING))
    assert banner.text() == "Connection unstable - captions may come late"
    assert not banner.isHidden()


@pytest.mark.parametrize("why", list(Unreachable))
def test_the_status_page_is_offered_where_the_problem_may_be_ours(
    qapp: QApplication, why: Unreachable
) -> None:
    """Polyglotic-hq 563 (540's status page): while the server may be
    down - ours, or no telling - Home offers the site's status page; not
    while this PC is offline (it won't open), its network or clock is in
    the way, or the account is refused."""
    state = HomeState(
        ListeningState.WAITING, retry_at=108.0, chosen=True, unreachable=why
    )
    offered = {
        Unreachable.NO_ANSWER,
        Unreachable.DOWN,
        Unreachable.RESTARTING,
        Unreachable.SERVER_ERROR,
        Unreachable.MAINTENANCE,
    }
    assert state_line(state, 100.0).status_page is (why in offered)
