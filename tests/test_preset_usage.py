"""The preset in use, counted (polyglotic-hq 556): the session summary's
optional `preset` and `preset_<setting>` properties - which preset, and
the settings in it that differ from its defaults, as names and fixed
values only - sent with the summary, so only with consent to usage
statistics (polyglotic-server's tracking plan, `listening_session_ended`)."""

from dataclasses import replace

from polyglotic_desktop.ui import use_presets
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui.use_presets import EVERYDAY, VIDEO

ALLOWED = {"preset"} | {f"preset_{name}" for name in use_presets.PRESET_SETTINGS}


def test_an_untouched_install_says_everyday_and_nothing_changed() -> None:
    assert use_presets.usage(AppSettings()) == {"preset": EVERYDAY}


def test_a_change_in_video_is_its_name_and_value_only() -> None:
    value = use_presets.chosen(AppSettings(), VIDEO)
    value = use_presets.saved_into(replace(value, word_links="arrows", opacity=0.7))
    assert use_presets.usage(value) == {
        "preset": VIDEO,
        "preset_word_links": "arrows",
        "preset_opacity": 0.7,
    }


def test_colours_are_counted_as_changed_never_by_their_value() -> None:
    value = use_presets.saved_into(replace(AppSettings(), translation_color="#5ee3ff"))
    assert use_presets.usage(value)["preset_translation_color"] is True


def test_an_own_preset_is_own_never_its_name() -> None:
    value = use_presets.added(AppSettings(), "Anime nights")
    sent = use_presets.usage(value)
    assert sent["preset"] == "own"
    assert "Anime nights" not in str(sent)


def test_every_property_is_in_the_plans_list_and_typed() -> None:
    value = use_presets.chosen(AppSettings(), VIDEO)
    value = replace(
        value,
        reading_lines=("zh",),
        fade_after=None,
        my_speech=None,
        caption_mode_chosen="live",
        original_color="#eeeeee",
    )
    sent = use_presets.usage(use_presets.saved_into(value))
    assert set(sent) <= ALLOWED
    assert sent["preset_reading_lines"] == 1  # how many, not which
    assert sent["preset_fade_after"] == 0.0  # never
    assert sent["preset_my_speech"] == "each"
    assert all(isinstance(v, str | int | float | bool) for v in sent.values())
