"""A dictionary update merged an entry into another (decision 0007): what
the learner had under the old entry ID follows it to the new one."""

from datetime import timedelta

from tests.learning.fakes import Clock, MemoryLearningStore, facts

from polyglotic_desktop.core.learning.lookups import LookupContext
from polyglotic_desktop.core.learning.vocabulary import Vocabulary, VocabularyChanged
from polyglotic_desktop.core.shared import (
    EntryFacts,
    EntryId,
    LearningEvent,
    WordInLine,
    WordSaved,
    WordStatus,
    WordStatusChanged,
)

OLD = EntryId("test:錶帶-old")
NEW = EntryId("test:錶帶")
OTHER = EntryId("test:other")


def before(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    return EntryFacts(entry_id, 3, 5000, False)


def after(entry_id: EntryId, scheme: str) -> EntryFacts | None:
    """The updated dictionary: OLD now resolves to NEW."""
    return EntryFacts(NEW if entry_id == OLD else entry_id, 3, 5000, False)


def test_statuses_saves_and_exposures_follow_a_merged_entry() -> None:
    store = MemoryLearningStore()
    clock = Clock()
    vocab = Vocabulary(store, before, "hsk-2025", clock)
    vocab.set_status(OLD, WordStatus.LEARNING)
    vocab.save(
        OLD, "表带", "錶帶", "biǎo dài", "watchband", "saved", LookupContext("x")
    )
    vocab.caption_finished("c1", [WordInLine(0, 2, facts("錶帶-old"))], by_you=False)
    vocab.caption_finished("c2", [WordInLine(0, 2, facts("錶帶"))], by_you=False)
    set_at = clock.now

    updated = Vocabulary(store, after, "hsk-2025", clock)
    events: list[LearningEvent | VocabularyChanged] = []
    updated.subscribe(events.append)
    assert updated.follow_merged_entries([OLD]) == 1
    assert updated.status_of_entry(NEW).status is WordStatus.LEARNING
    word = updated.saved_word(NEW)
    assert word is not None and word.traditional == "錶帶"
    assert updated.saved_word(OLD) is None
    assert updated.exposures(NEW).heard == 2  # added together
    sent = [e for e in events if not isinstance(e, VocabularyChanged)]
    assert sent == [
        WordStatusChanged(NEW, WordStatus.LEARNING, set_at),
        WordSaved(NEW, word.saved_at),
    ]
    # kept: nothing left under the old ID, and nothing to move next time
    assert OLD not in store.statuses and OLD not in store.words
    assert OLD not in store.exposures
    assert Vocabulary(store, after, "hsk-2025").follow_merged_entries([OLD]) == 0


def test_the_later_status_wins_when_both_entries_had_one() -> None:
    store = MemoryLearningStore()
    clock = Clock()
    vocab = Vocabulary(store, before, "hsk-2025", clock)
    vocab.set_status(NEW, WordStatus.KNOWN)
    clock.now += timedelta(days=1)
    vocab.set_status(OLD, WordStatus.IGNORED)
    vocab.set_status(OTHER, WordStatus.KNOWN)

    updated = Vocabulary(store, after, "hsk-2025", clock)
    assert updated.follow_merged_entries([OLD]) == 1
    assert updated.status_of_entry(NEW).status is WordStatus.IGNORED
    assert updated.status_of_entry(OTHER).status is WordStatus.KNOWN


def test_only_the_dictionarys_merged_ids_are_looked_up() -> None:
    """At start, before the window: every word met's facts took 0.35 s at
    30,000 words met on CC-CEDICT, to find none merged (the shipped files
    have none; polyglotic-hq 220). Only the learner's among the
    dictionary's merged IDs are asked for now."""
    store = MemoryLearningStore()
    vocab = Vocabulary(store, before, "hsk-2025", Clock())
    for n in range(1000):
        vocab.set_status(EntryId(f"test:{n}"), WordStatus.KNOWN)
    vocab.set_status(OLD, WordStatus.LEARNING)
    asked: list[EntryId] = []

    def counted(entry_id: EntryId, scheme: str) -> EntryFacts | None:
        asked.append(entry_id)
        return after(entry_id, scheme)

    updated = Vocabulary(store, counted, "hsk-2025", Clock())
    assert updated.follow_merged_entries([OLD, EntryId("test:not-met")]) == 1
    assert asked == [OLD]
    assert updated.status_of_entry(NEW).status is WordStatus.LEARNING
    asked.clear()
    assert Vocabulary(store, counted, "hsk-2025").follow_merged_entries([]) == 0
    assert asked == []
