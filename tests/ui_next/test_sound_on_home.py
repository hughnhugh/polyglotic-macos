"""Sound on Home, and in Settings > Speech (polyglotic-hq 372; the user,
2026-11-15, DECISIONS #175: "Home should have an area to choose speaker /
microphone settings"): which speakers everything the PC plays comes from,
whether what I say is captioned, which mic, and its level - one state,
two cards. No real device is opened or listed here."""

from collections.abc import Iterator
from dataclasses import replace

import numpy as np
import pytest
import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from tests.ui.fakes import Built, MemorySettingsStore
from tests.ui.test_main_wiring import ChangingAppList, FakeCapture, FakePipeline

from polyglotic_desktop.main import Sources
from polyglotic_desktop.platform.audio_buffer import AudioBuffer
from polyglotic_desktop.ports.capture import SoundDevice, SoundDevices
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.home import HomePage
from polyglotic_desktop.ui_next.os_words import pc_or_mac
from polyglotic_desktop.ui_next.settings_page import SettingsPage
from polyglotic_desktop.ui_next.sound_card import SoundCard
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.home import Picker, PickerView
from polyglotic_desktop.ui_next.views.panels import (
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
)
from polyglotic_desktop.ui_next.views.sound import Sound, SoundView, level_of

SPEAKERS = SoundDevice("{out-1}", "Speakers (Realtek Audio)")
HEADSET = SoundDevice("{out-2}", "Headphones (USB Headset)")
LAPTOP_MIC = SoundDevice("{in-1}", "Microphone Array (Realtek)")
HEADSET_MIC = SoundDevice("{in-2}", "Headset Microphone (USB Headset)")
PLUGGED = SoundDevices(
    (HEADSET, SPEAKERS), (HEADSET_MIC, LAPTOP_MIC), SPEAKERS.id, LAPTOP_MIC.id
)
MADE: list[QWidget] = []


@pytest.fixture(autouse=True)
def deleted() -> Iterator[None]:
    """Each page and card deleted when its test ends (261)."""
    yield
    while MADE:
        made = MADE.pop()
        if shiboken6.isValid(made):
            made.close()
            shiboken6.delete(made)


class Commands:
    """`main`'s Hub, in memory: the settings it would change."""

    def __init__(self, devices: SoundDevices = PLUGGED) -> None:
        self.devices = devices
        self.peak: float | None = None
        self.view: SoundView | None = None
        self.calls: list[tuple[str, object]] = []

    def _changed(self, **changes: object) -> None:
        assert self.view is not None
        self.view.follow(replace(self.view.value, **changes))  # type: ignore[arg-type]

    def set_speaker_device(self, device: str | None) -> None:
        self.calls.append(("speaker", device))
        self._changed(speaker=device)

    def set_mic_device(self, device: str | None) -> None:
        self.calls.append(("mic", device))
        self._changed(mic=device)

    def set_my_speech(self, on: bool) -> None:
        self.calls.append(("my_speech", on))
        self._changed(my_speech=on)

    def sound_devices(self) -> SoundDevices:
        return self.devices

    def mic_peak(self) -> float | None:
        return self.peak


def view_with(
    value: Sound | None = None, commands: Commands | None = None
) -> SoundView:
    commands = commands or Commands()
    view = SoundView(value or Sound(), commands)
    commands.view = view
    return view


# -- the view ------------------------------------------------------------------------


def test_windows_default_comes_first_naming_the_device_it_is_now() -> None:
    sound = Sound(PLUGGED)
    assert sound.speakers() == [
        (None, SPEAKERS),
        (HEADSET.id, HEADSET),
        (SPEAKERS.id, SPEAKERS),
    ]
    assert sound.mics()[0] == (None, LAPTOP_MIC)
    assert Sound().speakers() == [(None, None)]  # nothing known: the default alone


def test_a_device_chosen_and_unplugged_is_kept_and_said() -> None:
    sound = Sound(PLUGGED, speaker="{gone}", mic=HEADSET_MIC.id)
    assert sound.speaker_missing and not sound.mic_missing
    assert not Sound(PLUGGED).speaker_missing  # the default is never missing


def test_the_level_reads_as_a_meter_does() -> None:
    assert level_of(None) is None
    assert level_of(0.0) == 0.0
    assert level_of(1.0) == 1.0
    assert level_of(0.001) == pytest.approx(0.0)  # -60 dB: the floor
    assert level_of(0.0316) == pytest.approx(0.5, abs=0.01)  # -30 dB: half
    assert level_of(2.0) == 1.0  # clipped


def test_the_view_asks_only_for_changes() -> None:
    commands = Commands()
    view = view_with(Sound(PLUGGED, speaker=HEADSET.id), commands)
    view.set_speaker(HEADSET.id)
    view.set_my_speech(False)
    assert commands.calls == []
    view.set_speaker(None)
    view.set_mic(HEADSET_MIC.id)
    view.set_my_speech(True)
    assert commands.calls == [
        ("speaker", None),
        ("mic", HEADSET_MIC.id),
        ("my_speech", True),
    ]


def test_the_devices_are_looked_at_again() -> None:
    commands = Commands(SoundDevices())
    view = view_with(Sound(), commands)
    commands.devices = PLUGGED  # a headset plugged in
    view.look_again()
    assert view.value.devices == PLUGGED


def test_the_level_is_read_only_while_what_i_say_is_captioned() -> None:
    commands = Commands()
    commands.peak = 1.0
    view = view_with(Sound(PLUGGED), commands)
    view.read_level()
    assert view.value.level is None  # the mic isn't captioned: never asked
    view.set_my_speech(True)
    view.read_level()
    assert view.value.level == 1.0


def test_the_buffers_peak_is_its_newest_tenth_of_a_second() -> None:
    buffer = AudioBuffer()
    assert buffer.peak() is None
    loud = np.full(16000, 0.5, dtype=np.float32)
    quiet = np.full(1600, 0.01, dtype=np.float32)
    buffer.append(0.0, loud)
    buffer.append(1.0, quiet)
    assert buffer.peak() == pytest.approx(0.01)  # the loud second is older
    assert buffer.peak(0.2) == pytest.approx(0.5)


# -- the settings, and what's captured -----------------------------------------------


def test_the_devices_are_saved_by_id_and_read_leniently() -> None:
    value = AppSettings(speaker_device=HEADSET.id, mic_device=None)
    stored = value.to_stored()
    assert stored["speaker_device"] == HEADSET.id
    assert AppSettings.from_stored(stored) == value
    assert AppSettings.from_stored({"mic_device": 3}).mic_device is None
    assert AppSettings().speaker_device is None and AppSettings().mic_device is None


def _sources(pipeline: FakePipeline, settings: list[AppSettings]) -> Sources:
    """Sources whose system and mic captures name the device the settings
    chose when they start - as `main` makes them."""
    return Sources(
        pipeline,  # type: ignore[arg-type]
        ChangingAppList(),
        True,
        lambda pid, name: FakeCapture(f"app {pid}"),
        lambda: FakeCapture(f"system {settings[-1].speaker_device}"),
        lambda: FakeCapture(f"mic {settings[-1].mic_device}"),
        everything_else_capture=lambda pid: FakeCapture(f"all but {pid}"),
    )


def test_choosing_another_device_restarts_what_captures_it() -> None:
    pipeline = FakePipeline()
    settings = [AppSettings(whole_system=True, caption_mic=True)]
    sources = _sources(pipeline, settings)
    sources.follow(settings[-1])
    assert pipeline.calls == [
        "system:system:system None:False",
        "mic:mic:mic None:True",
    ]
    pipeline.calls.clear()
    settings.append(
        AppSettings(whole_system=True, caption_mic=True, mic_device="{in-2}")
    )
    sources.follow(settings[-1])
    assert pipeline.calls == ["remove:mic", "mic:mic:mic {in-2}:True"]
    pipeline.calls.clear()
    settings.append(
        AppSettings(
            whole_system=True,
            caption_mic=True,
            mic_device="{in-2}",
            speaker_device="{out-2}",
        )
    )
    sources.follow(settings[-1])
    # the mic's check listens to the same speakers: it restarts too
    assert pipeline.calls == [
        "remove:system",
        "remove:mic",
        "system:system:system {out-2}:False",
        "mic:mic:mic {in-2}:True",
    ]


def test_the_mics_peak_is_there_only_while_it_is_captured() -> None:
    pipeline = FakePipeline()
    settings = [AppSettings(whole_system=True)]
    sources = _sources(pipeline, settings)
    sources.follow(settings[-1])
    assert sources.mic_peak() is None
    settings.append(AppSettings(whole_system=True, caption_mic=True))
    sources.follow(settings[-1])
    assert sources.mic_peak() is None  # captured, nothing heard yet
    sources._buffers["mic"].append(0.0, np.full(1600, 0.25, dtype=np.float32))  # type: ignore[index]
    assert sources.mic_peak() == pytest.approx(0.25)


# -- the cards -----------------------------------------------------------------------


def card_of(view: SoundView, qapp: QApplication) -> SoundCard:
    card = SoundCard(view)
    MADE.append(card)
    card.resize(560, 400)
    card.show()
    qapp.processEvents()
    return card


def test_the_devices_are_listed_once_the_card_is_shown_not_while(
    qapp: QApplication,
) -> None:
    """Home is the first page: listing Windows' devices (4-10 ms) and filling
    both lists in the card's show held the start's first paint back
    (polyglotic-hq 400). They're listed straight after, once."""
    commands = Commands()
    listed: list[SoundDevices] = []

    def counted() -> SoundDevices:
        listed.append(commands.devices)
        return commands.devices

    commands.sound_devices = counted  # type: ignore[method-assign]
    view = view_with(Sound(), commands)
    card = SoundCard(view)
    MADE.append(card)
    card.resize(560, 400)
    card.show()
    assert listed == [] and card.speakers.count() == 1  # Windows' default only
    qapp.processEvents()
    assert len(listed) == 1 and card.speakers.count() == 3
    card.hide()
    card.show()
    qapp.processEvents()
    assert len(listed) == 1  # after that, as a list is opened


def test_the_card_lists_the_devices_and_chooses_one(qapp: QApplication) -> None:
    commands = Commands()
    view = view_with(Sound(), commands)
    card = card_of(view, qapp)  # shown: the devices looked at
    names = [card.speakers.itemText(n) for n in range(card.speakers.count())]
    assert names == [
        pc_or_mac("This PC's", "This Mac's") + " default (Speakers (Realtek Audio))",
        "Headphones (USB Headset)",
        "Speakers (Realtek Audio)",
    ]
    card.speakers.activated.emit(1)
    assert commands.calls == [("speaker", HEADSET.id)]
    assert card.speakers.currentIndex() == 1
    card.mics.activated.emit(2)
    assert view.value.mic == LAPTOP_MIC.id


def test_an_unplugged_choice_says_the_default_is_used(qapp: QApplication) -> None:
    card = card_of(view_with(Sound(PLUGGED, mic="{gone}")), qapp)
    assert card.mics.currentIndex() == 0
    assert card.mics.currentText() == pc_or_mac(
        "Not plugged in - this PC's default is used",
        "Not plugged in - this Mac's default is used",
    )


def test_what_you_hear_and_what_you_say_are_told_apart(qapp: QApplication) -> None:
    card = card_of(view_with(Sound(PLUGGED)), qapp)
    words = card.speakers_row.detail.text()
    assert pc_or_mac("Everything the PC plays", "Everything the Mac plays") in words
    assert "Apps you add" in words
    assert card.speakers.accessibleName() == "Speakers"
    assert card.mics.accessibleName() == "Microphone"
    assert card.my_speech.switch.text() == "Caption what I say"
    assert "sent to the server only while this is on" in card.my_speech.detail.text()


def test_the_meter_reads_only_while_what_i_say_is_captioned(qapp: QApplication) -> None:
    commands = Commands()
    commands.peak = 0.0316
    view = view_with(Sound(PLUGGED), commands)
    card = card_of(view, qapp)
    assert not card.levels.isActive() and card.meter.level is None
    card.my_speech.switch.click()
    assert commands.calls == [("my_speech", True)]
    assert card.levels.isActive()
    view.read_level()
    assert card.meter.level == pytest.approx(0.5, abs=0.01)
    card.hide()
    assert not card.levels.isActive()  # no timer on a page no one sees


def test_home_and_settings_show_one_state(qapp: QApplication) -> None:
    commands = Commands()
    view = view_with(Sound(PLUGGED), commands)
    home = HomePage(
        PickerView(Picker(), None),  # type: ignore[arg-type]
        QAction("Pause"),
        QAction("Lock"),
        QAction("Hide"),
        ("#4dd0e1",),
        sound=view,
    )
    MADE.append(home)
    settings = SettingsPage(
        [("margin", "Margin")],
        {},
        QAction("Tell us"),
        look=LookView(CaptionLook()),
        timing=TimingView(Timing()),
        speech=LanguagesView(SessionLanguages()),
        sound=view,
    )
    MADE.append(settings)
    assert home.sound is not None and settings.sound is not None
    # Settings > Speech: Sound first
    column = settings._section_layout("speech")
    assert column.indexOf(settings.sound) < column.indexOf(settings.speech)
    home.sound.speakers.activated.emit(1)
    assert view.value.speaker == HEADSET.id
    assert settings.sound.speakers.currentIndex() == 1
    settings.sound.my_speech.switch.click()
    assert home.sound.my_speech.switch.isChecked()


# -- as `main` wires it --------------------------------------------------------------


def test_the_hub_saves_the_choices_and_captions_what_i_say(qapp: QApplication) -> None:
    built = Built(MemorySettingsStore({"apps": ["Chat.exe"]}))
    try:
        hub = built.hub
        hub.list_devices = lambda: PLUGGED
        assert hub.home.sound is not None and hub.settings.sound is not None
        hub.sound.look_again()
        hub.sound.set_mic(HEADSET_MIC.id)
        hub.sound.set_speaker(HEADSET.id)
        value = built.desktop.settings.value
        assert (value.mic_device, value.speaker_device) == (HEADSET_MIC.id, HEADSET.id)
        assert hub.sound.value.mic == HEADSET_MIC.id  # followed back
        hub.sound.set_my_speech(True)
        assert built.desktop.caption_mic.isChecked()
        hub.sound.set_mic(None)  # back to Windows' default
        assert built.desktop.settings.value.mic_device is None
    finally:
        built.close()


def test_a_device_plugged_in_later_is_in_the_list_when_it_opens(
    qapp: QApplication,
) -> None:
    commands = Commands(SoundDevices((SPEAKERS,), (LAPTOP_MIC,), SPEAKERS.id))
    card = card_of(view_with(Sound(), commands), qapp)
    assert card.mics.count() == 2
    commands.devices = PLUGGED  # a headset plugged in
    QTest.mouseClick(card.mics, Qt.MouseButton.LeftButton)
    card.mics.hidePopup()
    assert card.mics.count() == 3
