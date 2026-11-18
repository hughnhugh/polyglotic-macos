"""Every feature on for a new learner (polyglotic-hq 478; the user,
2026-11-18: "Default all functional features as on"): dictation, word
links, a hidden window shown again when speech starts. Readings stay over
every word (readings past what you know off: DECISIONS #206). Whoever saved settings keeps what they had; from this version
on the file records what was changed, so a switch nobody touched follows
the app's default (decision 0220)."""

from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.main import caption_look
from polyglotic_desktop.ui.settings import FOLLOW_DEFAULT, AppSettings, Settings
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LINKS_WHEN_ON, LookView

OFF_BEFORE = {
    "dictation": False,
    "word_links": "off",
    "show_hidden_on_speech": False,
    "reading_past": False,
    "whole_system": False,
}
"""The five as 0.1.7 saved them: every key, whether chosen or not."""


def test_a_new_learner_has_them_on() -> None:
    new = AppSettings.from_stored({})
    assert new.dictation
    assert new.word_links == LINKS_WHEN_ON.value == WordLinks.ARROWS.value
    assert new.show_hidden_on_speech and not new.reading_past
    look = caption_look(new)
    assert look.word_links is WordLinks.ARROWS and look.show_on_speech
    assert not look.reading_past
    assert new == AppSettings()


def test_what_stays_off() -> None:
    """Diagnostics, a spelling variant, consent and capture choices beyond
    everything the PC plays (on since 484: test_everything_from_the_start)."""
    new = AppSettings()
    assert not new.show_delay and not new.dictation_australian
    assert not new.caption_mic  # the windows' own switch says (the first's: on)
    assert not new.apps and not new.everything_else


def test_settings_from_before_keep_every_switch() -> None:
    """0.1.7 saved every key, so it can't say which were chosen: each is
    kept, never flipped."""
    kept = AppSettings.from_stored(OFF_BEFORE)
    assert not kept.dictation and kept.word_links == "off"
    assert not kept.show_hidden_on_speech and not kept.reading_past
    assert not kept.whole_system
    assert set(OFF_BEFORE) <= set(kept.changed)  # what 0.1.7 had of FOLLOW_DEFAULT
    assert set(OFF_BEFORE) < set(FOLLOW_DEFAULT)  # the quiet view's words: 0.1.8's


def test_a_switch_missing_from_before_takes_the_default() -> None:
    older = AppSettings.from_stored({"opacity": 0.5})  # before dictation was
    assert older.dictation and older.opacity == 0.5
    assert older.changed == ("opacity",)


def test_from_now_on_an_untouched_switch_follows_the_default() -> None:
    store = MemorySettingsStore({})
    settings = Settings(store)
    settings.update(opacity=0.6, dictation=False)
    assert store.values["changed"] == ["opacity", "dictation"]
    # a later version's default: what was never changed follows it
    later = {**store.values, "word_links": "off", "reading_past": True}
    again = AppSettings.from_stored(later)
    assert again.word_links == AppSettings().word_links
    assert not again.reading_past  # untouched: follows today's default
    assert not again.dictation  # changed: the learner's
    assert again.opacity == 0.6


def test_a_change_is_recorded_once_and_back_and_forth_stays_chosen() -> None:
    settings = Settings(MemorySettingsStore({}))
    settings.update(dictation=False)
    settings.update(dictation=True)
    assert settings.value.changed == ("dictation",)


def test_reset_to_defaults_is_the_new_learners_look() -> None:
    first = caption_look(AppSettings())
    view = LookView(CaptionLook(word_links=WordLinks.OFF, opacity=0.3), first=first)
    view.reset()
    assert view.value.word_links is WordLinks.ARROWS and view.value.opacity == 0.72
    plain = LookView(CaptionLook(word_links=WordLinks.COLOURS))
    plain.reset()  # no app defaults given (the UI lab's): the plain look
    assert plain.value.word_links is WordLinks.OFF
