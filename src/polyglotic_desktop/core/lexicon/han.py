"""Words in Chinese characters, by a dictionary pack's own words: the word
split `han` (polyglotic-hq 371 and 450; decision 0160).

Cantonese is written in Chinese characters without spaces, as Mandarin is,
so a caption's words are found by the pack's written forms, as Chinese's
own split finds them by CC-CEDICT's (`chinese.ChineseDictionary.split`):
each run of Chinese characters is cut into the pack's words - as few as
possible, so 而家 (now) and 佢哋 (they) stay whole; among equally few,
the most evenly sized; then the commoner words (by the pack's frequency
ranks); then the longer word first. A character the pack hasn't got is a
word of its own. **A phrase of two common words isn't a word** (as
Chinese's, decision 0151): a form without a rank that is two words each
among the `COMMON_PARTS` commonest is left to its words - 你嘅 ("your")
is 你 + 嘅, 非常重要 is 非常 + 重要. A run in another script (an English word in a Cantonese
line) is one word, as the row's.

371 measured it on HKCanCor's own word split (119,696 words of
conversation): with the Cantonese pack's words it keeps 86.6 % of the
words of two characters or more whole (CC-CEDICT's words alone: 53.0 %).

No library: plain Python over the pack's written forms, read once at the
first split (`DictionaryFile.headwords`), as Vietnamese's and Thai's are -
on the thread that warms the basic dictionaries (`ui.learning`).
"""

from __future__ import annotations

import math
import threading
from collections.abc import Container, Mapping, Sequence

from polyglotic_desktop.core.lexicon.chinese import COMMON_PARTS, is_han
from polyglotic_desktop.core.lexicon.english import words as letter_runs
from polyglotic_desktop.ports.dictionary import DictionaryFile
from polyglotic_desktop.ports.word_split import SplitWord

MAX_WORD = 12
"""The longest word the split looks for, in characters: CC-Canto's and
CC-CEDICT's longer entries are proverbs and titles, which a caption rarely
says whole."""


def commonness(rank: int | None) -> float:
    """Higher for commoner words: about log2 of a count, from the rank (as
    Chinese's split weighs them)."""
    return 0.0 if rank is None else max(0.0, 21 - math.log2(rank))


def is_phrase(form: str, common: Mapping[str, float]) -> bool:
    """Whether `form` is a phrase the split leaves to its words: it has no
    rank, and is two words each among the `COMMON_PARTS` commonest
    (`common`: a form -> its commonness)."""
    if common.get(form, 0.0):
        return False
    least = commonness(COMMON_PARTS)
    return any(
        common.get(form[:k], 0.0) >= least and common.get(form[k:], 0.0) >= least
        for k in range(1, len(form))
    )


def runs(text: str) -> list[tuple[int, int, bool]]:
    """(start, end, Chinese?) of each run of `text`: each run of Chinese
    characters, and between them each word of letters (`english.words`: an
    English word in a Cantonese line, "用iPhone睇"). Digits, spaces and
    punctuation are no word."""
    out: list[tuple[int, int, bool]] = []
    i, n = 0, len(text)
    while i < n:
        j = i
        han = is_han(text[i])
        while j < n and is_han(text[j]) == han:
            j += 1
        if han:
            out.append((i, j, True))
        else:
            out += [(i + a, i + b, False) for a, b in letter_runs(text[i:j])]
        i = j
    return out


def cut(
    run: str, words: Container[str], common: Mapping[str, float]
) -> list[tuple[int, int]]:
    """(start, end) of each word of `run` (Chinese characters only), cut
    into `words`: fewest, then most evenly sized (the least sum of squared
    lengths: 研究/生命, not 研究生/命), then commonest (`common`: a form ->
    its commonness), then the longer first. A single character is a word
    whether the pack has it or not."""
    n = len(run)
    # best[i]: (words, sum of squared lengths, -commonness, previous cut)
    best: list[tuple[int, int, float, int] | None] = [(0, 0, 0.0, -1)] + [None] * n
    for end in range(1, n + 1):
        for start in range(max(0, end - MAX_WORD), end):
            before = best[start]
            word = run[start:end]
            if before is None or (end - start > 1 and word not in words):
                continue
            candidate = (
                before[0] + 1,
                before[1] + (end - start) ** 2,
                before[2] - common.get(word, 0.0),
                start,
            )
            current = best[end]
            # <=: on a tie the later start wins - the longer earlier word
            if current is None or candidate[:3] <= current[:3]:
                best[end] = candidate
    cuts = []
    end = n
    while end > 0:
        step = best[end]
        assert step is not None  # every single character is a step
        cuts.append((step[3], end))
        end = step[3]
    return cuts[::-1]


def split(
    text: str, words: Container[str], common: Mapping[str, float]
) -> list[SplitWord]:
    """The words of `text`: each run of Chinese characters cut by `cut`, a
    run in another script whole."""
    out = []
    for start, end, han in runs(text):
        if not han:
            out.append(SplitWord(start, end))
            continue
        out += [
            SplitWord(start + a, start + b)
            for a, b in cut(text[start:end], words, common)
        ]
    return out


class HanSplit:
    """The `WordSplit` port for a language written in Chinese characters
    (Cantonese), over a dictionary pack's written forms and ranks."""

    def __init__(self, file: DictionaryFile) -> None:
        self._file = file
        self._data: tuple[frozenset[str], dict[str, float]] | None = None
        self._lock = threading.Lock()

    def _read(self) -> tuple[frozenset[str], dict[str, float]]:
        """The written forms of two characters or more that are words to
        the split (not a phrase: `is_phrase`), and every form's
        commonness - read now if not yet."""
        with self._lock:
            if self._data is None:
                common = {
                    form: commonness(rank)
                    for form, rank in self._file.frequency_ranks().items()
                }
                words = frozenset(
                    w
                    for w in self._file.headwords()
                    if len(w) > 1 and not is_phrase(w, common)
                )
                self._data = (words, common)
            return self._data

    def words(self, text: str) -> Sequence[SplitWord]:
        return split(text, *self._read())
