"""English as the second line by default (polyglotic-hq 555; the user,
2026-11-20: "Default secondary language caption to english once their
language has been selected", and "this feels like the premium feature so
I opt in by default").

A learner reading captions in a language other than English sees what is
already said in that language translated into English; one reading
English sees no second line. A choice - another language, or none - is
kept; the default isn't written as one, so it can change for everyone
who never chose (a paid feature later, the user's word). The files in
`settings_files/` are what 0.1.9 and 0.1.10-preview.1 saved (polyglotic-hq
project 555's `work/make_settings_files.py`)."""

import json
from pathlib import Path

import pytest
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.connection import listening as connection
from polyglotic_desktop.core.listening.captions import Language
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.main import (
    languages_settings,
    listening_settings,
    second_language_chosen,
    second_languages,
    second_languages_changes,
    session_languages,
)
from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.settings import AppSettings, Settings
from polyglotic_desktop.ui_next.views.panels import LanguagesView

FILES = Path(__file__).parent / "settings_files"
VERSIONS = ("0.1.9", "0.1.10-preview.1")
EN, JA, ZH = Language("en"), Language("ja"), Language("zh")
APP = SourceId("app-1")


def saved_by(version: str, learner: str) -> dict[str, object]:
    files = json.loads((FILES / f"{version}.json").read_text(encoding="utf-8"))
    return dict(files[learner])


def test_a_learner_reading_english_has_no_second_line() -> None:
    new = AppSettings()
    assert new.second_language_of("en") is None
    assert listening_settings(new).second_languages == {}


def test_a_learner_reading_another_language_has_english_under_it() -> None:
    value = AppSettings(targets=("ja",))
    assert value.second_language_of("ja") == "en"
    chosen = listening_settings(value)
    assert chosen.second_languages == {JA: EN}
    sent = connection.settings(chosen, limit=2)
    assert list(sent.targets) == ["ja"] and sent.second_languages == {"ja": "en"}
    assert value.second_languages == {}  # the default isn't written as a choice


def test_a_windows_own_language_has_english_under_it_too() -> None:
    """A caption window into French: the session's target is French, and
    its lines already in French come in English."""
    chosen = listening_settings(AppSettings(), own={APP: (Language("fr"),)})
    sent = connection.settings(chosen, limit=2)
    assert sent.second_languages == {"fr": "en"}
    # every window, whichever language it switches to (`follow_settings`)
    shown = second_languages(AppSettings())
    assert shown[Language("fr")] == shown[ZH] == shown[Language("zh-hant")] == EN
    assert EN not in shown


def test_none_chosen_is_kept() -> None:
    store = MemorySettingsStore({"targets": ["ja"]})
    settings = Settings(store)
    settings.update(**second_languages_changes(settings.value, {"ja": ""}))
    assert store.values["no_second_language"] == ["ja"]
    again = Settings(MemorySettingsStore(store.values)).value
    assert again.second_language_of("ja") is None
    assert listening_settings(again).second_languages == {}
    # English chosen back: the default again, not kept as a choice
    settings.update(**second_languages_changes(settings.value, {"ja": "en"}))
    assert settings.value.second_language_of("ja") == "en"
    assert store.values["no_second_language"] == []
    assert store.values["second_languages"] == {}


def test_another_language_chosen_is_kept() -> None:
    value = AppSettings(targets=("ja",), second_languages={"ja": "zh"})
    assert listening_settings(value).second_languages == {JA: ZH}


def test_the_languages_panel_shows_english_and_keeps_none() -> None:
    value = AppSettings(targets=("ja",))
    languages = session_languages(value, ["ja", "en"])
    assert languages.second_languages == {"ja": "en"}  # English's own: none
    unchanged = languages_settings(value, languages)
    assert unchanged["second_languages"] == {}
    assert unchanged["no_second_language"] == ()
    view = LanguagesView(languages)
    view.set_second("ja", None)
    changes = languages_settings(value, view.value)
    assert changes["no_second_language"] == ("ja",)
    view.set_second("ja", "ko")
    assert languages_settings(value, view.value)["second_languages"] == {"ja": "ko"}


@pytest.mark.parametrize("version", VERSIONS)
def test_a_file_from_before_gets_english_under_its_language(version: str) -> None:
    """Japanese captions, nothing chosen for their lines already in
    Japanese (an older version kept none as nothing): English now."""
    stored = saved_by(version, "ja_chinese")
    assert stored["targets"] == ["ja"] and stored["second_languages"] == {}
    value = AppSettings.from_stored(stored)
    assert listening_settings(value).second_languages == {JA: EN}
    english = AppSettings.from_stored(saved_by(version, "en_chinese"))
    assert listening_settings(english).second_languages == {}


def test_settings_can_edit_a_second_language_the_bar_saved() -> None:
    settings = Settings(MemorySettingsStore({"targets": ["ja"]}))
    settings.update_from_bar(**second_language_chosen(settings.value, "ja", "fr"))
    view = LanguagesView(session_languages(settings.value, ["ja"]))
    assert view.value.second_languages == {"ja": "fr"}
    view.set_second("ja", None)
    settings.update(**languages_settings(settings.value, view.value))
    assert settings.value.second_language_of("ja") is None
    assert use_presets.edits(settings.value) == ("preset_second_languages",)
    assert use_presets.discarded(settings.value).second_language_of("ja") == "fr"
