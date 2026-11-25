"""The settings' English, the source every language is translated from
(polyglotic-hq 845): one name per thing, no retired names, no words that
age. Read from the code's own strings (`tools.i18n.extract`), so a new
string that brings one back fails here before it reaches 21 languages."""

from tools.i18n import extract

from polyglotic_desktop.ui_next.presets_card import change_words


def _sources(context: str | None = None) -> list[str]:
    return [
        m.source
        for m in extract.read().messages
        if context is None or m.context == context
    ]


def test_no_string_names_a_retired_timing() -> None:
    """Quick preview went in decision 0246; the contrast slider and the
    Lab still compared captions with "Quick preview's line"."""
    assert [s for s in _sources() if "Quick preview" in s] == []


def test_a_windows_own_speech_has_one_name() -> None:
    """A caption window's menu said Show my speech here and its mic button
    and popover Caption what I say - the same setting (DOMAIN.md: "Show my
    speech here")."""
    assert [s for s in _sources() if s.startswith("Caption what I say")] == []
    window = _sources("CaptionWindow")
    assert "Show my speech here" in window
    assert "Show my speech here: on" in window
    assert "Show my speech here" in _sources("SettingsPopover")


def test_the_lab_names_the_default_not_as_now() -> None:
    """ "As now" meant the default the day each Lab setting was written."""
    assert [s for s in _sources("Lab") if "as now" in s.lower()] == []
    assert "Default" in _sources("Lab")


def test_colours_are_not_a_preset() -> None:
    """A preset is a Presets one (Everyday, Conversation...); Look's row of
    matched colours is Colours."""
    assert "Preset" not in _sources("Panels")
    assert "Colours" in _sources("Panels")


def test_the_presets_list_names_settings_as_settings_does() -> None:
    """What a preset changes, in the names and values its settings have
    where they're chosen: Underline, not Colours; Follow, not "Follow (the
    translation leads)"; Caption timing, not Caption mode."""
    said = dict(
        change_words(
            {
                "word_links": "colours",
                "caption_path": "follow",
                "caption_mode_chosen": "words",
                "steady_words_ahead": "none",
                "caption_edge": "shadow",
            }
        )
    )
    assert said == {
        "Word links": "Underline",
        "What you read first": "Follow",
        "Caption timing": "Steady",
        "Words ahead": "Off",
        "Around the letters": "Soft shadow",
    }
    panels, colours = _sources("Panels"), _sources("ColourControls")
    assert {"Underline", "Follow", "Caption timing", "Off"} <= set(panels)
    assert {"What you read first", "Words ahead"} <= set(panels)
    assert "Soft shadow" in colours and "Around the letters" in colours
