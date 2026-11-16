"""Levels and frequency bands: which entries count as known at first run
for a learner's level (MVP.md, "Known words")."""

from polyglotic_desktop.core.lexicon.entries import (
    DEFAULT_CHINESE_SCHEME,
    ENGLISH_FREQUENCY,
    HSK_2021,
    HSK_2025,
    SCHEMES,
    DictionaryEntry,
)
from polyglotic_desktop.core.shared import EntryId, Level


def entry(rank: int | None = None, **levels: int) -> DictionaryEntry:
    pairs = tuple((scheme.replace("_", "-"), level) for scheme, level in levels.items())
    return DictionaryEntry(
        EntryId("cedict:test"), "爱好", "愛好", "ài hào", ("hobby",), rank, pairs
    )


def test_hsk_levels_are_stored_per_scheme_and_never_mixed() -> None:
    hobby = entry(hsk_2025=2, hsk_2021=1)
    assert hobby.level_in(HSK_2025) == 2 and hobby.level_in(HSK_2021) == 1
    assert hobby.is_at_or_below(Level("hsk-2021", 1))
    assert not hobby.is_at_or_below(Level("hsk-2025", 1))
    assert hobby.is_at_or_below(Level("hsk-2025", 7))


def test_an_entry_outside_a_scheme_is_never_known_from_it() -> None:
    assert not entry().is_at_or_below(Level("hsk-2025", 7))
    assert not entry(hsk_2025=1).is_at_or_below(Level("no-such-scheme", 9))


def test_english_bands_come_from_the_frequency_rank() -> None:
    assert entry(1).level_in(ENGLISH_FREQUENCY) == 1
    assert entry(1000).level_in(ENGLISH_FREQUENCY) == 1
    assert entry(1001).level_in(ENGLISH_FREQUENCY) == 2
    assert entry(20000).level_in(ENGLISH_FREQUENCY) == 7
    assert entry(20001).level_in(ENGLISH_FREQUENCY) is None
    assert entry(None).level_in(ENGLISH_FREQUENCY) is None
    assert entry(4000).is_at_or_below(Level("en-frequency", 4))  # top 5,000
    assert not entry(4000).is_at_or_below(Level("en-frequency", 3))  # top 3,000


def test_the_level_picker_offers_each_scheme_with_its_labels() -> None:
    assert list(SCHEMES) == ["hsk-2025", "hsk-2021", "en-frequency"]
    assert DEFAULT_CHINESE_SCHEME is HSK_2025  # the user's choice, 2026-11-04
    assert HSK_2025.levels[-1] == "7-9"
    assert len(ENGLISH_FREQUENCY.levels) == len(ENGLISH_FREQUENCY.cutoffs)


def test_a_syllabus_entry_says_how_many_words_its_level_holds() -> None:
    """What places a word beside its rank (polyglotic-hq 323): HSK 2025's
    level 3 is about 1,000 words. A frequency band says nothing more than
    the rank does; the 2021 standard has no sizes kept."""
    hobby = entry(6000, hsk_2025=3, hsk_2021=2)
    assert hobby.facts("hsk-2025").level_words == 1000
    assert hobby.facts("hsk-2025").level == 3
    assert hobby.facts("hsk-2021").level_words is None
    assert hobby.facts("en-frequency").level_words is None
    assert entry(6000).facts("hsk-2025").level_words is None  # not listed
    assert entry(40, hsk_2025=7).facts("hsk-2025").level_words == 11000
