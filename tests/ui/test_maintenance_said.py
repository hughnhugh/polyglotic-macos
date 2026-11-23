"""Planned maintenance said on Home, the tray and the caption windows (polyglotic-hq 319).

Ahead, a quiet line on Home's banner in the learner's own time; the caption
windows once, five minutes before; during it, Home's title and the tray
say until when, instead of "restarting" or "down"; the window kept between
starts. Made-up apps only, offscreen.
"""

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from PySide6.QtCore import QByteArray, QDateTime, QLocale, QTime, QTimeZone
from PySide6.QtWidgets import QApplication
from tests.stopped_clock import AFTER_MIDNIGHT_IN_MELBOURNE, stopped_at
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop import main
from polyglotic_desktop.connection.session import SessionState, Status
from polyglotic_desktop.core.listening import maintenance as planned
from polyglotic_desktop.core.listening.maintenance import Maintenance
from polyglotic_desktop.core.listening.sources import MIC, SourceId
from polyglotic_desktop.core.listening.unreachable import Unreachable
from polyglotic_desktop.main import (
    Hub,
    MaintenanceSoon,
    Panels,
    QtListener,
    wire_caption_windows,
    wire_maintenance,
)
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next import home as home_page
from polyglotic_desktop.ui_next import maintenance as words
from polyglotic_desktop.ui_next.caption_window import notice_text
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import Notice
from polyglotic_desktop.ui_next.views.placement import Rect

APP_1 = SourceId("app-1")


def made_up_zone(offset_hours: float, short_name: str = "") -> QTimeZone:
    """A zone of a fixed offset, with the short name a locale would give it
    (none: "GMT+9" and the like) - no time zone database needed."""
    return QTimeZone(
        QByteArray(f"Polyglotic/Test{offset_hours:+}{short_name}".encode()),
        round(offset_hours * 3600),
        short_name,
        short_name,
        QLocale.Country.AnyCountry,
        "",
    )


MELBOURNE = made_up_zone(11, "AEDT")  # daylight saving's
NO_NAME = made_up_zone(9)
IN_UTC = QTimeZone.utc()

NOW = AFTER_MIDNIGHT_IN_MELBOURNE
"""Every clock these tests reach reads this (`stopped`)."""


@pytest.fixture(autouse=True)
def stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app's clocks - Home's, and `main`'s for a kept window - and the
    tests' own read one instant: words read from the clock twice, once by
    the app and once by the test, named another day when the PC's midnight
    fell between (2026-11-14, #622; polyglotic-hq 344)."""
    for module in (main, home_page):
        monkeypatch.setattr(module, "datetime", stopped_at(NOW))
    monkeypatch.setattr(words, "wall_clock", lambda: NOW)
    monkeypatch.setattr(words, "_held", [None])  # each test's own window


def short(hour: int, minute: int) -> str:
    return QLocale().toString(QTime(hour, minute), QLocale.FormatType.ShortFormat)


# --- the words, in a zone and across a day's end ---------------------------------


def test_ahead_today_and_tomorrow_are_the_learners_days(qapp: QApplication) -> None:
    """13:30-14:00 UTC is 00:30-01:00 on Sunday in Melbourne: at 12:00 UTC
    (23:00 on Saturday there) it's tomorrow; at 13:00 UTC (midnight), today -
    and in UTC it's today at 13:30 (ENGINEERING.md 9b's 13:30 UTC)."""
    window = Maintenance(
        datetime(2026, 11, 14, 13, 30, tzinfo=UTC),
        datetime(2026, 11, 14, 14, tzinfo=UTC),
    )
    saturday_night = datetime(2026, 11, 14, 12, tzinfo=UTC)
    assert words.banner(window, saturday_night, MELBOURNE) == (
        f"Planned maintenance tomorrow, {short(0, 30)}-{short(1, 0)} (AEDT): "
        "captions pause then, and come back by themselves."
    )
    midnight = datetime(2026, 11, 14, 13, tzinfo=UTC)
    assert words.banner(window, midnight, MELBOURNE) == (
        f"Planned maintenance today, {short(0, 30)}-{short(1, 0)} (AEDT): "
        "captions pause then, and come back by themselves."
    )
    assert words.banner(window, saturday_night, IN_UTC) == (
        f"Planned maintenance today, {short(13, 30)}-{short(14, 0)} (UTC): "
        "captions pause then, and come back by themselves."
    )


def test_a_window_over_midnight_names_the_day_it_ends(qapp: QApplication) -> None:
    window = Maintenance(
        datetime(2026, 11, 14, 12, 30, tzinfo=UTC),
        datetime(2026, 11, 14, 13, 30, tzinfo=UTC),
    )
    sunday = QLocale().dayName(7, QLocale.FormatType.LongFormat)
    assert words.soon_line(window, MELBOURNE) == (
        f"Captions pause at {short(23, 30)} for planned maintenance, until "
        f"{sunday} {short(0, 30)} (AEDT)"
    )
    during = datetime(2026, 11, 14, 12, 45, tzinfo=UTC)
    assert words.state_title(window, during, MELBOURNE) == (
        f"Planned maintenance until {sunday} {short(0, 30)} (AEDT)"
    )
    assert words.banner(window, during, MELBOURNE) == (
        f"Planned maintenance until {sunday} {short(0, 30)} (AEDT): captions "
        "pause until then, and come back by themselves."
    )


# --- whose time it is: the PC's zone, named once a line (polyglotic-hq 542) -------


@pytest.fixture
def in_australia() -> Iterator[None]:
    """The interface in Australia's English: the locale whose names for
    Melbourne's zone are "AEDT" and "AEST"."""
    before = QLocale()
    QLocale.setDefault(QLocale(QLocale.Language.English, QLocale.Country.Australia))
    try:
        yield
    finally:
        QLocale.setDefault(before)


TOMORROW_AT_SIX = Maintenance(
    datetime(2026, 11, 20, 19, tzinfo=UTC),  # 06:00-07:30 on the 21st, AEDT
    datetime(2026, 11, 20, 20, 30, tzinfo=UTC),
)


def test_every_line_with_a_time_names_the_zone_once_after_its_last_time(
    qapp: QApplication,
) -> None:
    """The user, 2026-11-20, of the 21st's notice: "display the timezone,
    use the system timezone and specify it for them to remove ambiguity"."""
    window = TOMORROW_AT_SIX
    the_day_before = datetime(2026, 11, 20, 9, tzinfo=UTC)
    during = datetime(2026, 11, 20, 19, 30, tzinfo=UTC)
    lines = [
        words.banner(window, the_day_before, MELBOURNE),
        words.soon_line(window, MELBOURNE),
        words.state_title(window, during, MELBOURNE),
        words.banner(window, during, MELBOURNE),
    ]
    six, half_past_seven = short(6, 0), short(7, 30)
    assert lines == [
        (
            f"Planned maintenance tomorrow, {six}-{half_past_seven} (AEDT): "
            "captions pause then, and come back by themselves."
        ),
        (
            f"Captions pause at {six} for planned maintenance, until "
            f"{half_past_seven} (AEDT)"
        ),
        f"Planned maintenance until {half_past_seven} (AEDT)",
        (
            f"Planned maintenance until {half_past_seven} (AEDT): captions pause "
            "until then, and come back by themselves."
        ),
    ]


def test_with_no_zone_given_its_the_pcs_own(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The app passes no zone: the lines name the PC's (Windows' own)."""
    monkeypatch.setattr(words, "pc_zone", lambda: MELBOURNE, raising=False)
    assert words.soon_line(TOMORROW_AT_SIX) == (
        f"Captions pause at {short(6, 0)} for planned maintenance, until "
        f"{short(7, 30)} (AEDT)"
    )
    assert words.state_title(TOMORROW_AT_SIX, NOW).endswith(f"{short(7, 30)} (AEDT)")


@pytest.mark.parametrize(
    ("zone", "named"),
    [
        (NO_NAME, "UTC+9"),  # the locale's only name an offset: "GMT+9"
        # the locale's name an offset, as Windows' Qt names Tokyo in
        # Australia's English (polyglotic-hq 544): its offset, as UTC's
        (made_up_zone(9, "GMT+9"), "UTC+9"),
        (QTimeZone(19800), "UTC+5:30"),  # a zone that is only an offset
        (QTimeZone(-12600), "UTC-3:30"),
        (QTimeZone(-10800), "UTC-3"),
        (made_up_zone(5.75), "UTC+5:45"),
    ],
)
def test_a_zone_the_locale_has_no_name_for_is_written_as_its_offset(
    qapp: QApplication, zone: QTimeZone, named: str
) -> None:
    assert words.zone_name(TOMORROW_AT_SIX.ends_at, zone) == named
    assert words.soon_line(TOMORROW_AT_SIX, zone).endswith(f" ({named})")


def test_utc_itself_is_utc() -> None:
    assert words.utc_offset(0) == "UTC"


def real_zone(name: str) -> QTimeZone:
    zone = QTimeZone(QByteArray(name.encode()))
    if not zone.isValid():
        pytest.skip(f"no time zone database with {name} here")
    return zone


@pytest.mark.parametrize(
    ("place", "at", "named"),
    [
        ("Australia/Melbourne", datetime(2026, 11, 20, 20, 30, tzinfo=UTC), "AEDT"),
        ("Australia/Melbourne", datetime(2026, 6, 20, 21, 30, tzinfo=UTC), "AEST"),
    ],
)
def test_the_name_is_the_one_for_that_date(
    qapp: QApplication, in_australia: None, place: str, at: datetime, named: str
) -> None:
    """Summer's and winter's names."""
    assert words.zone_name(at, real_zone(place)) == named


def test_a_real_zone_is_named_as_the_platform_names_it(
    qapp: QApplication, in_australia: None
) -> None:
    """Tokyo in Australia's English: Windows' Qt has only an offset for it
    ("GMT+9"), so "UTC+9"; Linux's has letters ("JST"), kept (polyglotic-hq
    544). The offset rule itself is above, on made-up zones that answer
    the same everywhere."""
    at = datetime(2026, 11, 20, 20, 30, tzinfo=UTC)
    tokyo = real_zone("Asia/Tokyo")
    platform = tokyo.displayName(
        QDateTime.fromMSecsSinceEpoch(round(at.timestamp() * 1000), tokyo),
        QTimeZone.NameType.ShortName,
        QLocale(),
    )
    named = words.zone_name(at, tokyo)
    assert named == (platform if platform.isalpha() else "UTC+9"), platform


SWITCHES = [
    # daylight saving ends at 03:00 AEDT: 02:30 comes twice
    (datetime(2027, 4, 3, 15, 30, tzinfo=UTC), (2, 30, "AEDT"), (2, 30, "AEST")),
    # and starts at 02:00 AEST: the clock jumps to 03:00
    (datetime(2026, 10, 3, 15, 30, tzinfo=UTC), (1, 30, "AEST"), (3, 30, "AEDT")),
]


@pytest.mark.parametrize(("starts", "start", "end"), SWITCHES)
def test_daylight_saving_switching_inside_the_window_names_both_times(
    qapp: QApplication,
    in_australia: None,
    starts: datetime,
    start: tuple[int, int, str],
    end: tuple[int, int, str],
) -> None:
    """One name after both would put one of them an hour out."""
    melbourne = real_zone("Australia/Melbourne")
    window = Maintenance(starts, starts + timedelta(hours=1))
    first = f"{short(start[0], start[1])} ({start[2]})"
    then = f"{short(end[0], end[1])} ({end[2]})"
    assert words.soon_line(window, melbourne) == (
        f"Captions pause at {first} for planned maintenance, until {then}"
    )
    the_evening_before = starts - timedelta(hours=5)
    assert words.banner(window, the_evening_before, melbourne) == (
        f"Planned maintenance tomorrow, {first}-{then}: captions pause then, and "
        "come back by themselves."
    )


def test_a_window_on_another_day_names_its_day_and_the_zone_once(
    qapp: QApplication,
) -> None:
    """Told on Friday of a window from Saturday 23:30 to Sunday 00:30:
    nothing on Friday (a day ahead at most), then today, its end's day
    named, the zone once."""
    window = Maintenance(
        datetime(2026, 11, 14, 12, 30, tzinfo=UTC),
        datetime(2026, 11, 14, 13, 30, tzinfo=UTC),
    )
    friday = datetime(2026, 11, 13, 5, tzinfo=UTC)  # 16:00 on Friday there
    assert words.banner(window, friday, MELBOURNE) is None
    saturday_morning = datetime(2026, 11, 13, 22, tzinfo=UTC)  # 09:00 Saturday
    sunday = QLocale().dayName(7, QLocale.FormatType.LongFormat)
    said = words.banner(window, saturday_morning, MELBOURNE)
    assert said == (
        f"Planned maintenance today, {short(23, 30)}-{sunday} {short(0, 30)} "
        "(AEDT): captions pause then, and come back by themselves."
    )
    assert said.count("AEDT") == 1


def test_a_pc_clock_a_day_fast_still_says_today(qapp: QApplication) -> None:
    window = Maintenance(
        datetime(2026, 11, 14, 4, tzinfo=UTC),
        datetime(2026, 11, 14, 4, 30, tzinfo=UTC),
        pc_ahead=timedelta(days=1),
    )
    pc_now = datetime(2026, 11, 15, 2, tzinfo=UTC)  # the server: 02:00 on the 14th
    banner = words.banner(window, pc_now, IN_UTC)
    assert banner is not None and banner.startswith("Planned maintenance today,")
    assert words.banner(window, datetime(2026, 11, 14, 2, tzinfo=UTC), IN_UTC) is None


# --- Home, the tray and the caption windows ----------------------------------------


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


def on_now() -> Maintenance:
    start = NOW - timedelta(minutes=5)
    return Maintenance(start, start + timedelta(minutes=35))


def test_during_it_home_and_the_tray_say_until_when_not_down(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, windows, built = hub
    window = on_now()
    built.set_maintenance(window)
    listener = QtListener(desktop, None)
    listener._show_status(
        Status(
            SessionState.WAITING, retry_in=120.0, unreachable=Unreachable.MAINTENANCE
        )
    )
    home = built.home.state
    title = home.title_label.text()
    assert title == words.state_title(window, NOW)
    assert title.startswith("Planned maintenance until ")
    until = words.clock_time(window.ends_at)
    assert title.endswith(f"{until} ({words.zone_name(window.ends_at)})")
    # never "down" (319's promise; 329's QA, 330), and no countdown to the
    # next try: it'd be noise for half an hour
    assert home.detail.text() == (
        "not your internet - captions come back by themselves when it's over"
    )
    assert "down" not in home.detail.text()
    assert desktop.state_title == title  # the tray's tooltip: "Polyglotic - ..."
    assert home.notice.isHidden()  # the state line says it: no banner beside it
    # the caption windows say until when too, in the PC's zone, named (563:
    # they said only "Planned maintenance - captions come back by themselves")
    caption = windows.windows["Web Browser"]
    caption._tick()
    assert caption.notice.text() == (
        f"Planned maintenance until {until} ({words.zone_name(window.ends_at)})"
        " - captions come back by themselves"
    )


def test_the_caption_windows_notice_names_the_zone_and_the_day_it_ends(
    qapp: QApplication, in_australia: None
) -> None:
    """The user, 2026-11-20: "use the system timezone and specify it for
    them to remove ambiguity" - the caption windows' notice too (563)."""
    words.hold(TOMORROW_AT_SIX)
    during = datetime(2026, 11, 20, 19, 30, tzinfo=UTC)
    assert words.notice_until(during, MELBOURNE) == (
        f"Planned maintenance until {short(7, 30)} (AEDT) - captions come back "
        "by themselves"
    )
    # read on the evening before (the notice is for during it): its day named
    the_day_before = datetime(2026, 11, 20, 9, tzinfo=UTC)
    saturday = QLocale().dayName(6, QLocale.FormatType.LongFormat)
    assert words.notice_until(the_day_before, MELBOURNE) == (
        f"Planned maintenance until {saturday} {short(7, 30)} (AEDT) - captions "
        "come back by themselves"
    )


def test_with_no_window_held_the_notice_says_only_that_its_planned(
    qapp: QApplication,
) -> None:
    """The server said maintenance with no window told (or it was called
    off): no time to say, as before."""
    words.hold(None)
    assert words.notice_until(NOW) is None
    assert notice_text(Notice.MAINTENANCE, None) == (
        "Planned maintenance - captions come back by themselves"
    )


def test_helps_check_says_it_as_a_sentence_never_down(qapp: QApplication) -> None:
    """Help's check words why the server can't be reached as Home does, as
    a sentence: the maintenance line too, with its full stop (330)."""
    from polyglotic_desktop.ui_next.home import unreachable_words

    title, sentence = unreachable_words(Unreachable.MAINTENANCE)
    assert title == "Planned maintenance"
    assert sentence == (
        "Not your internet - captions come back by themselves when it's over."
    )


def test_ahead_and_while_paused_the_banner_says_it_and_goes_when_cleared(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    desktop, _, built = hub
    home = built.home.state
    start = NOW + timedelta(minutes=50)
    ahead = Maintenance(start, start + timedelta(minutes=30))
    built.set_maintenance(ahead)
    assert not home.notice.isHidden()
    assert home.notice.text() == words.banner(ahead, NOW)
    assert "Planned maintenance " in home.notice.text()
    desktop.pause.setChecked(True)  # paused during it: the banner says until when
    built.set_maintenance(on_now())
    assert home.notice.text().startswith("Planned maintenance until ")
    built.set_maintenance(None)  # moved away or called off: taken down
    assert home.notice.isHidden()


def test_the_caption_windows_say_it_once_five_minutes_before(
    qapp: QApplication,
) -> None:
    said: list[str] = []
    clock = [datetime(2026, 11, 15, 3, 50, tzinfo=UTC)]
    soon = MaintenanceSoon(said.append, lambda: clock[0])
    window = Maintenance(
        datetime(2026, 11, 15, 4, tzinfo=UTC), datetime(2026, 11, 15, 4, 30, tzinfo=UTC)
    )
    soon.follow(window)
    assert said == [] and soon._timer.isActive()  # due at 03:55
    # the interval set: a coarse timer's remaining time may run over by a few %
    assert soon._timer.interval() == 300_000
    clock[0] = datetime(2026, 11, 15, 3, 56, tzinfo=UTC)
    soon.say()
    soon.say()
    soon.follow(window)  # told again (a reconnect's `welcome`): not said again
    assert said == [words.soon_line(window)]
    soon.follow(None)
    assert not soon._timer.isActive()
    soon.deleteLater()


class Held:
    """The connection's part `wire_maintenance` needs: the window it holds."""

    maintenance: Maintenance | None = None


def test_the_window_is_kept_between_starts_and_said_at_once(
    qapp: QApplication,
) -> None:
    """The app restarted (in the window, say, with the server down): the
    window kept from before is said before any session opens."""
    window = on_now()
    store = MemorySettingsStore(
        {
            "apps": ["Web Browser"],
            "targets": ["en"],
            "maintenance": planned.stored(window),
        }
    )
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    held = Held()
    listener = QtListener(desktop, None)
    try:
        wire_maintenance(held, listener, desktop, built, windows)  # type: ignore[arg-type]
        assert held.maintenance == window
        assert built.home.state.notice.text().startswith("Planned maintenance until ")
        # a session told none: let go, and no longer kept
        listener.maintenance_seen.emit(None)
        assert desktop.settings.value.maintenance == {}
        assert built.home.state.notice.isHidden()
    finally:
        built.window.keep_in_tray = False
        built.window.close()
        windows.close()
        desktop.close()


@pytest.mark.parametrize(
    "kept", [{"starts_at": "x"}, "junk", {"a": 1, "b": 2, "c": 3, "d": 4}]
)
def test_a_kept_window_that_cant_be_read_is_none(kept: Any) -> None:
    settings = AppSettings.from_stored({"maintenance": kept})
    assert planned.from_stored(settings.maintenance, NOW) is None


def test_a_window_told_on_the_sessions_thread_reaches_the_interface_thread(
    hub: tuple[DesktopApp, CaptionWindows, Hub], qapp: QApplication
) -> None:
    """The session tells its listener on its own thread; Home is changed
    only on the interface thread (decision 0012)."""
    desktop, _, _ = hub
    listener = QtListener(desktop, None)
    seen: list[tuple[Maintenance | None, bool]] = []
    listener.maintenance_seen.connect(
        lambda w: seen.append(
            (w, threading.current_thread() is threading.main_thread())
        )
    )
    window = on_now()
    told = threading.Thread(target=listener.maintenance_changed, args=(window,))
    told.start()
    told.join()
    deadline = time.monotonic() + 5
    while not seen and time.monotonic() < deadline:
        qapp.processEvents()
    assert seen == [(window, True)]
    listener.deleteLater()


class Pipeline:
    """The speech pipeline's part the listener drives: holding speech or not."""

    def __init__(self) -> None:
        self.held: list[bool] = []

    def hold_speech(self, holding: bool) -> None:
        self.held.append(holding)

    def set_pace_hint(self, live_interval_min: float | None) -> None:
        pass


def test_nothing_is_held_to_send_while_waiting_out_a_window(
    hub: tuple[DesktopApp, CaptionWindows, Hub],
) -> None:
    """polyglotic-hq 319, 320's measure: every app sending up to two minutes
    of held speech at a window's end slowed everyone's captions."""
    desktop, _, _ = hub
    pipeline = Pipeline()
    listener = QtListener(desktop, pipeline)  # type: ignore[arg-type]
    listener.status_changed(
        Status(SessionState.WAITING, retry_in=8.0, unreachable=Unreachable.DOWN)
    )
    listener.status_changed(
        Status(
            SessionState.WAITING, retry_in=120.0, unreachable=Unreachable.MAINTENANCE
        )
    )
    listener.status_changed(Status(SessionState.CONNECTING))
    listener.status_changed(Status(SessionState.LISTENING))
    assert pipeline.held == [
        True,
        False,
        True,
        True,
    ]  # an outage still holds two minutes
    listener.deleteLater()
