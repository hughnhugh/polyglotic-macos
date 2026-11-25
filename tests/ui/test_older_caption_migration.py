"""807: existing learners follow the lighter Older captions default unless chosen."""

import pytest
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.main import caption_look
from polyglotic_desktop.ui.settings import (
    CAPTION_LAB_VERSION,
    Settings,
    _contrast_older,
)
from polyglotic_desktop.ui_next.views.lab import (
    CaptionLab,
    NewFade,
    by_place,
    ink_between,
)
from polyglotic_desktop.ui_next.views.presets import _mix, contrast, contrast_alpha


def loaded(stored: dict[str, object]):
    return Settings(MemorySettingsStore(stored)).value


def test_an_untouched_0_1_10_profile_gets_the_lighter_default() -> None:
    value = loaded({"caption_lab": {}, "changed": []})
    assert value.caption_lab_version == CAPTION_LAB_VERSION
    older = caption_look(value).lab.older
    assert older == 0.85
    assert f"{older:.0%} default" in (_contrast_older.__doc__ or "")


@pytest.mark.parametrize(
    ("chosen", "field", "wanted"),
    [
        ({"new_for": 7.0}, "new_for", 7.0),
        ({"new_fade": "instant"}, "new_fade", NewFade.INSTANT),
        ({"older": 0.7}, "older", 0.7),
        ({"older_steps": 2}, "older_steps", 2),
    ],
)
def test_each_chosen_age_value_stays_while_the_other_defaults_move(
    chosen: dict[str, object], field: str, wanted: object
) -> None:
    lab = caption_look(
        loaded(
            {
                "caption_lab": chosen,
                "caption_lab_version": CAPTION_LAB_VERSION,
                "changed": [],
            }
        )
    ).lab
    assert getattr(lab, field) == wanted
    for other, default in {
        "new_for": 3.0,
        "new_fade": NewFade.GRADUAL,
        "older": 0.85,
        "older_steps": 5,
    }.items():
        if other != field:
            assert getattr(lab, other) == default


def test_a_chosen_old_ink_value_keeps_the_original_row_looking_the_same() -> None:
    value = loaded(
        {
            "caption_lab": {"older": 0.75},
            "changed": ["caption_lab"],
            "original_color": "#ffffff",
            "background_color": "#0a0c10",
        }
    )
    lab = caption_look(value).lab
    assert lab.older == 0.56
    old_ratio = contrast(_mix("#0a0c10", "#ffffff", 0.75), "#0a0c10")
    new_alpha = contrast_alpha("#ffffff", "#0a0c10", lab.older)
    new_ratio = contrast(_mix("#0a0c10", "#ffffff", new_alpha), "#0a0c10")
    assert new_ratio == pytest.approx(old_ratio, rel=0.03)


def test_a_preset_carried_choice_is_migrated_as_the_flat_choice() -> None:
    value = loaded(
        {
            "preset": "everyday",
            "preset_values": {"everyday": {"caption_lab": {"older": 0.75}}},
            "caption_lab": {"older": 0.75},
        }
    )
    assert value.caption_lab == {"older": 0.56}
    assert "everyday" not in value.preset_values
    assert caption_look(value).lab.older == 0.56


def test_over_five_captions_never_steps_below_the_85_percent_floor() -> None:
    lab = CaptionLab(older=0.85, older_steps=5)
    panel, colour = "#0a0c10", "#ffffff"
    full = contrast(colour, panel)
    floor = contrast_alpha(colour, panel, lab.older)
    for place in range(5):
        alpha = ink_between(floor, by_place(place, lab))
        retained = contrast(_mix(panel, colour, alpha), panel) / full
        assert retained >= 0.85
