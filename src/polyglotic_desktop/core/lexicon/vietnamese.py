"""Vietnamese words: the word split for Vietnamese captions (polyglotic-hq
325; decision 0121).

Vietnamese writes every syllable apart - "học sinh" (pupil) is two
syllables and one word - so a caption's words are found by the
dictionary: each run of syllables with only spaces between them is cut
into the dictionary's words, as few as possible; among equally few, the
commoner words (by their frequency ranks); then the longer word first.
It is Chinese's longest match (`chinese`), over syllables instead of
characters. 325 measured it on 60 hand-checked caption lines (speech
captions, Tatoeba's sentences, subtitles): 97.9 % of words right, where
pyvi got 96.1 % and underthesea 94.6 %, at about 0.04 ms a line.

The pack's written forms are read once, at the first split
(`DictionaryFile.headwords`): about 34,000, in about 90 ms - on the
thread that warms the basic dictionaries (`ui.learning`).
"""

from __future__ import annotations

import math
import threading
import unicodedata
from collections.abc import Container, Mapping, Sequence

from polyglotic_desktop.core.lexicon.english import words as letter_runs
from polyglotic_desktop.ports.dictionary import DictionaryFile
from polyglotic_desktop.ports.word_split import SplitWord

MAX_SYLLABLES = 6
"""The longest word the split looks for. Wiktionary's longer Vietnamese
entries are proverbs, which a caption rarely says whole."""


def key(text: str) -> str:
    """How a word is matched: lower case, composed (NFC), one space
    between syllables."""
    return unicodedata.normalize("NFC", " ".join(text.lower().split()))


def commonness(rank: int | None) -> float:
    """Higher for commoner words: about log2 of a count, from the rank (as
    Chinese's split weighs them)."""
    return 0.0 if rank is None else max(0.0, 21 - math.log2(rank))


_LINE_BREAKS = frozenset("\n\r\u2028\u2029")


def runs(text: str) -> list[list[tuple[int, int]]]:
    """The syllables of `text`, as (start, end), in runs: syllables with
    only spaces between them. Punctuation, digits or a line break ends a
    run - a word never crosses a comma."""
    out: list[list[tuple[int, int]]] = []
    last = -1
    for start, end in letter_runs(text):
        gap = text[last:start]
        if last < 0 or not gap.isspace() or _LINE_BREAKS & set(gap):
            out.append([])
        out[-1].append((start, end))
        last = end
    return out


def cut(
    text: str, words: Container[str], common: Mapping[str, float]
) -> list[tuple[int, int]]:
    """(start, end) of each word of `text`: each run of syllables cut into
    words of `words` (keys, `key`) - fewest, then commonest (`common`: key
    -> commonness), then the longer first. A syllable is a word whether
    the dictionary has it or not."""
    spans: list[tuple[int, int]] = []
    for run in runs(text):
        syllables = [key(text[a:b]) for a, b in run]
        n = len(syllables)
        # best[i]: (words, -summed commonness, previous cut) for run[:i]
        best: list[tuple[int, float, int] | None] = [(0, 0.0, -1)] + [None] * n
        for end in range(1, n + 1):
            for start in range(max(0, end - MAX_SYLLABLES), end):
                before = best[start]
                word = " ".join(syllables[start:end])
                if before is None or (end - start > 1 and word not in words):
                    continue
                candidate = (before[0] + 1, before[1] - common.get(word, 0.0), start)
                current = best[end]
                # <=: on a tie the later start wins - the longer earlier word
                if current is None or candidate[:2] <= current[:2]:
                    best[end] = candidate
        cuts = []
        end = n
        while end > 0:
            step = best[end]
            assert step is not None  # every single syllable is a step
            cuts.append((run[step[2]][0], run[end - 1][1]))
            end = step[2]
        spans += reversed(cuts)
    return spans


class VietnameseSplit:
    """The `WordSplit` port for Vietnamese, over a dictionary pack's
    headwords and ranks."""

    def __init__(self, file: DictionaryFile) -> None:
        self._file = file
        self._words: frozenset[str] | None = None
        self._common: dict[str, float] = {}
        self._lock = threading.Lock()

    def _data(self) -> tuple[frozenset[str], dict[str, float]]:
        """The headwords (keys) and their commonness, read now if not yet."""
        with self._lock:
            if self._words is None:
                for form, rank in self._file.frequency_ranks().items():
                    k = key(form)
                    self._common[k] = max(self._common.get(k, 0.0), commonness(rank))
                self._words = frozenset(key(w) for w in self._file.headwords())
            return self._words, self._common

    def words(self, text: str) -> Sequence[SplitWord]:
        words, common = self._data()
        return [SplitWord(start, end) for start, end in cut(text, words, common)]
