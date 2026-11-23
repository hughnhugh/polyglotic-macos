"""Presets for use cases (polyglotic-hq 556, decision 0264): picking one
writes its values; a new install starts on Everyday; a setup from before
presets becomes Custom with nothing lost. A change applies at once and
leaves the preset edited until it's saved, saved as a new one or discarded
(587, decision 0283)."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.settings import BUILT_INS, AppSettings, Settings
from polyglotic_desktop.ui.use_presets import (
    CONVERSATION,
    CUSTOM,
    EVERYDAY,
    LEARNING,
    VIDEO,
)


def _settings(stored: Mapping[str, object] | None = None) -> Settings:
    return Settings(MemorySettingsStore(dict(stored or {})))


def test_a_new_install_starts_on_everyday_with_nothing_changed() -> None:
    settings = _settings()
    assert settings.value.preset == EVERYDAY
    assert settings.value.preset_values == {} and settings.value.own_presets == ()


def test_a_file_from_before_presets_with_nothing_chosen_is_everyday() -> None:
    value = _settings({"changed": [], "theme": "glaze"}).value  # not a preset's
    assert value.preset == EVERYDAY and CUSTOM not in value.own_presets


def test_picking_video_sets_its_subtitles_and_takes_links_and_readings_off() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    value = settings.value
    assert value.preset == VIDEO
    assert value.subtitles and value.word_links == "off"
    assert (
        value.reading_lines == () and "reading_lines" in value.changed
    )  # none, chosen
    assert not value.show_source and not value.show_language
    assert value.my_speech is False
    # Video originals and translations are both live by default.
    assert value.caption_mode_chosen == "live" and value.steady_cards


def test_a_change_in_a_preset_saved_into_it_comes_back() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.update(word_links="arrows", subtitle_size=2.0)  # links on, in Video
    settings.change(use_presets.saved_into(settings.value))  # Save to Video
    assert settings.value.preset_values[VIDEO] == {
        "word_links": "arrows",
        "subtitle_size": 2.0,
    }
    settings.change(use_presets.chosen(settings.value, CONVERSATION))
    assert settings.value.word_links == "hover"  # Conversation's own
    assert not settings.value.subtitles
    settings.change(use_presets.chosen(settings.value, VIDEO))
    assert settings.value.word_links == "arrows"  # as it was left
    assert settings.value.subtitle_size == 2.0


def test_a_saved_change_is_in_the_file_at_once() -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.change(use_presets.chosen(settings.value, LEARNING))
    settings.update(translation_after=3.5)
    settings.change(use_presets.saved_into(settings.value))
    saved = store.load()
    assert saved["preset"] == LEARNING
    assert saved["preset_values"] == {LEARNING: {"translation_after": 3.5}}
    again = Settings(store).value  # read again: the same
    assert again.preset == LEARNING and again.translation_after == 3.5
    assert again.caption_path == "acquisition"


def test_a_preset_takes_everydays_colours_unless_it_names_them() -> None:
    settings = _settings()
    settings.update(translation_color="#5ee3ff", opacity=0.9)  # in Everyday
    settings.change(use_presets.saved_into(settings.value))
    settings.change(use_presets.chosen(settings.value, VIDEO))
    assert settings.value.translation_color == "#5ee3ff"  # Everyday's
    assert settings.value.opacity == 0.0  # Video names its panel: none


def test_a_file_from_before_presets_becomes_custom_with_nothing_lost() -> None:
    old = {  # 0.1.9's: a record of changes, links turned off, a colour picked
        "changed": ["word_links", "translation_color", "show_source"],
        "word_links": "off",
        "translation_color": "#5ee3ff",
        "show_source": False,
        "fade_after": 8.0,  # 0.1.7 and before kept every key as chosen too
    }
    value = _settings(old).value
    assert value.preset == CUSTOM and value.own_presets == (CUSTOM,)
    assert value.word_links == "off" and value.translation_color == "#5ee3ff"
    assert value.preset_values[CUSTOM] == {
        "word_links": "off",
        "translation_color": "#5ee3ff",
        "show_source": False,
        "fade_after": 8.0,
    }
    # and Conversation, picked and left, gives it all back
    settings = _settings(old)
    settings.change(use_presets.chosen(settings.value, CONVERSATION))
    assert settings.value.word_links == "hover" and settings.value.show_source
    settings.change(use_presets.chosen(settings.value, CUSTOM))
    assert settings.value.word_links == "off" and not settings.value.show_source


def test_a_setting_that_follows_the_default_keeps_following_it() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))  # names word links
    settings.change(use_presets.chosen(settings.value, EVERYDAY))
    assert "word_links" not in settings.value.changed  # follows the app's again
    assert "reading_lines" not in settings.value.changed
    assert settings.value.word_links == AppSettings().word_links


def test_readings_all_off_in_everyday_is_kept_as_a_choice() -> None:
    settings = _settings()
    settings.update(reading_lines=("zh",))
    settings.update(reading_lines=())  # every reading off: a choice, at ()
    settings.change(use_presets.saved_into(settings.value))
    assert "reading_lines" in settings.value.preset_values[EVERYDAY]
    settings.change(use_presets.chosen(settings.value, LEARNING))
    settings.change(use_presets.chosen(settings.value, EVERYDAY))
    assert "reading_lines" in settings.value.changed  # still none, not the default


def test_reset_drops_what_was_changed_in_it() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.update(opacity=0.8, subtitle_width=0.6)
    settings.change(use_presets.saved_into(settings.value))
    assert use_presets.restorable(settings.value, VIDEO)
    settings.change(use_presets.reset(settings.value, VIDEO))
    assert settings.value.opacity == 0.0 and settings.value.subtitle_width == 0.8
    assert VIDEO not in settings.value.preset_values


def test_an_own_preset_is_a_copy_named_and_chosen() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.update(word_links="arrows")
    settings.change(use_presets.added(settings.value, "Anime"))
    value = settings.value
    assert value.preset == "own1" and value.own_presets == ("own1",)
    assert value.preset_names["own1"] == "Anime"
    assert value.subtitles and value.word_links == "arrows"  # Video as it was
    assert use_presets.edits(value) == ()  # saved, in the new one
    assert VIDEO not in value.preset_values  # and Video as it was saved
    settings.change(use_presets.chosen(value, EVERYDAY))
    settings.change(use_presets.chosen(settings.value, "own1"))
    assert settings.value.subtitles and settings.value.word_links == "arrows"
    settings.change(use_presets.removed(settings.value, "own1"))
    assert settings.value.preset == EVERYDAY and settings.value.own_presets == ()
    assert not settings.value.subtitles


def test_no_more_than_five_of_ones_own() -> None:
    value = AppSettings()
    for n in range(7):
        value = use_presets.added(value, f"Mine {n}")
    assert len(value.own_presets) == use_presets.OWN_MOST


def test_a_rename_and_back_to_its_own_name() -> None:
    value = use_presets.renamed(AppSettings(), VIDEO, "  Films  ")
    assert value.preset_names == {VIDEO: "Films"}
    assert use_presets.renamed(value, VIDEO, "").preset_names == {}


def test_a_rollbacks_change_is_kept_in_the_windows_not_saved() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    stored = settings.value.to_stored()
    stored["opacity"] = 0.7  # an older version moved the panel after a rollback
    value = _settings(stored).value
    assert value.preset == VIDEO and value.opacity == 0.7  # nothing lost
    assert VIDEO not in value.preset_values  # Video as saved
    assert use_presets.edits(value) == ("opacity",)


def test_stored_presets_not_valid_are_dropped() -> None:
    stored = {
        "preset": "own9",  # no such preset
        "preset_values": {
            VIDEO: {"opacity": "solid", "word_links": "arrows", "theme": "glaze"},
            "nobody": {"opacity": 0.5},
        },
        "preset_names": {VIDEO: "  ", LEARNING: "Study"},
    }
    value = _settings(stored).value
    assert value.preset == EVERYDAY
    assert value.preset_values == {VIDEO: {"word_links": "arrows"}}  # the valid
    assert value.preset_names == {LEARNING: "Study"}


def test_every_preset_setting_is_a_setting() -> None:
    names = set(AppSettings.__dataclass_fields__)
    assert set(use_presets.PRESET_SETTINGS) <= names
    for named in use_presets.BUILT_IN.values():
        assert set(named) <= set(use_presets.PRESET_SETTINGS)
        replace(AppSettings(), **named)  # type: ignore[arg-type]  # each takes it


# -- saving on purpose (587, decision 0283) ---------------------------------------------


def test_a_change_leaves_the_preset_as_saved_until_its_saved() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, LEARNING))
    settings.update(word_links="hover", fade_after=6.0, opacity=0.5)
    value = settings.value
    assert value.word_links == "hover" and value.opacity == 0.5  # on screen now
    assert LEARNING not in value.preset_values  # the preset as it was
    assert use_presets.edits(value) == ("fade_after", "word_links", "opacity")
    settings.change(use_presets.saved_into(value))  # Save to Learning
    assert use_presets.edits(settings.value) == ()
    assert settings.value.preset_values[LEARNING] == {
        "word_links": "hover",
        "fade_after": 6.0,
        "opacity": 0.5,
    }


def test_discard_takes_the_windows_back_to_the_preset_as_saved() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.update(word_links="arrows")
    settings.change(use_presets.discarded(settings.value))
    value = settings.value
    assert value.word_links == "off" and use_presets.edits(value) == ()
    assert "word_links" in value.changed  # Video's off, still a choice


def test_save_as_makes_a_new_preset_and_switches_to_it() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, LEARNING))
    settings.update(fade_after=6.0)
    settings.change(use_presets.added(settings.value, "Learning 2"))
    value = settings.value
    assert value.preset == "own1" and value.preset_names["own1"] == "Learning 2"
    assert value.fade_after == 6.0 and value.caption_path == "acquisition"
    assert use_presets.edits(value) == ()  # saved in the new one
    assert LEARNING not in value.preset_values  # Learning as it was saved
    settings.change(use_presets.chosen(value, LEARNING))
    assert settings.value.fade_after == AppSettings().fade_after


def test_switching_drops_changes_not_saved_and_undo_gives_them_back() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, LEARNING))
    settings.update(word_links="hover", reading_lines=("zh",))
    edited = settings.value
    was = use_presets.before(edited)
    settings.change(use_presets.chosen(edited, CONVERSATION))
    assert settings.value.preset == CONVERSATION
    assert use_presets.edits(settings.value) == ()
    assert LEARNING not in settings.value.preset_values  # the switch saved nothing
    settings.update(interface_language="fr")  # meanwhile, an app-wide setting
    settings.change(use_presets.restored(settings.value, was))  # Undo
    value = settings.value
    assert value.preset == LEARNING and value.word_links == "hover"
    assert value.reading_lines == ("zh",) and "reading_lines" in value.changed
    assert use_presets.edits(value) == use_presets.edits(edited)  # still not saved
    assert value.interface_language == "fr"  # Undo leaves the rest as it is


def test_an_edited_preset_is_still_edited_after_a_restart() -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.update(opacity=0.6, subtitle_size=0.06)
    again = Settings(store).value  # the app started again
    assert again.preset == VIDEO and again.opacity == 0.6  # nothing lost
    assert use_presets.edits(again) == ("opacity", "subtitle_size")
    assert VIDEO not in again.preset_values


def test_what_556_saved_at_once_is_the_presets_saved_state() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.update(word_links="arrows")
    stored = use_presets.saved_into(settings.value).to_stored()  # 556's file
    del stored["built_ins"]
    stored["preset_values"] = {
        VIDEO: {"word_links": "arrows"},
        LEARNING: {"opacity": 0.4},
    }
    value = _settings(stored).value
    assert value.preset_values == {
        VIDEO: {"word_links": "arrows"},
        LEARNING: {"opacity": 0.4},
    }
    assert use_presets.edits(value) == ()  # as saved: nothing to save


def test_app_wide_settings_are_never_changes_not_saved() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, LEARNING))
    settings.update(
        interface_language="de",
        theme="glaze",
        targets=("ja",),
        hotkeys={"next_preset": "Ctrl+Alt+P"},
        interface_text_size="larger",
    )
    assert use_presets.edits(settings.value) == ()
    assert LEARNING not in settings.value.preset_values


def test_a_built_in_with_saved_changes_can_be_restored() -> None:
    value = AppSettings()
    assert not use_presets.restorable(value, EVERYDAY)
    settings = _settings()
    settings.update(opacity=0.4)
    value = use_presets.saved_into(settings.value)
    assert use_presets.restorable(value, EVERYDAY)
    own = use_presets.added(value, "Mine")
    assert not use_presets.restorable(own, own.preset)  # its own: rename, delete


def test_video_defaults_to_instant_and_older_untouched_settings_follow() -> None:
    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    assert settings.value.caption_mode_chosen == "live"
    stored = settings.value.to_stored()
    stored["caption_mode_chosen"] = "words"  # as 556 left Video: Steady
    del stored["built_ins"]
    value = _settings(stored).value
    assert value.caption_mode_chosen == "live" and use_presets.edits(value) == ()
    assert value.built_ins == BUILT_INS
    # as 626 (built_ins=3) left Video untouched: Instant stays Instant
    v3 = settings.value.to_stored()
    v3["built_ins"] = 3
    v3["caption_mode_chosen"] = "live"
    v3_migrated = _settings(v3).value
    assert (
        v3_migrated.caption_mode_chosen == "live"
        and use_presets.edits(v3_migrated) == ()
    )
    assert v3_migrated.built_ins == BUILT_INS
    # saved with another timing on purpose (including Instant): theirs is kept
    v3_explicit = {
        **v3,
        "preset_values": {VIDEO: {"caption_mode_chosen": "live"}},
    }
    kept_instant = _settings(v3_explicit).value
    assert (
        kept_instant.caption_mode_chosen == "live"
        and use_presets.edits(kept_instant) == ()
    )
    stored["caption_mode_chosen"] = "calm"
    stored["preset_values"] = {VIDEO: {"caption_mode_chosen": "calm"}}
    value = _settings(stored).value
    assert value.caption_mode_chosen == "calm" and use_presets.edits(value) == ()
    # Steady chosen and not saved since: still the learner's, still not saved
    settings.update(caption_mode_chosen="words")
    again = _settings(settings.value.to_stored()).value
    assert again.caption_mode_chosen == "words"
    assert again.caption_mode is CaptionMode.INSTANT
    assert (
        replace(again, preset=EVERYDAY, subtitles=False).caption_mode
        is CaptionMode.STEADY
    )
    assert (
        replace(again, caption_mode_chosen=CaptionMode.WHOLE.value).caption_mode
        is CaptionMode.INSTANT
    )
    assert use_presets.edits(again) == ("caption_mode_chosen",)


def test_tunable_defaults_follow_the_active_preset_and_a_learner_choice_wins(
    tmp_path: Path,
) -> None:
    from polyglotic_desktop.core.listening.preset_reading import VIDEO_FADE
    from polyglotic_desktop.tunable_config import load

    # Just picking Video writes its flat values, even when none was changed.
    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.change(use_presets.chosen(settings.value, VIDEO))
    stored = store.load()
    file = tmp_path / "tunables.toml"
    file.write_text("[presets.video]\nfade_after = 5.0")
    try:
        assert not load(
            tmp_path, None, stored, cohort={"presets.video.fade_after": 4.5}
        ).warnings
        assert Settings(store).value.fade_after == VIDEO_FADE.value == 5.0
        learner = Settings(store)
        learner.update(fade_after=6.0)
        assert not load(tmp_path, None, store.load()).warnings
        assert Settings(store).value.fade_after == VIDEO_FADE.value == 6.0
        assert use_presets.reset(learner.value, VIDEO).fade_after == 5.0
        # A stored flat value from a previous local experiment follows again after removal.
        file.unlink()
        load(tmp_path, None, stored)
        stale = {**stored, "fade_after": 5.0}
        assert _settings(stale).value.fade_after == 4.0
    finally:
        load(tmp_path, tmp_path / "empty.toml", {})


def test_a_refused_learner_layer_cannot_reenter_through_saved_presets(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from polyglotic_desktop.tunable_config import load

    settings = _settings()
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.update(fade_after=6.0, opacity=0.5)
    stored = settings.value.to_stored()
    stored["preset_values"] = {
        VIDEO: {"fade_after": 6.0, "opacity": 0.5, "caption_path": "acquisition"},
        CONVERSATION: {"caption_mode_chosen": "calm"},
    }
    stored["caption_path"] = "acquisition"
    try:
        result = load(tmp_path, None, stored, cohort={"presets.video.fade_after": 5.0})
        assert "learner: whole layer refused: R7" in caplog.text
        assert result.values["presets.video.fade_after"] == 5.0
        value = _settings(stored).value
        assert value.fade_after == 5.0 and value.opacity == 0.5
        assert "caption_path" not in value.preset_values.get(VIDEO, {})
        assert value.preset_values[CONVERSATION]["caption_mode_chosen"] == "calm"
    finally:
        load(tmp_path, None, {})


@pytest.mark.parametrize("preset", use_presets.ORDER)
def test_every_built_in_starts_at_its_recommended_timing_and_migrates_its_old_default(
    preset: str,
) -> None:
    from polyglotic_desktop.core.listening.preset_reading import recommendation_for

    rec = recommendation_for(preset)
    assert rec is not None
    value = use_presets.chosen(_settings().value, preset)
    assert value.caption_mode is rec.recommended_timing
    assert use_presets.edits(value) == ()
    old = value.to_stored()
    old["built_ins"] = 2
    old["caption_mode_chosen"] = "live" if preset == VIDEO else None
    migrated = _settings(old).value
    assert migrated.built_ins == BUILT_INS
    assert migrated.caption_mode is rec.recommended_timing
    assert use_presets.edits(migrated) == ()


@pytest.mark.parametrize("preset", use_presets.ORDER)
def test_built_in_migration_preserves_a_saved_timing_and_a_draft(preset: str) -> None:
    chosen = use_presets.chosen(_settings().value, preset)
    old = {
        **chosen.to_stored(),
        "built_ins": 2,
        "changed": [*chosen.changed, "caption_mode_chosen"],
        "caption_mode_chosen": "words",
        "preset_values": {preset: {"caption_mode_chosen": "calm"}},
    }
    value = _settings(old).value
    assert value.requested_caption_mode is CaptionMode.STEADY
    assert use_presets.edits(value) == ("caption_mode_chosen",)
    assert use_presets.discarded(value).requested_caption_mode is CaptionMode.CALM


def test_legacy_lyrics_and_a_custom_presets_implicit_steady_survive() -> None:
    old = {
        "preset": "own1",
        "own_presets": ["own1"],
        "built_ins": 2,
        "caption_mode_chosen": None,
        "lyrics": True,
    }
    value = _settings(old).value
    assert value.caption_mode is CaptionMode.STEADY
    assert use_presets.edits(value) == ()
    for preset in use_presets.keys(value):
        assert use_presets.chosen(value, preset).lyrics


def test_partial_bar_save_leaves_a_settings_draft_and_survives_reload() -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.update(opacity=0.4)
    settings.update_from_bar(caption_mode_chosen=CaptionMode.WHOLE.value, lyrics=True)
    value = Settings(store).value
    assert use_presets.edits(value) == ("opacity",)
    assert value.preset_values == {
        EVERYDAY: {"caption_mode_chosen": CaptionMode.WHOLE.value, "lyrics": True},
    }
    cleared = use_presets.discarded(value)
    assert cleared.caption_mode is CaptionMode.WHOLE and cleared.lyrics
    assert cleared.opacity != 0.4
    assert not use_presets.chosen(cleared, VIDEO).lyrics


def test_delayed_translation_reports_the_existing_live_original_timing() -> None:
    video = use_presets.chosen(_settings().value, VIDEO)
    delayed = replace(video, caption_mode_chosen=CaptionMode.SCROLLING.value)
    assert (
        use_presets.usage(delayed)["preset_caption_mode_chosen"]
        == CaptionMode.INSTANT.value
    )


def test_bar_source_choices_stay_out_of_usage() -> None:
    settings = _settings()
    settings.update_from_bar(
        lyrics=True,
        preset_languages={"Private App": {"translate_into": "ja"}},
        preset_second_languages={"ja": "fr"},
    )
    assert use_presets.usage(settings.value) == {"preset": EVERYDAY}


def test_saved_presets_inherit_parent_recommendation_and_no_parent_shows_none() -> None:
    from polyglotic_desktop.core.listening.preset_reading import recommendation_for

    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.change(use_presets.chosen(settings.value, VIDEO))
    settings.change(use_presets.added(settings.value, "Anime"))
    assert settings.value.preset == "own1"
    assert settings.value.preset_parents == {"own1": VIDEO}
    assert use_presets.parent_of(settings.value, "own1") == VIDEO
    rec = recommendation_for("own1", use_presets.parent_of(settings.value, "own1"))
    assert rec is not None and rec.recommended_timing is CaptionMode.INSTANT

    # Save as new from an own preset keeps the built-in ancestor
    settings.change(use_presets.added(settings.value, "Anime 2"))
    assert settings.value.preset == "own2"
    assert settings.value.preset_parents == {"own1": VIDEO, "own2": VIDEO}

    # Reloaded from disk: parent survives, invalid parents dropped
    stored = store.load()
    stored_parents = stored["preset_parents"]
    assert isinstance(stored_parents, dict)
    stored["preset_parents"] = {
        **stored_parents,
        "own9": VIDEO,
        "own2": "not_a_builtin",
    }
    reloaded = _settings(stored).value
    assert reloaded.preset_parents == {"own1": VIDEO}
    assert use_presets.parent_of(reloaded, "own2") is None
    assert recommendation_for("own2", use_presets.parent_of(reloaded, "own2")) is None

    # Undo restores a deleted own preset's parent
    was = use_presets.before(reloaded)
    deleted = use_presets.removed(reloaded, "own1")
    assert "own1" not in deleted.preset_parents
    assert use_presets.restored(deleted, was).preset_parents == {"own1": VIDEO}

    # Custom (migrated from before presets) has no parent and no recommendation
    legacy = _settings({"changed": ["word_links"], "word_links": "off"}).value
    assert legacy.preset == CUSTOM
    assert use_presets.parent_of(legacy, CUSTOM) is None
    assert recommendation_for(CUSTOM, use_presets.parent_of(legacy, CUSTOM)) is None


def test_learning_recommendation_is_a_one_value_tunable_change(
    tmp_path: Path,
) -> None:
    from polyglotic_desktop.core.listening.preset_reading import recommendation_for
    from polyglotic_desktop.tunable_config import load

    file = tmp_path / "tunables.toml"
    file.write_text('[presets.learning]\ncaption_mode = "calm"\n')
    try:
        assert not load(tmp_path, file, {}).warnings
        rec = recommendation_for(LEARNING)
        assert rec is not None and rec.recommended_timing is CaptionMode.CALM
        chosen = use_presets.chosen(_settings().value, LEARNING)
        assert chosen.caption_mode is CaptionMode.CALM
    finally:
        load(tmp_path, tmp_path / "empty.toml", {})


@pytest.mark.parametrize("active", [VIDEO, EVERYDAY])
def test_saved_video_blocks_migrate_even_when_another_preset_is_active(
    active: str,
) -> None:
    stored = _settings().value.to_stored()
    stored.update(
        preset=active,
        built_ins=4,
        caption_mode_chosen="steady",
        preset_values={
            VIDEO: {"caption_mode_chosen": "steady"},
            EVERYDAY: {"caption_mode_chosen": "steady"},
        },
    )
    value = _settings(stored).value
    assert value.preset_values[VIDEO]["caption_mode_chosen"] == "live"
    assert value.preset_values[EVERYDAY]["caption_mode_chosen"] == "steady"
    assert value.caption_mode_chosen == ("live" if active == VIDEO else "steady")


@pytest.mark.parametrize(
    ("old", "new"), [("live", "scrolling"), ("delayed_translation", "live")]
)
def test_preview_video_timing_migrates_once(old: str, new: str) -> None:
    video = use_presets.chosen(_settings().value, VIDEO)
    own = use_presets.added(video, "My Video")
    stored = own.to_stored()
    stored.pop("video_layout")
    stored["caption_mode_chosen"] = old
    stored["preset_values"] = {
        VIDEO: {"caption_mode_chosen": old},
        own.preset: {"caption_mode_chosen": old, "subtitles": True},
        LEARNING: {"caption_mode_chosen": "live"},
    }
    value = _settings(stored).value
    assert value.caption_mode.value == new
    assert value.preset_values[VIDEO]["caption_mode_chosen"] == new
    assert value.preset_values[own.preset]["caption_mode_chosen"] == new
    assert value.preset_values[LEARNING]["caption_mode_chosen"] == "live"
    assert _settings(value.to_stored()).value == value


def test_legacy_centred_video_copy_migrates_its_saved_blocks_to_instant() -> None:
    video = use_presets.chosen(_settings().value, VIDEO)
    own = use_presets.added(video, "My Video")
    stored = own.to_stored()
    stored["caption_mode_chosen"] = CaptionMode.WHOLE.value
    stored["preset_values"] = {
        own.preset: {"caption_mode_chosen": CaptionMode.WHOLE.value, "subtitles": True}
    }
    value = _settings(stored).value
    assert value.subtitles
    assert value.caption_mode is CaptionMode.INSTANT
    assert value.preset_values[own.preset]["caption_mode_chosen"] == CaptionMode.INSTANT
    assert (
        replace(value, caption_mode_chosen=CaptionMode.STEADY.value).caption_mode
        is CaptionMode.INSTANT
    )
    assert (
        replace(value, caption_mode_chosen=CaptionMode.SCROLLING.value).caption_mode
        is CaptionMode.SCROLLING
    )
