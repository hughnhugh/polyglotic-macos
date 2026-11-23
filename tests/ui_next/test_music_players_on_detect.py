"""A music player is heard on Detect (polyglotic-hq 568, from 558): told a
language, live's speech model turned music into "The.", "Music." and the
like for 544 of 580 pieces, while on Detect it wrote nothing for any of
them. So a music player's window starts on Detect whatever new windows
start with, Home's Spoken language leaves it be, and its Detect isn't what
new windows copy - unless the learner names a language in its own window."""

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.made_up import EN, ZH

from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.main import new_interface
from polyglotic_desktop.platform.windows.categories import category_of
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import (
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.placement import Rect

SPOTIFY = "Spotify.exe"
DISCORD = "Discord.exe"
MUSIC = SourceId("app-2")
THIRD = SourceId("app-3")
JA = Language("ja")


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


class Store:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def load(self) -> dict[str, object]:
        return dict(self.values)

    def save(self, values: object) -> None:
        assert isinstance(values, dict)
        self.values = dict(values)


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    """The learner names English for new windows ("Start new windows like
    this"); Spotify is the music player."""
    found = CaptionWindows(Store({"targets": ["en"]}), MIC, areas)
    found.stored.start_like_this = True
    found.stored.last = WindowChoices("en", spoken_language="en")
    found.music_player = lambda key: key == SPOTIFY
    yield found
    found.close()


def test_a_music_players_new_window_starts_on_detect(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC)])
    assert windows.spoken_languages() == {APP: EN, MUSIC: None}
    assert windows.windows[SPOTIFY].choices.translate_into == "en"  # the rest copied


def test_homes_spoken_language_leaves_a_music_player_be(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC)])
    windows.set_spoken_everywhere("zh")
    assert windows.spoken_languages() == {APP: ZH, MUSIC: None}


def test_a_language_named_in_the_music_players_own_window_is_kept(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC)])
    windows.windows[SPOTIFY].set_spoken_language("ja")  # Japanese songs
    assert windows.spoken_languages()[MUSIC] == JA
    windows.set_spoken_everywhere("zh")
    assert windows.spoken_languages() == {APP: ZH, MUSIC: JA}
    windows.save_now()  # and kept between launches
    again = CaptionWindows(windows._store, MIC, areas)
    again.music_player = windows.music_player
    again.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC)])
    assert again.spoken_languages()[MUSIC] == JA
    again.close()


def test_new_windows_dont_start_on_a_music_players_detect(
    windows: CaptionWindows,
) -> None:
    windows.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC)])
    windows.windows[SPOTIFY].set_text_size(1.25)  # the last window changed
    windows.set_captioned([(DISCORD, APP), (SPOTIFY, MUSIC), ("chrome.exe", THIRD)])
    assert windows.spoken_languages()[THIRD] == EN
    assert windows.windows["chrome.exe"].choices.text_size == 1.25


@pytest.mark.parametrize("first_use", [False, True])
def test_for_new_puts_a_music_player_on_detect(first_use: bool) -> None:
    """Whatever it would copy: "Start new windows like this", or today's
    one spoken language moved over on first use."""
    stored = StoredWindows(
        last=WindowChoices("ja", spoken_language="zh"),
        first_use=first_use,
        start_like_this=True,
    )
    assert stored.for_new(0, DISCORD).spoken == ZH
    music = stored.for_new(0, SPOTIFY, music_player=True)
    assert music.spoken is None and music.translate_into == "ja"


def test_main_tells_the_windows_which_apps_are_music_players(
    qapp: QApplication,
) -> None:
    """From the known-apps list, playing or not (Windows' here)."""
    store = MemorySettingsStore({"targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    interface = new_interface(
        desktop, store, None, per_app=True, app_category=category_of
    )
    try:
        music_player = interface.windows.music_player
        assert music_player(SPOTIFY) and music_player("spotify.exe")
        assert music_player("foobar2000.exe")
        assert not music_player(DISCORD) and not music_player("vlc.exe")
        assert not music_player("system")  # everything the PC plays
    finally:
        interface.close()
        desktop.close()
