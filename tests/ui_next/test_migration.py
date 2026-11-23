"""Today's caption settings moved to each caption window's own, once
(project 109's structure, sections 1.1 and 9; build step 6) - plain
Python, no Qt. With the caption windows and today's settings writing the
same file: `tests/ui/test_next_interface_migration.py`."""

from polyglotic_desktop.ui_next.views.caption_window import (
    STORED_KEY,
    StoredWindows,
    WindowChoices,
)
from polyglotic_desktop.ui_next.views.migration import (
    moved_over,
    stored_windows,
    todays_sources,
    todays_values,
)
from polyglotic_desktop.ui_next.views.placement import Preset, Rect

TODAY = {
    "targets": ["zh", "en"],
    "text_scale": 1.3,
    "caption_mic": True,
    "overlay_position": "custom",
    "overlay_geometry": {"zh": [100, 200, 700, 260], "en": [100, 500, 700, 260]},
    "apps": ["Chat App", "Video Player", "Web Browser", "Game"],
}


def test_each_of_todays_sources_gets_todays_values() -> None:
    stored = moved_over(TODAY)
    assert list(stored.by_key) == ["Chat App", "Video Player", "Web Browser", "Game"]
    for choices in stored.by_key.values():
        assert choices.translate_into == "zh"  # targets[0]
        assert choices.show_mic  # caption_mic, in every window
        assert choices.text_size == 1.3  # text_scale


def test_the_first_source_is_where_the_first_languages_overlay_was_put() -> None:
    """overlay_geometry was by target language; now it's by source - the
    first source's. The others open at their default slots, not on top of
    it."""
    stored = moved_over(TODAY)
    first = stored.by_key["Chat App"]
    assert (first.preset, first.geometry) == (Preset.CUSTOM, Rect(100, 200, 700, 260))
    for key in ("Video Player", "Web Browser", "Game"):
        other = stored.by_key[key]
        assert (other.preset, other.geometry) == (Preset.BOTTOM_CENTRE, None)


def test_a_preset_is_kept_for_every_window() -> None:
    stored = moved_over({**TODAY, "overlay_position": "top_centre"})
    assert {c.preset for c in stored.by_key.values()} == {Preset.TOP_CENTRE}
    assert {c.geometry for c in stored.by_key.values()} == {None}


def test_where_i_put_it_without_a_place_kept_is_bottom_centre() -> None:
    gone = moved_over({**TODAY, "overlay_geometry": {"en": [1, 2, 300, 100]}})
    assert gone.by_key["Chat App"].preset is Preset.BOTTOM_CENTRE
    assert todays_values({"overlay_position": "custom"}).preset is Preset.BOTTOM_CENTRE


def test_everything_the_pc_plays_is_one_source() -> None:
    assert todays_sources({**TODAY, "whole_system": True}) == ["system"]
    assert todays_sources({"apps": ["A", "A", "", 3, "B"]}) == ["A", "B"]
    assert todays_sources({}) == []


def test_nothing_set_today_is_the_defaults() -> None:
    assert todays_values({}) == WindowChoices()
    bad = {
        "targets": "zh",
        "text_scale": 9,
        "caption_mic": "yes",
        "overlay_position": 1,
    }
    assert todays_values(bad) == WindowChoices()
    assert moved_over({}).by_key == {}


def test_it_runs_while_no_window_has_settings_of_its_own() -> None:
    stored = stored_windows(TODAY)
    assert stored.first_use  # moved over now: to be saved
    assert list(stored.by_key) == TODAY["apps"]


def test_it_runs_once_and_never_changes_a_windows_own() -> None:
    """Saved once, the windows' own are read: today's settings changed
    since (today's interface ran in between) don't move them again."""
    saved = {**TODAY, STORED_KEY: moved_over(TODAY).to_stored()}
    changed_today = {**saved, "targets": ["ja"], "caption_mic": False}
    again = stored_windows(changed_today)
    assert not again.first_use
    assert again.by_key["Chat App"].translate_into == "zh"
    assert again.by_key["Chat App"].show_mic
    own = WindowChoices("", 0.8, False, Preset.TOP_CENTRE, None)
    with_own = {**TODAY, STORED_KEY: StoredWindows({"Chat App": own}, own).to_stored()}
    assert stored_windows(with_own).by_key == {"Chat App": own}


def test_a_value_missing_from_a_windows_own_is_todays() -> None:
    partial = {
        **TODAY,
        STORED_KEY: {"windows": {"Chat App": {"position": "top_centre"}}},
    }
    choices = stored_windows(partial).by_key["Chat App"]
    assert choices.preset is Preset.TOP_CENTRE
    assert (choices.translate_into, choices.text_size, choices.show_mic) == (
        "zh",
        1.3,
        True,
    )


def test_todays_keys_are_not_touched() -> None:
    """Only the windows' own key is written: today's interface reads what it
    did."""
    before = dict(TODAY)
    stored = moved_over(TODAY)
    assert before == TODAY
    assert set(stored.to_stored()) == {
        "windows",
        "last",
        "joined",
        "looked_up",
        "recent_spoken",
        "declined_spoken",
        "reading_hinted",
        "respeaking_hinted",
        "set_up",  # the first window's set-up answered (465)
        "start_like_this",
        "kept_languages",  # while every window shows the original only (556)
    }


def test_a_source_today_didnt_name_takes_todays_values_until_saved() -> None:
    """Windows 10 captions everything the PC plays even with apps picked:
    that window, opened first, takes today's values and place."""
    stored = moved_over(TODAY)
    system = stored.for_new(0)
    assert system.show_mic and system.preset is Preset.CUSTOM
    stored.first_use = False  # saved, a window opened: from now on, new ones
    assert stored.for_new(1) == WindowChoices("zh", 1.3, translation_size=1.3)
