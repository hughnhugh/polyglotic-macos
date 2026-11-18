"""Exposures counted once per finished caption, joins and withdrawals
following the latest finished text."""

from datetime import date

from tests.learning.fakes import facts

from polyglotic_desktop.core.learning.exposures import (
    RECENT_CAPTIONS,
    ExposureChange,
    ExposureCount,
    ExposureCounter,
    apply,
)
from polyglotic_desktop.core.shared import EntryId, WordInLine

DAY = date(2026, 11, 4)


def words(*names: str) -> list[WordInLine]:
    return [WordInLine(0, 1, facts(n, is_name=n.istitle())) for n in names]


def summary(changes: list[ExposureChange]) -> list[tuple[str, int]]:
    return [(c.entry_id.removeprefix("test:"), c.delta) for c in changes]


def test_a_word_counts_once_per_caption_and_names_not_at_all() -> None:
    counter = ExposureCounter()
    changes = counter.finished("c1", words("cat", "cat", "dog", "Zhang"), False, DAY)
    assert summary(changes) == [("cat", 1), ("dog", 1)]
    assert summary(counter.finished("c2", words("cat"), False, DAY)) == [("cat", 1)]


def test_a_join_finishing_a_caption_again_counts_only_the_difference() -> None:
    counter = ExposureCounter()
    counter.finished("c1", words("cat", "dog"), False, DAY)
    again = counter.finished("c1", words("cat", "bird"), False, DAY)
    assert summary(again) == [("dog", -1), ("bird", 1)]


def test_a_withdrawn_caption_takes_its_exposures_back() -> None:
    counter = ExposureCounter()
    counter.finished("c1", words("cat"), True, DAY)
    changes = counter.withdrawn("c1")
    assert summary(changes) == [("cat", -1)] and changes[0].by_you
    assert counter.withdrawn("c1") == []  # once only
    assert counter.withdrawn("never-seen") == []


def test_only_recent_captions_are_remembered() -> None:
    counter = ExposureCounter()
    for n in range(RECENT_CAPTIONS + 1):
        counter.finished(f"c{n}", words("cat"), False, DAY)
    assert counter.withdrawn("c0") == []  # forgotten: nothing to take back
    assert summary(counter.withdrawn(f"c{RECENT_CAPTIONS}")) == [("cat", -1)]


def test_the_mic_is_counted_separately_and_in_deck_only_when_in_the_deck() -> None:
    cat = EntryId("test:cat")
    count = ExposureCount()
    count = apply(count, ExposureChange(cat, 1, False, DAY), in_deck=False)
    count = apply(count, ExposureChange(cat, 1, False, DAY), in_deck=True)
    count = apply(count, ExposureChange(cat, 1, True, DAY), in_deck=True)
    assert count == ExposureCount(
        heard=2,
        heard_by_you=1,
        heard_in_deck=1,
        first_heard=DAY,
        days_heard=1,
        last_heard=DAY,
    )
    count = apply(count, ExposureChange(cat, -5, True, DAY), in_deck=True)
    assert count.heard_by_you == 0  # never below zero
