"""Learning data from the server, deleting it, and handing over finished
days' exposure counts (core.learning.vocabulary): what another PC set is
applied by the latest-wins rule and never published back; deleting
empties this PC's data but keeps the level and categories."""

from datetime import UTC, date, datetime, timedelta

from tests.learning.fakes import MemoryLearningStore
from tests.learning.test_vocabulary import ENTRIES, LINE, Setup, eid, words_of

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.statuses import StatusSource
from polyglotic_desktop.core.learning.vocabulary import (
    Changed,
    EntryText,
    VocabularyChanged,
)
from polyglotic_desktop.core.shared import (
    EntryId,
    Level,
    WordSaved,
    WordStatus,
    WordStatusChanged,
    WordUnsaved,
)

EARLIER = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


def describe(entry_id: EntryId) -> EntryText | None:
    if entry_id == eid("榴莲"):
        return EntryText("榴莲", "榴槤", "liú lián", "durian")
    return None


def changes(s: Setup) -> list[Changed]:
    found = [e.what for e in s.events if isinstance(e, VocabularyChanged)]
    s.events.clear()
    return found


def test_a_status_from_another_pc_is_applied_and_not_sent_back() -> None:
    s = Setup()
    applied = s.vocab.apply_from_server(
        [WordStatusChanged(eid("酸奶"), WordStatus.KNOWN, EARLIER)], describe
    )
    assert applied == 1
    record = s.vocab.status_of_entry(eid("酸奶"))
    assert (record.status, record.source, record.at) == (
        WordStatus.KNOWN,
        StatusSource.LEARNER,
        EARLIER,
    )
    assert s.store.statuses[eid("酸奶")].source == "learner"
    assert s.sent() == []  # nothing published for the server
    assert changes(s) == []  # sent() cleared them; check the next one
    s.vocab.apply_from_server(
        [WordStatusChanged(eid("超市"), WordStatus.LEARNING, EARLIER)], describe
    )
    assert changes(s) == [Changed.STATUSES]


def test_the_latest_status_wins() -> None:
    s = Setup()
    s.vocab.set_status(eid("酸奶"), WordStatus.LEARNING)  # at the clock: 2026-11-04
    stale = WordStatusChanged(eid("酸奶"), WordStatus.KNOWN, EARLIER)
    assert s.vocab.apply_from_server([stale], describe) == 0
    assert s.vocab.status_of_entry(eid("酸奶")).status is WordStatus.LEARNING
    newer = WordStatusChanged(eid("酸奶"), WordStatus.KNOWN, LATER)
    assert s.vocab.apply_from_server([newer], describe) == 1
    assert s.vocab.status_of_entry(eid("酸奶")).status is WordStatus.KNOWN


def test_the_learners_own_status_wins_over_an_estimate_here() -> None:
    s = Setup()
    s.vocab.set_level(Level("hsk-2025", 2))
    s.vocab.looked_up(ENTRIES["我"], pinned=True)  # estimated known -> new, now
    own = WordStatusChanged(eid("我"), WordStatus.KNOWN, EARLIER)
    assert s.vocab.apply_from_server([own], describe) == 1
    record = s.vocab.status_of_entry(eid("我"))
    assert record.status is WordStatus.KNOWN and record.is_learners_own


def test_a_word_saved_on_another_pc() -> None:
    s = Setup()
    events = [WordSaved(eid("榴莲"), EARLIER), WordSaved(eid("折扣"), EARLIER)]
    assert (
        s.vocab.apply_from_server(events, describe) == 1
    )  # 折扣: not in this dictionary
    (word,) = s.vocab.saved_words
    assert (word.headword, word.traditional, word.reading, word.meaning) == (
        "榴莲",
        "榴槤",
        "liú lián",
        "durian",
    )
    assert word.category_id == s.vocab.categories[0].id
    assert (word.source_sentence, word.saved_at) == ("", EARLIER)
    assert s.sent() == []
    spans = s.vocab.saved_spans(LINE, words_of(LINE, ENTRIES))
    assert [LINE[x.start : x.end] for x in spans] == ["榴莲"]  # highlighted at once


def test_a_word_saved_here_keeps_its_sentence() -> None:
    s = Setup()
    category = s.vocab.categories[1].id
    s.vocab.save(
        eid("榴莲"), "榴莲", "", "", "", category, LookupContext("我 买 榴莲", "")
    )
    s.vocab.apply_from_server([WordSaved(eid("榴莲"), EARLIER)], describe)
    word = s.vocab.saved_word(eid("榴莲"))
    assert word is not None
    assert (word.category_id, word.source_sentence) == (category, "我 买 榴莲")


def test_a_word_unsaved_elsewhere_later_is_unsaved_here() -> None:
    s = Setup()
    category = s.vocab.categories[0].id
    s.vocab.save(eid("榴莲"), "榴莲", "", "", "", category, LookupContext("", ""))
    stale = WordUnsaved(eid("榴莲"), EARLIER)
    assert s.vocab.apply_from_server([stale], describe) == 0
    assert s.vocab.saved_word(eid("榴莲")) is not None
    assert s.vocab.apply_from_server([WordUnsaved(eid("榴莲"), LATER)], describe) == 1
    assert s.vocab.saved_word(eid("榴莲")) is None
    assert eid("榴莲") not in s.store.words
    assert [e for e in s.sent() if isinstance(e, WordUnsaved)] == []


def test_deleting_the_learning_data_on_this_pc() -> None:
    store = MemoryLearningStore()
    s = Setup(store)
    s.vocab.set_level(Level("hsk-2025", 2))
    s.vocab.set_status(eid("酸奶"), WordStatus.LEARNING)
    category = s.vocab.categories[0].id
    s.vocab.save(eid("榴莲"), "榴莲", "", "", "", category, LookupContext("x", ""))
    s.vocab.caption_finished("c1", words_of(LINE, ENTRIES), by_you=False)
    s.sent()
    s.vocab.delete_learning_data()
    assert s.vocab.saved_words == [] and s.vocab.vocabulary_list() == []
    assert s.vocab.exposures(eid("酸奶")).heard == 0
    assert s.vocab.line is not None and len(s.vocab.categories) == 2
    assert s.sent() == []  # no unsaves or statuses published
    assert not store.statuses and not store.words and not store.exposures
    assert not store.daily and store.level is not None and store.categories


def test_finished_days_are_handed_over_once() -> None:
    s = Setup()
    words = words_of(LINE, ENTRIES)
    s.vocab.caption_finished("c1", words, by_you=False)  # 2026-11-04
    s.clock.advance(days=1)
    s.vocab.caption_finished("c2", words[:2], by_you=False)  # 2026-11-05
    s.vocab.caption_finished("c3", words[:1], by_you=True)  # the mic: never shared
    today = date(2026, 11, 5)
    taken = s.vocab.take_finished_exposure_days(today)
    assert list(taken) == [date(2026, 11, 4)]
    assert taken[date(2026, 11, 4)][eid("酸奶")] == 1
    assert eid("张伟") not in taken[date(2026, 11, 4)]  # names aren't counted
    assert s.vocab.take_finished_exposure_days(today) == {}
    later = s.vocab.take_finished_exposure_days(today + timedelta(days=1))
    assert later == {date(2026, 11, 5): {eid("我"): 1, eid("今天"): 1}}
    assert s.vocab.exposures(eid("我")).heard == 2  # the totals stay


def test_daily_counts_stay_on_the_pc_8_weeks_once_handed_over() -> None:
    """Decision 0041 (polyglotic-hq 163, DECISIONS.md #64's default): a
    finished day is handed over once, then kept - not deleted - until it's
    8 weeks old. Before, it was forgotten as it was handed over."""
    s = Setup()
    s.vocab.caption_finished("c1", words_of(LINE, ENTRIES), by_you=False)
    day = date(2026, 11, 4)
    assert list(s.vocab.take_finished_exposure_days(day + timedelta(days=1))) == [day]
    assert s.store.daily[day][eid("酸奶")] == 1  # kept on this PC
    assert s.vocab.take_finished_exposure_days(day + timedelta(days=2)) == {}
    s.vocab.take_finished_exposure_days(day + timedelta(weeks=8))  # 8 weeks: kept
    assert day in s.store.daily
    s.vocab.take_finished_exposure_days(day + timedelta(weeks=8, days=1))
    assert day not in s.store.daily and day not in s.store.handed_over
