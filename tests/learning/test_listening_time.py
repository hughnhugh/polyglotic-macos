"""Listening time: the time from one finished caption to the next counts,
to the next one's day and source category, unless the gap was 2 minutes or
more; two sources at once count the time once; kept per UTC day and
deleted with the learning data (polyglotic-hq project 163, 155's L3)."""

from datetime import UTC, date, datetime, timedelta

from tests.learning.fakes import MemoryLearningStore
from tests.learning.test_vocabulary import Setup

from polyglotic_desktop.core.learning.listening_time import (
    STILL_LISTENING_SEC,
    Listened,
    ListeningCounter,
)
from polyglotic_desktop.core.learning.vocabulary import Changed, VocabularyChanged

AT = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
DAY = date(2026, 11, 4)


def at(seconds: float) -> datetime:
    return AT + timedelta(seconds=seconds)


def test_the_time_between_finished_captions_counts_to_the_later_ones_category() -> None:
    counter = ListeningCounter()
    assert counter.heard(at(0), "video") is None  # the first of a run: nothing
    assert counter.heard(at(4), "video") == Listened(DAY, "video", 4.0)
    assert counter.heard(at(10), "game") == Listened(DAY, "game", 6.0)


def test_a_long_gap_starts_a_new_run_and_doesnt_count() -> None:
    counter = ListeningCounter()
    counter.heard(at(0), "video")
    quiet = at(STILL_LISTENING_SEC - 1)  # a quiet stretch: still listening
    assert counter.heard(quiet, "video") == Listened(
        DAY, "video", STILL_LISTENING_SEC - 1
    )
    later = quiet + timedelta(seconds=STILL_LISTENING_SEC)  # paused, or left on
    assert counter.heard(later, "video") is None
    assert counter.heard(later + timedelta(seconds=3), "video") == Listened(
        DAY, "video", 3.0
    )


def test_two_sources_at_once_count_the_time_once() -> None:
    counter = ListeningCounter()
    counted = [
        counter.heard(at(s), category)
        for s, category in [(0, "video"), (2, "call"), (3, "video"), (7, "call")]
    ]
    assert sum(c.seconds for c in counted if c is not None) == 7.0


def test_after_midnight_the_seconds_go_to_the_new_day() -> None:
    counter = ListeningCounter()
    counter.heard(datetime(2026, 11, 4, 23, 59, 58, tzinfo=UTC), "video")
    late = counter.heard(datetime(2026, 11, 5, 0, 0, 3, tzinfo=UTC), "video")
    assert late == Listened(date(2026, 11, 5), "video", 5.0)


def test_vocabulary_keeps_the_days_and_sums_the_last_7() -> None:
    store = MemoryLearningStore()
    s = Setup(store)
    for _ in range(4):  # three gaps of 10 s on the 4th
        s.vocab.listened("video")
        s.clock.advance(seconds=10)
    s.clock.advance(days=7)  # the 11th: the 4th is 8 days back
    s.events.clear()
    s.vocab.listened("game")
    s.clock.advance(seconds=5)
    s.vocab.listened("game")
    assert s.events == [VocabularyChanged(Changed.EXPOSURES)]  # once: one counted
    assert s.vocab.listening() == 35.0
    assert s.vocab.listening(days=7) == 5.0
    assert s.vocab.listening(days=8) == 35.0
    again = Setup(store)  # the app started again
    again.clock.now = s.clock.now
    assert again.vocab.listening() == 35.0 and again.vocab.listening(days=7) == 5.0
    again.vocab.delete_learning_data()
    assert again.vocab.listening() == 0.0 and store.listening == {}
