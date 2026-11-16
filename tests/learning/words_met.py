"""A learner's words met for the tests of what Words reads (polyglotic-hq
project 212): words heard, one only given a status and one only saved, on
a made-up dictionary whose reads are counted."""

from datetime import UTC, datetime

from tests.learning.fakes import MemoryLearningStore, facts

from polyglotic_desktop.core.learning.vocabulary import Vocabulary
from polyglotic_desktop.core.shared import EntryFacts, EntryId, Level
from polyglotic_desktop.ports.learning import (
    StoredExposures,
    StoredSavedWord,
    StoredStatus,
)


def eid(word: str) -> EntryId:
    return EntryId(f"test:{word}")


ENTRIES = {
    f.entry_id: f
    for f in (
        facts("我", level=1, rank=5),
        facts("超市", level=2, rank=3000),
        facts("酸奶", level=3, rank=9000),
        facts("榴莲", level=None, rank=30000),
        facts("张伟", level=None, rank=None, is_name=True),
        facts("折扣", level=4, rank=7000),
        facts("水果", level=2, rank=2500),
    )
}
APPLE = facts("苹果", level=1, rank=900)  # not met at the start
ENTRIES_AND_APPLE = {**ENTRIES, APPLE.entry_id: APPLE}
HEARD = {"我": (40, 0), "超市": (9, 1), "酸奶": (9, 0), "榴莲": (9, 0), "张伟": (3, 0)}
"""Heard from the PC and by you: 超市, 酸奶 and 榴莲 tie on the PC."""
HEARD_BY_ID = {eid(word): heard for word, heard in HEARD.items()}


class Counting:
    """The dictionary's facts, counting the reads."""

    def __init__(self, entries: dict[EntryId, EntryFacts] = ENTRIES_AND_APPLE) -> None:
        self.entries = entries
        self.read: list[tuple[EntryId, str]] = []

    def __call__(self, entry_id: EntryId, scheme: str) -> EntryFacts | None:
        self.read.append((entry_id, scheme))
        return self.entries.get(entry_id)


def store(heard: dict[EntryId, tuple[int, int]] | None = None) -> MemoryLearningStore:
    """Words heard, one only given a status (折扣) and one only saved
    (水果) - all met - with HSK 1 picked."""
    found = MemoryLearningStore()
    for entry_id, (times, by_you) in (heard or HEARD_BY_ID).items():
        found.exposures[entry_id] = StoredExposures(entry_id, times, by_you, 0)
    at = datetime(2026, 11, 8, tzinfo=UTC)
    found.statuses[eid("折扣")] = StoredStatus(eid("折扣"), "known", "learner", at)
    found.words[eid("水果")] = StoredSavedWord(
        eid("水果"), "水果", "水果", "shuǐ guǒ", "fruit", "saved", "", "", at
    )
    Vocabulary(found, Counting(), "hsk-2025").set_level(Level("hsk-2025", 1))
    return found


def started(lookup: Counting, kept: MemoryLearningStore | None = None) -> Vocabulary:
    """The learner's vocabulary as at the app's start: nothing read yet."""
    return Vocabulary(kept or store(), lookup, "hsk-2025")
