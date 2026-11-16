"""Saved words, their categories, and finding saved words in a line.

From the proof of concept's `vocab.py`. A saved word is a dictionary entry
the learner saved into a category - each with a name and a colour - with
the line it was saved from (its source sentence) and that line's
translation; wherever it turns up again it's drawn in its category's
colour.

A saved Chinese word matches in either script (电脑 and 電腦), and inside
longer words too (游戏 in 打游戏) - but never across a word boundary: 个人
isn't matched in 这个人, which the word split reads 这个/人. A saved
English word matches whole words, inflected forms included ("ran" for a
saved "run"), by entry ID.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from polyglotic_desktop.core.shared import EntryId, WordInLine

CategoryId = str


@dataclass(frozen=True)
class Category:
    id: CategoryId
    name: str
    color: str  # "#rrggbb"


DEFAULT_CATEGORIES = (
    Category("saved", "Saved", "#6fc3ff"),
    Category("tricky", "Tricky", "#ff7a9a"),
)
"""The categories a new learner starts with. The proof of concept's third,
"Know it", is now the word status "known". Their colours keep clear of the
overlays' own: white (what was said) and yellow (a translation)."""

NEW_CATEGORY_COLORS = ("#c9a7ff", "#ffa25c", "#5fe0d0", "#ff9de2", "#8be38f")


@dataclass(frozen=True)
class SavedWord:
    entry_id: EntryId
    headword: str  # simplified Chinese, or the English word
    traditional: str  # "" for English
    reading: str  # pinyin with tone marks, or IPA
    meaning: str  # short, as saved
    category_id: CategoryId
    source_sentence: str  # the line it was saved from; stays on this PC
    source_translation: str  # that line's translation, if any
    saved_at: datetime

    @property
    def is_chinese(self) -> bool:
        """A CC-CEDICT entry: it has a traditional form (ECDICT's don't)."""
        return bool(self.traditional)

    @property
    def forms(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(f for f in (self.headword, self.traditional) if f))


@dataclass(frozen=True, slots=True)
class SavedSpan:
    """A saved word found in a line: `line[start:end]`, of `entry_id`."""

    start: int
    end: int
    entry_id: EntryId


class SavedWordMatcher:
    """Finds saved words in a line. Built from the saved words; build a new
    one when they change."""

    def __init__(self, words: Iterable[SavedWord]) -> None:
        self._ids: set[EntryId] = set()
        self._forms: dict[str, EntryId] = {}
        for word in words:
            self._ids.add(word.entry_id)
            if word.is_chinese:
                for form in word.forms:
                    self._forms.setdefault(form, word.entry_id)
        self._longest = max((len(f) for f in self._forms), default=0)

    def spans(self, line: str, words: Sequence[WordInLine]) -> list[SavedSpan]:
        """The saved words in `line`, left to right, never overlapping: at
        each point the longest saved Chinese form that doesn't cut across
        any of `words` (the line's word split), and any word whose entry is
        saved ("ran" for "run")."""
        found = self._chinese_spans(line, words) if self._forms else []
        taken = [(s.start, s.end) for s in found]
        for word in words:
            if word.entry.entry_id in self._ids and not any(
                a < word.end and word.start < b for a, b in taken
            ):
                found.append(SavedSpan(word.start, word.end, word.entry.entry_id))
        return sorted(found, key=lambda s: s.start)

    def _chinese_spans(self, line: str, words: Sequence[WordInLine]) -> list[SavedSpan]:
        bounds = [(w.start, w.end) for w in words]
        found = []
        i, n = 0, len(line)
        while i < n:
            for length in range(min(self._longest, n - i), 0, -1):
                end = i + length
                entry_id = self._forms.get(line[i:end])
                if entry_id is not None and _within_words(bounds, i, end):
                    found.append(SavedSpan(i, end, entry_id))
                    i = end
                    break
            else:
                i += 1
        return found


def _within_words(words: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    """Whether [start, end) doesn't cut across a word: every word it
    touches is either wholly inside it or wholly contains it."""
    for a, b in words:
        if b <= start or a >= end:
            continue
        if not (start <= a and b <= end) and not (a <= start and end <= b):
            return False
    return True
