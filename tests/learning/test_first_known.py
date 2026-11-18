"""Marking the commonest words known at once, Undo and Reset (polyglotic-hq
342; the user, 2026-11-15: "a quick select option to mark first x
thousand words as known, make this resettable too"): one move of the known
line, never a status per word, so the learner's own marks survive all
three - and the learning file's statuses are the same before and after."""

import sqlite3
from pathlib import Path

import pytest
from tests.learning.fakes import Clock, MemoryLearningStore
from tests.learning.test_vocabulary import ENTRIES, eid, lookup

from polyglotic_desktop.adapters.sqlite_learning import (
    VERSION,
    SqliteLearningStore,
    level_file,
)
from polyglotic_desktop.core.learning.first_known import (
    FIRST_KNOWN,
    Before,
    QuickMarks,
    marks_more,
)
from polyglotic_desktop.core.learning.levels import KnownLine
from polyglotic_desktop.core.learning.vocabulary import (
    Changed,
    Vocabulary,
    VocabularyChanged,
)
from polyglotic_desktop.core.shared import (
    LearningEvent,
    Level,
    WordStatus,
    WordStatusChanged,
)
from polyglotic_desktop.ports.learning import LearningStore

# -- the rules ------------------------------------------------------------------------------


def test_only_a_number_past_the_line_marks_more() -> None:
    assert FIRST_KNOWN == (1000, 2000, 3000, 5000, 10000)
    assert [marks_more(3000, n) for n in FIRST_KNOWN] == [
        False, False, False, True, True,
    ]  # fmt: skip
    assert marks_more(None, 1000)  # a scheme not known in words: any
    assert not marks_more(0, 0)


def test_undo_goes_back_one_mark_and_reset_to_before_the_first() -> None:
    hsk3 = KnownLine("hsk-2025", 3)
    marks = QuickMarks().marked(hsk3)  # HSK 3 -> 2,000
    assert marks == QuickMarks(Before(hsk3), Before(hsk3))
    marks = marks.marked(KnownLine.words(2000))  # 2,000 -> 5,000
    assert marks.reset_to == Before(hsk3)  # still before the first
    assert marks.undo_to == Before(KnownLine.words(2000))
    undone = marks.undone()
    assert undone is not None
    back, after = undone
    assert back == Before(KnownLine.words(2000))
    assert after == QuickMarks(Before(hsk3))  # Reset stays; Undo is used
    assert after.undone() is None
    reset = after.reset()
    assert reset == (Before(hsk3), QuickMarks())
    assert QuickMarks().reset() is None


def test_undoing_the_first_mark_leaves_nothing_to_reset() -> None:
    marks = QuickMarks().marked(None)  # no line set yet
    undone = marks.undone()
    assert undone == (Before(None), QuickMarks())


@pytest.mark.parametrize(
    "line",
    [None, KnownLine.words(0), KnownLine.words(3000), KnownLine("hsk-2025", 3)],
)
def test_where_reset_goes_is_kept_as_it_was(line: KnownLine | None) -> None:
    kept = Before(line).to_stored()
    assert Before.from_stored(kept) == Before(line)


@pytest.mark.parametrize(
    "stored", [None, "words", {"scale": "words"}, {"scale": "", "known": 3},
               {"scale": "words", "known": -1}, {"scale": "words", "known": True}]
)  # fmt: skip
def test_a_reset_point_not_valid_is_no_reset(stored: object) -> None:
    assert Before.from_stored(stored) is None


# -- the learner's vocabulary ---------------------------------------------------------------


class Learner:
    def __init__(self, store: LearningStore) -> None:
        self.store = store
        self.vocab = Vocabulary(store, lookup, "hsk-2025", Clock())
        self.events: list[LearningEvent | VocabularyChanged] = []
        self.vocab.subscribe(self.events.append)

    def status(self, word: str) -> WordStatus:
        return self.vocab.status_of_entry(eid(word)).status

    def statuses(self) -> dict[str, WordStatus]:
        return {word: self.status(word) for word in ENTRIES}


def test_marking_the_first_words_known_moves_the_line_and_keeps_hand_marks() -> None:
    """超市 (rank 3,000) and 折扣 (7,000) are new to a learner of 1,000
    words; marking the first 5,000 makes 超市 known, not 折扣 - and a word
    the learner made new again by hand (还有, rank 150) stays new."""
    s = Learner(MemoryLearningStore())
    s.vocab.set_known_words(1000)
    s.vocab.set_status(eid("还有"), WordStatus.NEW)  # their own mark
    s.vocab.set_status(eid("折扣"), WordStatus.KNOWN)  # their own mark
    s.events.clear()
    s.vocab.set_known_words(5000)  # "Mark the first 5,000 known"
    assert s.status("超市") is WordStatus.KNOWN
    assert s.status("酸奶") is WordStatus.NEW  # rank 9,000
    assert s.status("还有") is WordStatus.NEW and s.status("折扣") is WordStatus.KNOWN
    # one change of the line: nothing sent per word
    assert s.events == [VocabularyChanged(Changed.LEVEL)]
    assert not any(isinstance(e, WordStatusChanged) for e in s.events)


def test_undo_and_reset_restore_the_line_and_never_touch_hand_marks() -> None:
    s = Learner(MemoryLearningStore())
    s.vocab.set_level(Level("hsk-2025", 1))  # as an older picker kept it
    s.vocab.set_status(eid("还有"), WordStatus.NEW)
    before = s.statuses()
    marks = QuickMarks().marked(s.vocab.line)
    s.vocab.set_known_words(10000)
    assert s.status("酸奶") is WordStatus.KNOWN and s.status("还有") is WordStatus.NEW
    s.vocab.set_status(eid("超市"), WordStatus.LEARNING)  # marked after: theirs
    reset = marks.reset()
    assert reset is not None
    s.vocab.restore_line(reset[0].line)
    assert s.vocab.line == KnownLine("hsk-2025", 1)
    after = s.statuses()
    assert after.pop("超市") is WordStatus.LEARNING  # kept through the reset
    before.pop("超市")
    assert after == before


def test_going_back_to_no_line_clears_the_level_kept() -> None:
    """A quick mark made before any level was set: Undo goes back to none
    - estimated at the starting level, and none kept, so a new start reads
    none too (not the level the mark wrote)."""
    store = MemoryLearningStore()
    s = Learner(store)
    assert s.vocab.line is None
    before = s.statuses()
    s.vocab.set_known_words(10000)
    s.vocab.restore_line(None)
    assert s.vocab.line is None and store.level is None
    assert s.statuses() == before
    assert Vocabulary(store, lookup, "hsk-2025").line is None


# -- the learning file, before and after ------------------------------------------------------


def _rows(path: Path) -> dict[str, list[tuple[object, ...]]]:
    db = sqlite3.connect(path)
    try:
        return {
            "version": db.execute("PRAGMA user_version").fetchall(),
            "level": db.execute("SELECT scheme, midpoint FROM level").fetchall(),
            "statuses": db.execute(
                "SELECT entry_id, status, source FROM statuses ORDER BY entry_id"
            ).fetchall(),
        }
    finally:
        db.close()


def test_the_learning_file_changes_only_its_level_row(tmp_path: Path) -> None:
    """Marking writes one row - the level - and no status: the file stays
    at the version it was opened at. Reset puts the row back as it was;
    back to no line, the row and its copy beside the file go."""
    path = tmp_path / "learning.sqlite"
    store = SqliteLearningStore(path)
    s = Learner(store)
    s.vocab.set_status(eid("还有"), WordStatus.NEW)
    s.vocab.set_known_words(1000)
    store.close()
    first = _rows(path)
    assert first["version"] == [(VERSION,)] and VERSION == 11

    store = SqliteLearningStore(path)
    s = Learner(store)
    s.vocab.set_known_words(5000)
    store.close()
    marked = _rows(path)
    assert marked["level"] == [("words", 5000.0)]
    assert marked["statuses"] == first["statuses"]  # not one row more
    assert marked["version"] == first["version"]

    store = SqliteLearningStore(path)
    Learner(store).vocab.restore_line(KnownLine.words(1000))
    store.close()
    assert _rows(path) == first

    store = SqliteLearningStore(path)
    Learner(store).vocab.restore_line(None)
    store.close()
    assert _rows(path)["level"] == []
    assert not level_file(path).exists()
    again = SqliteLearningStore(path)  # a new start takes no level from a copy
    assert again.load().level is None
    again.close()
