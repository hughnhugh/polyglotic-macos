"""Coverage: each finished caption's tokens counted towards its day, by the
learner's statuses as it finished - names known, the user's own mic left
out, a join counted once, a withdrawn caption taken back - and the last 7
days' share, with no number under 200 tokens (polyglotic-hq project 163,
155's L2)."""

from collections.abc import Callable
from datetime import date, timedelta

from tests.learning.fakes import MemoryLearningStore, words_of
from tests.learning.test_vocabulary import ENTRIES, Setup, eid

from polyglotic_desktop.core.learning.coverage import (
    MIN_TOKENS,
    Coverage,
    CoverageCounter,
    coverage_of,
)
from polyglotic_desktop.core.learning.vocabulary import Changed, VocabularyChanged
from polyglotic_desktop.core.shared import EntryFacts, Level, WordStatus

LINE = "我 今天 和 张伟 去 超市 买 水果 和 酸奶"  # 10 tokens, 张伟 a name
DAY = date(2026, 11, 4)


def statuses(**by_word: WordStatus) -> Callable[[EntryFacts], WordStatus]:
    found = {eid(w): s for w, s in by_word.items()}
    return lambda facts: found.get(facts.entry_id, WordStatus.NEW)


def test_a_captions_tokens_by_status_names_and_ignored_words_known() -> None:
    words = words_of(LINE, ENTRIES)
    status = statuses(
        我=WordStatus.KNOWN,
        和=WordStatus.KNOWN,
        去=WordStatus.IGNORED,
        水果=WordStatus.LEARNING,
        张伟=WordStatus.NEW,  # a name counts as known whatever its status
    )
    covered = coverage_of(words, status)
    # 我 和 和 张伟 去 known (5); 水果 in the deck; 今天 超市 买 酸奶 new
    assert covered == Coverage(known=5, deck=1, new=4)
    assert covered.tokens == 10  # every time a word comes up, not once


def test_no_share_under_200_tokens() -> None:
    assert Coverage(known=MIN_TOKENS - 1).share is None
    assert Coverage(known=MIN_TOKENS - 1).one_new_in is None
    assert Coverage(known=MIN_TOKENS).share == 1.0


def test_the_share_and_one_word_in_n() -> None:
    week = Coverage(known=910, deck=30, new=60)
    assert week.share == 0.91
    assert week.one_new_in == 11  # 90 not known of 1,000: 1 in 11
    assert Coverage(known=1000).one_new_in is None  # every word known


def test_a_join_replaces_what_its_caption_counted() -> None:
    counter = CoverageCounter()
    first = counter.finished("c1", Coverage(known=3, new=1), DAY)
    again = counter.finished("c1", Coverage(known=5, new=1), DAY)
    assert first == {DAY: Coverage(known=3, new=1)}
    assert again == {DAY: Coverage(known=2)}  # only the difference
    assert counter.finished("c1", Coverage(known=5, new=1), DAY) == {}


def test_a_withdrawn_caption_takes_back_what_it_counted() -> None:
    counter = CoverageCounter()
    counter.finished("c1", Coverage(known=3, deck=2), DAY)
    assert counter.withdrawn("c1") == {DAY: Coverage(known=-3, deck=-2)}
    assert counter.withdrawn("c1") == {}  # never counted twice
    assert counter.withdrawn("never seen") == {}


def test_a_join_after_midnight_moves_the_caption_to_the_new_day() -> None:
    counter = CoverageCounter()
    counter.finished("c1", Coverage(known=4), DAY)
    nxt = DAY + timedelta(days=1)
    assert counter.finished("c1", Coverage(known=4), nxt) == {
        DAY: Coverage(known=-4),
        nxt: Coverage(known=4),
    }


def _finish(s: Setup, caption_id: str, line: str = LINE, by_you: bool = False) -> None:
    s.vocab.caption_finished(caption_id, words_of(line, ENTRIES), by_you)


def test_vocabulary_counts_each_finished_caption_by_the_statuses_then() -> None:
    s = Setup()
    s.vocab.set_level(Level("hsk-2025", 0))  # just starting: every word new
    s.vocab.set_status(eid("我"), WordStatus.KNOWN)
    _finish(s, "c1")  # 我 known; 张伟 a name; 8 new
    s.vocab.set_status(eid("和"), WordStatus.KNOWN)
    s.vocab.set_status(eid("水果"), WordStatus.LEARNING)
    _finish(s, "c2")  # 我 和 和 张伟 known; 水果 in the deck
    assert s.vocab.coverage() == Coverage(known=2 + 4, deck=1, new=8 + 5)
    # marking a word known later doesn't change what was counted
    s.vocab.set_status(eid("酸奶"), WordStatus.KNOWN)
    assert s.vocab.coverage() == Coverage(known=6, deck=1, new=13)


def test_the_users_own_mic_counts_no_coverage() -> None:
    s = Setup()
    _finish(s, "mine", by_you=True)
    assert s.vocab.coverage() == Coverage()
    assert s.store.coverage == {}


def test_a_join_and_a_withdrawal_through_vocabulary() -> None:
    s = Setup()
    _finish(s, "c1", "我 去 超市")
    _finish(s, "c1", "我 今天 去 超市")  # the join: one more token, not four
    assert s.vocab.coverage().tokens == 4
    s.vocab.caption_withdrawn("c1")
    assert s.vocab.coverage() == Coverage()
    assert s.store.coverage[DAY].known + s.store.coverage[DAY].new == 0


def test_the_last_7_days_today_included() -> None:
    s = Setup()
    _finish(s, "old")  # 2026-11-04
    s.clock.advance(days=7)  # 2026-11-11: the 4th is 8 days back
    _finish(s, "new", "我 去")
    assert s.vocab.coverage().tokens == 2
    assert s.vocab.coverage(days=8).tokens == 12
    s.clock.advance(days=6)  # the 17th: the 11th is the 7th day back
    assert s.vocab.coverage().tokens == 2


def test_one_change_published_per_caption() -> None:
    s = Setup()
    s.events.clear()
    _finish(s, "c1")
    assert s.events == [VocabularyChanged(Changed.EXPOSURES)]
    s.events.clear()
    _finish(s, "c2", "张伟")  # a name alone: no exposure, but a token
    assert s.events == [VocabularyChanged(Changed.EXPOSURES)]
    assert s.vocab.coverage().tokens == 11


def test_coverage_is_kept_and_deleted_with_the_learning_data() -> None:
    store = MemoryLearningStore()
    s = Setup(store)
    s.vocab.set_level(Level("hsk-2025", 0))  # just starting: every word new
    _finish(s, "c1")
    again = Setup(store)  # the app started again
    assert again.vocab.coverage() == Coverage(known=1, new=9)
    again.vocab.delete_learning_data()
    assert again.vocab.coverage() == Coverage()
    assert store.coverage == {}


def test_new_words_are_those_first_heard_in_the_last_7_days() -> None:
    """`first_heard` (polyglotic-hq 163, L5): set when a word is first heard
    from what the PC played, cleared if a withdrawal takes it back."""
    s = Setup()
    _finish(s, "old", "我 去")  # 2026-11-04
    s.clock.advance(days=7)  # the 11th
    _finish(s, "new", "我 超市")
    assert s.vocab.exposures(eid("我")).first_heard == date(2026, 11, 4)
    assert s.vocab.exposures(eid("超市")).first_heard == date(2026, 11, 11)
    assert s.vocab.new_words() == 1  # 超市; 我 and 去 were the 4th
    assert s.vocab.new_words(days=8) == 3
    _finish(s, "mine", "酸奶", by_you=True)  # the mic: not met
    assert s.vocab.exposures(eid("酸奶")).first_heard is None
    s.vocab.caption_withdrawn("new")
    assert s.vocab.exposures(eid("超市")).first_heard is None
    assert s.vocab.new_words() == 0
