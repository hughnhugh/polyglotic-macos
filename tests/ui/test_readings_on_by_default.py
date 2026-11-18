"""Reading lines on from the start (the user, 2026-11-18: "default
pinyin/script assistance on for next release"; polyglotic-hq 511): every
language with a reading line but the learner's own - the interface's
language and the caption windows' translations - over every word
(DECISIONS #206). Until the learner changes them they follow the app's
default, as decision 0220's switches do; a change is kept."""

from dataclasses import replace

from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.core.listening.display import READING_LANGUAGES
from polyglotic_desktop.main import (
    caption_look,
    look_changes,
    readings_by_default,
)
from polyglotic_desktop.ui.settings import FOLLOW_DEFAULT, AppSettings, Settings

ENGLISH_LEARNER_OF_CHINESE = AppSettings(interface_language="en", targets=("en",))
CHINESE_LEARNER_OF_ENGLISH = AppSettings(interface_language="zh_CN", targets=("zh",))


def test_an_english_speaker_sees_pinyin_over_chinese_from_the_start() -> None:
    look = caption_look(ENGLISH_LEARNER_OF_CHINESE)
    assert "zh" in look.reading_lines and "en" not in look.reading_lines
    # every other one too (yue, ja, ru, ko, hi): all but English, its own
    assert look.reading_lines == tuple(sorted(set(READING_LANGUAGES) - {"en"}))
    assert not look.reading_past  # over every word (DECISIONS #206)


def test_none_over_the_learners_own_language() -> None:
    """A Chinese interface, or a window translating into Chinese: pinyin
    over the learner's own language is noise."""
    assert "zh" not in caption_look(CHINESE_LEARNER_OF_ENGLISH).reading_lines
    by_window = caption_look(ENGLISH_LEARNER_OF_CHINESE, own=["zh-hant"])
    assert "zh" not in by_window.reading_lines
    taiwan = replace(ENGLISH_LEARNER_OF_CHINESE, interface_language="zh_TW")
    assert "zh" not in readings_by_default(taiwan)


def test_a_file_that_never_chose_follows_the_default() -> None:
    """0.1.8's previews saved every key with a record of what was changed:
    reading_lines [] there was never a choice."""
    assert "reading_lines" in FOLLOW_DEFAULT
    stored = {**AppSettings().to_stored(), "interface_language": "en"}
    assert stored["reading_lines"] == [] and stored["changed"] == []
    value = AppSettings.from_stored(stored)
    assert "zh" in caption_look(value).reading_lines


def test_a_choice_is_kept() -> None:
    store = MemorySettingsStore({"interface_language": "en", "changed": []})
    settings = Settings(store)
    look = caption_look(settings.value)
    # all off: what an unchosen file holds too, a choice all the same
    settings.update(**look_changes(settings.value, replace(look, reading_lines=())))
    assert "reading_lines" in settings.value.changed
    again = AppSettings.from_stored(store.values)
    assert caption_look(again).reading_lines == ()


def test_another_look_change_leaves_the_default_unchosen() -> None:
    """Saving the look (a colour) writes every look setting: the reading
    lines it shows by default aren't made a choice by it."""
    settings = Settings(
        MemorySettingsStore({"interface_language": "en", "changed": []})
    )
    look = replace(caption_look(settings.value), opacity=0.5)
    settings.update(**look_changes(settings.value, look))
    assert settings.value.opacity == 0.5
    assert "reading_lines" not in settings.value.changed


# -- files from before the record (0.1.7) ---------------------------------------------


def test_an_old_file_with_no_reading_lines_follows_the_default() -> None:
    """0.1.7 saved every key and no record of what was chosen: `[]` is what
    every untouched file holds - pinyin was never on by default - so it
    follows the new default, the user's own install among them."""
    old = {**AppSettings().to_stored(), "interface_language": "en"}
    del old["changed"]
    value = AppSettings.from_stored(old)
    assert "reading_lines" not in value.changed
    assert "zh" in caption_look(value).reading_lines
    assert "opacity" in value.changed  # every other key it holds: chosen


def test_an_old_files_reading_lines_are_kept() -> None:
    """A list with a language in it was turned on: a choice."""
    old = {**AppSettings().to_stored(), "interface_language": "en"}
    del old["changed"]
    old["reading_lines"] = ["zh"]
    value = AppSettings.from_stored(old)
    assert caption_look(value).reading_lines == ("zh",)


def test_a_new_file_keeps_all_off_as_a_choice() -> None:
    """With the record, `[]` named in it is the learner's: none."""
    stored = {
        **AppSettings().to_stored(),
        "interface_language": "en",
        "changed": ["reading_lines"],
    }
    assert caption_look(AppSettings.from_stored(stored)).reading_lines == ()
