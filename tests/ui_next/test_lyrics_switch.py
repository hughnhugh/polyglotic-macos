"""The Lyrics switch (polyglotic-hq 595, DECISIONS.md #248; decision 0287):
songs mode for music players heard on Detect, off by default. One setting,
in two places: a music player's caption window - offered only there, and
only while it hears Detect - and Settings > Captions > Speech. With it on,
the music players' windows on Detect are the sources heard in songs mode;
with it off, none."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore

from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.main import (
    follow_settings,
    languages_settings,
    session_languages,
    wire_caption_windows,
)
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.panels import LanguagesPanel
from polyglotic_desktop.ui_next.settings_popover import (
    COLUMN_ROWS,
    LANGUAGE_ROWS,
    ROWS,
    SettingsPopover,
)
from polyglotic_desktop.ui_next.views.panels import LanguagesView, SessionLanguages
from polyglotic_desktop.ui_next.views.placement import Rect

SPOTIFY = "Spotify.exe"
DISCORD = "Discord.exe"
MUSIC = SourceId("app-2")


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


class Store:
    def __init__(self) -> None:
        self.values: dict[str, object] = {"targets": ["en"]}

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    """Discord and Spotify captioned; Spotify is the music player."""
    found = CaptionWindows(Store(), MIC, areas)
    found.music_player = lambda key: key == SPOTIFY
    found.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC)])
    yield found
    found.close()


def test_it_is_off_for_a_new_learner() -> None:
    """Music or singing alone gives no captions until the learner asks."""
    assert not AppSettings().lyrics
    assert not AppSettings.from_stored({}).lyrics


def test_only_a_music_players_window_on_detect_offers_it(
    windows: CaptionWindows,
) -> None:
    """In the language chip's popover, under They speak - and only there."""
    shown = {}
    for key, window in windows.windows.items():
        popover = SettingsPopover(window, None, LANGUAGE_ROWS)
        popover.refresh()
        lyrics = popover.rows["lyrics"]
        shown[key] = lyrics.isVisibleTo(popover)
        popover.deleteLater()
    assert shown == {DISCORD: False, SPOTIFY: True}
    for rows in (ROWS, COLUMN_ROWS):
        for window in windows.windows.values():
            popover = SettingsPopover(window, None, rows)
            popover.refresh()
            assert "lyrics" not in popover.rows
            popover.deleteLater()
    spotify = windows.windows[SPOTIFY]
    spotify.set_spoken_language("ja")  # a language named: kept to Detect
    assert not spotify.offers_lyrics
    spotify.set_spoken_language(None)
    assert spotify.offers_lyrics


def test_the_windows_switch_is_the_one_setting(windows: CaptionWindows) -> None:
    """A window's switch asks for the setting; the setting, as `main` hands
    it back, shows in every window's switch."""
    wanted: list[bool] = []
    windows.lyrics_wanted.connect(wanted.append)
    windows.windows[SPOTIFY].controls["lyrics"].trigger()
    assert wanted == [True]
    windows.set_lyrics(True)
    assert all(w.controls["lyrics"].isChecked() for w in windows.windows.values())
    windows.set_lyrics(False)
    assert not any(w.controls["lyrics"].isChecked() for w in windows.windows.values())


def test_with_it_on_the_music_players_on_detect_are_heard_as_songs(
    windows: CaptionWindows,
) -> None:
    assert windows.songs_sources() == frozenset()  # off: none
    windows.set_lyrics(True)
    assert windows.songs_sources() == frozenset({MUSIC})  # never Discord's
    windows.windows[SPOTIFY].set_spoken_language("ja")
    assert windows.songs_sources() == frozenset()  # a language named
    windows.windows[SPOTIFY].set_spoken_language(None)
    assert windows.songs_sources() == frozenset({MUSIC})
    windows.set_lyrics(False)
    assert windows.songs_sources() == frozenset()


def test_a_window_opened_later_shows_the_setting(windows: CaptionWindows) -> None:
    windows.set_lyrics(True)
    windows.set_captioned([(DISCORD, APP)])
    windows.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC)])
    assert windows.windows[SPOTIFY].controls["lyrics"].isChecked()
    assert windows.windows[SPOTIFY].music_player


def test_settings_speech_has_the_switch_and_keeps_it_as_the_setting(
    qapp: QApplication,
) -> None:
    view = LanguagesView(SessionLanguages())
    panel = LanguagesPanel(view, speech=True)
    assert panel.lyrics is not None and not panel.lyrics.isChecked()
    panel.lyrics.click()
    assert view.value.lyrics
    assert languages_settings(AppSettings(), view.value)["lyrics"] is True
    assert session_languages(AppSettings(lyrics=True), ()).lyrics
    panel.deleteLater()
    # only Settings > Speech: a transcript's Languages has no such row
    other = LanguagesPanel(LanguagesView(SessionLanguages()))
    assert other.lyrics is None
    other.deleteLater()


class FakeSources:
    """What `follow_settings` asks of the captured sources."""

    per_app = True
    sample_shown = False

    def app_id(self, name: str) -> SourceId:
        return MUSIC

    def shown(self) -> dict[SourceId, tuple[str, str]]:
        return {}


def test_the_switch_and_the_setting_go_both_ways(qapp: QApplication) -> None:
    """A window's switch changes the setting (`wire_caption_windows`); the
    setting reaches every window's switch (`follow_settings`)."""
    store = MemorySettingsStore({"targets": ["en"], "apps": [SPOTIFY]})
    desktop = DesktopApp(store, None, FakeAppList())
    found = CaptionWindows(store, MIC, areas)
    found.music_player = lambda key: key == SPOTIFY
    try:
        wire_caption_windows(found, desktop, lambda: None)
        follow_settings(found, desktop, FakeSources())  # type: ignore[arg-type]
        spotify = found.windows[SPOTIFY]
        assert spotify.offers_lyrics and not spotify.controls["lyrics"].isChecked()
        spotify.controls["lyrics"].trigger()
        assert desktop.settings.value.lyrics
        follow_settings(found, desktop, FakeSources())  # type: ignore[arg-type]
        assert found.lyrics and spotify.controls["lyrics"].isChecked()
        assert found.songs_sources() == frozenset({MUSIC})
    finally:
        found.close()
        desktop.close()
