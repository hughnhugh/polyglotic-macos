"""Mongolian and Kazakh aren't offered as targets (polyglotic-hq
DECISIONS.md #40): a saved choice of one falls back (not pickable in the
new interface: tests/ui_next/test_window_choices.py); and saving keeps
the keys this version doesn't know (RELEASING.md section 5, G11)."""

from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.ui.settings import AppSettings, Settings, removed_targets


def test_a_saved_choice_of_one_is_dropped_and_the_rest_kept() -> None:
    value = AppSettings.from_stored(
        {"targets": ["mn", "zh", "kk"], "second_languages": {"zh": "kk", "mn": "en"}}
    )
    assert value.targets == ("zh",)
    assert value.second_languages == {}


def test_a_saved_choice_of_only_those_falls_back_to_the_default() -> None:
    value = AppSettings.from_stored({"targets": ["kk"]})
    assert value.targets == AppSettings().targets


def test_no_choice_saved_is_still_no_choice() -> None:
    assert AppSettings.from_stored({"targets": []}).targets == ()
    assert removed_targets({"targets": []}) == ()
    assert removed_targets({"targets": "mn"}) == ()


def test_a_save_keeps_keys_this_version_does_not_know() -> None:
    """A newer version's key survives an older version's save (project 107, G11)."""
    store = MemorySettingsStore()
    store.save({"targets": ["zh"], "from_a_newer_version": {"a": [1, 2]}})
    settings = Settings(store)
    settings.update(text_scale=1.5)
    saved = store.load()
    assert saved["from_a_newer_version"] == {"a": [1, 2]}
    assert saved["text_scale"] == 1.5


def test_a_save_keeps_keys_saved_since_by_another_part_of_the_app() -> None:
    """The caption windows write their own key into the same file after the
    settings were read: kept, at its newest value (117 Low 13)."""
    store = MemorySettingsStore({"targets": ["zh"], "caption_windows": {"v": 1}})
    settings = Settings(store)
    store.save({**store.load(), "caption_windows": {"v": 2}, "added_since": True})
    settings.update(text_scale=1.5)
    saved = store.load()
    assert saved["caption_windows"] == {"v": 2}
    assert saved["added_since"] is True
    assert saved["text_scale"] == 1.5


def test_a_save_does_not_bring_back_a_key_another_part_removed() -> None:
    """117 Low 9: a key gone from the file stays gone."""
    store = MemorySettingsStore({"targets": ["zh"], "caption_windows": {"v": 1}})
    settings = Settings(store)
    store.save({k: v for k, v in store.load().items() if k != "caption_windows"})
    settings.update(text_scale=1.5)
    assert "caption_windows" not in store.load()


def test_a_save_after_the_file_could_not_be_read_keeps_the_keys_known() -> None:
    """Nothing read (the file gone, or locked for a moment) isn't "every other
    key removed": the caption windows' choices aren't lost with it."""
    store = MemorySettingsStore({"targets": ["zh"], "caption_windows": {"v": 1}})
    settings = Settings(store)
    store.values = {}
    settings.update(text_scale=1.5)
    assert store.load()["caption_windows"] == {"v": 1}
