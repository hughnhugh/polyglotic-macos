"""The caption windows above a game that is itself always on top
(`caption_windows.keep_on_top`; polyglotic-hq project 141): once such a
game is clicked it goes above them, and a new caption didn't bring them
back. While one is in front they go back on top - the windows, then the
lookup card - when the foreground changes and when a caption comes, at
most once a second; otherwise nothing is touched. Offscreen, Windows'
band made up."""

from collections.abc import Iterator, Sequence

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import chinese_tools
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import caption_windows as caption_windows_module
from polyglotic_desktop.ui_next.caption_windows import ON_TOP_EVERY_SEC, CaptionWindows
from polyglotic_desktop.ui_next.views.placement import Rect

OTHER_APP = SourceId("app-2")
THIRD_APP = SourceId("app-3")


class Band:
    """Windows' always-on-top band, made up: whether a game is in front,
    and each `put_on_top` (native handles, bottom first)."""

    def __init__(self) -> None:
        self.game = True
        self.put: list[list[int]] = []

    def game_in_front(self) -> bool:
        return self.game

    def put_on_top(self, windows: Sequence[int]) -> None:
        self.put.append(list(windows))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    found = Clock()
    monkeypatch.setattr(caption_windows_module, "time", found)
    return found


@pytest.fixture
def band() -> Band:
    return Band()


@pytest.fixture
def windows(qapp: QApplication, band: Band, clock: Clock) -> Iterator[CaptionWindows]:
    found = CaptionWindows(
        None,
        MIC,
        lambda: [Rect(0, 0, 1920, 1040)],
        learner=chinese_tools(),
        on_top=band,
    )
    found.set_captioned([("app", APP), ("other", OTHER_APP)])
    qapp.processEvents()
    yield found
    found.close()


def _ids(windows: CaptionWindows, *keys: str) -> list[int]:
    return [int(windows.windows[key].winId()) for key in keys]


def test_a_caption_puts_them_back_above_a_game_in_front(
    windows: CaptionWindows, band: Band
) -> None:
    windows.apply(finished_updates(1)[0])
    assert band.put == [_ids(windows, "app", "other")]


def test_the_lookup_card_goes_last_above_them(
    windows: CaptionWindows, band: Band
) -> None:
    assert windows.card is not None
    windows.card.show()
    windows.keep_on_top()
    assert band.put == [[*_ids(windows, "app", "other"), int(windows.card.winId())]]


def test_without_a_game_in_front_nothing_is_touched(
    windows: CaptionWindows, band: Band
) -> None:
    """Not over the Start menu, Alt+Tab or an ordinary window."""
    band.game = False
    windows.apply(finished_updates(1)[0])
    windows.keep_on_top()
    assert band.put == []


def test_captions_put_them_back_at_most_once_a_second(
    windows: CaptionWindows, band: Band, clock: Clock
) -> None:
    updates = finished_updates(3)
    windows.apply(updates[0])
    clock.now += ON_TOP_EVERY_SEC / 2
    windows.apply(updates[1])
    assert len(band.put) == 1
    clock.now += ON_TOP_EVERY_SEC / 2
    windows.apply(updates[2])
    assert len(band.put) == 2


def test_the_foreground_changing_puts_them_back_on_the_interfaces_thread(
    windows: CaptionWindows, band: Band, qapp: QApplication
) -> None:
    windows.front_changed.emit()  # from the watch's own thread, in `main`
    assert band.put == []  # queued
    qapp.processEvents()
    assert band.put == [_ids(windows, "app", "other")]


def test_hidden_or_joined_only_what_shows(windows: CaptionWindows, band: Band) -> None:
    windows.set_hidden(True)
    windows.keep_on_top()
    assert band.put == []
    windows.set_hidden(False)
    windows.join()
    windows.keep_on_top()
    assert windows.joined_window is not None
    assert band.put == [[int(windows.joined_window.winId())]]


def test_a_card_open_goes_back_above_a_window_shown_after_it(
    windows: CaptionWindows, band: Band
) -> None:
    """141: a caption window shown after the card came up above it and
    covered it where they overlap. With or without a game in front."""
    band.game = False
    assert windows.card is not None
    windows.card.show()
    windows.set_captioned([("app", APP), ("other", OTHER_APP), ("third", THIRD_APP)])
    card = int(windows.card.winId())
    assert band.put == [[card]]
    windows.set_hidden(True)  # the card goes with them
    windows.set_hidden(False)
    assert band.put == [[card]]
    windows.card.show()
    windows.show_window("app")
    windows.set_hidden(True)
    windows.card.show()  # (as if opened again from a transcript)
    windows.set_hidden(False)
    assert band.put == [[card], [card], [card]]


def test_without_a_card_open_nothing_is_put_on_top(
    windows: CaptionWindows, band: Band
) -> None:
    band.game = False
    windows.set_captioned([("app", APP), ("other", OTHER_APP), ("third", THIRD_APP)])
    windows.show_window("app")
    assert band.put == []
