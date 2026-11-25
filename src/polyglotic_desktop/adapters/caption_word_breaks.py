"""Language-pack word splitting for the pure caption model."""

from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from polyglotic_desktop.ports.word_breaks import WordBreaks
from polyglotic_desktop.ports.word_split import SplitWord, WordSplit


@dataclass(frozen=True, slots=True)
class CaptionWordSplit:
    """Adapt a dictionary's span-or-``SplitWord`` split for captions."""

    split: Callable[[str], Sequence[SplitWord | tuple[int, int]]]

    def words(self, text: str) -> tuple[SplitWord, ...]:
        return tuple(
            word if isinstance(word, SplitWord) else SplitWord(*word)
            for word in self.split(text)
        )


RECENT_CLAUSES = 128
"""Distinct (language, text) pairs to reuse across live revisions and surfaces.
Older splits can be recomputed from their caption text."""


@dataclass(slots=True)
class PackWordBreaks(WordBreaks):
    """Select the installed analyser for a caption's actual language.

    Recent results are cached by language and clause text for live revisions,
    while ``CaptionModel`` identity keeps settled clauses from asking again.
    """

    splitters: Mapping[str, WordSplit] | Callable[[str], WordSplit | None]
    _cache: OrderedDict[tuple[str, str], tuple[SplitWord, ...] | None] = field(
        default_factory=OrderedDict, init=False
    )

    def words(self, text: str, language: str | None) -> tuple[SplitWord, ...] | None:
        code = (language or "").lower()
        key = (code, text)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        splitter = (
            self.splitters(code)
            if callable(self.splitters)
            else self.splitters.get(code)
        )
        found = tuple(splitter.words(text)) if splitter is not None else None
        self._cache[key] = found
        if len(self._cache) > RECENT_CLAUSES:
            self._cache.popitem(last=False)
        return found
