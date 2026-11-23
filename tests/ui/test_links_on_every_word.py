"""Word links on every word by default, the learning side too
(polyglotic-hq 555; the user, 2026-11-20: "Default arrow links to every
word, even learning section").

Captions' "Most words" is every word the server links (grammar words -
particles, fillers - it never links), and has been the default since the
start. What linked fewer was the learning side: 0.1.9 and
0.1.10-preview.1 chose "Past what you know" by themselves for each
language added (323). A language added now writes no choice, and a file
from those versions has that choice cleared once; a choice the learner
made that can be told apart (a place to start from, or Off) stays.

The files in `settings_files/` are what those versions saved, made by
their own settings code (polyglotic-hq project 555's
`work/make_settings_files.py`)."""

import json
from pathlib import Path

import pytest
from tests.ui.fakes import MemorySettingsStore

from polyglotic_desktop.core.learning.levels import LanguageChoices, LinkChoice
from polyglotic_desktop.core.listening.display import LinkDetail, WordLinks
from polyglotic_desktop.ui.settings import (
    AppSettings,
    Settings,
    language_choices_changes,
    learning_changes,
)

FILES = Path(__file__).parent / "settings_files"
VERSIONS = ("0.1.9", "0.1.10-preview.1")


def saved_by(version: str, learner: str) -> dict[str, object]:
    files = json.loads((FILES / f"{version}.json").read_text(encoding="utf-8"))
    return dict(files[learner])


def test_a_new_learner_links_every_word() -> None:
    new = AppSettings()
    assert new.word_links == WordLinks.ARROWS.value
    assert new.link_detail == LinkDetail.MOST.value  # every word the server links
    added = learning_changes(new.learning_languages.added("zh"))
    after = AppSettings.from_stored({**new.to_stored(), **added})
    assert after.choices_for("zh").links is LinkChoice.EVERY


@pytest.mark.parametrize("version", VERSIONS)
def test_the_choice_an_older_version_made_by_itself_is_cleared(version: str) -> None:
    """Chinese, added on that version: "Past what you know" was the app's,
    so every word is linked now."""
    stored = saved_by(version, "ja_chinese")
    assert stored["language_choices"] == {"zh": {"links": "past_known"}}
    value = AppSettings.from_stored(stored)
    assert value.choices_for("zh").links is LinkChoice.EVERY
    assert value.language_choices == {}
    assert value.language_links_chosen


@pytest.mark.parametrize("version", VERSIONS)
def test_a_choice_the_learner_made_stays(version: str) -> None:
    """Spanish's links from the 3,000th word were chosen: kept, beside
    Chinese's cleared."""
    value = AppSettings.from_stored(saved_by(version, "en_chinese"))
    assert value.choices_for("zh").links is LinkChoice.EVERY
    assert value.choices_for("es") == LanguageChoices(
        links=LinkChoice.PAST_KNOWN, links_from=3000
    )
    off = AppSettings.from_stored({"language_choices": {"ja": {"links": "off"}}})
    assert off.choices_for("ja").links is LinkChoice.OFF
    window = AppSettings.from_stored(
        {"language_choices": {"zh": {"links": "past_known", "window": 500}}}
    )
    assert window.language_choices == {"zh": {"window": 500}}  # its window stays


@pytest.mark.parametrize("version", VERSIONS)
def test_past_what_you_know_chosen_again_is_kept(version: str) -> None:
    """Cleared once: the learner who chooses it again after the update
    keeps it through every restart."""
    store = MemorySettingsStore(saved_by(version, "ja_chinese"))
    settings = Settings(store)
    choices = LanguageChoices(links=LinkChoice.PAST_KNOWN)
    settings.update(**language_choices_changes(settings.value, "zh", choices))
    assert store.values["language_links_chosen"] is True
    again = Settings(MemorySettingsStore(store.values))
    assert again.value.choices_for("zh").links is LinkChoice.PAST_KNOWN


def test_a_file_from_this_version_is_read_as_saved() -> None:
    stored = {
        "language_choices": {"zh": {"links": "past_known"}},
        "language_links_chosen": True,
    }
    value = AppSettings.from_stored(stored)
    assert value.choices_for("zh").links is LinkChoice.PAST_KNOWN
