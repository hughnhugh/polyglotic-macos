"""Lookups kept on this PC with their counts and the last time
(polyglotic-hq 373; the user, DECISIONS #176 (c): "yes, keep everything"),
and a word the learner said they know, looked up again, offered in a check
and never changed by the app (#176 (d)). Made-up words."""

import pytest
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.learning.test_vocabulary import ENTRIES, eid, lookup

from polyglotic_desktop.core.learning.highlights import WordIntroductions
from polyglotic_desktop.core.learning.levels import UNLIMITED
from polyglotic_desktop.core.learning.lookups import (
    CHECK_AFTER,
    DEEP_WITHIN,
    TURNS_NEW_AFTER,
    LookupCount,
)
from polyglotic_desktop.core.learning.statuses import StatusSource
from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.lexicon.entries import SCHEMES
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    Level,
    WordInLine,
    WordStatus,
)
from polyglotic_desktop.ports.learning import StoredLookups, StoredStatus

ME, SUPERMARKET = ENTRIES["我"], ENTRIES["超市"]


def vocabulary(store: MemoryLearningStore, clock: Clock) -> Vocabulary:
    return Vocabulary(store, lookup, "hsk-2025", clock)


def test_each_lookup_is_counted_with_its_time_and_kept() -> None:
    store, clock = MemoryLearningStore(), Clock()
    vocab = vocabulary(store, clock)
    vocab.looked_up(SUPERMARKET, pinned=False)
    clock.advance(minutes=3)
    vocab.looked_up(SUPERMARKET, pinned=True)
    vocab.looked_up(SUPERMARKET, pinned=False)
    assert vocab.lookups(eid("超市")) == LookupCount(1, 2, clock.now, 0)
    assert vocab.lookups(eid("我")) == LookupCount()  # never looked up
    again = vocabulary(store, clock)  # the next start
    assert again.lookups(eid("超市")) == LookupCount(1, 2, clock.now, 0)


def test_a_word_said_known_and_looked_up_twice_is_offered_in_a_check() -> None:
    """It stays known: the app never changes the learner's own word."""
    store, clock = MemoryLearningStore(), Clock()
    vocab = vocabulary(store, clock)
    vocab.set_status(eid("超市"), WordStatus.KNOWN)
    vocab.looked_up(SUPERMARKET, pinned=False)  # a hover: no evidence
    vocab.looked_up(SUPERMARKET, pinned=True)
    assert vocab.to_check() == []
    vocab.looked_up(SUPERMARKET, pinned=True)
    assert CHECK_AFTER == 2
    assert vocab.to_check() == [eid("超市")]
    assert vocab.status(SUPERMARKET).status is WordStatus.KNOWN
    assert vocab.status(SUPERMARKET).source is StatusSource.LEARNER
    assert vocabulary(store, clock).to_check() == [eid("超市")]  # kept


def test_lookups_before_the_learner_said_known_dont_count_towards_a_check() -> None:
    vocab = vocabulary(MemoryLearningStore(), Clock())
    vocab.looked_up(SUPERMARKET, pinned=True)
    vocab.looked_up(SUPERMARKET, pinned=True)
    vocab.set_status(eid("超市"), WordStatus.KNOWN)
    assert vocab.to_check() == []
    assert vocab.lookups(eid("超市")).pinned == 2


def test_saying_anything_about_the_word_again_starts_the_check_again() -> None:
    vocab = vocabulary(MemoryLearningStore(), Clock())
    vocab.set_status(eid("超市"), WordStatus.KNOWN)
    vocab.looked_up(SUPERMARKET, pinned=True)
    vocab.looked_up(SUPERMARKET, pinned=True)
    vocab.set_status(eid("超市"), WordStatus.KNOWN)  # "Still know it": yes
    assert vocab.to_check() == []
    vocab.set_status(eid("超市"), WordStatus.LEARNING)
    vocab.looked_up(SUPERMARKET, pinned=True)
    vocab.looked_up(SUPERMARKET, pinned=True)
    assert vocab.to_check() == []  # not known: nothing to check


def test_a_word_only_assumed_known_turns_new_on_its_second_pinned_lookup() -> None:
    """One click alone leaves it known (397); the second turns it new, as
    one did before 397. Each lookup is counted; hovers never turn it."""
    vocab = vocabulary(MemoryLearningStore(), Clock())
    vocab.set_level(Level("hsk-2025", 1))
    assert vocab.status(ME).status is WordStatus.KNOWN
    vocab.looked_up(ME, pinned=True)
    vocab.looked_up(ME, pinned=False)
    assert vocab.status(ME).status is WordStatus.KNOWN
    assert TURNS_NEW_AFTER == 2
    vocab.looked_up(ME, pinned=True)
    assert vocab.status(ME).status is WordStatus.NEW
    assert vocab.status(ME).source is StatusSource.ESTIMATED
    assert vocab.lookups(eid("我")) == LookupCount(
        2, 1, vocab.lookups(eid("我")).last, 0
    )
    assert vocab.to_check() == []


@pytest.mark.parametrize("scheme", ["en-frequency", "hsk-2025"])
def test_one_click_never_dots_a_common_word_as_new(scheme: str) -> None:
    """397: in preview 1 "the", "that", "you", "but" and "man" were dotted
    as new (a few per caption, the window unlimited): each had been clicked
    once, and one click turned a word assumed known new. A learner who
    never set a line, and one at 2,000 words, click every one of the
    language's 1,000 commonest words once: none is new, none dotted.
    (Chinese's are HSK 3 or below here: by level, as main reads a line
    until 349's step 3, a commoner HSK 4 word is new without a click.)"""
    words = [
        EntryFacts(EntryId(f"test:{rank}"), 1 if rank <= 300 else 3, rank, False)
        for rank in range(1, 1001)
    ]
    by_id = {w.entry_id: w for w in words}
    for line in (None, 2000):
        vocab = Vocabulary(
            MemoryLearningStore(),
            lambda e, _: by_id.get(e),
            scheme,
            Clock(),
            level_words=lambda s, n: SCHEMES[s].words_at(n),
        )
        if line is not None:
            vocab.set_known_words(line)
        for word in words:
            vocab.looked_up(word, pinned=False)  # the card on hover, then
            vocab.looked_up(word, pinned=True)  # the click
        assert [
            w for w in words if vocab.status(w).status is not WordStatus.KNOWN
        ] == []
        caption = [WordInLine(n, n + 1, w) for n, w in enumerate(words)]
        for every in (WordIntroductions.A_FEW, WordIntroductions.EVERY):
            for size in (None, UNLIMITED):
                shown = vocab.highlights([("x" * len(words), caption)], every, size)
                assert shown[0].unfamiliar == [], (scheme, line, every, size)
        assert not any(vocab.knowledge.of(w).status is WordStatus.NEW for w in words)


def test_no_number_of_clicks_makes_a_word_deep_within_the_line_new() -> None:
    """397's loop: the harness clicked "The" on three rows and it was
    dotted again. A word in the first half of the line (`DEEP_WITHIN`)
    stays known however often it is clicked; one past it, up to the line,
    turns new on the second click. With no line set, the starting one
    (English: about 3,000 words) is the line."""
    the, cousin = (
        EntryFacts(EntryId("test:the"), 1, 1, False),
        EntryFacts(EntryId("test:cousin"), 1, 1600, False),
    )
    by_id = {w.entry_id: w for w in (the, cousin)}
    for line in (None, 2000):
        vocab = Vocabulary(
            MemoryLearningStore(),
            lambda e, _: by_id.get(e),
            "en-frequency",
            Clock(),
            level_words=lambda s, n: SCHEMES[s].words_at(n),
        )
        if line is not None:
            vocab.set_known_words(line)
        assert DEEP_WITHIN == 0.5
        for _ in range(5):
            vocab.looked_up(the, pinned=True)
        assert vocab.status(the).status is WordStatus.KNOWN
        assert vocab.lookups(the.entry_id).pinned == 5  # still counted
        vocab.looked_up(cousin, pinned=True)
        assert vocab.status(cousin).status is WordStatus.KNOWN
        vocab.looked_up(cousin, pinned=True)
        assert vocab.status(cousin).status is WordStatus.NEW, line


def test_a_status_one_click_left_before_397_is_not_read() -> None:
    """Learning data from before 397 keeps a status "new" (source
    "estimated") for every word clicked once - from before lookups were
    counted too (version 8 counted each as one pinned lookup). It isn't
    read: the word is as the line says, and the file is left as it was. A
    word looked up twice keeps its "new"."""
    store, clock = MemoryLearningStore(), Clock()
    vocab = vocabulary(store, clock)
    vocab.set_level(Level("hsk-2025", 2))  # both known by the line
    for facts in (ME, SUPERMARKET):
        store.save_status(StoredStatus(facts.entry_id, "new", "estimated", clock.now))
        store.save_lookups(StoredLookups(facts.entry_id, 1, 0, clock.now, 0))
    store.save_lookups(StoredLookups(eid("超市"), 2, 0, clock.now, 0))
    again = vocabulary(store, clock)
    assert again.status(ME).status is WordStatus.KNOWN  # one click: the line's
    assert again.status(ME).source is StatusSource.ESTIMATED
    assert again.knowledge.of(ME).known
    assert again.status(SUPERMARKET).status is WordStatus.NEW  # twice: kept
    assert eid("我") in store.statuses  # the file as it was


def test_lookups_go_with_the_learning_data_and_follow_a_merged_entry() -> None:
    store, clock = MemoryLearningStore(), Clock()
    old, new = EntryId("test:old"), EntryId("test:new")
    vocab = Vocabulary(
        store, lambda e, _: EntryFacts(e, 3, 5000, False), "hsk-2025", clock
    )
    vocab.looked_up(EntryFacts(old, 3, 5000, False), pinned=True)
    vocab.looked_up(EntryFacts(new, 3, 5000, False), pinned=False)
    merged = Vocabulary(
        store,
        lambda e, _: EntryFacts(new if e == old else e, 3, 5000, False),
        "hsk-2025",
        clock,
    )
    assert merged.follow_merged_entries([old]) == 1
    assert merged.lookups(new) == LookupCount(1, 1, clock.now, 0)
    assert merged.lookups(old) == LookupCount()
    assert list(store.lookups) == [new]
    merged.delete_learning_data()
    assert merged.lookups(new) == LookupCount() and store.lookups == {}
