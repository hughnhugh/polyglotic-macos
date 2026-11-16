"""A hidden caption window stops loading the server (polyglotic-hq 335):
real caption windows offscreen, the app's Hide (Ctrl+Alt+H, the tray),
Home and the tray's tooltip - on a made-up clock."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.hidden import Sight
from polyglotic_desktop.core.listening.sources import MIC, SourceId
from polyglotic_desktop.main import Hub, Panels, wire_caption_windows
from polyglotic_desktop.ui.app import ConnectionState, DesktopApp
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import BehaviourPanel
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView
from polyglotic_desktop.ui_next.views.placement import Rect

APP_1, APP_2 = SourceId("app-1"), SourceId("app-2")
MIN = 60.0


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def hub(qapp: QApplication) -> Iterator[tuple[DesktopApp, CaptionWindows, Hub, Clock]]:
    store = MemorySettingsStore({"apps": ["Browser", "Game"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, lambda: [Rect(0, 0, 1920, 1040)])
    windows.clock = clock = Clock()
    wire_caption_windows(windows, desktop, lambda: None)
    windows.set_captioned([("Browser", APP_1), ("Game", APP_2)])
    assert desktop.apps is not None
    built = Hub(desktop, windows, Panels(desktop.settings, windows), desktop.apps, True)
    yield desktop, windows, built, clock
    built.window.close()
    windows.close()
    desktop.close()


def _rows(built: Hub) -> dict[str, str]:
    """Home's captioned apps: each one's line under its name."""
    return {key: row.status.text() for key, row in built.home.picker_card.rows.items()}


def test_hidden_15_minutes_its_listening_pauses_and_showing_starts_it(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    desktop, windows, built, clock = hub
    paused: list[frozenset[SourceId]] = []
    windows.paused_changed.connect(lambda: paused.append(windows.paused_sources()))
    windows.set_show_mic("Game", True)  # my speech in one window
    desktop.feed.apply(finished_updates(1, source=APP_1)[0])  # a caption shown
    desktop.hide_windows.setChecked(True)  # the tray's Hide, or Ctrl+Alt+H
    assert not any(w.isVisible() for w in windows.windows.values())
    clock.now += 14 * MIN
    windows.tick()
    assert paused == [] and windows.paused_sources() == frozenset()
    clock.now += 2 * MIN
    windows.tick()
    # nothing of either app is sent - nor my speech, its only window paused
    assert paused == [frozenset({APP_1, APP_2, MIC})]
    assert windows.sight("Browser") == (Sight.PAUSED, 15)
    rows = _rows(built)
    assert (
        rows["Browser"]
        == rows["Game"]
        == ("paused after 15 minutes hidden - show it to carry on")
    )
    assert desktop.hidden_line == (
        "Captions paused after 15 minutes hidden - show the windows to carry on"
    )
    # a paused window keeps its captions and choices
    assert windows.windows["Game"].choices.show_mic
    assert len(windows.windows["Browser"].view.lines) == 1
    # Home's Captions shows the windows again: listening starts again
    built.picker.show_window("Browser")
    assert not desktop.hide_windows.isChecked()
    assert all(w.isVisible() for w in windows.windows.values())
    assert paused[-1] == frozenset() == windows.paused_sources()
    assert desktop.hidden_line == ""
    assert _rows(built)["Browser"] != rows["Browser"]


def test_homes_title_says_paused_while_every_window_is(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    """336's Q2 (368): every window paused after being hidden, nothing is
    sent - yet Home's title, and the tray's tip after it, said "Listening".
    Now "Paused", saying how to go on; one window listening, "Listening"."""
    desktop, windows, built, clock = hub
    desktop.set_connection(ConnectionState.LISTENING)
    state = built.home.state
    assert state.title_label.text() == "Listening"
    windows.set_captioned([("Browser", APP_1)])
    desktop.hide_windows.setChecked(True)
    clock.now += 16 * MIN
    windows.tick()  # one paused; the other app's window not open: listening
    assert windows.sight("Browser") == (Sight.PAUSED, 15)
    assert state.title_label.text() == "Listening"
    windows.set_captioned([("Browser", APP_1), ("Game", APP_2)])  # opens hidden
    clock.now += 16 * MIN
    windows.tick()  # every window paused: nothing is sent
    assert windows.paused_sources() == frozenset({APP_1, APP_2})
    assert state.title_label.text() == "Paused"
    assert state.detail.text() == (
        "every caption window hidden over 15 minutes - show them to carry on"
    )
    assert desktop.state_title == "Paused"  # the tray's tip
    desktop.hide_windows.setChecked(False)  # shown: listening again
    assert state.title_label.text() == "Listening"


def test_a_shown_window_is_never_paused(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    _, windows, _, clock = hub
    clock.now += 600 * MIN
    windows.tick()
    assert windows.paused_sources() == frozenset()
    assert windows.sight("Browser") == (Sight.SHOWN, None)


def test_never_keeps_a_hidden_window_listening(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    desktop, windows, _, clock = hub
    windows.set_look(replace(windows.look, pause_hidden_after=None))
    desktop.hide_windows.setChecked(True)
    clock.now += 600 * MIN
    windows.tick()
    assert windows.paused_sources() == frozenset()


def test_a_window_opened_while_hidden_has_its_own_timer(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    desktop, windows, _, clock = hub
    windows.set_look(replace(windows.look, pause_hidden_after=5))
    windows.set_captioned([("Browser", APP_1)])
    desktop.hide_windows.setChecked(True)
    clock.now += 3 * MIN
    windows.set_captioned([("Browser", APP_1), ("Game", APP_2)])  # opens hidden
    assert not windows.windows["Game"].isVisible()
    clock.now += 3 * MIN
    windows.tick()
    assert windows.paused_sources() == frozenset({APP_1})
    clock.now += 3 * MIN
    windows.tick()
    assert windows.paused_sources() == frozenset({APP_1, APP_2})


def test_joined_windows_count_as_hidden_only_when_they_are(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    desktop, windows, _, clock = hub
    windows.join()
    assert windows.joined_window is not None and windows.joined_window.isVisible()
    clock.now += 60 * MIN
    windows.tick()
    assert windows.paused_sources() == frozenset()  # shown, joined
    desktop.hide_windows.setChecked(True)
    assert not windows.joined_window.isVisible()
    clock.now += 16 * MIN
    windows.tick()
    assert windows.paused_sources() == frozenset({APP_1, APP_2})
    desktop.hide_windows.setChecked(False)
    assert windows.joined_window.isVisible()
    assert windows.paused_sources() == frozenset()


def test_captioning_while_hidden_is_said_on_home_and_in_the_tray(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    desktop, windows, built, clock = hub
    desktop.hide_windows.setChecked(True)
    clock.now += MIN
    desktop.feed.apply(finished_updates(1, source=APP_1)[0])
    assert windows.sight("Browser") == (Sight.CAPTIONING, None)
    assert _rows(built)["Browser"] == "captioning while hidden"
    assert desktop.hidden_line == "Captioning Browser while hidden"
    assert desktop.hide_windows.isChecked()  # not brought back: not asked for
    clock.now += 31
    windows.tick()
    assert desktop.hidden_line == ""  # quiet again


def test_a_hidden_window_comes_back_when_speech_starts_if_asked(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    desktop, windows, _, clock = hub
    windows.set_look(replace(windows.look, show_on_speech=True))
    desktop.hide_windows.setChecked(True)
    clock.now += 5  # hidden just now: not straight back
    desktop.feed.apply(finished_updates(1, source=APP_1)[0])
    assert desktop.hide_windows.isChecked()
    clock.now += 2 * MIN  # talk again after a quiet spell
    desktop.feed.apply(finished_updates(1, source=APP_1, start=1)[0])
    assert not desktop.hide_windows.isChecked()
    assert all(w.isVisible() for w in windows.windows.values())


def test_behaviours_choices_reach_the_windows_and_are_kept(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    desktop, windows, built, _ = hub
    assert windows.sights.limit == 15 and not windows.show_on_speech
    built.panels.look.set_pause_hidden_after(5)  # Settings > Captions > Behaviour
    built.panels.look.set_show_on_speech(True)
    assert windows.sights.limit == 5 and windows.show_on_speech
    built.panels.save_look()
    value = desktop.settings.value
    assert value.pause_hidden_after == 5 and value.show_hidden_on_speech
    built.panels.look.set_pause_hidden_after(None)  # Never
    built.panels.save_look()
    assert windows.sights.limit is None
    assert desktop.settings.value.pause_hidden_after is None
    built.panels.look.reset()  # the look's reset keeps what a hidden window does
    assert windows.sights.limit is None and windows.show_on_speech


def test_a_stored_limit_not_offered_is_the_default() -> None:
    assert AppSettings.from_stored({"pause_hidden_after": 7}).pause_hidden_after == 15
    assert (
        AppSettings.from_stored({"pause_hidden_after": True}).pause_hidden_after == 15
    )
    assert (
        AppSettings.from_stored({"pause_hidden_after": None}).pause_hidden_after is None
    )
    assert AppSettings.from_stored({"pause_hidden_after": 60}).pause_hidden_after == 60


def test_only_settings_offers_what_a_hidden_window_does(qapp: QApplication) -> None:
    """Every window's choice, in Settings > Captions > Behaviour - not in a
    transcript's narrow rail, which shows the rest of Behaviour."""
    view = LookView(CaptionLook())
    rail = BehaviourPanel(view)
    settings = BehaviourPanel(view, notes=True, hidden_windows=True)
    assert rail.pause_hidden is None and rail.show_on_speech is None
    assert settings.pause_hidden is not None and settings.show_on_speech is not None
    settings.pause_hidden.changed.emit(60)
    settings.show_on_speech.click()
    assert view.value.pause_hidden_after == 60 and view.value.show_on_speech
    for panel in (rail, settings):
        panel.deleteLater()


def test_the_trays_tip_fits_windows_without_cutting_a_word(
    hub: tuple[DesktopApp, CaptionWindows, Hub, Clock],
) -> None:
    """Windows keeps a tray icon's tip in 127 characters and Qt cuts the
    rest there, mid-word: one window captioning while hidden ("VLC media
    player", as Home names it) and another paused made 136, and the stand-in
    taskbar was handed "... show the windows to c" (polyglotic-hq 336). The
    "captioning" line goes first - Home's row says it too - and what to do
    stays whole."""
    desktop = hub[0]
    desktop.show_state_title("Listening")
    desktop.show_hidden(["VLC media player"], 15)
    tip = desktop._tooltip()
    assert len(tip) <= 127  # NOTIFYICONDATA's szTip, with its end
    assert tip == (
        "Polyglotic - Listening\n"
        "Captions paused after 15 minutes hidden - show the windows to carry on"
    )
    desktop.show_hidden(["VLC media player"], None)  # captioning only: it fits
    assert desktop._tooltip() == (
        "Polyglotic - Listening\nCaptioning VLC media player while hidden"
    )


def test_a_tip_too_long_even_so_ends_at_a_word() -> None:
    from polyglotic_desktop.ui.app import TIP_MAX, fitted_tip

    long_line = "Untertitel pausiert: 15 Minuten ausgeblendet – " * 4
    tip = fitted_tip(["Polyglotic - Hört zu", long_line.strip()])
    assert len(tip) <= TIP_MAX and tip.endswith("…")
    kept = tip.split("\n")[1][:-1]
    assert long_line.startswith(kept) and long_line[len(kept)] == " "  # a whole word
    assert fitted_tip(["Polyglotic - Listening"]) == "Polyglotic - Listening"
