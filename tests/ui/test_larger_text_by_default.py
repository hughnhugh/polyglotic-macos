"""The app's text is larger by default (polyglotic-hq 524, the user,
2026-11-19: "normal should be between larger to largest"; decision 0244):
every step shifted up, and a learner's size from 0.1.9 or before kept as
it was on screen - unless it was 0.1.9's Normal, which every file held,
chosen or not, and which follows the new default."""

import pytest
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.ui.settings import (
    FOLLOW_DEFAULT,
    OLD_TEXT_SIZE,
    OLD_TEXT_SIZES,
    AppSettings,
    Settings,
)
from polyglotic_desktop.ui_next import style

SIZE = "interface_text_size"
STEPS_0_1_9 = {"smaller": 0.9, "normal": 1.0, "larger": 1.2, "largest": 1.45}
"""0.1.9's steps (decision 0084), what its files' `app_text_size` meant."""


def test_normal_is_between_0_1_9s_larger_and_largest_and_the_default() -> None:
    assert (
        STEPS_0_1_9["larger"] < style.APP_TEXT_SIZES["normal"] < STEPS_0_1_9["largest"]
    )
    assert AppSettings().interface_text_size == "normal"
    assert SIZE in FOLLOW_DEFAULT


def test_every_step_moves_with_it() -> None:
    """Smaller is 0.1.9's Normal, Larger its Largest, and a Largest above
    it - no larger than the floor's (`ui_next.main_window.FLOOR_SCALE`:
    the main window at a 1366 x 768 laptop's 150 %, every page fitting)."""
    steps = style.APP_TEXT_SIZES
    assert steps["smaller"] == STEPS_0_1_9["normal"]
    assert steps["larger"] == STEPS_0_1_9["largest"]
    assert steps["larger"] < steps["largest"] <= 1.8
    assert list(steps.values()) == sorted(steps.values())


def test_a_size_chosen_before_is_the_nearest_step_on_screen() -> None:
    """Each of 0.1.9's chosen steps becomes today's whose factor - its text
    on screen - is nearest; its Normal isn't one (it follows the default)."""
    for old, new in OLD_TEXT_SIZES.items():
        factor = STEPS_0_1_9[old]
        nearest = min(
            style.APP_TEXT_SIZES, key=lambda k: abs(style.APP_TEXT_SIZES[k] - factor)
        )
        assert new == nearest, old
    assert set(OLD_TEXT_SIZES) == set(STEPS_0_1_9) - {"normal"}


@pytest.mark.parametrize(
    ("stored", "size", "chosen"),
    [
        # a file from 0.1.7 or before: every key, no record of changes
        ({OLD_TEXT_SIZE: "normal"}, "normal", False),
        ({OLD_TEXT_SIZE: "smaller"}, "smaller", True),
        ({OLD_TEXT_SIZE: "larger"}, "normal", True),
        ({OLD_TEXT_SIZE: "largest"}, "larger", True),
        # 0.1.8's and 0.1.9's, with the record: Normal again counts as untouched
        ({OLD_TEXT_SIZE: "normal", "changed": [OLD_TEXT_SIZE]}, "normal", False),
        ({OLD_TEXT_SIZE: "normal", "changed": []}, "normal", False),
        ({OLD_TEXT_SIZE: "largest", "changed": [OLD_TEXT_SIZE]}, "larger", True),
        ({OLD_TEXT_SIZE: "larger", "changed": ["dictation"]}, "normal", True),
        # not valid: as though there were none
        ({OLD_TEXT_SIZE: "huge"}, "normal", False),
        ({OLD_TEXT_SIZE: 1.2, "changed": [OLD_TEXT_SIZE]}, "normal", False),
        # written since: today's key, and 0.1.9's beside it is left alone
        ({SIZE: "largest", "changed": [SIZE]}, "largest", True),
        (
            {SIZE: "smaller", OLD_TEXT_SIZE: "largest", "changed": [SIZE]},
            "smaller",
            True,
        ),
        ({SIZE: "normal", OLD_TEXT_SIZE: "largest", "changed": []}, "normal", False),
    ],
)
def test_a_file_from_before_keeps_a_chosen_size_and_follows_the_default_otherwise(
    stored: dict[str, object], size: str, chosen: bool
) -> None:
    read = AppSettings.from_stored(stored)
    assert read.interface_text_size == size
    assert (SIZE in read.changed) == chosen


def test_an_untouched_size_follows_the_next_default_too() -> None:
    """Untouched, the size isn't kept: what the version running has as
    Normal is the learner's (`FOLLOW_DEFAULT`)."""
    store = MemorySettingsStore({OLD_TEXT_SIZE: "normal", "changed": [OLD_TEXT_SIZE]})
    settings = Settings(store)
    settings.update(dictation=False)  # saved: any change saves every setting
    assert store.values[SIZE] == "normal"
    assert SIZE not in settings.value.changed
    assert store.values["changed"] == list(settings.value.changed)


def test_0_1_9_finds_its_own_after_a_rollback() -> None:
    """The old key is never written, only read: a learner who goes back to
    0.1.9 finds the size they had there, and one who changes it here keeps
    the change in today's key."""
    store = MemorySettingsStore({OLD_TEXT_SIZE: "largest", "changed": [OLD_TEXT_SIZE]})
    settings = Settings(store)
    assert settings.value.interface_text_size == "larger"
    settings.update(interface_text_size="largest")
    assert store.values[OLD_TEXT_SIZE] == "largest"  # 0.1.9's, as it was
    assert store.values[SIZE] == "largest"
    assert Settings(store).value.interface_text_size == "largest"
