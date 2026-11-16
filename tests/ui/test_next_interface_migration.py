"""Today's caption settings moved to each caption window's own (project
109's build step 6), with the caption windows and today's settings
writing the same file: it runs once, today's keys stay, and whichever
interface runs next loses nothing (117 Low 9 and 13: the second writer)."""

from pathlib import Path

from PySide6.QtWidgets import QApplication
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.adapters.json_settings import JsonSettingsStore
from polyglotic_desktop.core.listening.sources import MIC, SourceId
from polyglotic_desktop.ports.settings import SettingsStore
from polyglotic_desktop.ui.settings import Settings
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.transcripts import Transcripts
from polyglotic_desktop.ui_next.views.caption_window import STORED_KEY
from polyglotic_desktop.ui_next.views.placement import Preset, Rect
from polyglotic_desktop.ui_next.views.transcript import STORED_KEY as TRANSCRIPTS_KEY
from polyglotic_desktop.ui_next.views.transcript import TranscriptChoices

TODAY = {
    "targets": ["zh", "en"],
    "text_scale": 1.3,
    "caption_mic": True,
    "overlay_position": "custom",
    "overlay_geometry": {"zh": [100, 200, 700, 260], "en": [100, 500, 700, 260]},
    "apps": ["Chat App", "Video Player"],
}
SCREEN = [Rect(0, 0, 1920, 1040)]


def windows_on(store: SettingsStore) -> CaptionWindows:
    return CaptionWindows(store, MIC, lambda: SCREEN)


def test_it_is_saved_at_once_beside_todays_keys(qapp: QApplication) -> None:
    store = MemorySettingsStore(TODAY)
    windows = windows_on(store)
    saved = store.load()
    assert set(saved[STORED_KEY]["windows"]) == {"Chat App", "Video Player"}  # type: ignore[index]
    assert {k: v for k, v in saved.items() if k != STORED_KEY} == TODAY
    windows.close()


def test_the_windows_open_with_todays_values(qapp: QApplication) -> None:
    store = MemorySettingsStore(TODAY)
    windows = windows_on(store)
    windows.set_captioned(
        [("Chat App", SourceId("app-1")), ("Video Player", SourceId("app-2"))]
    )
    first, second = windows.windows["Chat App"], windows.windows["Video Player"]
    assert first.choices.translate_into == second.choices.translate_into == "zh"
    assert first.choices.show_mic and second.choices.show_mic
    assert first.choices.text_size == second.choices.text_size == 1.3
    assert first.choices.geometry == Rect(100, 200, 700, 260)
    assert second.choices.preset is Preset.BOTTOM_CENTRE
    windows.close()


def test_it_runs_once(qapp: QApplication) -> None:
    """Today's interface ran in between and changed its settings: the
    windows keep what they were given (and anything changed since)."""
    store = MemorySettingsStore(TODAY)
    windows_on(store).close()
    today = Settings(store)
    today.update(targets=("ja",), caption_mic=False, text_scale=0.8)
    again = windows_on(store)
    choices = again.stored.by_key["Chat App"]
    assert (choices.translate_into, choices.show_mic, choices.text_size) == (
        "zh",
        True,
        1.3,
    )
    again.close()


def test_todays_interface_running_next_loses_nothing(qapp: QApplication) -> None:
    store = MemorySettingsStore(TODAY)
    windows = windows_on(store)
    windows.set_captioned([("Chat App", SourceId("app-1"))])
    windows.windows["Chat App"].set_language("")  # Original only
    windows.save_now()
    windows.close()
    mine = store.load()[STORED_KEY]
    today = Settings(store)  # today's interface starts, and saves a change
    assert today.value.targets == ("zh", "en")
    assert today.value.caption_mic and today.value.text_scale == 1.3
    today.update(opacity=0.5)
    assert store.load()[STORED_KEY] == mine  # the windows' own kept
    again = windows_on(store)  # the new interface runs next
    assert again.stored.by_key["Chat App"].translate_into == ""
    again.close()


def test_nothing_picked_today_saves_nothing_until_a_window_opens(
    qapp: QApplication,
) -> None:
    """With no source today, the first window opened takes today's values
    (place and my speech too), and that is saved."""
    store = MemorySettingsStore({**TODAY, "apps": []})
    windows = windows_on(store)
    assert STORED_KEY not in store.load()
    windows.set_captioned([("system", SourceId("system"))])
    window = windows.windows["system"]
    assert window.choices.show_mic and window.choices.geometry == Rect(
        100, 200, 700, 260
    )
    windows.save_now()
    assert "system" in store.load()[STORED_KEY]["windows"]  # type: ignore[index]
    windows.close()


def test_a_save_while_the_file_cant_be_read_keeps_every_writers_newest_values(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Three writers on one file - today's settings, the caption windows,
    the transcripts - each re-reading it before a save. The file unreadable
    for a moment (locked, half-written by something else): a writer saving
    then builds on the newest state, not on its own older copy, which would
    bring back another writer's earlier value (project 128, 2026-11-07:
    a window set to Original only went back to its language)."""
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(TODAY)
    today = Settings(store)
    windows = windows_on(store)
    transcripts = Transcripts(windows, store, areas=lambda: SCREEN)
    windows.set_captioned([("Chat App", SourceId("app-1"))])
    windows.save_now()
    today.update(opacity=0.5)  # today's reads the windows' key as it is now
    transcripts.follow()
    transcripts.stored.by_key["Chat App"] = TranscriptChoices(text_size=1.4)
    transcripts.save_now()  # the transcripts read the windows' key as it is now
    windows.windows["Chat App"].set_language("")  # Original only, saved
    windows.save_now()
    store.path.write_text("{", encoding="utf-8")  # unreadable for a moment
    today.update(opacity=0.7)
    store.path.write_text("{", encoding="utf-8")
    transcripts.save_now()
    saved = store.load()
    assert saved["opacity"] == 0.7 and saved["targets"] == ["zh", "en"]
    assert saved[STORED_KEY]["windows"]["Chat App"]["translate_into"] == ""  # type: ignore[index]
    assert saved[TRANSCRIPTS_KEY]["Chat App"]["text_size"] == 1.4  # type: ignore[index]
    transcripts.close()
    windows.close()
