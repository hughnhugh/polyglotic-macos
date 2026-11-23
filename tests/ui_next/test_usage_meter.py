"""A capped plan's usage meter (polyglotic-hq 684; PLAN-OPEN-BETA v17): its
words, the ring on a caption window's bar at every compression step, the
tray's line, and the warnings - none of it on an unlimited plan."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QDate, QLocale, QRect, QTimeZone
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.test_caption_window import MIC, window_of

from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.shared.open_beta import (
    Account,
    Allowance,
    UsageMeter,
    UsageWarnings,
)
from polyglotic_desktop.main import show_usage_meter
from polyglotic_desktop.ui.app import TIP_MAX, DesktopApp, _units
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_window import CaptionWindow, StripLabels
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.maintenance import clock_time
from polyglotic_desktop.ui_next.usage import meter_text, tray_line
from polyglotic_desktop.ui_next.views.placement import Rect

APP_1, APP_2 = SourceId("app-1"), SourceId("app-2")
MELBOURNE = QTimeZone(b"Australia/Melbourne")
MIDNIGHT = datetime(2026, 11, 22, 13, tzinfo=UTC)  # Melbourne's, 23 November
DECEMBER = datetime(2026, 11, 30, 13, tzinfo=UTC)  # Melbourne's 1 December
FREE = UsageMeter("beta_free", 62, MIDNIGHT)
LITE = UsageMeter("lite", 74, DECEMBER)


# -- the words ----------------------------------------------------------------------


def test_the_free_meter_says_today_and_midnight_on_this_pcs_clock() -> None:
    text = meter_text(FREE, MELBOURNE)
    assert text == "Free today: 62% left - resets at midnight"
    # 13:00 UTC is the account's midnight, not a traveller's in UTC: the
    # time itself is said there
    abroad = meter_text(FREE, QTimeZone.utc())
    assert (
        abroad
        == f"Free today: 62% left - resets at {clock_time(MIDNIGHT, QTimeZone.utc())}"
    )
    assert meter_text(UsageMeter("beta_free", 62), MELBOURNE) == "Free today: 62% left"


def test_a_monthly_meter_names_its_plan_and_the_reset_day_where_the_pc_is() -> None:
    # 13:00 UTC on 30 November: already 1 December in Melbourne (the day is
    # this PC's, not UTC's)
    first = QLocale().toString(QDate(2026, 12, 1), QLocale.FormatType.LongFormat)
    assert meter_text(LITE, MELBOURNE) == (
        f"Lite: 74% of this month’s hours left - resets {first}"
    )
    last = QLocale().toString(QDate(2026, 11, 30), QLocale.FormatType.LongFormat)
    assert meter_text(LITE, QTimeZone.utc()).endswith(f"resets {last}")
    standard = UsageMeter("standard", 9)
    assert meter_text(standard) == "9% of this month’s hours left"
    later = UsageMeter("a_later_plan", 40, DECEMBER)  # unnamed, still metered
    assert meter_text(later, MELBOURNE) == "40% of this month’s hours left"


def test_the_trays_line_is_a_percentage_never_a_count() -> None:
    assert tray_line(FREE) == "62% of today’s free captions left"
    assert tray_line(LITE) == "74% of this month’s hours left"


# -- the bar's ring -----------------------------------------------------------------


@pytest.fixture
def window(qapp: QApplication) -> Iterator[CaptionWindow]:
    style.use_app_text_size("normal")
    shown = window_of(qapp, captions=0)
    yield shown
    shown.close()
    shown.deleteLater()


def test_the_bar_has_a_ring_only_while_the_plan_is_capped(
    window: CaptionWindow,
) -> None:
    ring = window.usage_ring
    assert ring.isHidden()  # an unlimited plan, or not signed in: no meter
    least = window.strip_least()
    window.set_usage(FREE)
    assert not ring.isHidden()
    assert ring.toolTip() == meter_text(FREE)
    assert ring.accessibleDescription() == ring.toolTip()  # a screen reader's
    assert ring.accessibleName() == "Listening allowance"
    assert ring in window.tips.texts  # said on hover: the window is never active
    assert window.strip_least() > least  # the window can't shrink over it
    window.set_usage(UsageMeter("beta_free", 61, MIDNIGHT))
    assert "61%" in ring.toolTip()
    window.set_usage(None)  # upgraded to an unlimited plan
    assert ring.isHidden() and window.strip_least() == least


def on_window(window: CaptionWindow, widget: QWidget) -> QRect:
    return QRect(widget.mapTo(window, widget.rect().topLeft()), widget.size())


@pytest.mark.parametrize("app_size", ["smaller", "normal", "largest"])
def test_the_ring_stays_at_every_compression_step_and_covers_nothing(
    qapp: QApplication, app_size: str
) -> None:
    style.use_app_text_size(app_size)
    window = window_of(qapp, captions=0)
    try:
        window.set_reporting(True)
        window.set_show_mic(True)
        window.set_usage(FREE)
        window.hovered = True
        window._show_band(True)
        ring = window.usage_ring
        steps = set()
        for width in range(window._minimum().width, 1301):
            window.resize(width, 300)
            steps.add(window.strip_labels)
            assert ring.isVisible(), width
            place = on_window(window, ring)
            assert window.band.geometry().contains(place), width
            assert ring.width() >= ring.sizeHint().width(), width
            others: list[QWidget] = [window.tag, *window._chips, window.mic_button]
            others += list(window.buttons.values())
            for other in others:
                if not other.isHidden():
                    assert not place.intersects(on_window(window, other)), (
                        width,
                        other.objectName(),
                    )
        assert steps == set(StripLabels)
        # beside the mic, at its right
        assert (
            on_window(window, ring).left()
            >= on_window(window, window.mic_button).right()
        )
        # narrower than the icons' step: chips go into the gear, never the ring
        window.resize(window._minimum().width - ring.width() - 30, 300)
        window._fit_band()
        assert ring.isVisible() and window.mic_button.isVisible()
    finally:
        window.close()
        window.deleteLater()
        style.use_app_text_size("normal")


# -- everywhere it shows --------------------------------------------------------------


@pytest.fixture
def shown(
    qapp: QApplication,
) -> Iterator[tuple[DesktopApp, CaptionWindows, list[str], list[str]]]:
    store = MemorySettingsStore({"apps": ["Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    windows.set_captioned([("Browser", APP_1)])
    home: list[str] = []
    captions: list[str] = []
    desktop.home_notice.connect(home.append)
    desktop.caption_notice.connect(captions.append)
    yield desktop, windows, home, captions
    windows.close()
    desktop.deleteLater()


def account(plan: str, percent: int | None) -> Account:
    allowance = Allowance(percent, MIDNIGHT) if percent is not None else None
    return Account("account", "open_beta", True, plan, allowance)


def test_a_capped_plan_shows_on_every_bar_and_in_the_tray_and_warns_twice(
    shown: tuple[DesktopApp, CaptionWindows, list[str], list[str]],
) -> None:
    desktop, windows, home, captions = shown
    warnings = UsageWarnings()
    first = windows.windows["Browser"]
    assert (
        show_usage_meter(account("beta_free", 62), warnings, windows, desktop) is None
    )
    assert first.usage_ring.meter == FREE
    assert desktop.usage.isVisible()
    assert desktop.usage.text() == "62% of today’s free captions left"
    assert "62% of today’s free captions left" in desktop._tooltip().split("\n")
    assert desktop.usage in desktop.tray_menu.actions()
    assert not home and not captions
    # a window opened later has it too
    windows.set_captioned([("Browser", APP_1), ("Game", APP_2)])
    assert windows.windows["Game"].usage_ring.meter == FREE
    levels = [
        show_usage_meter(account("beta_free", left), warnings, windows, desktop)
        for left in (20, 19, 5, 4, 0, 0)
    ]
    assert levels == [20, None, 5, None, 0, None]
    assert home == captions and len(home) == 3
    assert home[0].startswith("20% of today’s free captions left")
    assert home[1].startswith("5% of today’s free captions left")
    assert "used up" in home[2]
    assert desktop.usage.text() == "0% of today’s free captions left"


def test_an_unlimited_plan_shows_no_meter_anywhere(
    shown: tuple[DesktopApp, CaptionWindows, list[str], list[str]],
) -> None:
    desktop, windows, home, _captions = shown
    warnings = UsageWarnings()
    show_usage_meter(account("lite", 4), warnings, windows, desktop)
    assert desktop.usage.isVisible() and home
    for unlimited in (account("plus", None), account("premium", None), None):
        show_usage_meter(unlimited, warnings, windows, desktop)
        assert not desktop.usage.isVisible()
        assert "left" not in desktop._tooltip()
        assert all(w.usage_ring.isHidden() for w in windows.windows.values())
    assert len(home) == 1


def test_the_trays_tooltip_drops_the_usage_line_before_cutting_what_to_do(
    shown: tuple[DesktopApp, CaptionWindows, list[str], list[str]],
) -> None:
    desktop, _windows, _home, _captions = shown
    desktop.show_state_title("Listening")
    desktop.show_usage("74% of this month’s hours left")
    desktop.show_hidden(["VLC media player", "Discord"], 15)
    tip = desktop._tooltip()
    assert _units(tip) <= TIP_MAX
    assert tip.startswith("Polyglotic - Listening")
    assert "this month" not in tip  # the middle line went first
    assert tip.split("\n")[-1].startswith("Captions paused after 15 minutes")
