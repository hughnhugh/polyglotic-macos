"""Fakes for testing Learning without storage or a dictionary: a
`LearningStore` in memory, made-up entries, and words in a line."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta

from polyglotic_desktop.core.shared import EntryFacts, EntryId, WordInLine
from polyglotic_desktop.ports.learning import (
    LearningSnapshot,
    StoredAnkiExport,
    StoredCategory,
    StoredCoverage,
    StoredCurriculumWord,
    StoredDeckWord,
    StoredExposures,
    StoredLevel,
    StoredLineChange,
    StoredListening,
    StoredLoadWord,
    StoredLookups,
    StoredSavedWord,
    StoredSentence,
    StoredSetWord,
    StoredStatus,
    StoredStatusChange,
)


class MemoryLearningStore:
    """Everything a learning store keeps, in dicts."""

    def __init__(self) -> None:
        self.level: StoredLevel | None = None
        self.statuses: dict[str, StoredStatus] = {}
        self.categories: dict[str, StoredCategory] = {}
        self.words: dict[str, StoredSavedWord] = {}
        self.exposures: dict[str, StoredExposures] = {}
        self.daily: dict[date, dict[str, int]] = {}
        self.deck_words: dict[str, StoredDeckWord] = {}
        # by entry and kind of file: each kind its own (368)
        self.anki_exports: dict[tuple[str, str], StoredAnkiExport] = {}
        self.coverage: dict[date, StoredCoverage] = {}
        self.listening: dict[tuple[date, str], float] = {}
        self.handed_over: set[date] = set()
        self.load_words: dict[str, StoredLoadWord] = {}
        self.lookups: dict[str, StoredLookups] = {}
        self.sentences: dict[str, StoredSentence] = {}
        self.curriculum: dict[str, StoredCurriculumWord] = {}
        self.status_history: list[StoredStatusChange] = []
        self.line_history: list[StoredLineChange] = []
        self.set_words: dict[tuple[str, str], StoredSetWord] = {}

    def load(self) -> LearningSnapshot:
        return LearningSnapshot(
            self.level,
            list(self.statuses.values()),
            list(self.categories.values()),
            list(self.words.values()),
            list(self.exposures.values()),
            list(self.deck_words.values()),
            list(self.anki_exports.values()),
            [self.coverage[day] for day in sorted(self.coverage)],
            [StoredListening(d, c, s) for (d, c), s in sorted(self.listening.items())],
            list(self.load_words.values()),
            list(self.lookups.values()),
            list(self.curriculum.values()),
            list(self.set_words.values()),
        )

    def save_level(self, level: StoredLevel) -> None:
        self.level = level

    def clear_level(self) -> None:
        self.level = None

    def save_status(self, status: StoredStatus) -> None:
        self.statuses[status.entry_id] = status

    def save_category(self, category: StoredCategory) -> None:
        self.categories[category.id] = category

    def delete_category(self, category_id: str) -> None:
        self.categories.pop(category_id, None)
        self.words = {
            k: w for k, w in self.words.items() if w.category_id != category_id
        }
        self.sentences = {
            k: s for k, s in self.sentences.items() if s.category_id != category_id
        }

    def save_word(self, word: StoredSavedWord) -> None:
        self.words[word.entry_id] = word

    def delete_word(self, entry_id: str) -> None:
        self.words.pop(entry_id, None)

    def saved_sentences(self) -> list[StoredSentence]:
        return list(self.sentences.values())

    def save_sentence(self, sentence: StoredSentence) -> None:
        self.sentences[sentence.id] = sentence

    def delete_sentence(self, sentence_id: str) -> None:
        self.sentences.pop(sentence_id, None)

    def save_deck_word(self, word: StoredDeckWord) -> None:
        self.deck_words[word.entry_id] = word

    def delete_deck_word(self, entry_id: str) -> None:
        self.deck_words.pop(entry_id, None)

    def save_anki_exports(self, exports: Iterable[StoredAnkiExport]) -> None:
        for export in exports:
            self.anki_exports[export.entry_id, export.kind] = export

    def save_load_words(self, words: Sequence[StoredLoadWord]) -> None:
        for word in words:
            self.load_words[word.entry_id] = word

    def delete_load_words(self, entry_ids: Sequence[str]) -> None:
        for entry_id in entry_ids:
            self.load_words.pop(entry_id, None)

    def save_lookups(self, lookups: StoredLookups) -> None:
        self.lookups[lookups.entry_id] = lookups

    def save_curriculum_words(self, words: Sequence[StoredCurriculumWord]) -> None:
        for word in words:
            self.curriculum[word.entry_id] = word

    def delete_curriculum_words(self, entry_ids: Sequence[str]) -> None:
        for entry_id in entry_ids:
            self.curriculum.pop(entry_id, None)

    def add_status_changes(self, changes: Sequence[StoredStatusChange]) -> None:
        self.status_history.extend(changes)

    def add_line_change(self, change: StoredLineChange) -> None:
        self.line_history.append(change)

    def status_changes(self) -> Sequence[StoredStatusChange]:
        return list(self.status_history)

    def line_changes(self) -> Sequence[StoredLineChange]:
        return list(self.line_history)

    def save_set_words(self, words: Sequence[StoredSetWord]) -> None:
        for word in words:
            self.set_words[(word.name, word.entry_id)] = word

    def delete_set_words(self, name: str, entry_ids: Sequence[str]) -> None:
        for entry_id in entry_ids:
            self.set_words.pop((name, entry_id), None)

    def forget_entry(self, entry_id: str) -> None:
        self.curriculum.pop(entry_id, None)
        for key in [k for k in self.set_words if k[1] == entry_id]:
            del self.set_words[key]
        self.lookups.pop(entry_id, None)
        self.load_words.pop(entry_id, None)
        self.deck_words.pop(entry_id, None)
        for key in [k for k in self.anki_exports if k[0] == entry_id]:
            del self.anki_exports[key]
        self.statuses.pop(entry_id, None)
        self.words.pop(entry_id, None)
        self.exposures.pop(entry_id, None)

    def save_exposures(
        self, counts: Sequence[StoredExposures], daily: Mapping[date, Mapping[str, int]]
    ) -> None:
        for count in counts:
            self.exposures[count.entry_id] = count
        for day, changes in daily.items():
            kept = self.daily.setdefault(day, {})
            for entry_id, delta in changes.items():
                kept[entry_id] = kept.get(entry_id, 0) + delta

    def daily_exposures(self, day: date) -> Mapping[str, int]:
        return {e: n for e, n in self.daily.get(day, {}).items() if n}

    def exposure_days(self) -> Sequence[date]:
        return sorted(self.daily)

    def days_to_hand_over(self) -> Sequence[date]:
        return sorted(d for d in self.daily if d not in self.handed_over)

    def mark_handed_over(self, days: Iterable[date]) -> None:
        self.handed_over.update(days)

    def forget_daily_exposures(self, days: Iterable[date]) -> None:
        for day in days:
            self.daily.pop(day, None)
            self.handed_over.discard(day)

    def add_coverage(self, changes: Iterable[StoredCoverage]) -> None:
        for c in changes:
            was = self.coverage.get(c.day, StoredCoverage(c.day, 0, 0, 0))
            self.coverage[c.day] = StoredCoverage(
                c.day, was.known + c.known, was.deck + c.deck, was.new + c.new
            )

    def add_listening(self, listened: Iterable[StoredListening]) -> None:
        for e in listened:
            key = (e.day, e.category)
            self.listening[key] = self.listening.get(key, 0.0) + e.seconds

    def delete_learning_data(self) -> None:
        self.statuses.clear()
        self.words.clear()
        self.sentences.clear()
        self.deck_words.clear()
        self.anki_exports.clear()
        self.exposures.clear()
        self.daily.clear()
        self.coverage.clear()
        self.listening.clear()
        self.handed_over.clear()
        self.load_words.clear()
        self.lookups.clear()
        self.curriculum.clear()
        self.status_history.clear()
        self.line_history.clear()
        self.set_words.clear()


def facts(
    name: str,
    level: int | None = 1,
    rank: int | None = 100,
    is_name: bool = False,
    level_words: int | None = None,
) -> EntryFacts:
    return EntryFacts(EntryId(f"test:{name}"), level, rank, is_name, level_words)


def words_of(line: str, known: Mapping[str, EntryFacts]) -> list[WordInLine]:
    """Words in `line` separated by spaces, each found in `known` by its
    text (a stand-in for Lexicon's word split)."""
    found = []
    start = 0
    for token in line.split(" "):
        if token in known:
            found.append(WordInLine(start, start + len(token), known[token]))
        start += len(token) + 1
    return found


class Clock:
    """A clock the test moves on by hand."""

    def __init__(
        self, start: datetime = datetime(2026, 11, 4, 9, 0, tzinfo=UTC)
    ) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)
