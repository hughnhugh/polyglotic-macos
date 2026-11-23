"""A new learner's first caption window captions their own speech, its
switch on in the set-up, and the Mac asks for the mic then (polyglotic-hq
478; the user, 2026-11-18: "record user mic in first window is the
default"). Existing users' windows keep what they chose."""

from collections.abc import Callable, Iterator

import pytest
from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList, MemorySettingsStore
from tests.ui_next.made_up import SEPARATE

from polyglotic_desktop.core.listening.sources import SAMPLE, SourceId
from polyglotic_desktop.main import MicAsked, mic_refused_text, wire_caption_windows
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next.caption_window import CaptionWindow
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.migration import stored_windows
from polyglotic_desktop.ui_next.views.placement import Rect

VIDEO = SourceId("app-2")


def areas() -> list[Rect]:
    return [Rect(0, 0, 1920, 1040)]


# -- which window shows my speech (plain Python) ------------------------------------


def test_a_new_learners_first_window_shows_my_speech() -> None:
    new = stored_windows({"targets": ["en"]})  # a new PC: today's values, no window
    assert new.first_window
    assert new.for_new(0, "Discord.exe", set_up=True).show_mic
    later = StoredWindows()  # the first use over, nothing kept yet
    assert later.for_new(0, "Discord.exe", set_up=True).show_mic
    # only with the set-up (`main`'s): the UI lab's and tests' windows as before
    assert not later.for_new(0, "Discord.exe").show_mic


def test_only_the_first_window() -> None:
    stored = StoredWindows()
    stored.by_key["Discord.exe"] = stored.for_new(0, "Discord.exe", set_up=True)
    assert not stored.first_window
    assert not stored.for_new(1, "Video", set_up=True).show_mic  # off, as before


def test_not_the_samples_window_which_leaves_the_first_for_the_learners_app() -> None:
    stored = StoredWindows()
    sample = stored.for_new(0, SAMPLE, set_up=True)
    assert not sample.show_mic  # a trial: my speech isn't in it
    stored.by_key[SAMPLE] = sample
    assert stored.first_window
    assert stored.for_new(0, "Discord.exe", set_up=True).show_mic


def test_a_learner_with_windows_keeps_what_they_chose() -> None:
    """0.1.7's windows (no "set_up"): not a new learner - each window keeps
    its own switch, and a new one starts without my speech, as before."""
    before = {
        "windows": {"Discord.exe": WindowChoices(show_mic=False).to_stored()},
        "last": WindowChoices().to_stored(),
    }
    stored = stored_windows({"targets": ["en"], STORED_KEY: before})
    assert not stored.first_window
    assert not stored.by_key["Discord.exe"].show_mic
    assert not stored.for_new(1, "Video", set_up=True).show_mic
    assert not StoredWindows(set_up=True).for_new(0, "Video", set_up=True).show_mic
    # today's settings moved over, apps picked: their choice ("Caption my
    # own speech" off) is each window's
    moved = stored_windows({"apps": ["Discord.exe"], "caption_mic": False})
    assert not moved.by_key["Discord.exe"].show_mic


def test_preset_defaults_conversation_on_and_video_off_for_new_windows() -> None:
    """651: Conversation defaults new windows to own speech on, Video defaults
    them off (even on the first window), while SAMPLE stays off."""
    fresh = StoredWindows()
    assert fresh.for_new(0, "VLC", set_up=True, my_speech=False).show_mic is False
    assert fresh.for_new(0, "Discord.exe", set_up=True, my_speech=True).show_mic is True
    fresh.by_key["Discord.exe"] = WindowChoices(show_mic=False)  # explicit choice
    assert fresh.for_new(1, "Zoom", set_up=True, my_speech=True).show_mic is True
    assert fresh.for_new(1, "VLC", set_up=True, my_speech=False).show_mic is False
    assert fresh.for_new(0, SAMPLE, set_up=True, my_speech=True).show_mic is False


# -- in the windows and the set-up --------------------------------------------------


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
    found = CaptionWindows(Store({"targets": ["en"]}), MIC, areas, offer_set_up=True)
    found.stored.joined = SEPARATE  # on their own: windows start joined (554)
    yield found
    found.close()


def first(windows: CaptionWindows, qapp: QApplication) -> CaptionWindow:
    windows.set_captioned([("Discord.exe", APP)])
    window = windows.windows["Discord.exe"]
    window.show()
    qapp.processEvents()
    return window


def test_the_first_window_shows_my_speech_and_the_set_up_says_so(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    wanted: list[bool] = []
    windows.mic_wanted.connect(wanted.append)
    window = first(windows, qapp)
    assert window.choices.show_mic and windows.show_mic_anywhere
    assert wanted[-1] is True  # "Caption my own speech" goes on
    set_up = window.set_up
    assert set_up is not None and "set_up_mic" in set_up.rows
    switch = window.controls["show_mic"]
    assert switch.isChecked()  # seen on, in the set-up
    switch.trigger()  # and turned off there
    assert not window.choices.show_mic and wanted[-1] is False
    windows.set_captioned([("Discord.exe", APP), ("Video", VIDEO)])
    assert not windows.windows["Video"].choices.show_mic


def test_a_later_window_asks_again_with_my_speech_off(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    """Without Use as my default, the next window that opens asks again
    (478) - with its own switch, off: only the first shows my speech."""
    window = first(windows, qapp)
    window.finish_set_up()  # Start captions, not as my default
    windows.set_captioned([("Discord.exe", APP), ("Video", VIDEO)])
    video = windows.windows["Video"]
    video.show()
    qapp.processEvents()
    assert video.set_up is not None and "set_up_mic" in video.set_up.rows
    assert not video.choices.show_mic and not video.controls["show_mic"].isChecked()
    assert window.choices.show_mic  # the first keeps it


def test_the_samples_window_neither_asks_nor_shows_my_speech(
    windows: CaptionWindows, qapp: QApplication
) -> None:
    windows.set_captioned([(SAMPLE, SAMPLE)])
    sample = windows.windows[SAMPLE]
    sample.show()
    qapp.processEvents()
    assert sample.set_up is None and not sample.choices.show_mic
    window = first(windows, qapp)  # the learner's own app, after
    assert window.set_up is not None and window.choices.show_mic


# -- the OS's leave to hear the mic (a Mac's) ---------------------------------------


class Permission:
    """A stand-in `MicPermission`: the answer it holds, and the questions."""

    def __init__(self, allowed: bool | None) -> None:
        self.value = allowed
        self.asked: list[Callable[[bool], None]] = []

    def allowed(self) -> bool | None:
        return self.value

    def ask(self, answered: Callable[[bool], None]) -> None:
        self.asked.append(answered)


@pytest.fixture
def wired(qapp: QApplication) -> Iterator[tuple[DesktopApp, CaptionWindows]]:
    store = MemorySettingsStore({"apps": ["Web Browser"], "targets": ["en"]})
    desktop = DesktopApp(store, None, FakeAppList())
    windows = CaptionWindows(store, MIC, areas)
    yield desktop, windows
    windows.close()
    desktop.close()


def notices(desktop: DesktopApp) -> list[str]:
    said: list[str] = []
    desktop.home_notice.connect(said.append)
    desktop.caption_notice.connect(said.append)
    return said


def test_given_or_windows_my_speech_turns_the_mic_on(
    wired: tuple[DesktopApp, CaptionWindows], qapp: QApplication
) -> None:
    desktop, windows = wired
    for permission in (None, Permission(True)):
        asked = wire_caption_windows(windows, desktop, lambda: None, permission)
        asked.wanted(True)
        assert desktop.caption_mic.isChecked()
        asked.wanted(False)
        assert not desktop.caption_mic.isChecked()


def test_never_asked_the_mac_asks_then_and_yes_turns_it_on(
    wired: tuple[DesktopApp, CaptionWindows], qapp: QApplication
) -> None:
    desktop, windows = wired
    permission = Permission(None)
    asked = wire_caption_windows(windows, desktop, lambda: None, permission)
    windows.set_captioned([("Web Browser", APP)])
    windows.set_show_mic_everywhere(True)
    assert len(permission.asked) == 1  # asked once, at that moment
    assert not desktop.caption_mic.isChecked()  # no mic until the answer
    asked.wanted(True)
    assert len(permission.asked) == 1  # not asked twice while asking
    permission.asked[0](True)  # from macOS's thread, on Qt's after
    qapp.processEvents()
    assert desktop.caption_mic.isChecked()


def test_refused_the_switch_goes_off_and_says_so(
    wired: tuple[DesktopApp, CaptionWindows], qapp: QApplication
) -> None:
    desktop, windows = wired
    said = notices(desktop)
    permission = Permission(None)
    wire_caption_windows(windows, desktop, lambda: None, permission)
    windows.set_captioned([("Web Browser", APP)])
    windows.set_show_mic_everywhere(True)
    permission.asked[0](False)
    qapp.processEvents()
    assert not windows.show_mic_anywhere and not desktop.caption_mic.isChecked()
    assert said == [mic_refused_text(), mic_refused_text()]  # Home, the windows
    assert "Privacy & Security > Microphone" in said[0]


def test_refused_before_it_isnt_asked_again(
    wired: tuple[DesktopApp, CaptionWindows], qapp: QApplication
) -> None:
    desktop, windows = wired
    said = notices(desktop)
    permission = Permission(False)
    asked: MicAsked = wire_caption_windows(windows, desktop, lambda: None, permission)
    windows.set_captioned([("Web Browser", APP)])
    windows.set_show_mic_everywhere(True)
    assert not permission.asked
    assert not windows.show_mic_anywhere and not desktop.caption_mic.isChecked()
    assert said and said[0] == mic_refused_text()
    asked.wanted(False)  # nothing shows my speech: nothing to say
    assert len(said) == 2
