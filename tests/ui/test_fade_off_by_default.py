""" "Fade after silence" is off for a learner who hasn't chosen (the user's
rehearsal feedback F15, polyglotic-hq 249, 2026-11-08); a learner who
chose a time keeps it."""

from polyglotic_desktop.main import caption_look
from polyglotic_desktop.ui.settings import AppSettings
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import LookView


def test_a_new_learner_s_captions_never_fade() -> None:
    assert AppSettings().fade_after is None
    assert CaptionLook().fade_after is None
    assert caption_look(AppSettings()).fade_after is None


def test_reset_to_defaults_turns_fading_off() -> None:
    view = LookView(CaptionLook(fade_after=15.0))
    view.reset()
    assert view.value.fade_after is None


def test_a_saved_choice_is_kept() -> None:
    for seconds in (5.0, 8.0, 30.0):
        stored = AppSettings(fade_after=seconds).to_stored()
        assert AppSettings.from_stored(stored).fade_after == seconds
    assert AppSettings.from_stored({"fade_after": None}).fade_after is None
