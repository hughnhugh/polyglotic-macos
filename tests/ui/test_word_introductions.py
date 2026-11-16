"""Word introductions in the settings (polyglotic-hq 262; the user's F19 and
F30): Off · A few per caption · Every new word, kept as two keys - the
newer `marks_off` and "common words only" as it was - so a version that
knows only the second still has the cap the learner chose, and turning
introductions on again brings back a few."""

import pytest

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.main import caption_look, look_settings
from polyglotic_desktop.ui.settings import AppSettings, introductions_changes


def test_a_few_per_caption_is_the_default() -> None:
    assert AppSettings().word_introductions is WordIntroductions.A_FEW


def test_a_file_from_before_off_existed_keeps_its_choice() -> None:
    older = AppSettings.from_stored({"common_words_only": False})
    assert older.word_introductions is WordIntroductions.EVERY
    assert AppSettings.from_stored({}).word_introductions is WordIntroductions.A_FEW


@pytest.mark.parametrize("choice", list(WordIntroductions))
def test_each_choice_is_kept_and_read_back(choice: WordIntroductions) -> None:
    value = AppSettings.from_stored(
        AppSettings(**introductions_changes(choice)).to_stored()  # type: ignore[arg-type]
    )
    assert value.word_introductions is choice


def test_off_keeps_the_cap_for_an_older_version_and_for_coming_back() -> None:
    stored = AppSettings(**introductions_changes(WordIntroductions.OFF)).to_stored()  # type: ignore[arg-type]
    assert stored["marks_off"] is True
    assert stored["common_words_only"] is True  # an older version: a few


def test_a_change_of_look_leaves_word_introductions_as_they_were() -> None:
    """The caption windows' look carries the choice, and a change made from
    the look (Settings' captions) doesn't write it: it's Learning's - Off
    never turns itself on again (polyglotic-hq 262)."""
    value = AppSettings(**introductions_changes(WordIntroductions.OFF))  # type: ignore[arg-type]
    look = caption_look(value)
    assert look.introductions is WordIntroductions.OFF
    changes = look_settings(look)
    assert "marks_off" not in changes and "common_words_only" not in changes
