"""Detect is the default everywhere, and nothing pushes the learner to name
a language (polyglotic-hq 555; the user, 2026-11-20: "Detect should be the
default mode and we shouldn't push users to force a language choice to
caption"). Naming one stays possible.

Every path to captioning starts on Detect: the settings, the first run's
caption window and its set-up, every new window and dictation. The one
push there was - a window asking "This sounds like Russian. Always hear it
as Russian?" once Detect heard one language steadily (317) - is behind its
flag, off (`core.releases.flags.SPOKEN_NUDGE`; test_spoken_nudge turns it
on)."""

from collections.abc import Iterator
from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui_next.made_up import finished_updates

from polyglotic_desktop.core.listening.captions import CaptionUpdate, Language
from polyglotic_desktop.core.listening.spoken import STEADY_CAPTIONS
from polyglotic_desktop.core.releases import flags
from polyglotic_desktop.main import listening_settings
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import (
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.placement import Rect

RU = Language("ru")


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


def russian(count: int) -> list[CaptionUpdate]:
    return [
        replace(update, language=RU, languages_heard=(RU,))
        for update in finished_updates(count, APP)
    ]


@pytest.fixture
def windows(qapp: QApplication) -> Iterator[CaptionWindows]:
    found = CaptionWindows(None, MIC, areas, offer_set_up=True)
    found.set_captioned([("Discord.exe", APP)])
    yield found
    found.close()


def test_the_nudge_is_off() -> None:
    assert not flags.on(flags.SPOKEN_NUDGE)
    assert flags.SPOKEN_NUDGE in flags.DECLARED


def test_every_setting_starts_on_detect() -> None:
    new = AppSettings()
    assert new.spoken_language is None and new.dictation_language is None
    assert listening_settings(new).spoken_language is None
    assert WindowChoices().spoken_language is None
    stored = StoredWindows(first_use=False)
    assert all(stored.for_new(n, f"app-{n}").spoken_language is None for n in (0, 1, 2))


def test_the_first_window_and_its_set_up_start_on_detect(
    windows: CaptionWindows,
) -> None:
    window = windows.windows["Discord.exe"]
    assert window.choices.spoken_language is None
    # the set-up asks with the window's choices filled in: Detect
    assert window.set_up is not None


def test_steady_speech_in_one_language_asks_nothing(windows: CaptionWindows) -> None:
    window = windows.windows["Discord.exe"]
    for update in russian(STEADY_CAPTIONS + 2):
        windows.apply(update)
    assert window.nudge is None and window.asking_spoken is None
    assert window.choices.spoken_language is None  # still Detect


def test_naming_a_language_stays_possible(windows: CaptionWindows) -> None:
    window = windows.windows["Discord.exe"]
    window.set_spoken_language("ru")
    assert window.choices.spoken_language == "ru"
    window.set_spoken_language(None)
    assert window.choices.spoken_language is None


def test_a_music_player_is_never_asked_either(qapp: QApplication) -> None:
    """A music player stays on Detect (polyglotic-hq 536: a language named
    there made the speech model translate the other songs of a playlist
    instead of writing them down)."""
    windows = CaptionWindows(None, MIC, areas)
    windows.set_captioned([("Spotify.exe", APP)])
    try:
        player = windows.windows["Spotify.exe"]
        for update in russian(STEADY_CAPTIONS + 2):
            windows.apply(update)
        assert player.nudge is None and player.choices.spoken_language is None
    finally:
        windows.close()
