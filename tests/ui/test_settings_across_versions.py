"""Settings across versions (polyglotic-hq RELEASING.md section 5; project
132): the build before the switch-over (`main` at #154, 2026-11-07) run
after this one still reads the settings file and loses nothing - every
key it knew is still there, with the value it reads back - and this one,
run again after it, finds its windows' choices as they were.

The older build's reader is the one here: `AppSettings.from_stored` and
its checks didn't change at the switch-over (only `look()` and
`target_languages` went), and saving keeps the keys a version doesn't know
(G11). Made-up apps; settings in a temporary folder."""

from pathlib import Path

from PySide6.QtWidgets import QApplication
from tests.ui.fakes import FakeAppList

from polyglotic_desktop.adapters.json_settings import JsonSettingsStore
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.main import new_interface
from polyglotic_desktop.ui.app import DesktopApp
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next.views.caption_window import STORED_KEY
from polyglotic_desktop.ui_next.views.transcript import STORED_KEY as TRANSCRIPTS_KEY
from polyglotic_desktop.ui_next.views.transcript import TranscriptChoices

BEFORE_THE_SWITCH = {
    # every key the build before the switch-over knew, none at its default
    "learning": "zh",
    "targets": ["ja", "en"],
    "second_languages": {"ja": "en"},
    "spoken_language": "zh",
    "translate_live": False,
    "spelling_hints": ["Caleb"],
    "show_original": False,
    "word_links": "colours",
    "link_detail": "key",
    "text_scale": 1.3,
    "opacity": 0.6,
    "show_language": False,
    "fade_after": None,
    "caption_timing": "live",
    "live_update_interval": 2.0,
    "common_words_only": False,
    "locked": True,
    "overlay_geometry": {"ja": [100, 200, 700, 260]},
    "caption_font": "Georgia",
    "original_color": "#cfe8ff",
    "translation_color": "#ffb347",
    "background_color": "#1b2a41",
    "overlay_position": "custom",
    "overlay_width": 0.6,
    "theme": "glaze",
    "window_theme": "light",
    "whole_system": False,
    "apps": ["Video Player"],
    "caption_mic": True,
    "source_names": {"Video Player": "Films"},
    "source_colors": {"Video Player": "#ff6e9c"},
    "show_source": False,
}
OWNED_BY_THE_OLDER_BUILD = (  # the new interface reads them, never writes them
    "targets",
    "text_scale",
    "overlay_geometry",
    "overlay_position",
    "overlay_width",
)
PLAYER = SourceId("app-10")


def older_keys(values: dict[str, object]) -> dict[str, object]:
    """The keys the build before the switch-over knew. Its reader here is
    this build's, which knows settings added since (`everything_else`,
    polyglotic-hq 139); the older build keeps them as they are (G11)."""
    return {k: values[k] for k in BEFORE_THE_SWITCH}


def test_every_key_before_the_switch_is_still_a_setting() -> None:
    known = set(AppSettings().to_stored())
    assert set(BEFORE_THE_SWITCH) <= known
    stored = AppSettings.from_stored(BEFORE_THE_SWITCH).to_stored()
    # all valid: none read as its default (keys added since are this build's)
    assert older_keys(stored) == BEFORE_THE_SWITCH


def test_the_build_before_the_switch_runs_after_this_one_and_loses_nothing(
    qapp: QApplication, tmp_path: Path
) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(BEFORE_THE_SWITCH)  # a learner of the older build

    # this build runs: the settings migrated, then changed in the new interface
    desktop = DesktopApp(store, None, FakeAppList())
    built = new_interface(desktop, store, None, per_app=True)
    assert built.windows.preset_menu.video_lines_shown == 2
    built.windows.video_lines_wanted.emit(1)
    built.windows.set_captioned([("Video Player", PLAYER)])
    built.windows.windows["Video Player"].set_language("ko")
    built.hub.picker.add("Web Browser")
    built.panels.look.set_opacity(0.8)
    built.panels.timing.set_mode(CaptionMode.WHOLE)
    built.hub.settings.theme_chosen.emit("signal")
    desktop.lock_windows.setChecked(False)
    built.transcripts.follow()
    built.transcripts.stored.by_key["Video Player"] = TranscriptChoices(text_size=1.4)
    built.transcripts.save_now()
    built.close()
    desktop.close()
    saved = store.load()
    assert STORED_KEY in saved and TRANSCRIPTS_KEY in saved  # the new keys
    for key in OWNED_BY_THE_OLDER_BUILD:
        assert saved[key] == BEFORE_THE_SWITCH[key], key
    changed = {
        "apps": ["Video Player", "Web Browser"],
        "source_colors": {"Video Player": "#ff6e9c", "Web Browser": "#4dd0e1"},
        "opacity": 0.8,
        "caption_timing": "steady",
        "caption_mode_chosen": "steady",  # chosen in the Timing panel (176)
        "theme": "signal",
        "locked": False,
    }
    assert {k: saved[k] for k in changed} == changed
    unchanged = set(BEFORE_THE_SWITCH) - set(changed)
    assert {k: saved[k] for k in unchanged} == {
        k: BEFORE_THE_SWITCH[k] for k in unchanged
    }

    # the older build runs next: it reads every key back as written
    older = Settings(store)
    assert older_keys(older.value.to_stored()) == older_keys(saved)
    older.update(opacity=0.5)  # and saves a change
    after = store.load()
    assert after["video_lines_shown"] == 1
    assert after[STORED_KEY] == saved[STORED_KEY]  # the windows' choices kept
    assert after[TRANSCRIPTS_KEY] == saved[TRANSCRIPTS_KEY]

    # this build again: its windows as they were
    reopened = DesktopApp(store, None, FakeAppList())
    again = new_interface(reopened, store, None, per_app=True)
    assert again.windows.stored.by_key["Video Player"].translate_into == "ko"
    assert again.windows.preset_menu.video_lines_shown == 1
    again.close()
    reopened.close()
