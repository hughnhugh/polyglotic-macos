"""Settings across versions (polyglotic-hq RELEASING.md section 5; project
132): the build before the switch-over (`main` at #154, 2026-11-07) run
after this one still reads the settings file and loses nothing - every
key it knew is still there, with the value it reads back - and this one,
run again after it, finds its windows' choices as they were.

The older build's reader is the one here: `AppSettings.from_stored` and
its checks didn't change at the switch-over (only `look()` and
`target_languages` went), and saving keeps the keys a version doesn't know
(G11). Made-up apps; settings in a temporary folder."""

import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
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

ROOT = Path(__file__).resolve().parents[2]
LAST_RELEASE_REF = "c51062c4a"  # Release 0.1.12 (#1205)

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
RETIRED = ("translate_live",)
"""Keys this build no longer writes: live translation is always on (810), and
the build before reads the key's default, True, so it loses nothing."""


def older_keys(values: dict[str, object]) -> dict[str, object]:
    """The keys the build before the switch-over knew. Its reader here is
    this build's, which knows settings added since (`everything_else`,
    polyglotic-hq 139); the older build keeps them as they are (G11)."""
    return {k: values[k] for k in BEFORE_THE_SWITCH if k not in RETIRED}


def test_every_key_before_the_switch_is_still_a_setting() -> None:
    known = set(AppSettings().to_stored())
    assert set(BEFORE_THE_SWITCH) - set(RETIRED) <= known
    stored = AppSettings.from_stored(BEFORE_THE_SWITCH).to_stored()
    # all valid: none read as its default (keys added since are this build's)
    assert older_keys(stored) == older_keys(BEFORE_THE_SWITCH)


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
    unchanged = set(BEFORE_THE_SWITCH) - set(changed) - set(RETIRED)
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


def _extract_release_src(ref: str, dest: Path) -> Path:
    """Extract `src/polyglotic_desktop` at git commit `ref` into `dest`."""
    try:
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        archived = subprocess.run(
            ["git", "archive", "--format=tar", ref, "src/polyglotic_desktop"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        message = (
            f"cannot load {ref} from git (git missing or a shallow/snapshot checkout): "
            f"{exc}"
        )
        if os.environ.get("GITHUB_REPOSITORY", "").endswith("/polyglotic-desktop"):
            pytest.fail(message)
        pytest.skip(message)
    with tarfile.open(fileobj=io.BytesIO(archived.stdout)) as archive:
        archive.extractall(dest, filter="data")
    return dest / "src"


_ROLLBACK_CHECK_SCRIPT = """
import json
import sys
from dataclasses import fields, replace
from pathlib import Path

old_src, in_path, out_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(old_src))
import polyglotic_desktop
from polyglotic_desktop.ui.settings import _INVALID, _valid, AppSettings

loaded_from = Path(polyglotic_desktop.__file__).resolve()
assert loaded_from.is_relative_to(old_src), loaded_from

stored = json.loads(in_path.read_text(encoding="utf-8"))
defaults = AppSettings()
rejected = {
    f.name: stored[f.name]
    for f in fields(AppSettings)
    if f.name in stored and _valid(f.name, stored[f.name], getattr(defaults, f.name)) is _INVALID
}
assert not rejected, f"0.1.12 rejected existing keys: {rejected}"

value = AppSettings.from_stored(stored)
known = {f.name for f in fields(AppSettings)}
unknown = {k: v for k, v in stored.items() if k not in known}
changed = replace(value, transcript_ask_at_quit=not value.transcript_ask_at_quit)
saved = {**unknown, **changed.to_stored()}
out_path.write_text(json.dumps(saved), encoding="utf-8")
print(json.dumps({
    "hotkeys": value.hotkeys,
    "dictation_key": value.dictation_key,
    "respeak_key": value.respeak_key,
    "last_respeak_key": value.last_respeak_key,
    "theme": value.theme,
    "window_theme": value.window_theme,
    "learning": value.learning,
    "opacity": value.opacity,
    "caption_mode_chosen": value.caption_mode_chosen,
    "japanese_reading": value.japanese_reading,
    "video_lines_shown": value.video_lines_shown,
    "type_what": value.type_what,
    "saved_hotkeys": saved["hotkeys"],
    "unknown_keys": sorted(unknown),
}))
"""


def _run_release_reader(
    old_src: Path, stored: dict[str, object], tmp_path: Path, stem: str
) -> tuple[dict[str, object], dict[str, object]]:
    in_path = tmp_path / f"{stem}_in.json"
    out_path = tmp_path / f"{stem}_out.json"
    in_path.write_text(json.dumps(stored), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(old_src)}
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            _ROLLBACK_CHECK_SCRIPT,
            str(old_src),
            str(in_path),
            str(out_path),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, (
        f"0.1.12 reader failed:\nSTDOUT:\n{done.stdout}\nSTDERR:\n{done.stderr}"
    )
    report = json.loads(done.stdout)
    after = json.loads(out_path.read_text(encoding="utf-8"))
    return report, after


def test_rollback_to_0_1_12_keeps_hotkeys_and_settings_and_round_trips(
    tmp_path: Path,
) -> None:
    """0.1.12 (`c51062c4a`) reading a settings file written by 0.1.13 must
    accept every existing key without resetting `hotkeys` or hold keys, and
    saving an unrelated change in 0.1.12 must preserve every 0.1.13 choice."""
    old_src = _extract_release_src(LAST_RELEASE_REF, tmp_path / "v0_1_12")
    legacy_hotkeys = {
        "lock": "ctrl+alt+l",
        "pause": "f9",
        "copy": "ctrl+alt+c",
        "live": "space",
        "smaller": "",
    }
    new_only_hotkeys = {
        "hide": "space",
        "bigger": "a",
        "preset": "media_play",
        "bar": "ctrl+alt+comma",
    }
    all_hotkeys = {**legacy_hotkeys, **new_only_hotkeys}
    scopes = {"hide": "app", "bigger": "everywhere", "pause": "app"}

    # Case 1: 0.1.13-only typing/media/punctuation hotkeys and hold keys.
    v13_new_keys = AppSettings.from_stored(
        {
            "hotkeys": all_hotkeys,
            "hotkey_scopes": scopes,
            "dictation_key": "semicolon",
            "respeak_key": "media_play",
            "last_respeak_key": "ctrl+alt+comma",
            "learning": "zh",
            "theme": "glaze",
            "window_theme": "light",
            "opacity": 0.8,
            "caption_mode_chosen": "steady",
            "japanese_reading": "romaji",
            "video_lines_shown": 1,
            "type_theirs": True,
            "type_what": "translation",
            "transcript_ask_at_quit": True,
        }
    )
    assert v13_new_keys.hotkeys == all_hotkeys
    assert v13_new_keys.hotkey_scopes == scopes
    assert v13_new_keys.dictation_key == "semicolon"
    assert v13_new_keys.respeak_key == "media_play"
    assert v13_new_keys.last_respeak_key == "ctrl+alt+comma"

    report, after = _run_release_reader(
        old_src, v13_new_keys.to_stored(), tmp_path, "new_keys"
    )
    assert report["hotkeys"] == legacy_hotkeys
    assert report["saved_hotkeys"] == legacy_hotkeys
    assert report["theme"] == "glaze"
    assert report["window_theme"] == "light"
    assert report["learning"] == "zh"
    assert report["opacity"] == 0.8
    assert report["caption_mode_chosen"] == "steady"
    assert report["japanese_reading"] == "romaji"
    assert report["video_lines_shown"] == 1
    assert report["type_what"] == "translation"

    reopened = AppSettings.from_stored(after)
    assert reopened.hotkeys == all_hotkeys
    assert reopened.hotkey_scopes == scopes
    assert reopened.dictation_key == "semicolon"
    assert reopened.respeak_key == "media_play"
    assert reopened.last_respeak_key == "ctrl+alt+comma"
    assert reopened.transcript_ask_at_quit is False  # changed in 0.1.12

    # Case 2: 0.1.12-valid hold keys survive alongside 0.1.13-only hotkeys.
    v13_legacy_hold = AppSettings.from_stored(
        {
            "hotkeys": all_hotkeys,
            "hotkey_scopes": scopes,
            "dictation_key": "f10",
            "respeak_key": "f7",
            "last_respeak_key": "f7",
        }
    )
    report2, after2 = _run_release_reader(
        old_src, v13_legacy_hold.to_stored(), tmp_path, "legacy_hold"
    )
    assert report2["hotkeys"] == legacy_hotkeys
    assert report2["dictation_key"] == "f10"
    assert report2["respeak_key"] == "f7"
    assert report2["last_respeak_key"] == "f7"

    reopened2 = AppSettings.from_stored(after2)
    assert reopened2.hotkeys == all_hotkeys
    assert reopened2.dictation_key == "f10"
    assert reopened2.respeak_key == "f7"
    assert reopened2.last_respeak_key == "f7"


def test_resetting_v2_keys_in_settings_does_not_leave_stale_values(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Clearing or replacing 0.1.13-only hotkeys or hold keys through `Settings`
    must clear the add-only v2 keys too, rather than letting `_unknown` keep
    old values alive on disk."""
    store = JsonSettingsStore(tmp_path / "settings.json")
    try:
        settings = Settings(store)
        settings.update(
            hotkeys={"lock": "ctrl+alt+l", "hide": "space"},
            hotkey_scopes={"hide": "app"},
            dictation_key="semicolon",
            respeak_key="media_play",
            last_respeak_key="ctrl+alt+comma",
        )
        store.flush()
        reloaded = AppSettings.from_stored(store.load())
        assert reloaded.hotkeys == {"lock": "ctrl+alt+l", "hide": "space"}
        assert reloaded.dictation_key == "semicolon"
        assert reloaded.respeak_key == "media_play"
        assert reloaded.last_respeak_key == "ctrl+alt+comma"

        settings.update(
            hotkeys={},
            hotkey_scopes={},
            dictation_key="f9",
            respeak_key="f7",
            last_respeak_key="f7",
        )
        store.flush()
        after_reset = AppSettings.from_stored(store.load())
        assert after_reset.hotkeys == {}
        assert after_reset.hotkey_scopes == {}
        assert after_reset.dictation_key == "f9"
        assert after_reset.respeak_key == "f7"
        assert after_reset.last_respeak_key == "f7"
    finally:
        store.close()
