"""Planned maintenance said on Home, the tray and the caption windows (polyglotic-hq 319).

Ahead, a quiet line on Home's banner in the learner's own time; the caption
windows once, five minutes before; during it, Home's title and the tray
say until when, instead of "restarting" or "down"; the window kept between
starts. Made-up apps only, offscreen.
"""

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from PySide6.QtCore import QLocale, QTime
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
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect

APP_1 = SourceId("app-1")
MELBOURNE = timezone(timedelta(hours=11))  # daylight saving's

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
        f"Planned maintenance tomorrow, {short(0, 30)}-{short(1, 0)}: captions "
        "pause then, and come back by themselves."
    )
    midnight = datetime(2026, 11, 14, 13, tzinfo=UTC)
    assert words.banner(window, midnight, MELBOURNE) == (
        f"Planned maintenance today, {short(0, 30)}-{short(1, 0)}: captions "
        "pause then, and come back by themselves."
    )
    assert words.banner(window, saturday_night, UTC) == (
        f"Planned maintenance today, {short(13, 30)}-{short(14, 0)}: captions "
        "pause then, and come back by themselves."
    )


def test_a_window_over_midnight_names_the_day_it_ends(qapp: QApplication) -> None:
    window = Maintenance(
        datetime(2026, 11, 14, 12, 30, tzinfo=UTC),
        datetime(2026, 11, 14, 13, 30, tzinfo=UTC),
    )
    sunday = QLocale().dayName(7, QLocale.FormatType.LongFormat)
    assert words.soon_line(window, MELBOURNE) == (
        f"Captions pause at {short(23, 30)} for planned maintenance, until "
        f"{sunday} {short(0, 30)}"
    )
    during = datetime(2026, 11, 14, 12, 45, tzinfo=UTC)
    assert words.state_title(window, during, MELBOURNE) == (
        f"Planned maintenance until {sunday} {short(0, 30)}"
    )


def test_a_pc_clock_a_day_fast_still_says_today(qapp: QApplication) -> None:
    window = Maintenance(
        datetime(2026, 11, 14, 4, tzinfo=UTC),
        datetime(2026, 11, 14, 4, 30, tzinfo=UTC),
        pc_ahead=timedelta(days=1),
    )
    pc_now = datetime(2026, 11, 15, 2, tzinfo=UTC)  # the server: 02:00 on the 14th
    banner = words.banner(window, pc_now, UTC)
    assert banner is not None and banner.startswith("Planned maintenance today,")
    assert words.banner(window, datetime(2026, 11, 14, 2, tzinfo=UTC), UTC) is None


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
    assert title.endswith(words.clock_time(window.ends_at))
    # never "down" (319's promise; 329's QA, 330), and no countdown to the
    # next try: it'd be noise for half an hour
    assert home.detail.text() == (
        "not your internet - captions come back by themselves when it's over"
    )
    assert "down" not in home.detail.text()
    assert desktop.state_title == title  # the tray's tooltip: "Polyglotic - ..."
    assert home.notice.isHidden()  # the state line says it: no banner beside it
    caption = windows.windows["Web Browser"]
    caption._tick()
    assert caption.notice.text() == (
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
