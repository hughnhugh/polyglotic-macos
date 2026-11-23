"""Follow, Acquisition, Both: what a learner reads first in a paced mode,
one setting (polyglotic-hq 526, decision 0253; DECISIONS #230 item 6)."""

from dataclasses import replace

from polyglotic_desktop.core.listening.playout import (
    TRANSLATION_AFTER_SEC,
    ReadingPath,
)
from polyglotic_desktop.core.listening.timing import CaptionMode
from polyglotic_desktop.ui.settings import AppSettings


def test_both_is_the_default_and_the_choice_is_kept() -> None:
    value = AppSettings()
    assert value.caption_path == ReadingPath.BOTH.value
    assert value.playout_rules.translation_after == 0.0
    chosen = replace(value, caption_path="acquisition", translation_after=3.0)
    again = AppSettings.from_stored(chosen.to_stored())
    assert (again.caption_path, again.translation_after) == ("acquisition", 3.0)
    lenient = AppSettings.from_stored({"caption_path": "skim", "translation_after": 99})
    assert lenient.caption_path == "both"
    assert lenient.translation_after == TRANSLATION_AFTER_SEC


def test_acquisition_holds_the_translation_back_in_the_paced_modes_only() -> None:
    value = AppSettings(
        caption_mode_chosen=CaptionMode.STEADY.value,
        caption_path="acquisition",
        translation_after=3.0,
    )
    assert value.caption_mode is CaptionMode.STEADY and value.acquisition
    assert value.playout_rules.translation_after == 3.0
    whole = replace(value, caption_mode_chosen=CaptionMode.WHOLE.value)
    assert not whole.acquisition and whole.playout_rules.translation_after == 0.0
    follow = replace(value, caption_path="follow")
    assert follow.playout_rules.translation_after == 0.0


def test_acquisition_translates_nothing_live() -> None:
    """Its translation shows only after the clause: the finished caption's
    is soon enough (526's translating.md: live updates are 75-80 % of the
    translator's time)."""
    from polyglotic_desktop.main import listening_settings, timing_changes, timing_of

    assert listening_settings(AppSettings()).translate_live  # Both: by clause
    assert listening_settings(AppSettings(caption_path="follow")).translate_live
    value = AppSettings(
        caption_mode_chosen=CaptionMode.STEADY.value, caption_path="acquisition"
    )
    assert not listening_settings(value).translate_live
    timing = timing_of(value)
    assert timing.path is ReadingPath.ACQUISITION
    changes = timing_changes(value, replace(timing, path=ReadingPath.FOLLOW))
    assert changes["caption_path"] == "follow"


def test_the_card_stack_is_the_learners_to_turn_off() -> None:
    """Steady's card stack (decision 0260) has a switch in Settings >
    Timing: it is saved, and read back (polyglotic-hq 552)."""
    from polyglotic_desktop.main import timing_changes, timing_of

    value = AppSettings()
    timing = timing_of(value)
    assert timing.cards is value.steady_cards
    off = timing_changes(value, replace(timing, cards=False))
    assert off["steady_cards"] is False
    assert not timing_of(replace(value, steady_cards=False)).cards
